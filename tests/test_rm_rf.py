import sys, os, shutil, subprocess, time
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

def test():
    # Mount FUSE in background
    mount_dir = "/tmp/bloxdrive_test_mnt"
    os.makedirs(mount_dir, exist_ok=True)
    
    print("Mounting...")
    # Clean db
    subprocess.run(["mysql", "-u", "bloxdrive", "-pbloxdrive", "-e", "DROP DATABASE IF EXISTS bloxdrive; CREATE DATABASE bloxdrive;"])
    
    fuse_proc = subprocess.Popen(["bash", "bloxdrive.sh", "start"], env=dict(os.environ, MOUNT_DIR=mount_dir))
    time.sleep(3) # Wait for mount
    
    try:
        print("Creating files...")
        os.makedirs(f"{mount_dir}/folder_b")
        with open(f"{mount_dir}/folder_b/file1.txt", "w") as f:
            f.write("hello")
        with open(f"{mount_dir}/file2.txt", "w") as f:
            f.write("world")
            
        print("Running rm -rf...")
        result = subprocess.run(["rm", "-rf", f"{mount_dir}/folder_b", f"{mount_dir}/file2.txt"], capture_output=True, text=True)
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        print("RETURN CODE:", result.returncode)
        
        if os.path.exists(f"{mount_dir}/folder_b"):
            print("ERROR: folder_b still exists!")
        else:
            print("folder_b deleted successfully!")
    finally:
        subprocess.run(["fusermount", "-u", mount_dir])
        fuse_proc.terminate()

if __name__ == "__main__":
    test()
