import argparse
import os
import math
import asyncio
import hashlib
from db import DatabaseManager
from roblox import RobloxClient
from encoder import ImageCoder
from fuse_app import mount_drive
import config

async def upload_file(filepath: str, filename_override: str = None):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        return

    filename = filename_override if filename_override else os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    db = DatabaseManager()
    
    # Check if exists
    if db.get_file(filename):
        print(f"Error: File '{filename}' already exists in BloxDrive.")
        return

    file_id = db.add_file(filename, file_size)
    roblox = RobloxClient()

    chunk_size = config.CHUNK_SIZE_BYTES
    total_chunks = math.ceil(file_size / chunk_size)
    
    print(f"Uploading '{filename}' ({file_size} bytes) in {total_chunks} chunks...")

    with open(filepath, 'rb') as f:
        from crypto import CryptoManager
        for seq in range(total_chunks):
            chunk_data = f.read(chunk_size)
            actual_size = len(chunk_data)
            
            encrypted_data = CryptoManager.encrypt(chunk_data)
            
            chunk_hash = hashlib.md5(encrypted_data).hexdigest()
            existing_chunk = db.get_chunk_by_hash(chunk_hash)
            
            if existing_chunk:
                print(f"  [{seq+1}/{total_chunks}] Chunk duplicated! Skipping upload and reusing asset ID: {existing_chunk['asset_id']}")
                db.add_chunk(file_id, seq, existing_chunk['asset_id'], actual_size, existing_chunk['cdn_url'], chunk_hash)
                continue
                
            print(f"  [{seq+1}/{total_chunks}] Encoding chunk...")
            tmp_png = f"/tmp/bloxdrive_tmp_{file_id}_{seq}.png"
            ImageCoder.encode(encrypted_data, tmp_png)
            
            print(f"  [{seq+1}/{total_chunks}] Uploading to Roblox...")
            try:
                asset_id = await roblox.upload_asset(tmp_png, f"{filename}_part_{seq}")
                print(f"  [{seq+1}/{total_chunks}] Success! Asset ID: {asset_id}")
                
                db.add_chunk(file_id, seq, str(asset_id), actual_size, None, chunk_hash)
            except Exception as e:
                print(f"  Failed to upload chunk: {e}")
                # Note: A robust system would cleanup partial db entries here
                return
            finally:
                if os.path.exists(tmp_png):
                    os.remove(tmp_png)
            
    print(f"Upload complete: {filename}")

def main():
    parser = argparse.ArgumentParser(description="BloxDrive - Roblox-backed Cloud Storage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Mount command
    parser_mount = subparsers.add_parser("mount", help="Mount BloxDrive to a directory")
    parser_mount.add_argument("path", type=str, nargs='?', default=config.MOUNT_DIR, help="Directory to mount to")

    # Upload command
    parser_upload = subparsers.add_parser("upload", help="Upload a file to BloxDrive")
    parser_upload.add_argument("file", type=str, help="Path to local file")

    # List command
    parser_list = subparsers.add_parser("list", help="List files in BloxDrive")

    # Auth command
    parser_auth = subparsers.add_parser("auth", help="Force re-authenticate BloxDrive")

    args = parser.parse_args()

    if args.command == "auth":
        import auth_server
        auth_server.force_reauth()
        return

    if args.command == "mount":
        if not os.path.exists(args.path):
            os.makedirs(args.path)
        mount_drive(args.path)
        
    elif args.command == "upload":
        asyncio.run(upload_file(args.file))
        
    elif args.command == "list":
        db = DatabaseManager()
        files = db.list_files()
        print(f"{'ID':<5} | {'Filename':<40} | {'Size (Bytes)':<15}")
        print("-" * 65)
        for f in files:
            print(f"{f['id']:<5} | {f['filename']:<40} | {f['size']:<15}")

if __name__ == "__main__":
    main()
