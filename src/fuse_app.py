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

class BloxDriveFUSE(Operations):
    def __init__(self, db_manager):
        self.db = db_manager
        self.roblox = RobloxClient()
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
        file_record = self.db.get_file(filename)
        
        if not file_record:
            raise FuseOSError(errno.ENOENT)

        return {
            'st_mode': (stat.S_IFREG | 0o644),
            'st_nlink': 1,
            'st_size': file_record['size'],
            'st_ctime': file_record['created_at'].timestamp(),
            'st_mtime': file_record['created_at'].timestamp(),
            'st_atime': file_record['created_at'].timestamp()
        }

    def readdir(self, path, fh):
        if path != '/':
            raise FuseOSError(errno.ENOENT)

        dirents = ['.', '..']
        files = self.db.list_files()
        for f in files:
            dirents.append(f['filename'])
        return dirents

    def open(self, path, flags):
        filename = path.lstrip('/')
        file_record = self.db.get_file(filename)
        if not file_record:
            raise FuseOSError(errno.ENOENT)
        
        import uuid
        fh = self.next_fh
        self.next_fh += 1
        
        # If writable, spool the entire file from BloxDrive to local!
        if (flags & 3) != os.O_RDONLY:
            spool_path = os.path.join(self.spool_dir, str(uuid.uuid4()))
            with open(spool_path, 'wb') as f:
                chunks = self.db.get_chunks(file_record['id'])
                for seq in range(len(chunks)):
                    chunk = next((c for c in chunks if c['sequence'] == seq), None)
                    if chunk:
                        data = self._fetch_chunk_data(chunk)
                        if data:
                            f.write(data)
            self.open_files[fh] = {'path': spool_path, 'dirty': False, 'filename': filename}
        else:
            self.open_files[fh] = {'path': None, 'dirty': False, 'filename': filename}
            
        return fh

    def read(self, path, length, offset, fh):
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
        if self.cache_chunk_id == chunk['id'] and (time.time() - self.cache_time < 300):
            return self.cache_data

        cdn_url = chunk['cdn_url']
        if not cdn_url:
            # Resolve URL if missing
            cdn_url = self.loop.run_until_complete(self.roblox.resolve_cdn_url(chunk['asset_id']))
            if cdn_url:
                self.db.update_chunk_cdn_url(chunk['id'], cdn_url)
            else:
                return None # Could not resolve

        try:
            # We must download the image to decode it.
            # While Roblox CDN supports Range requests, the ImageCoder needs the full image 
            # to decode the pixels back into bytes.
            # Future Optimization: Since PNGs are compressed, random access into the raw binary
            # requires streaming the image, decoding it, and then pulling the bytes. 
            # For now, we fetch the whole 20MB PNG into memory, decode it, and cache it.
            resp = requests.get(cdn_url, timeout=10)
            if resp.status_code == 200:
                encrypted_bytes = ImageCoder.decode(resp.content)
                from crypto import CryptoManager
                raw_bytes = CryptoManager.decrypt(encrypted_bytes)
                
                self.cache_chunk_id = chunk['id']
                self.cache_data = raw_bytes
                self.cache_time = time.time()
                return raw_bytes
            else:
                print(f"Failed to fetch CDN: {resp.status_code}")
                return None
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
            # Not optimally handled for FUSE if fh is not provided, but usually truncate is called before open in FUSE if not handled.
            pass
            
        self.db.update_file_size(file_record['id'], length)

    def create(self, path, mode, fi=None):
        filename = path.lstrip('/')
        import uuid
        
        if not self.db.get_file(filename):
            self.db.add_file(filename, 0)
        else:
            self.db.delete_file(filename)
            self.db.add_file(filename, 0)
            
        fh = self.next_fh
        self.next_fh += 1
        
        spool_path = os.path.join(self.spool_dir, str(uuid.uuid4()))
        open(spool_path, 'wb').close()
        
        self.open_files[fh] = {'path': spool_path, 'dirty': True, 'filename': filename}
        return fh

    def release(self, path, fh):
        info = self.open_files.pop(fh, None)
        if info and info['dirty'] and info['path']:
            filename = info['filename']
            from main import upload_file
            
            # Delete old chunks via db
            file_record = self.db.get_file(filename)
            if file_record:
                self.db.delete_file(filename)
                
            self.loop.run_until_complete(upload_file(info['path'], filename_override=filename))
        
        if info and info['path'] and os.path.exists(info['path']):
            os.remove(info['path'])
            
        return 0

    def unlink(self, path):
        filename = path.lstrip('/')
        file_record = self.db.get_file(filename)
        if file_record:
            self.db.delete_file(filename)
        else:
            raise FuseOSError(errno.ENOENT)

def mount_drive(mountpoint):
    db = DatabaseManager()
    print(f"Mounting BloxDrive at {mountpoint}...")
    FUSE(BloxDriveFUSE(db), mountpoint, nothreads=True, foreground=True)
