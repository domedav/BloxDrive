import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import DatabaseManager
from fuse_app import BloxDriveFUSE

def test_deduplication():
    print("--- Testing Deduplication Logic ---")
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)
    
    # 1. Write File A
    test_data = b"This is identical data for deduplication test!" * 1000
    fh1 = fuse.create("/dedup_A.bin", 0o644)
    fuse.write("/dedup_A.bin", test_data, 0, fh1)
    print("Uploading File A...")
    fuse.flush("/dedup_A.bin", fh1)
    fuse.release("/dedup_A.bin", fh1)
    
    # 2. Write File B (Same data)
    fh2 = fuse.create("/dedup_B.bin", 0o644)
    fuse.write("/dedup_B.bin", test_data, 0, fh2)
    print("Uploading File B (Should be deduplicated)...")
    fuse.flush("/dedup_B.bin", fh2)
    fuse.release("/dedup_B.bin", fh2)
    
    # 3. Verify they share the same asset_id
    file_a = db.get_file("dedup_A.bin")
    file_b = db.get_file("dedup_B.bin")
    
    chunks_a = db.get_chunks(file_a['id'])
    chunks_b = db.get_chunks(file_b['id'])
    
    assert chunks_a[0]['asset_id'] == chunks_b[0]['asset_id'], "Deduplication FAILED! Asset IDs do not match."
    assert chunks_a[0]['chunk_hash'] == chunks_b[0]['chunk_hash'], "Chunk hashes do not match."
    
    print("Deduplication Test: PASS (File B successfully reused File A's Asset ID)")
    
    fuse.unlink("/dedup_A.bin")
    fuse.unlink("/dedup_B.bin")

if __name__ == "__main__":
    test_deduplication()
