import os
import sys
import errno
import stat
import math
import asyncio
from fuse import FUSE, FuseOSError, Operations
from db import DatabaseManager
from roblox import RobloxClient
from encoder import ImageCoder
import config
import time
import requests # For synchronous range requests during read
import threading

class BloxDriveFUSE(Operations):
    def __init__(self, db_manager):
        self.db = db_manager
        from roblox_pool import RobloxPool
        self.pool = RobloxPool()
        self.chunk_size = config.CHUNK_SIZE_BYTES
        
        # Initialize loop for any async tasks if needed, though FUSE calls are sync
        self.loop = asyncio.new_event_loop()
        
        # Basic in-memory cache for the most recently requested chunk
        self.cache_chunk_id = None
        self.cache_data = None
        self.cache_time = 0
        
        self.spool_dir = "/tmp/bloxdrive_spool"
        os.makedirs(self.spool_dir, exist_ok=True)
        self.open_files = {} # fh -> {'path': spool_path, 'dirty': bool, 'filename': str}
        self.next_fh = 1
        self.fh_lock = threading.Lock()
        self.cache_lock = threading.Lock()
        self.loop_lock = threading.Lock()  # Protect shared asyncio loop from concurrent threads

    # --- Filesystem Methods ---

    def getattr(self, path, fh=None):
        if path == '/':
            return {
                'st_mode': (stat.S_IFDIR | 0o755),
                'st_nlink': 2,
                'st_size': 0,
                'st_ctime': time.time(),
                'st_mtime': time.time(),
                'st_atime': time.time()
            }

        filename = path.lstrip('/')
        
        if self.db.is_folder(filename):
            # Try to get the .keep file to use its metadata
            keep_record = self.db.get_file(filename + "/.keep")
            if keep_record:
                return {
                    'st_mode': keep_record.get('mode', (stat.S_IFDIR | 0o755)),
                    'st_nlink': 2,
                    'st_size': 0,
                    'st_uid': keep_record.get('uid', 1000),
                    'st_gid': keep_record.get('gid', 1000),
                    'st_atime': keep_record.get('atime', time.time()),
                    'st_mtime': keep_record.get('mtime', time.time()),
                    'st_ctime': keep_record.get('ctime', time.time())
                }
            else:
                return {
                    'st_mode': (stat.S_IFDIR | 0o755),
                    'st_nlink': 2,
                    'st_size': 0,
                    'st_uid': 1000,
                    'st_gid': 1000,
                    'st_ctime': time.time(),
                    'st_mtime': time.time(),
                    'st_atime': time.time()
                }

        file_record = self.db.get_file(filename)
        if not file_record:
            raise FuseOSError(errno.ENOENT)

        return {
            'st_mode': file_record.get('mode', (stat.S_IFREG | 0o644)),
            'st_nlink': 1,
            'st_size': file_record['size'],
            'st_uid': file_record.get('uid', 1000),
            'st_gid': file_record.get('gid', 1000),
            'st_atime': file_record.get('atime', file_record['created_at'].timestamp()),
            'st_mtime': file_record.get('mtime', file_record['created_at'].timestamp()),
            'st_ctime': file_record.get('ctime', file_record['created_at'].timestamp())
        }

    def readdir(self, path, fh):
        dirents = ['.', '..']
        files = self.db.list_files()
        prefix = "" if path == '/' else path.lstrip('/') + '/'
        
        for f in files:
            filename = f['filename']
            if filename.startswith(prefix):
                remainder = filename[len(prefix):]
                parts = remainder.split('/')
                if len(parts) == 1:
                    if remainder != '.keep' and remainder != '':
                        dirents.append(remainder)
                else:
                    dirname = parts[0]
                    if dirname not in dirents:
                        dirents.append(dirname)
        return dirents

    def mkdir(self, path, mode):
        filename = path.lstrip('/')
        self.db.add_file(filename + "/.keep", 0)
        self.db.update_mode(filename + "/.keep", stat.S_IFDIR | mode)

    def rmdir(self, path):
        filename = path.lstrip('/')
        prefix = filename + "/"
        files = self.db.list_files()
        # Ensure it's empty
        for f in files:
            if f['filename'].startswith(prefix) and f['filename'] != prefix + ".keep":
                raise FuseOSError(errno.ENOTEMPTY)
        
        self.db.delete_file(prefix + ".keep")

    def rename(self, old, new):
        old_filename = old.lstrip('/')
        new_filename = new.lstrip('/')
        
        if self.db.is_folder(old_filename):
            self.db.rename_folder(old_filename, new_filename)
        else:
            self.db.rename_file(old_filename, new_filename)

    def open(self, path, flags):
        filename = path.lstrip('/')
        file_record = self.db.get_file(filename)
        if not file_record:
            raise FuseOSError(errno.ENOENT)
        
        import uuid
        with self.fh_lock:
            fh = self.next_fh
            self.next_fh += 1
        
        # If writable, spool the entire file from BloxDrive to local!
        if (flags & 3) != os.O_RDONLY:
            spool_path = os.path.join(self.spool_dir, str(uuid.uuid4()))
            if flags & os.O_TRUNC:
                open(spool_path, 'wb').close()
                self.db.update_file_size(file_record['id'], 0)
                self.db.delete_chunks(file_record['id'])
            else:
                with open(spool_path, 'wb') as f:
                    chunks = self.db.get_chunks(file_record['id'])
                    for chunk in chunks:
                        data = self._fetch_chunk_data(chunk)
                        if data is None:
                            raise FuseOSError(errno.EIO)
                        f.seek(chunk['sequence'] * self.chunk_size)
                        f.write(data)
            self.open_files[fh] = {'path': spool_path, 'dirty': False, 'filename': filename}
        else:
            self.open_files[fh] = {'path': None, 'dirty': False, 'filename': filename}
            
        return fh

    def read(self, path, length, offset, fh):
        info = self.open_files.get(fh)
        if info and info['path']:
            # Read directly from local spool if open for write
            with open(info['path'], 'rb') as f:
                f.seek(offset)
                return f.read(length)
                
        filename = path.lstrip('/')
        file_record = self.db.get_file(filename)
        if not file_record:
            raise FuseOSError(errno.ENOENT)

        # Determine which chunks are needed
        start_chunk_seq = offset // self.chunk_size
        end_chunk_seq = (offset + length - 1) // self.chunk_size
        
        chunks = self.db.get_chunks(file_record['id'])
        
        result_data = bytearray()
        
        for seq in range(start_chunk_seq, end_chunk_seq + 1):
            # Find the specific chunk
            chunk = next((c for c in chunks if c['sequence'] == seq), None)
            if not chunk:
                break # Reached end of available chunks
                
            chunk_data = self._fetch_chunk_data(chunk)
            if not chunk_data:
                raise FuseOSError(errno.EIO)

            # Calculate slice
            chunk_offset = seq * self.chunk_size
            start_in_chunk = max(0, offset - chunk_offset)
            end_in_chunk = min(self.chunk_size, offset + length - chunk_offset)
            
            result_data.extend(chunk_data[start_in_chunk:end_in_chunk])

        return bytes(result_data)

    def _fetch_chunk_data(self, chunk):
        """Fetches and caches a chunk. First tries CDN URL, then falls back."""
        with self.cache_lock:
            if self.cache_chunk_id == chunk['id'] and (time.time() - self.cache_time < 300):
                return self.cache_data

        try:
            with self.loop_lock:
                raw_bytes = self.loop.run_until_complete(self.pool.fetch_chunk_data(chunk, self.db))
            if raw_bytes is not None:
                with self.cache_lock:
                    self.cache_chunk_id = chunk['id']
                    self.cache_data = raw_bytes
                    self.cache_time = time.time()
                return raw_bytes
        except Exception as e:
            print(f"Fetch error: {e}")
            
        return None

    def write(self, path, buf, offset, fh):
        info = self.open_files.get(fh)
        if not info or not info['path']:
            raise FuseOSError(errno.EIO)
            
        with open(info['path'], 'r+b') as f:
            f.seek(offset)
            f.write(buf)
            
        info['dirty'] = True
        
        # Update db file size locally immediately to reflect in getattr
        filename = info['filename']
        file_record = self.db.get_file(filename)
        new_size = max(file_record['size'], offset + len(buf))
        self.db.update_file_size(file_record['id'], new_size)
        
        return len(buf)

    def truncate(self, path, length, fh=None):
        filename = path.lstrip('/')
        file_record = self.db.get_file(filename)
        if not file_record:
            raise FuseOSError(errno.ENOENT)
            
        if fh and fh in self.open_files and self.open_files[fh]['path']:
            with open(self.open_files[fh]['path'], 'r+b') as f:
                f.truncate(length)
            self.open_files[fh]['dirty'] = True
        else:
            # Ghost chunk purge
            start_seq = math.ceil(length / self.chunk_size)
            self.db.delete_chunks_after(file_record['id'], start_seq)
            
        self.db.update_file_size(file_record['id'], length)

    def create(self, path, mode, fi=None):
        filename = path.lstrip('/')
        import uuid
        
        if not self.db.get_file(filename):
            self.db.add_file(filename, 0)
        else:
            self.db.delete_file(filename)
            self.db.add_file(filename, 0)
            
        self.db.update_mode(filename, stat.S_IFREG | mode)
        
        with self.fh_lock:
            fh = self.next_fh
            self.next_fh += 1
        
        spool_path = os.path.join(self.spool_dir, str(uuid.uuid4()))
        open(spool_path, 'wb').close()
        
        self.open_files[fh] = {'path': spool_path, 'dirty': True, 'filename': filename}
        return fh

    def flush(self, path, fh):
        # Do NOT upload here — flush() is called by the kernel on every close/fsync
        # and would block the entire FUSE thread (freezing all filesystem operations).
        # The actual upload is handled in release(), which runs in a background thread.
        return 0

    def release(self, path, fh):
        info = self.open_files.pop(fh, None)
        if not info:
            return 0

        spool_path = info.get('path')
        dirty = info.get('dirty', False)
        filename = info.get('filename')

        if spool_path and dirty:
            # Upload in a background daemon thread so release() returns immediately.
            # This keeps FUSE responsive — getattr/readdir from other apps won't freeze
            # while a potentially multi-minute Roblox upload is in progress.
            def _background_upload(sp, fn):
                loop = asyncio.new_event_loop()
                try:
                    from uploader import upload_file
                    loop.run_until_complete(upload_file(sp, filename_override=fn))
                except Exception as e:
                    print(f"Background upload failed for '{fn}': {e}")
                finally:
                    loop.close()
                    try:
                        if os.path.exists(sp):
                            os.remove(sp)
                    except Exception:
                        pass

            t = threading.Thread(target=_background_upload, args=(spool_path, filename), daemon=True)
            t.start()
        elif spool_path:
            # File was opened but not modified — just clean up the spool file.
            try:
                if os.path.exists(spool_path):
                    os.remove(spool_path)
            except Exception:
                pass

        return 0

    def unlink(self, path):
        filename = path.lstrip('/')
        file_record = self.db.get_file(filename)
        if file_record:
            self.db.delete_file(filename)
        else:
            raise FuseOSError(errno.ENOENT)

    # --- POSIX Compatibility Stubs ---
    
    def chmod(self, path, mode):
        filename = path.lstrip('/')
        if self.db.is_folder(filename):
            self.db.update_mode(filename + "/.keep", mode)
        else:
            self.db.update_mode(filename, mode)
        return 0

    def chown(self, path, uid, gid):
        filename = path.lstrip('/')
        if self.db.is_folder(filename):
            self.db.update_chown(filename + "/.keep", uid, gid)
        else:
            self.db.update_chown(filename, uid, gid)
        return 0

    def utimens(self, path, times=None):
        filename = path.lstrip('/')
        if times is None:
            atime = mtime = time.time()
        else:
            atime, mtime = times
            
        if self.db.is_folder(filename):
            self.db.update_utimens(filename + "/.keep", atime, mtime)
        else:
            self.db.update_utimens(filename, atime, mtime)
        return 0

    def access(self, path, mode):
        return 0

    def fsync(self, path, fdatasync, fh):
        return 0

    def statfs(self, path):
        # Report 1 Terabyte free to avoid 32-bit integer overflow in FUSE structs
        blocks = 2**28 # ~1 TB with 4K blocks
        return {
            'f_bsize': 4096,
            'f_frsize': 4096,
            'f_blocks': blocks,
            'f_bavail': blocks,
            'f_bfree': blocks,
            'f_files': 1000000,
            'f_ffree': 1000000,
            'f_namemax': 255
        }

    def mknod(self, path, mode, dev):
        # Sometimes used instead of 'create' by certain tools
        filename = path.lstrip('/')
        if stat.S_ISREG(mode):
            self.db.add_file(filename, 0)
        return 0

    def symlink(self, target, source):
        # We don't natively support symlinks in DB right now, but we can throw ENOSYS
        raise FuseOSError(errno.ENOSYS)

    def readlink(self, path):
        raise FuseOSError(errno.ENOSYS)

    def getxattr(self, path, name, position=0):
        # Just return ENODATA for extended attributes so tools don't crash
        raise FuseOSError(errno.ENODATA)

    def listxattr(self, path):
        return []

def mount_drive(mountpoint):
    db = DatabaseManager()
    print(f"Mounting BloxDrive at {mountpoint}...")
    # nothreads=False: allow FUSE to dispatch concurrent kernel requests on separate threads.
    # Without this, any blocking call (e.g. a Roblox upload) stalls ALL filesystem ops.
    FUSE(BloxDriveFUSE(db), mountpoint, nothreads=False, foreground=True)
