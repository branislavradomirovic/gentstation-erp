# gentstation_opus/core/database.py
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "company.db"

def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    ensure_schema(conn)
    return conn

def ensure_schema(conn):
    cursor = conn.cursor()
    # Submissions table (incoming video/audio reports)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id INTEGER,
        employee_id INTEGER,
        video_path TEXT,
        audio_path TEXT,
        role TEXT,
        timestamp TEXT DEFAULT (datetime('now')),
        processed INTEGER DEFAULT 0,
        FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE RESTRICT
    );
    """)

    # AI reports table (structured output)
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
        kpi_json TEXT,
        trend TEXT
    );
    """)

    # employees, regions, stations minimal schema (if missing)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS regions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stations (
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
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        surname TEXT,
        email TEXT UNIQUE,
        password TEXT,
        role TEXT,
        station_id INTEGER,
        region_id INTEGER,
        telegram_chat_id TEXT
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS director_regions (
        employee_id INTEGER,
        region_id INTEGER,
        PRIMARY KEY(employee_id, region_id),
        FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE CASCADE,
        FOREIGN KEY(region_id) REFERENCES regions(id) ON DELETE CASCADE
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT DEFAULT (datetime('now')),
        user_name TEXT,
        action TEXT,
        details TEXT,
        ip_address TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        station_id INTEGER,
        severity TEXT,
        message TEXT,
        created_at TEXT,
        FOREIGN KEY(station_id) REFERENCES stations(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT,
        failed_attempts INTEGER DEFAULT 0,
        locked_until TEXT
    );
    """)

    # Sessions table to store session tokens
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER,
        created_at TEXT,
        expires_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    );
    """)
    conn.commit()