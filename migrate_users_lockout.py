import sqlite3
from pathlib import Path

# Path to the database file
DB_PATH = Path(__file__).resolve().parent / "company.db"

def run_migration():
    """
    Adds 'failed_attempts' and 'locked_until' columns to 'users' table.
    """
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    print(f"🔧 Starting migration on: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    
    columns_to_add = [
        ("failed_attempts", "INTEGER DEFAULT 0"),
        ("locked_until", "TEXT")
    ]

    try:
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type};")
                print(f"   ✅ Added column '{col_name}'")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print(f"   ℹ️ Column '{col_name}' already exists.")
                else:
                    print(f"   ❌ Failed to add '{col_name}': {e}")
        conn.commit()
        print("✅ Migration completed.")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    run_migration()
