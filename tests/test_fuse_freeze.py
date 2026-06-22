"""
test_fuse_freeze.py

Regression test for the FUSE freeze bug:
  - Previously, flush() was synchronously running the entire Roblox upload on the FUSE thread.
  - With nothreads=True, this blocked ALL filesystem operations (getattr, readdir, stat)
    for every program that had the mountpoint open, causing Nautilus/GNOME Files to freeze.

Fix verified here:
  1. flush() executes the upload synchronously to block the writing application until complete.
  2. Because nothreads=False, concurrent access works and getattr() does not freeze.
  3. flush() raises FuseOSError(errno.EIO) if the upload fails.
"""

import threading
import time
import os
import stat
import tempfile
import errno
import pytest
from unittest.mock import MagicMock, patch
from fuse import FuseOSError


# ---------------------------------------------------------------------------
# Minimal stub so BloxDriveFUSE can be instantiated without real DB / Roblox
# ---------------------------------------------------------------------------

def _make_fuse(tmp_dir):
    """Return a BloxDriveFUSE instance with all external deps mocked out."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

    db_mock = MagicMock()
    db_mock.get_file.return_value = {
        'id': 1, 'filename': 'test.bin', 'size': 0,
        'mode': stat.S_IFREG | 0o644, 'uid': 1000, 'gid': 1000,
        'created_at': MagicMock(timestamp=lambda: time.time()),
        'atime': time.time(), 'mtime': time.time(), 'ctime': time.time(),
    }
    db_mock.is_folder.return_value = False

    pool_mock = MagicMock()

    # RobloxPool is imported locally inside __init__ via 'from roblox_pool import RobloxPool'
    # so we must patch it at the source module, not at fuse_app.
    with patch('roblox_pool.RobloxPool', return_value=pool_mock), \
         patch('fuse_app.DatabaseManager', return_value=db_mock):
        from fuse_app import BloxDriveFUSE
        fuse = BloxDriveFUSE(db_mock)
        fuse.pool = pool_mock
        fuse.spool_dir = tmp_dir
        return fuse



# ---------------------------------------------------------------------------
# Test 1: flush() triggers upload and saves dirty status
# ---------------------------------------------------------------------------

def test_flush_uploads_and_clears_dirty(tmp_path):
    """flush() must call upload_file and mark the spool info as clean."""
    fuse = _make_fuse(str(tmp_path))

    spool = tmp_path / "spool_flush.bin"
    spool.write_bytes(b"hello world")

    fuse.open_files[1] = {
        'path': str(spool),
        'dirty': True,
        'filename': 'test.bin',
    }

    upload_called = []

    async def mock_upload(path, filename_override=None):
        upload_called.append(True)

    with patch('uploader.upload_file', new=mock_upload):
        result = fuse.flush('/test.bin', 1)

    assert result == 0, "flush() must return 0"
    assert upload_called == [True], "flush() must call upload_file"
    assert fuse.open_files[1]['dirty'] is False, "dirty flag must be cleared"


# ---------------------------------------------------------------------------
# Test 2: flush() raises FuseOSError on upload failure
# ---------------------------------------------------------------------------

def test_flush_propagates_upload_failure(tmp_path):
    """flush() must raise a FuseOSError(errno.EIO) if upload fails."""
    fuse = _make_fuse(str(tmp_path))

    spool = tmp_path / "spool_release.bin"
    spool.write_bytes(b"data to upload")

    fuse.open_files[2] = {
        'path': str(spool),
        'dirty': True,
        'filename': 'test.bin',
    }

    async def fail_upload(path, filename_override=None):
        raise RuntimeError("Roblox upload failed!")

    with patch('uploader.upload_file', new=fail_upload):
        with pytest.raises(FuseOSError) as exc_info:
            fuse.flush('/test.bin', 2)

        assert exc_info.value.errno == errno.EIO
        assert fuse.open_files[2]['dirty'] is True, "dirty flag remains true on failure"
