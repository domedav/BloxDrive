import mysql.connector
from mysql.connector import Error
import config

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
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {self.database}")
            cursor.close()
            conn.close()

            # Now connect to the database to create tables
            conn = self.get_connection()
            cursor = conn.cursor()

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

            cursor.close()
            conn.close()
            print("Database initialized successfully.")
        except Error as e:
            print(f"Error initializing database: {e}")
            print("Please ensure MariaDB/MySQL is running and credentials in config.py are correct.")

    def add_file(self, filename, size):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO files (filename, size) VALUES (%s, %s)", (filename, size))
        file_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return file_id

    def add_chunk(self, file_id, sequence, asset_id, size, cdn_url=None, chunk_hash=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chunks (file_id, sequence, asset_id, size, cdn_url, chunk_hash) VALUES (%s, %s, %s, %s, %s, %s)",
            (file_id, sequence, asset_id, size, cdn_url, chunk_hash)
        )
        cursor.close()
        conn.close()

    def get_file(self, filename):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM files WHERE filename = %s", (filename,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def get_chunk_by_hash(self, chunk_hash):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM chunks WHERE chunk_hash = %s LIMIT 1", (chunk_hash,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result

    def get_chunks(self, file_id):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM chunks WHERE file_id = %s ORDER BY sequence", (file_id,))
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result

    def list_files(self):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM files")
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return result

    def update_chunk_cdn_url(self, chunk_id, cdn_url):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE chunks SET cdn_url = %s WHERE id = %s", (cdn_url, chunk_id))
        cursor.close()
        conn.close()

    def delete_file(self, filename):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM files WHERE filename = %s", (filename,))
        cursor.close()
        conn.close()

    def update_file_size(self, file_id, size):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE files SET size = %s WHERE id = %s", (size, file_id))
        cursor.close()
        conn.close()
