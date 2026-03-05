import sqlite3

def update_db_schema():
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()
    try:
        # 1. Ensure the submissions table exists (or rename report_logs if necessary)
        # Here we assume 'submissions' is our primary collection table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER,
                chat_id INTEGER,
                video_path TEXT,
                role TEXT,
                timestamp DATETIME,
                processed INTEGER DEFAULT 0
            )
        """)
        
        # 2. Add the processed column if the table already existed but lacked it
        try:
            cursor.execute("ALTER TABLE submissions ADD COLUMN processed INTEGER DEFAULT 0")
            print("✅ Column 'processed' added to submissions.")
        except sqlite3.OperationalError:
            print("ℹ️ Column 'processed' already exists.")
            
        conn.commit()
    except Exception as e:
        print(f"❌ Database update failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_db_schema()