import os
import math
import asyncio
import hashlib
import uuid
from db import DatabaseManager
from roblox_pool import RobloxPool
from encoder import ImageCoder
import config
from crypto import CryptoManager

async def upload_file(filepath: str, filename_override: str = None, file_id_override: int = None):
    if not os.path.exists(filepath):
        print(f"Error: File '{filepath}' not found.")
        return

    filename = filename_override if filename_override else os.path.basename(filepath)
    file_size = os.path.getsize(filepath)
    db = DatabaseManager()
    
    existing = db.get_file(filename)
    
    # Use a temporary filename for atomic safe replacement
    temp_filename = filename + f".tmp.{uuid.uuid4().hex}"
    file_id = db.add_file(temp_filename, file_size)

    pool = RobloxPool()
    N = pool.n
    raid_enabled = pool.raid_enabled
    
    chunk_size = config.CHUNK_SIZE_BYTES
    total_chunks = math.ceil(file_size / chunk_size)

    print(f"Uploading '{filename}' ({file_size} bytes) in {total_chunks} chunks...")

    try:
        with open(filepath, 'rb') as f:
            loop = asyncio.get_event_loop()
            
            data_per_stripe = max(1, N - 1) if raid_enabled else 1
            stripe_buffer = []
            data_chunk_ids = []
            
            for seq in range(total_chunks):
                chunk_data = await loop.run_in_executor(None, f.read, chunk_size)
                actual_size = len(chunk_data)
                
                encrypted_data = await loop.run_in_executor(None, CryptoManager.encrypt, chunk_data)
                
                stripe_index = seq // data_per_stripe
                position_in_stripe = seq % data_per_stripe
                assignment = pool.get_stripe_assignment(stripe_index)
                
                data_account_id = assignment['data'][position_in_stripe] if raid_enabled else assignment['data'][0]
                
                # SHA-256 for secure dedup
                chunk_hash = hashlib.sha256(encrypted_data).hexdigest()
                existing_chunk = db.get_chunk_by_hash(chunk_hash)
                
                if existing_chunk:
                    print(f"  [{seq+1}/{total_chunks}] Chunk duplicated! Reusing asset ID: {existing_chunk['asset_id']}")
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
                        print(f"  [Stripe {stripe_index}] Computing and uploading Parity...")
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

        # Upload successful. Swap files.
        conn = db.get_connection()
        conn.autocommit = False
        try:
            cursor = conn.cursor()
            try:
                if existing:
                    cursor.execute("DELETE FROM chunks WHERE file_id = %s", (existing['id'],))
                    cursor.execute("DELETE FROM files WHERE id = %s", (existing['id'],))
                cursor.execute("UPDATE files SET filename = %s WHERE filename = %s", (filename, temp_filename))
                conn.commit()
            finally:
                cursor.close()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        print(f"Upload complete: {filename}")
        
    except Exception as e:
        print(f"Fatal error during upload: {e}. Cleaning up temporary database record.")
        db.delete_chunks(file_id)
        db.delete_file_by_id(file_id)
        raise
