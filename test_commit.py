import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
from db import DatabaseManager

db = DatabaseManager()
file_id = db.add_file("test_commit_file.txt", 100)
db.add_chunk(file_id, 0, "12345", 100, None, "testhash")

# Now let's see if we can get it back using a new connection
db2 = DatabaseManager()
f = db2.get_file("test_commit_file.txt")
print("File:", f)
chunks = db2.get_chunks(file_id)
print("Chunks:", chunks)
