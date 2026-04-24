"""
PostgreSQL Database Module for GentStationAI

Handles all database connections and schema management for PostgreSQL.
Supports both local development and Docker deployment.
"""

import os
import logging
import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "gentstation")
DB_USER = os.getenv("DB_USER", "gentstation_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password")
_RESOLVED_DB_HOST = None
logger = logging.getLogger("gentstation.database_postgres")

class DatabaseConnection:
    """PostgreSQL connection manager with connection pooling support."""
    
    _connection = None
    
    @staticmethod
    def get_connection():
        """Get a database connection (singleton pattern for simplicity)."""
        global _RESOLVED_DB_HOST
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                connect_timeout=5
            )
            _RESOLVED_DB_HOST = DB_HOST
            return conn
        except psycopg2.Error as e:
            if DB_HOST == "postgres":
                try:
                    if _RESOLVED_DB_HOST != "localhost":
                        logger.debug("DB_HOST=postgres not reachable; retrying with localhost for local development.")
                    conn = psycopg2.connect(
                        host="localhost",
                        port=DB_PORT,
                        database=DB_NAME,
                        user=DB_USER,
                        password=DB_PASSWORD,
                        connect_timeout=5
                    )
                    _RESOLVED_DB_HOST = "localhost"
                    return conn
                except psycopg2.Error:
                    pass
            print(f"❌ Database connection failed: {e}")
            raise

def get_connection():
    """Wrapper function for backward compatibility."""
    conn = DatabaseConnection.get_connection()
    # Create tables if they don't exist
    ensure_schema(conn)
    return conn

def ensure_schema(conn):
    """
    Create all necessary tables and schema for GentStationAI.
    Uses idempotent CREATE TABLE IF NOT EXISTS statements.
    """
    cursor = conn.cursor()
    
    try:
        # Regions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS regions (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Stations table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS stations (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
            physical_address TEXT,
            email VARCHAR(255),
            lat DECIMAL(10, 8),
            lon DECIMAL(11, 8),
            category VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Employees table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            surname VARCHAR(255),
            email VARCHAR(255) UNIQUE,
            password TEXT,
            role VARCHAR(100),
            station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL,
            region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
            telegram_chat_id VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Director-Regions mapping table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS director_regions (
            employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
            region_id INTEGER REFERENCES regions(id) ON DELETE CASCADE,
            PRIMARY KEY(employee_id, region_id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Users table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE,
            password_hash TEXT NOT NULL,
            role VARCHAR(100) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            failed_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            dark_mode_enabled BOOLEAN DEFAULT FALSE
        );
        """)
        
        # Sessions table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            token VARCHAR(500) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );
        """)
        
        # Activity logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_name VARCHAR(255),
            action VARCHAR(255),
            details TEXT,
            ip_address VARCHAR(45)
        );
        """)
        
        # Submissions table (video/audio reports)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            station_id INTEGER REFERENCES stations(id) ON DELETE CASCADE,
            employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL,
            video_path TEXT,
            audio_path TEXT,
            role VARCHAR(100),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed INTEGER DEFAULT 0,
            data_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # AI Alerts table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_alerts (
            id SERIAL PRIMARY KEY,
            station_id INTEGER REFERENCES stations(id) ON DELETE CASCADE,
            severity VARCHAR(50),
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'new',
            resolved_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # System settings table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # AI Jobs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_jobs (
            id SERIAL PRIMARY KEY,
            job_type VARCHAR(100),
            status VARCHAR(50) DEFAULT 'pending',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # AI Reports table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_reports (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            report_role VARCHAR(100),
            station_id INTEGER REFERENCES stations(id) ON DELETE CASCADE,
            region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
            report_text TEXT,
            sentiment DECIMAL(4,2),
            safety_score INTEGER,
            cleanliness_score INTEGER,
            staff_score INTEGER,
            efficiency_score INTEGER,
            customer_score INTEGER,
            incidents_json JSONB,
            kpi_json JSONB,
            trend VARCHAR(50),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        
        # Create indexes for better query performance
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_station_id 
        ON submissions(station_id);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_processed 
        ON submissions(processed);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_station_id 
        ON ai_alerts(station_id);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_created_at 
        ON ai_alerts(created_at);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp 
        ON activity_logs(timestamp);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_employees_email 
        ON employees(email);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_username 
        ON users(username);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_jobs_status 
        ON ai_jobs(status);
        """)
        
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_reports_station_id 
        ON ai_reports(station_id);
        """)
        
        conn.commit()
        print("✅ Database schema initialized successfully")
        
    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Schema initialization error: {e}")
        raise

def execute_query(query, params=None, fetch=False):
    """
    Execute a SQL query safely.
    
    Args:
        query: SQL query string
        params: Query parameters (for parameterized queries)
        fetch: If True, return results; if False, return row count
    
    Returns:
        Query results if fetch=True, else row count
    """
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if fetch:
            results = cursor.fetchall()
            return results
        else:
            conn.commit()
            return cursor.rowcount
    except psycopg2.Error as e:
        conn.rollback()
        print(f"❌ Query execution error: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

def close_connection(conn):
    """Close database connection."""
    if conn:
        conn.close()
