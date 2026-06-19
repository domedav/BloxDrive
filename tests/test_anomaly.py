import sys, os, shutil, subprocess, time
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from db import DatabaseManager
from fuse_app import BloxDriveFUSE
import stat

def test():
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)

    # Clean db
    subprocess.run(["mysql", "-u", "bloxdrive", "-pbloxdrive", "-e", "DROP DATABASE IF EXISTS bloxdrive; CREATE DATABASE bloxdrive;"])
    db.init_db()
    
    # Create folder and file
    fuse.mkdir("/folder_a", 0o755)
    fuse.create("/folder_a/file1.txt", 0o644)
    fuse.create("/file_b.txt", 0o644)
    
    # Try batch delete logic
    fuse.unlink("/file_b.txt")
    fuse.unlink("/folder_a/file1.txt")
    
    try:
        fuse.rmdir("/folder_a")
        print("Anomaly test passed: folder was deleted.")
    except Exception as e:
        print(f"Anomaly test failed: {e}")

if __name__ == "__main__":
    test()
