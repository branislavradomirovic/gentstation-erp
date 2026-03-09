import sqlite3
import os

def setup_database():
    db_file = 'company.db'
    
    # 1. Remove the old database to avoid "missing column" errors
    if os.path.exists(db_file):
        os.remove(db_file)
        print("🗑️ Old database deleted.")

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")

    # 2. Create REGIONS (Simplified with email)
    cursor.execute('''
    CREATE TABLE regions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE
    )''')

    # 3. Create STATIONS
    cursor.execute('''
    CREATE TABLE stations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        region_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        phone TEXT,
        physical_address TEXT,
        lat REAL,
        lon REAL,
        established TEXT,
        FOREIGN KEY (region_id) REFERENCES regions (id)
    )''')

    # 4. Create EMPLOYEES (Role-Based)
    cursor.execute('''
    CREATE TABLE employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        surname TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT,
        role TEXT NOT NULL, 
        station_id INTEGER,
        region_id INTEGER,
        chat_id TEXT,
        FOREIGN KEY (station_id) REFERENCES stations (id),
        FOREIGN KEY (region_id) REFERENCES regions (id)
    )''')

    # 5. Create DIRECTOR_REGIONS (For Region Directors overseeing multiple)
    cursor.execute('''
    CREATE TABLE director_regions (
        employee_id INTEGER,
        region_id INTEGER,
        PRIMARY KEY (employee_id, region_id),
        FOREIGN KEY (employee_id) REFERENCES employees (id),
        FOREIGN KEY (region_id) REFERENCES regions (id)
    )''')

    conn.commit()
    conn.close()
    print("✅ New database 'company.db' initialized successfully with all columns!")

if __name__ == "__main__":
    setup_database()