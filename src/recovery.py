import asyncio
from db import DatabaseManager
from roblox_pool import RobloxPool
import aiohttp
from uploader import upload_file
import os

class RaidRecovery:
    def __init__(self):
        self.db = DatabaseManager()
        self.pool = RobloxPool()

    async def print_health(self):
        print("\n=== BloxDrive RAID Health Status ===")
        print(f"Total Configured Accounts: {self.pool.n}")
        if not self.pool.raid_enabled:
            print("Status: RAID is DISABLED (Requires 2+ accounts)")
            return

        print("Checking accounts...")
        accounts = self.db.get_healthy_accounts()
        for i, acc in enumerate(accounts):
            print(f"  Account {i}: {acc['label']} (ID: {acc['id']}) - Healthy")
            
        print("\nChecking file stripes...")
        files = self.db.list_files()
        
        healthy_files = 0
        degraded_files = []
        lost_files = []
        
        # Test connectivity and resolving for every chunk? Too slow.
        # We will just report if any chunks belong to accounts that are no longer in the pool.
        active_account_ids = set(self.pool.account_ids)
        
        for f in files:
            if f['size'] == 0:
                healthy_files += 1
                continue
                
            chunks = self.db.get_chunks(f['id'])
            stripes = self.db.get_stripes_for_file(f['id'])
            
            if not stripes:
                # Legacy file without RAID is healthy
                healthy_files += 1
                continue
                
            file_degraded = False
            file_lost = False
            
            for stripe in stripes:
                missing_chunks = 0
                for member in stripe['members']:
                    if member['account_id'] not in active_account_ids:
                        missing_chunks += 1
                        
                if missing_chunks == 1:
                    file_degraded = True
                elif missing_chunks > 1:
                    file_lost = True
                    break
                    
            if file_lost:
                lost_files.append(f)
            elif file_degraded:
                degraded_files.append(f)
            else:
                healthy_files += 1
                
        print(f"\nFiles Scanned: {len(files)}")
        print(f"  Healthy: {healthy_files}")
        print(f"  Degraded (1 Drive Failed): {len(degraded_files)}")
        print(f"  Lost (2+ Drives Failed): {len(lost_files)}")
        
        if degraded_files:
            print("\nWARNING: Some files are degraded and relying on parity. Run 'python3 src/main.py raid recover' to rebuild them on healthy accounts.")

    async def interactive_recover(self):
        if not self.pool.raid_enabled:
            print("RAID is not enabled. Cannot recover.")
            return
            
        print("Scanning for degraded files...")
        
        files = self.db.list_files()
        active_account_ids = set(self.pool.account_ids)
        
        degraded_files = []
        for f in files:
            if f['size'] == 0: continue
            stripes = self.db.get_stripes_for_file(f['id'])
            if not stripes: continue
            
            for stripe in stripes:
                missing = sum(1 for m in stripe['members'] if m['account_id'] not in active_account_ids)
                if missing == 1:
                    degraded_files.append(f)
                    break
                    
        if not degraded_files:
            print("No degraded files found. Everything is healthy.")
            return
            
        print(f"Found {len(degraded_files)} degraded files.")
        
        from raid_migration import RaidMigration
        migration = RaidMigration()
        
        recovered = 0
        for f in degraded_files:
            print(f"Recovering '{f['filename']}'...")
            chunks = self.db.get_chunks(f['id'])
            try:
                await migration._migrate_file(f, chunks)
                recovered += 1
            except Exception as e:
                print(f"  Failed to recover '{f['filename']}': {e}")
                
        print(f"\nRecovery complete. Successfully rebuilt {recovered} out of {len(degraded_files)} files.")

if __name__ == "__main__":
    asyncio.run(RaidRecovery().print_health())
