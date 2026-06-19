import sys
import os
import errno
import stat
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import DatabaseManager
from fuse_app import BloxDriveFUSE

def test_metadata():
    print("--- Testing FUSE POSIX Metadata Persistence ---")
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)
    
    # Clean state
    try: fuse.unlink("/meta_test.txt")
    except: pass
    try: fuse.rmdir("/meta_dir")
    except: pass

    # 1. Create file and folder
    print("Creating file and folder...")
    fh = fuse.create("/meta_test.txt", 0o644)
    fuse.release("/meta_test.txt", fh)
    fuse.mkdir("/meta_dir", 0o755)

    # 2. Test chmod
    print("Testing chmod...")
    new_mode = stat.S_IFREG | 0o777
    fuse.chmod("/meta_test.txt", new_mode)
    attr = fuse.getattr("/meta_test.txt")
    assert attr['st_mode'] == new_mode, f"chmod failed: expected {oct(new_mode)}, got {oct(attr['st_mode'])}"
    
    dir_mode = stat.S_IFDIR | 0o700
    fuse.chmod("/meta_dir", dir_mode)
    attr_dir = fuse.getattr("/meta_dir")
    assert attr_dir['st_mode'] == dir_mode, "chmod on dir failed"
    print("chmod: PASS")

    # 3. Test chown
    print("Testing chown...")
    new_uid, new_gid = 500, 500
    fuse.chown("/meta_test.txt", new_uid, new_gid)
    attr = fuse.getattr("/meta_test.txt")
    assert attr['st_uid'] == new_uid, "uid mismatch"
    assert attr['st_gid'] == new_gid, "gid mismatch"
    
    fuse.chown("/meta_dir", 600, 600)
    attr_dir = fuse.getattr("/meta_dir")
    assert attr_dir['st_uid'] == 600, "dir uid mismatch"
    print("chown: PASS")

    # 4. Test utimens
    print("Testing utimens (mtime, atime)...")
    target_time = 1600000000.0
    fuse.utimens("/meta_test.txt", (target_time, target_time))
    attr = fuse.getattr("/meta_test.txt")
    assert attr['st_atime'] == target_time, "atime mismatch"
    assert attr['st_mtime'] == target_time, "mtime mismatch"
    
    fuse.utimens("/meta_dir", (target_time, target_time))
    attr_dir = fuse.getattr("/meta_dir")
    assert attr_dir['st_atime'] == target_time, "dir atime mismatch"
    print("utimens: PASS")

    # Cleanup
    fuse.unlink("/meta_test.txt")
    fuse.rmdir("/meta_dir")
    
    print("All POSIX metadata tests passed!")

if __name__ == "__main__":
    test_metadata()
