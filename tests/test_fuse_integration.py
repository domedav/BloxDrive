import sys
import os
import asyncio
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import DatabaseManager
from fuse_app import BloxDriveFUSE

def test_fuse_read_write():
    print("--- Testing FUSE Read/Write & Streaming ---")
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)
    
    test_filename = "fuse_test_integration.bin"
    test_path = f"/{test_filename}"
    
    # 1. Test Create
    fh = fuse.create(test_path, 0o644)
    print("FUSE Create: PASS")
    
    # 2. Test Write (Spooling)
    # Write 1.5 MB of random data
    data_size = int(1.5 * 1024 * 1024)
    test_data = os.urandom(data_size)
    
    written = fuse.write(test_path, test_data, 0, fh)
    assert written == data_size, "Failed to write full data"
    print("FUSE Write (Spooling): PASS")
    
    # 3. Test Release (Triggers Upload)
    print("FUSE Release (Uploading to Roblox...)")
    fuse.release(test_path, fh)
    print("FUSE Release (Upload): PASS")
    
    # 4. Test GetAttr
    attr = fuse.getattr(test_path)
    assert attr['st_size'] == data_size, f"Size mismatch. Expected {data_size}, got {attr['st_size']}"
    print("FUSE GetAttr: PASS")
    
    # 5. Test Read (Streaming chunks)
    print("FUSE Read (Streaming)...")
    fh_read = fuse.open(test_path, os.O_RDONLY)
    
    # Test reading the exact middle of the file (streaming offset)
    offset = data_size // 2
    length = 1024 * 50 # 50KB chunk
    
    read_data = fuse.read(test_path, length, offset, fh_read)
    
    assert len(read_data) == length, f"Read length mismatch. Expected {length}, got {len(read_data)}"
    assert read_data == test_data[offset:offset+length], "Data corruption! Read data does not match original written data at offset."
    print("FUSE Streaming Read (Offset Access): PASS")
    
    fuse.release(test_path, fh_read)
    
    # 6. Test Unlink (Delete)
    fuse.unlink(test_path)
    try:
        fuse.getattr(test_path)
        assert False, "File should have been deleted"
    except Exception as e:
        # FuseOSError expected
        print("FUSE Unlink (Delete): PASS")

if __name__ == "__main__":
    test_fuse_read_write()
