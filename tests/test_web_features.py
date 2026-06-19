import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import DatabaseManager

def test_web_features():
    print("--- Testing Web UI Features (DB Layer) ---")
    db = DatabaseManager()
    
    # 1. Test Folder Creation (.keep file)
    print("Testing Folder Creation...")
    test_folder = "test_ui_folder"
    keep_file = f"{test_folder}/.keep"
    db.add_file(keep_file, 0)
    
    f = db.get_file(keep_file)
    assert f is not None, "Folder creation failed."
    assert f['size'] == 0, "Folder size should be 0."
    print("Folder Creation: PASS")
    
    # 2. Test File Rename
    print("Testing File Rename...")
    db.add_file("old_file.txt", 123)
    db.rename_file("old_file.txt", "new_file.txt")
    
    old_f = db.get_file("old_file.txt")
    new_f = db.get_file("new_file.txt")
    
    assert old_f is None, "Old file should not exist."
    assert new_f is not None, "New file should exist."
    assert new_f['size'] == 123, "Size should be preserved."
    print("File Rename: PASS")
    
    # 3. Test Folder Rename
    print("Testing Folder Rename...")
    db.add_file(f"{test_folder}/file1.txt", 10)
    db.add_file(f"{test_folder}/subfolder/file2.txt", 20)
    
    new_folder = "renamed_ui_folder"
    db.rename_folder(test_folder, new_folder)
    
    assert db.get_file(f"{test_folder}/.keep") is None, "Old folder should not exist."
    assert db.get_file(f"{new_folder}/.keep") is not None, "New folder keep file should exist."
    assert db.get_file(f"{new_folder}/file1.txt") is not None, "File 1 should be renamed."
    assert db.get_file(f"{new_folder}/subfolder/file2.txt") is not None, "Subfolder file should be renamed."
    print("Folder Rename: PASS")
    
    # Clean up
    db.delete_file(f"{new_folder}/.keep")
    db.delete_file(f"{new_folder}/file1.txt")
    db.delete_file(f"{new_folder}/subfolder/file2.txt")
    db.delete_file("new_file.txt")
    print("Cleanup: PASS")
    print("All Web UI feature tests passed!")

if __name__ == "__main__":
    test_web_features()
