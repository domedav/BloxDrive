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
        from uploader import upload_file
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
            auth_server.run_setup(mode="add_account")
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
