import sys
import os
import errno
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))
from db import DatabaseManager
from fuse_app import BloxDriveFUSE

def test_delete():
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)

    # 1. Create a folder "folder_a"
    fuse.mkdir("/folder_a", 0o755)

    # 2. Create file "folder_a/file1.txt"
    fh1 = fuse.create("/folder_a/file1.txt", 0o644)
    fuse.release("/folder_a/file1.txt", fh1)

    # 3. Create a regular file "file2.txt" outside
    fh2 = fuse.create("/file2.txt", 0o644)
    fuse.release("/file2.txt", fh2)

    # Now the file manager deletes them.
    # It deletes file2.txt
    fuse.unlink("/file2.txt")

    # It deletes file1.txt
    fuse.unlink("/folder_a/file1.txt")

    # It deletes folder_a
    try:
        fuse.rmdir("/folder_a")
        print("rmdir successful!")
    except Exception as e:
        print(f"rmdir failed: {e}")

if __name__ == "__main__":
    test_delete()
