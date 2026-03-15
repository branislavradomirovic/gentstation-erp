import sqlite3
from pathlib import Path

# Path to the database file
DB_PATH = Path(__file__).resolve().parent / "company.db"

def run_migration():
    """
    Adds 'ip_address' column to 'activity_logs' table if it doesn't exist.
    """
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    print(f"🔧 Starting migration on: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    
    try:
        conn.execute("ALTER TABLE activity_logs ADD COLUMN ip_address TEXT;")
        conn.commit()
        print("✅ Migration successful: Added 'ip_address' to 'activity_logs'.")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("ℹ️ Column 'ip_address' already exists. No action needed.")
        else:
            print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
