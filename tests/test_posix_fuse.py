import sys
import os
import errno
import stat

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import DatabaseManager
from fuse_app import BloxDriveFUSE
from fuse import FuseOSError

def test_posix_fuse():
    print("--- Testing FUSE POSIX Operations ---")
    db = DatabaseManager()
    fuse = BloxDriveFUSE(db)
    
    # Clean state
    try: fuse.rmdir("/posix_dir")
    except: pass
    try: fuse.unlink("/posix_file.txt")
    except: pass
    try: fuse.unlink("/posix_dir/moved.txt")
    except: pass

    # 1. Test mkdir
    print("Testing mkdir...")
    fuse.mkdir("/posix_dir", 0o755)
    attr = fuse.getattr("/posix_dir")
    assert stat.S_ISDIR(attr['st_mode']), "Directory was not created properly"
    print("mkdir: PASS")
    
    # 2. Test readdir
    print("Testing readdir...")
    dirents = fuse.readdir("/", None)
    assert "posix_dir" in dirents, "Directory not found in root readdir"
    print("readdir: PASS")
    
    # 3. Test POSIX stubs (chmod, chown, utimens)
    print("Testing POSIX stubs (chmod, chown, utimens)...")
    assert fuse.chmod("/posix_dir", 0o777) == 0
    assert fuse.chown("/posix_dir", 1000, 1000) == 0
    assert fuse.utimens("/posix_dir", None) == 0
    print("POSIX stubs: PASS")

    # 4. Test file creation & write
    print("Testing create and write...")
    fh = fuse.create("/posix_file.txt", 0o644)
    data = b"Hello BloxDrive POSIX!"
    fuse.write("/posix_file.txt", data, 0, fh)
    fuse.release("/posix_file.txt", fh)
    
    attr_file = fuse.getattr("/posix_file.txt")
    assert stat.S_ISREG(attr_file['st_mode']), "File is not a regular file"
    assert attr_file['st_size'] == len(data), "File size mismatch"
    print("create/write: PASS")
    
    # 5. Test copy/duplicate (Deduplication implicit via main.py in actual daemon, here we test rename)
    print("Testing rename (mv)...")
    fuse.rename("/posix_file.txt", "/posix_dir/moved.txt")
    
    try:
        fuse.getattr("/posix_file.txt")
        assert False, "Old file should not exist"
    except FuseOSError as e:
        assert e.errno == errno.ENOENT
        
    attr_moved = fuse.getattr("/posix_dir/moved.txt")
    assert attr_moved['st_size'] == len(data), "Moved file size mismatch"
    
    # Check directory contents
    dir_contents = fuse.readdir("/posix_dir", None)
    assert "moved.txt" in dir_contents, "File not in destination directory"
    print("rename (mv): PASS")
    
    # 6. Test rmdir (should fail if not empty)
    print("Testing rmdir (not empty)...")
    try:
        fuse.rmdir("/posix_dir")
        assert False, "rmdir should fail on non-empty directory"
    except FuseOSError as e:
        assert e.errno == errno.ENOTEMPTY
    print("rmdir (not empty): PASS")
    
    # 7. Test unlink and rmdir
    print("Testing unlink and rmdir...")
    fuse.unlink("/posix_dir/moved.txt")
    fuse.rmdir("/posix_dir")
    
    try:
        fuse.getattr("/posix_dir")
        assert False, "Directory should be deleted"
    except FuseOSError:
        pass
    print("unlink and rmdir: PASS")
    
    print("All POSIX FUSE tests passed!")

if __name__ == "__main__":
    test_posix_fuse()
