import sqlite3
from pathlib import Path

# Path to the database file (assuming this script is in the project root)
DB_PATH = Path(__file__).resolve().parent / "company.db"

def run_migration():
    """
    Migrates the 'stations' table to include ON DELETE SET NULL for the region_id foreign key.
    """
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        return

    print(f"🔧 Starting migration on: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        # 1. Disable Foreign Keys Support temporarily to allow table manipulation
        cursor.execute("PRAGMA foreign_keys=OFF;")
        
        # 2. Begin Transaction
        cursor.execute("BEGIN TRANSACTION;")

        # 3. Rename existing 'stations' table
        print("   Renaming table 'stations' to 'stations_old'...")
        cursor.execute("ALTER TABLE stations RENAME TO stations_old;")

        # 4. Create new 'stations' table with ON DELETE SET NULL constraint
        print("   Creating new 'stations' table with updated schema...")
        cursor.execute("""
        CREATE TABLE stations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            region_id INTEGER,
            physical_address TEXT,
            email TEXT,
            lat REAL,
            lon REAL,
            category TEXT,
            FOREIGN KEY(region_id) REFERENCES regions(id) ON DELETE SET NULL
        );
        """)

        # 5. Copy data from old table to new table
        print("   Copying data...")
        cursor.execute("""
        INSERT INTO stations (id, name, region_id, physical_address, email, lat, lon, category)
        SELECT id, name, region_id, physical_address, email, lat, lon, category
        FROM stations_old;
        """)

        # 6. Drop old table
        print("   Dropping 'stations_old'...")
        cursor.execute("DROP TABLE stations_old;")

        # 7. Commit changes
        conn.commit()
        print("✅ Migration successful: 'stations' table updated to ON DELETE SET NULL.")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        if conn:
            conn.rollback()
            print("   Rolled back changes.")
    finally:
        # Re-enable foreign keys
        if conn:
            cursor.execute("PRAGMA foreign_keys=ON;")
            conn.close()

if __name__ == "__main__":
    run_migration()