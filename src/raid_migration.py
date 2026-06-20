import asyncio
import os
from db import DatabaseManager
from roblox_pool import RobloxPool
import aiohttp
from main import upload_file

class RaidMigration:
    def __init__(self):
        self.db = DatabaseManager()
        self.pool = RobloxPool()

    async def migrate_existing_files(self):
        if not self.pool.raid_enabled:
            print("RAID is not enabled. Add more accounts first using 'python3 src/main.py raid add'.")
            return

        print("Scanning for files that need RAID migration...")
        files = self.db.list_files()
        
        migrated_count = 0
        for f in files:
            if f['filename'].endswith('.keep'):
                continue
                
            if f['size'] == 0:
                continue

            chunks = self.db.get_chunks(f['id'])
            if not chunks:
                continue
                
            # Check if it needs migration
            # A file needs migration if any of its chunks lack RAID protection
            needs_migration = False
            for c in chunks:
                if c.get('account_id') is None or c.get('account_id') == -1 or c.get('chunk_type') is None:
                    needs_migration = True
                    break
                    
            if needs_migration:
                print(f"Migrating '{f['filename']}' ({f['size']} bytes) to RAID-{self.pool.n}...")
                await self._migrate_file(f, chunks)
                migrated_count += 1
                
        if migrated_count == 0:
            print("All files are fully protected. No migration needed.")
        else:
            print(f"Migration complete. Migrated {migrated_count} files to RAID-{self.pool.n}.")

    async def _migrate_file(self, file_record, chunks):
        tmp_path = f"/tmp/bloxdrive_migrate_{file_record['id']}.tmp"
        
        try:
            # Step 1: Download the file to a temp location
            print(f"  Downloading existing chunks for '{file_record['filename']}'...")
            async with aiohttp.ClientSession() as session:
                with open(tmp_path, 'wb') as f:
                    for chunk in chunks:
                        data = await self.pool.fetch_chunk_data(chunk, self.db, session)
                        if data is None:
                            raise IOError(f"Failed to fetch chunk {chunk['id']}")
                        f.write(data)
                        
            # Step 2: Upload the file again using the same file ID
            # upload_file will automatically stripe it across the pool
            print(f"  Re-uploading '{file_record['filename']}' with RAID protection...")
            await upload_file(tmp_path, filename_override=file_record['filename'], file_id_override=file_record['id'])
            
            print(f"  Successfully migrated '{file_record['filename']}'.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    asyncio.run(RaidMigration().migrate_existing_files())
