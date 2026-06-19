import re

with open('src/db.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_method = False
i = 0
while i < len(lines):
    line = lines[i]
    if line.strip().startswith('def '):
        new_lines.append(line)
        # Skip down to where conn = self.get_connection() might be
        i += 1
        continue
        
    if 'conn = self.get_connection()' in line:
        indent = line[:len(line) - len(line.lstrip())]
        next_line = lines[i+1]
        if 'cursor = conn.cursor(' in next_line:
            # It's our pattern!
            dict_flag = 'dictionary=True' in next_line
            # Replace with with closing(self.get_connection()) as conn, closing(conn.cursor(...)) as cursor:
            cursor_args = 'dictionary=True' if dict_flag else ''
            new_lines.append(f"{indent}with closing(self.get_connection()) as conn, closing(conn.cursor({cursor_args})) as cursor:\n")
            
            # Now we indent all following lines until we see cursor.close()
            i += 2
            while i < len(lines):
                inner_line = lines[i]
                if inner_line.strip() == 'cursor.close()':
                    # Skip cursor.close() and conn.close()
                    if i + 1 < len(lines) and lines[i+1].strip() == 'conn.close()':
                        i += 1 # skip conn.close()
                    i += 1
                    break
                elif inner_line.strip() == 'conn.close()':
                    i += 1
                    break
                else:
                    new_lines.append("    " + inner_line if inner_line.strip() else inner_line)
                i += 1
            continue
            
    new_lines.append(line)
    i += 1

# Add import
content = "".join(new_lines)
if 'from contextlib import closing' not in content:
    content = content.replace('import config', 'import config\nfrom contextlib import closing')

with open('src/db.py', 'w') as f:
    f.write(content)

print("db.py refactored successfully.")
