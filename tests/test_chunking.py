import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

# Force a small chunk size just for this test so we can test chunking 
# without uploading hundreds of megabytes.
import config
config.CHUNK_SIZE_MB = 1
config.CHUNK_SIZE_BYTES = 1024 * 1024

from db import DatabaseManager
from fuse_app import BloxDriveFUSE

def test_chunking():
    print(f"--- Testing Multi-Chunk Logic (Chunk Size = {config.CHUNK_SIZE_MB}MB) ---")
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)
    
    test_filename = "chunk_test.bin"
    test_path = f"/{test_filename}"
    
    # Generate 2.5 MB of data, which should result in 3 chunks (1MB, 1MB, 0.5MB)
    data_size = int(2.5 * 1024 * 1024)
    test_data = os.urandom(data_size)
    
    # 1. Write the file
    fh_write = fuse.create(test_path, 0o644)
    written = fuse.write(test_path, test_data, 0, fh_write)
    assert written == data_size, "Failed to write full data to spool"
    
    print("Uploading 2.5MB file (Should split into 3 chunks)...")
    fuse.flush(test_path, fh_write)
    fuse.release(test_path, fh_write)
    
    # 2. Test "Simple" Full Read
    print("Testing Simple Sequential Read...")
    fh_read = fuse.open(test_path, os.O_RDONLY)
    
    full_read_data = bytearray()
    read_size = 1024 * 512 # Read in 512KB blocks
    offset = 0
    while offset < data_size:
        chunk = fuse.read(test_path, read_size, offset, fh_read)
        if not chunk:
            break
        full_read_data.extend(chunk)
        offset += len(chunk)
        
    assert len(full_read_data) == data_size, f"Full read size mismatch. Expected {data_size}, got {len(full_read_data)}"
    assert full_read_data == test_data, "Data corruption! The reassembled file does not match the original."
    print("Simple Sequential Read: PASS")
    
    # 3. Test "Streamed" boundary read
    # We want to read a slice that crosses the boundary between Chunk 0 and Chunk 1.
    # Chunk 0 ends at 1MB (1,048,576 bytes).
    # We will read from 0.8 MB to 1.2 MB.
    print("Testing Streamed Boundary Read (Crossing chunk 0 -> 1)...")
    stream_offset = int(0.8 * 1024 * 1024)
    stream_length = int(0.4 * 1024 * 1024)
    
    stream_read_data = fuse.read(test_path, stream_length, stream_offset, fh_read)
    
    assert len(stream_read_data) == stream_length, f"Boundary stream length mismatch. Expected {stream_length}, got {len(stream_read_data)}"
    assert stream_read_data == test_data[stream_offset:stream_offset+stream_length], "Data corruption! Boundary read data does not match original."
    print("Streamed Boundary Read: PASS")
    
    fuse.flush(test_path, fh_read)
    fuse.release(test_path, fh_read)
    fuse.unlink(test_path)
    print("Multi-Chunk Test Completed Successfully!")

def test_legacy_chunk_retrieval():
    print("--- Testing Legacy Chunk Retrieval and Parity Filtering ---")
    db = DatabaseManager()
    
    # 1. Create a dummy file
    filename = "legacy_test_file.bin"
    file_id = db.add_file(filename, 300)
    
    try:
        # 2. Add chunks with different chunk_types
        # Sequence 0: 'data'
        db.add_chunk(
            file_id=file_id,
            sequence=0,
            asset_id="asset_data",
            size=100,
            cdn_url=None,
            chunk_hash="hash_data",
            account_id=1,
            chunk_type="data"
        )
        # Sequence 1: None (legacy NULL chunk)
        db.add_chunk(
            file_id=file_id,
            sequence=1,
            asset_id="asset_legacy",
            size=100,
            cdn_url=None,
            chunk_hash="hash_legacy",
            account_id=1,
            chunk_type=None
        )
        # Sequence 2: 'parity'
        db.add_chunk(
            file_id=file_id,
            sequence=2,
            asset_id="asset_parity",
            size=100,
            cdn_url=None,
            chunk_hash="hash_parity",
            account_id=1,
            chunk_type="parity"
        )
        
        # 3. Retrieve chunks with include_parity=False (default)
        data_chunks = db.get_chunks(file_id, include_parity=False)
        assert len(data_chunks) == 2, f"Expected 2 data chunks, got {len(data_chunks)}"
        
        sequences = [c['sequence'] for c in data_chunks]
        assert 0 in sequences, "Sequence 0 (data) missing"
        assert 1 in sequences, "Sequence 1 (legacy NULL) missing"
        assert 2 not in sequences, "Sequence 2 (parity) was incorrectly included in data chunks"
        
        # 4. Retrieve chunks with include_parity=True
        all_chunks = db.get_chunks(file_id, include_parity=True)
        assert len(all_chunks) == 3, f"Expected 3 chunks, got {len(all_chunks)}"
        
        all_sequences = [c['sequence'] for c in all_chunks]
        assert 0 in all_sequences
        assert 1 in all_sequences
        assert 2 in all_sequences
        
        print("Legacy Chunk Retrieval and Parity Filtering: PASS")
        
    finally:
        # Cleanup
        db.delete_file(filename)

if __name__ == "__main__":
    test_chunking()
    test_legacy_chunk_retrieval()
