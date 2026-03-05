import sqlite3

def update_db_schema():
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()
    try:
        # Kreiranje tabele za Activity Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT,
                action TEXT,
                details TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Osiguraj da submissions tabela ima 'processed' kolonu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id INTEGER,
                processed INTEGER DEFAULT 0
            )
        """)
        
        try:
            cursor.execute("ALTER TABLE submissions ADD COLUMN processed INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Kolona već postoji
            
        conn.commit()
        print("✅ Baza je uspešno ažurirana. Tabela 'activity_logs' je spremna.")
    except Exception as e:
        print(f"❌ Greška: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_db_schema()