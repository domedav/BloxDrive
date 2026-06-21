import mysql.connector
from mysql.connector import Error
import config
from contextlib import closing

class DatabaseManager:
    """
    Manages metadata for BloxDrive.
    Compatible with MySQL and TiDB.
    """
    def __init__(self):
        self.host = config.DB_HOST
        self.port = config.DB_PORT
        self.user = config.DB_USER
        self.password = config.DB_PASS
        self.database = config.DB_NAME
        self.init_db()

    def get_connection(self):
        """Returns a new database connection."""
        return mysql.connector.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            autocommit=True
        )

    def init_db(self):
        """Initializes the database and tables if they don't exist."""
        try:
            # Connect without database selected first to create it if missing
            conn = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password
            )
            cursor = conn.cursor()
            import re
            if not re.match(r'^[a-zA-Z0-9_]+$', self.database):
                raise ValueError("Invalid database name")
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{self.database}`")
            cursor.close()
            conn.close()

            # Now connect to the database to create tables
            with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:

                # Files table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS files (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        filename VARCHAR(255) NOT NULL,
                        size BIGINT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_filename (filename)
                    )
                """)

                # Chunks table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS chunks (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        file_id INT NOT NULL,
                        sequence INT NOT NULL,
                        asset_id VARCHAR(255) NOT NULL,
                        chunk_hash VARCHAR(64),
                        cdn_url TEXT,
                        size BIGINT NOT NULL,
                        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                        UNIQUE KEY unique_chunk (file_id, sequence)
                    )
                """)
            
                # Ensure chunk_hash exists if table was already created
                try:
                    cursor.execute("ALTER TABLE chunks ADD COLUMN chunk_hash VARCHAR(64)")
                except Error:
                    pass

                # Add RAID columns to chunks
                try:
                    cursor.execute("ALTER TABLE chunks ADD COLUMN account_id INT DEFAULT NULL")
                    cursor.execute("ALTER TABLE chunks ADD COLUMN chunk_type VARCHAR(10) DEFAULT 'data'")
                except Error:
                    pass

                # Accounts table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        label VARCHAR(100) NOT NULL,
                        api_key TEXT NOT NULL,
                        user_id VARCHAR(50) NOT NULL,
                        auth_token TEXT,
                        status VARCHAR(20) DEFAULT 'healthy',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE KEY unique_label (label)
                    )
                """)

                # App Settings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key_name VARCHAR(100) PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)

                # Raid Stripes table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS raid_stripes (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        file_id INT NOT NULL,
                        stripe_index INT NOT NULL,
                        FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE,
                        UNIQUE KEY unique_stripe (file_id, stripe_index)
                    )
                """)

                # Raid Stripe Members table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS raid_stripe_members (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        stripe_id INT NOT NULL,
                        chunk_id INT NOT NULL,
                        role VARCHAR(10) NOT NULL,
                        account_id INT NOT NULL,
                        FOREIGN KEY (stripe_id) REFERENCES raid_stripes(id) ON DELETE CASCADE,
                        FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
                        FOREIGN KEY (account_id) REFERENCES accounts(id)
                    )
                """)

                # Metadata columns for POSIX compliance
                metadata_columns = {
                    "uid": "INT DEFAULT 1000",
                    "gid": "INT DEFAULT 1000",
                    "mode": "INT DEFAULT 33188", # 0o100644
                    "atime": "DOUBLE DEFAULT 0",
                    "mtime": "DOUBLE DEFAULT 0",
                    "ctime": "DOUBLE DEFAULT 0"
                }
            
                for col, col_type in metadata_columns.items():
                    try:
                        cursor.execute(f"ALTER TABLE files ADD COLUMN {col} {col_type}")
                        # If newly added, set the times to current time
                        if col in ['atime', 'mtime', 'ctime']:
                            import time
                            cursor.execute(f"UPDATE files SET {col} = %s", (time.time(),))
                    except Error:
                        pass

            print("Database initialized successfully.")
        except Error as e:
            print(f"Error initializing database: {e}")
            print("Please ensure MariaDB/MySQL is running and credentials in config.py are correct.")

    def add_file(self, filename, size):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("INSERT INTO files (filename, size) VALUES (%s, %s)", (filename, size))
            file_id = cursor.lastrowid
        return file_id

    def add_chunk(self, file_id, sequence, asset_id, size, cdn_url=None, chunk_hash=None, account_id=None, chunk_type='data'):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO chunks (file_id, sequence, asset_id, size, cdn_url, chunk_hash, account_id, chunk_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (file_id, sequence, asset_id, size, cdn_url, chunk_hash, account_id, chunk_type)
            )
            return cursor.lastrowid

    def get_file(self, filename):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM files WHERE filename = %s", (filename,))
            result = cursor.fetchone()
        return result

    def get_chunk_by_hash(self, chunk_hash, account_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM chunks WHERE chunk_hash = %s AND account_id = %s AND chunk_type = 'data' LIMIT 1", (chunk_hash, account_id))
            result = cursor.fetchone()
        return result

    def get_chunks(self, file_id, include_parity=False):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            if include_parity:
                cursor.execute("SELECT * FROM chunks WHERE file_id = %s ORDER BY sequence", (file_id,))
            else:
                cursor.execute("SELECT * FROM chunks WHERE file_id = %s AND (chunk_type != 'parity' OR chunk_type IS NULL) ORDER BY sequence", (file_id,))
            result = cursor.fetchall()
        return result

    def list_files(self):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM files")
            result = cursor.fetchall()
        return result

    def update_chunk_cdn_url(self, chunk_id, cdn_url):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE chunks SET cdn_url = %s WHERE id = %s", (cdn_url, chunk_id))
            conn.commit()

    def delete_file(self, filename):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM files WHERE filename = %s", (filename,))
            conn.commit()

    def delete_file_by_id(self, file_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM files WHERE id = %s", (file_id,))
            conn.commit()

    def delete_chunks(self, file_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM chunks WHERE file_id = %s", (file_id,))
            conn.commit()

    def delete_chunks_after(self, file_id, sequence):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM chunks WHERE file_id = %s AND sequence >= %s", (file_id, sequence))
            conn.commit()

    def delete_folder(self, folder_path):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            prefix = folder_path + "/"
            like_prefix = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            cursor.execute("DELETE FROM files WHERE filename LIKE %s", (like_prefix,))
            conn.commit()

    def update_file_size(self, file_id, size):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE files SET size = %s WHERE id = %s", (size, file_id))
            conn.commit()

    def rename_file(self, old_filename, new_filename):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE files SET filename = %s WHERE filename = %s", (new_filename, old_filename))
            conn.commit()

    def rename_folder(self, old_folder_path, new_folder_path):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            # Ensure we match exactly the folder prefix
            # old_folder_path = "folder" -> matches "folder/..."
            prefix = old_folder_path + "/"
            new_prefix = new_folder_path + "/"
            like_prefix = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        
            # MySQL/TiDB REPLACE function or CONCAT
            cursor.execute("""
                UPDATE files 
                SET filename = CONCAT(%s, SUBSTRING(filename, CHAR_LENGTH(%s) + 1))
                WHERE filename LIKE %s
            """, (new_prefix, prefix, like_prefix))
            conn.commit()
    def is_folder(self, folder_path):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            prefix = folder_path + "/"
            like_prefix = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            cursor.execute("SELECT 1 FROM files WHERE filename LIKE %s LIMIT 1", (like_prefix,))
            result = cursor.fetchone()
        return result is not None

    def update_mode(self, filename, mode):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE files SET mode = %s WHERE filename = %s", (mode, filename))

    def update_chown(self, filename, uid, gid):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE files SET uid = %s, gid = %s WHERE filename = %s", (uid, gid, filename))

    def update_utimens(self, filename, atime, mtime):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE files SET atime = %s, mtime = %s WHERE filename = %s", (atime, mtime, filename))

    # --- Accounts and Settings ---
    def add_account(self, label, api_key, user_id, auth_token):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO accounts (label, api_key, user_id, auth_token) VALUES (%s, %s, %s, %s)",
                (label, api_key, user_id, auth_token)
            )
            return cursor.lastrowid

    def get_accounts(self):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM accounts ORDER BY id ASC")
            return cursor.fetchall()

    def get_healthy_accounts(self):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM accounts WHERE status = 'healthy' ORDER BY id ASC")
            return cursor.fetchall()

    def update_account_status(self, account_id, status):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("UPDATE accounts SET status = %s WHERE id = %s", (status, account_id))

    def remove_account(self, account_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute("DELETE FROM accounts WHERE id = %s", (account_id,))

    def get_setting(self, key_name, default=None):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT value FROM app_settings WHERE key_name = %s", (key_name,))
            result = cursor.fetchone()
            if result:
                return result['value']
            return default

    def set_setting(self, key_name, value):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO app_settings (key_name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = %s",
                (key_name, value, value)
            )

    # --- RAID ---
    def add_raid_stripe(self, file_id, stripe_index):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO raid_stripes (file_id, stripe_index) VALUES (%s, %s)",
                (file_id, stripe_index)
            )
            return cursor.lastrowid

    def add_stripe_member(self, stripe_id, chunk_id, role, account_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO raid_stripe_members (stripe_id, chunk_id, role, account_id) VALUES (%s, %s, %s, %s)",
                (stripe_id, chunk_id, role, account_id)
            )

    def get_stripe_for_chunk(self, chunk_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT stripe_id FROM raid_stripe_members WHERE chunk_id = %s", (chunk_id,))
            result = cursor.fetchone()
            if not result:
                return None
            
            stripe_id = result['stripe_id']
            cursor.execute("SELECT * FROM raid_stripes WHERE id = %s", (stripe_id,))
            stripe = cursor.fetchone()
            
            cursor.execute("SELECT * FROM raid_stripe_members WHERE stripe_id = %s", (stripe_id,))
            members = cursor.fetchall()
            
            stripe['members'] = members
            return stripe

    def get_stripes_for_file(self, file_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM raid_stripes WHERE file_id = %s ORDER BY stripe_index", (file_id,))
            stripes = cursor.fetchall()
            for stripe in stripes:
                cursor.execute("SELECT * FROM raid_stripe_members WHERE stripe_id = %s", (stripe['id'],))
                stripe['members'] = cursor.fetchall()
            return stripes

    def get_chunks_on_account(self, account_id):
        with closing(self.get_connection()) as conn, closing(conn.cursor(dictionary=True)) as cursor:
            cursor.execute("SELECT * FROM chunks WHERE account_id = %s", (account_id,))
            return cursor.fetchall()

