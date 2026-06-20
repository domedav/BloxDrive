import argparse
import os
import math
import asyncio
import hashlib
from db import DatabaseManager
from roblox_pool import RobloxPool
from encoder import ImageCoder
from fuse_app import mount_drive
import config

async def upload_file(filepath: str, filename_override: str = None, file_id_override: int = None):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        return

    filename = filename_override if filename_override else os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    db = DatabaseManager()
    
    # Check if exists
    existing = db.get_file(filename)
    if existing and not file_id_override:
        print(f"Error: File '{filename}' already exists in BloxDrive.")
        return

    if file_id_override:
        file_id = file_id_override
        db.update_file_size(file_id, file_size)
        db.delete_chunks(file_id)
    else:
        file_id = db.add_file(filename, file_size)

    pool = RobloxPool()
    N = pool.n
    raid_enabled = pool.raid_enabled
    
    chunk_size = config.CHUNK_SIZE_BYTES
    total_chunks = math.ceil(file_size / chunk_size)

    if not raid_enabled:
        print(f"Uploading '{filename}' ({file_size} bytes) in {total_chunks} chunks (No RAID)...")
    else:
        print(f"Uploading '{filename}' ({file_size} bytes) in {total_chunks} chunks (RAID-{N} enabled)...")

    try:
        with open(filepath, 'rb') as f:
            from crypto import CryptoManager
            loop = asyncio.get_event_loop()
            
            data_per_stripe = max(1, N - 1) if raid_enabled else 1
            stripe_buffer = []
            data_chunk_ids = []
            
            for seq in range(total_chunks):
                # Offload disk read
                chunk_data = await loop.run_in_executor(None, f.read, chunk_size)
                actual_size = len(chunk_data)
                
                # Offload encryption
                encrypted_data = await loop.run_in_executor(None, CryptoManager.encrypt, chunk_data)
                
                stripe_index = seq // data_per_stripe
                position_in_stripe = seq % data_per_stripe
                assignment = pool.get_stripe_assignment(stripe_index)
                
                # Data account
                data_account_id = assignment['data'][position_in_stripe] if raid_enabled else assignment['data'][0]
                
                chunk_hash = hashlib.md5(encrypted_data).hexdigest()
                existing_chunk = db.get_chunk_by_hash(chunk_hash)
                
                if existing_chunk:
                    print(f"  [{seq+1}/{total_chunks}] Chunk duplicated! Skipping upload and reusing asset ID: {existing_chunk['asset_id']}")
                    chunk_id = db.add_chunk(file_id, seq, existing_chunk['asset_id'], actual_size, existing_chunk['cdn_url'], chunk_hash, data_account_id, 'data')
                    data_chunk_ids.append(chunk_id)
                else:
                    print(f"  [{seq+1}/{total_chunks}] Encoding chunk...")
                    tmp_png = f"/tmp/bloxdrive_tmp_{file_id}_{seq}.png"
                    await loop.run_in_executor(None, ImageCoder.encode, encrypted_data, tmp_png)
                    
                    print(f"  [{seq+1}/{total_chunks}] Uploading to Roblox (Account {data_account_id})...")
                    client = pool.get_client(data_account_id)
                    try:
                        asset_id = await client.upload_asset(tmp_png, f"{filename}_part_{seq}")
                        print(f"  [{seq+1}/{total_chunks}] Success! Asset ID: {asset_id}")
                        chunk_id = db.add_chunk(file_id, seq, str(asset_id), actual_size, None, chunk_hash, data_account_id, 'data')
                        data_chunk_ids.append(chunk_id)
                    finally:
                        if os.path.exists(tmp_png):
                            os.remove(tmp_png)
                
                if raid_enabled:
                    stripe_buffer.append(encrypted_data)
                    
                    if len(stripe_buffer) == data_per_stripe:
                        # Full stripe, compute parity and upload
                        print(f"  [Stripe {stripe_index}] Computing and uploading Parity...")
                        parity_data = RobloxPool.compute_parity(*stripe_buffer)
                        
                        tmp_png_parity = f"/tmp/bloxdrive_tmp_{file_id}_parity_{stripe_index}.png"
                        await loop.run_in_executor(None, ImageCoder.encode, parity_data, tmp_png_parity)
                        
                        parity_account_id = assignment['parity']
                        client = pool.get_client(parity_account_id)
                        try:
                            asset_id = await client.upload_asset(tmp_png_parity, f"{filename}_parity_{stripe_index}")
                            print(f"  [Stripe {stripe_index}] Parity Success! Asset ID: {asset_id}")
                            
                            # Use sequence = -1 or similar? Actually we can use a huge sequence or let sequence be NULL. But chunks table requires sequence INT NOT NULL.
                            # We can just use (total_chunks + stripe_index) for parity sequence to keep it unique per file.
                            parity_seq = total_chunks + stripe_index
                            parity_chunk_id = db.add_chunk(file_id, parity_seq, str(asset_id), len(parity_data), None, None, parity_account_id, 'parity')
                            
                            # Record stripe mapping
                            stripe_id = db.add_raid_stripe(file_id, stripe_index)
                            for i, buf_chunk_id in enumerate(data_chunk_ids):
                                db.add_stripe_member(stripe_id, buf_chunk_id, 'data', assignment['data'][i])
                            db.add_stripe_member(stripe_id, parity_chunk_id, 'parity', parity_account_id)
                            
                        finally:
                            if os.path.exists(tmp_png_parity):
                                os.remove(tmp_png_parity)
                                
                        stripe_buffer = []
                        data_chunk_ids = []

            # Handle incomplete final stripe
            if raid_enabled and stripe_buffer:
                stripe_index = total_chunks // data_per_stripe
                assignment = pool.get_stripe_assignment(stripe_index)
                
                print(f"  [Stripe {stripe_index}] Computing and uploading Parity (partial stripe)...")
                parity_data = RobloxPool.compute_parity(*stripe_buffer)
                
                tmp_png_parity = f"/tmp/bloxdrive_tmp_{file_id}_parity_{stripe_index}.png"
                await loop.run_in_executor(None, ImageCoder.encode, parity_data, tmp_png_parity)
                
                parity_account_id = assignment['parity']
                client = pool.get_client(parity_account_id)
                try:
                    asset_id = await client.upload_asset(tmp_png_parity, f"{filename}_parity_{stripe_index}")
                    print(f"  [Stripe {stripe_index}] Parity Success! Asset ID: {asset_id}")
                    
                    parity_seq = total_chunks + stripe_index
                    parity_chunk_id = db.add_chunk(file_id, parity_seq, str(asset_id), len(parity_data), None, None, parity_account_id, 'parity')
                    
                    stripe_id = db.add_raid_stripe(file_id, stripe_index)
                    for i, buf_chunk_id in enumerate(data_chunk_ids):
                        db.add_stripe_member(stripe_id, buf_chunk_id, 'data', assignment['data'][i])
                    db.add_stripe_member(stripe_id, parity_chunk_id, 'parity', parity_account_id)
                    
                finally:
                    if os.path.exists(tmp_png_parity):
                        os.remove(tmp_png_parity)

        print(f"Upload complete: {filename}")
    except Exception as e:
        print(f"Fatal error during upload: {e}. Cleaning up database record.")
        db.delete_file(filename)
        raise

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

    # RAID command
    parser_raid = subparsers.add_parser("raid", help="Manage RAID redundancy and accounts")
    parser_raid.add_argument("raid_action", choices=["status", "add", "remove", "enable", "recover", "protect"], help="RAID action to perform")
    parser_raid.add_argument("--label", type=str, help="Account label to remove or replace")

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
            
    elif args.command == "raid":
        if args.raid_action == "status":
            from recovery import RaidRecovery
            asyncio.run(RaidRecovery().print_health())
        elif args.raid_action == "add":
            import auth_server
            auth_server.run_web_setup(mode="add_account")
        elif args.raid_action == "remove":
            if not args.label:
                print("Error: You must provide an account --label to remove.")
                return
            db = DatabaseManager()
            accounts = db.get_accounts()
            target_acc = next((a for a in accounts if a['label'] == args.label or str(a['id']) == args.label), None)
            if not target_acc:
                print(f"Error: Account '{args.label}' not found.")
                return
            db.remove_account(target_acc['id'])
            print(f"Successfully removed account '{target_acc['label']}'.")
            print("Run 'python3 src/main.py raid recover' if you need to rebuild missing parity chunks.")
        elif args.raid_action == "enable" or args.raid_action == "protect":
            from raid_migration import RaidMigration
            asyncio.run(RaidMigration().migrate_existing_files())
        elif args.raid_action == "recover":
            from recovery import RaidRecovery
            asyncio.run(RaidRecovery().interactive_recover())

if __name__ == "__main__":
    main()
