import sqlite3

def update_db_schema():
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()
    try:
        # Kreiranje tabele za Activity Logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT,
    report_role TEXT,
    station_id INTEGER,
    region_id INTEGER,
    report_text TEXT,
    sentiment REAL,
    safety_score INTEGER,
    cleanliness_score INTEGER,
    staff_score INTEGER,
    efficiency_score INTEGER,
    customer_score INTEGER,
    incidents_json TEXT,
    trend TEXT
)
        """)
            
        conn.commit()
        print("✅ Baza je uspešno ažurirana. Tabela 'activity_logs' je spremna.")
    except Exception as e:
        print(f"❌ Greška: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_db_schema()