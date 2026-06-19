import sys, os, time, subprocess
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test():
    mount_dir = "/tmp/bloxdrive_test_mnt"
    os.makedirs(mount_dir, exist_ok=True)
    subprocess.run(["mysql", "-u", "bloxdrive", "-pbloxdrive", "-e", "DROP DATABASE IF EXISTS bloxdrive; CREATE DATABASE bloxdrive;"])
    
    fuse_proc = subprocess.Popen(["python3", "bloxdrive.sh", "start"], env=dict(os.environ, MOUNT_DIR=mount_dir))
    time.sleep(3)
    
    try:
        os.makedirs(f"{mount_dir}/folder_a")
        with open(f"{mount_dir}/folder_a/file1.txt", "w") as f:
            f.write("hello")
        with open(f"{mount_dir}/file2.txt", "w") as f:
            f.write("world")
            
        # GUI Trash simulation
        os.makedirs(f"{mount_dir}/.Trash-1000/files", exist_ok=True)
        os.makedirs(f"{mount_dir}/.Trash-1000/info", exist_ok=True)
        
        # Batch move to trash
        os.rename(f"{mount_dir}/folder_a", f"{mount_dir}/.Trash-1000/files/folder_a")
        os.rename(f"{mount_dir}/file2.txt", f"{mount_dir}/.Trash-1000/files/file2.txt")
        
        print("Rename successful!")
    except Exception as e:
        print(f"Failed: {e}")
    finally:
        subprocess.run(["fusermount", "-u", mount_dir])
        fuse_proc.terminate()

if __name__ == "__main__":
    test()
