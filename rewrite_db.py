import re

with open('src/db.py', 'r') as f:
    content = f.read()

# Add import if not present
if 'from contextlib import closing' not in content:
    content = content.replace('import config', 'import config\nfrom contextlib import closing')

# We'll replace the common pattern:
# conn = self.get_connection()
# cursor = conn.cursor(dictionary=True) or conn.cursor()
# ... do stuff ...
# cursor.close()
# conn.close()

# Let's add a helper to DatabaseManager
helper = """
    @contextlib.contextmanager
    def _cursor(self, dictionary=False):
        conn = self.get_connection()
        try:
            cursor = conn.cursor(dictionary=dictionary)
            try:
                yield conn, cursor
            finally:
                cursor.close()
        finally:
            conn.close()
"""
if 'def _cursor(' not in content:
    import contextlib # to ensure it's imported
    if 'import contextlib' not in content:
        content = content.replace('import config', 'import config\nimport contextlib')
    # find where to insert
    content = content.replace('    def get_connection(self):', helper[1:] + '\n    def get_connection(self):')

def replace_func(match):
    body = match.group(0)
    return body

# Actually, replacing it with regex is error prone because of indentation.
# Let's just use a python AST transformer or manually replace it for safety.
