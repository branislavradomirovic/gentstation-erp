import sqlite3

def update_db_schema():
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()
    try:
        # 1. Kreiranje / Provera tabele submissions
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER,
                chat_id INTEGER,
                video_path TEXT,
                role TEXT,
                timestamp DATETIME,
                processed INTEGER DEFAULT 0,
                FOREIGN KEY (station_id) REFERENCES stations(id)
            )
        """)
        
        # 2. Kreiranje tabele za Activity Logs (NOVO)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT,
                action TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Provera i dodavanje 'processed' kolone u submissions
        try:
            cursor.execute("ALTER TABLE submissions ADD COLUMN processed INTEGER DEFAULT 0")
            print("✅ Column 'processed' added to submissions.")
        except sqlite3.OperationalError:
            print("ℹ️ Column 'processed' already exists.")
            
        conn.commit()
        print("🚀 Database schema is up to date.")
        
    except Exception as e:
        print(f"❌ Database update failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_db_schema()