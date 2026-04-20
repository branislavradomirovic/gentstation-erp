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
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "gentstation")
DB_USER = os.getenv("DB_USER", "gentstation_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password")
_RESOLVED_DB_HOST = None
_SCHEMA_INITIALIZED = False
logger = logging.getLogger("gentstation.database")


def _connect(host: str):
    return psycopg2.connect(
        host=host,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=5,
    )


def _translate_placeholders(query: str) -> str:
    """
    Allow legacy SQLite-style `?` placeholders to keep older pages working.
    PostgreSQL still uses `%s`, so we only translate when the query does not
    already contain psycopg2-style placeholders.
    """
    if "?" in query and "%s" not in query:
        return query.replace("?", "%s")
    return query


class CompatCursor:
    """
    Small adapter that makes psycopg2 cursors behave more like sqlite3 cursors.

    This keeps the existing Streamlit pages working while we migrate them one
    module at a time to native PostgreSQL style.
    """

    def __init__(self, connection, cursor):
        self._connection = connection
        self._cursor = cursor
        self._lastrowid = None

    def execute(self, query, params=None):
        query = _translate_placeholders(query)
        if params is None:
            self._cursor.execute(query)
        else:
            self._cursor.execute(query, params)

        self._lastrowid = None
        lowered = query.lstrip().lower()
        if lowered.startswith("insert") and "returning" not in lowered:
            probe = None
            try:
                probe = self._connection.cursor()
                probe.execute("SELECT LASTVAL()")
                row = probe.fetchone()
                if row:
                    self._lastrowid = row[0]
            except Exception:
                self._lastrowid = None
            finally:
                try:
                    if probe is not None:
                        probe.close()
                except Exception:
                    pass

        return self

    def executemany(self, query, param_list):
        query = _translate_placeholders(query)
        self._cursor.executemany(query, param_list)
        return self

    @property
    def lastrowid(self):
        return self._lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class CompatConnection:
    """Adapter that exposes sqlite-like convenience methods on psycopg2."""

    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        return CompatCursor(self, self._conn.cursor(*args, **kwargs))

    def execute(self, query, params=None):
        return self.cursor().execute(query, params)

    def executemany(self, query, param_list):
        return self.cursor().executemany(query, param_list)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

class DatabaseConnection:
    """PostgreSQL connection manager with connection pooling support."""
    
    _connection = None
    
    @staticmethod
    def get_connection():
        """Get a database connection (singleton pattern for simplicity)."""
        global _RESOLVED_DB_HOST
        try:
            conn = _connect(DB_HOST)
            _RESOLVED_DB_HOST = DB_HOST
            return conn
        except psycopg2.Error as e:
            # Local development often runs Streamlit outside Docker, where the
            # `postgres` service name is not resolvable. Fall back to localhost
            # automatically in that case so the same .env can serve both modes.
            if DB_HOST == "postgres":
                try:
                    if _RESOLVED_DB_HOST != "localhost":
                        logger.debug("DB_HOST=postgres not reachable; retrying with localhost for local development.")
                    _RESOLVED_DB_HOST = "localhost"
                    return _connect("localhost")
                except psycopg2.Error as fallback_error:
                    logger.error("Database connection failed: %s", fallback_error)
                    raise

            logger.error("Database connection failed: %s", e)
            raise

def get_connection():
    """Wrapper function for backward compatibility."""
    global _SCHEMA_INITIALIZED
    conn = CompatConnection(DatabaseConnection.get_connection())
    # Create tables if they don't exist, but only once per process to avoid
    # repeated noisy logs on every Streamlit rerun.
    if not _SCHEMA_INITIALIZED:
        ensure_schema(conn)
        _SCHEMA_INITIALIZED = True
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

        # Employee shift logs table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS employee_shifts (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
            station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL,
            shift_type VARCHAR(50) DEFAULT 'standard',
            scheduled_start_at TIMESTAMP,
            scheduled_end_at TIMESTAMP,
            clock_in_at TIMESTAMP,
            clock_out_at TIMESTAMP,
            shift_started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            shift_ended_at TIMESTAMP,
            status VARCHAR(50) DEFAULT 'active',
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS shift_type VARCHAR(50) DEFAULT 'standard';
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS scheduled_start_at TIMESTAMP;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS scheduled_end_at TIMESTAMP;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS clock_in_at TIMESTAMP;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS clock_out_at TIMESTAMP;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS break_started_at TIMESTAMP;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS break_ended_at TIMESTAMP;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS break_duration_minutes INTEGER DEFAULT 15;
        """)
        cursor.execute("""
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS is_on_break BOOLEAN DEFAULT FALSE;
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
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_employee_id
        ON employee_shifts(employee_id);
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_status
        ON employee_shifts(status);
        """)

        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_started_at
        ON employee_shifts(shift_started_at);
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_scheduled_start_at
        ON employee_shifts(scheduled_start_at);
        """)
        cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_station_id
        ON employee_shifts(station_id);
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

        def sync_serial_sequence(table_name: str, column_name: str = "id"):
            seq_row = cursor.execute(
                "SELECT pg_get_serial_sequence(%s, %s)",
                (table_name, column_name),
            ).fetchone()
            sequence_name = seq_row[0] if seq_row else None
            if not sequence_name:
                return

            max_row = cursor.execute(
                f'SELECT COALESCE(MAX("{column_name}"), 0) FROM "{table_name}"'
            ).fetchone()
            max_id = int(max_row[0] or 0) if max_row else 0
            if max_id > 0:
                cursor.execute(
                    "SELECT setval(%s, %s, true)",
                    (sequence_name, max_id),
                )
            else:
                cursor.execute(
                    "SELECT setval(%s, 1, false)",
                    (sequence_name,),
                )

        for table_name in (
            "regions",
            "stations",
            "employees",
            "users",
            "activity_logs",
            "submissions",
            "employee_shifts",
            "ai_alerts",
            "ai_jobs",
            "ai_reports",
        ):
            sync_serial_sequence(table_name)

        cursor.execute("""
        UPDATE employee_shifts es
        SET station_id = e.station_id
        FROM employees e
        WHERE es.station_id IS NULL
          AND es.employee_id = e.id
          AND e.station_id IS NOT NULL;
        """)
        cursor.execute("""
        UPDATE employee_shifts
        SET scheduled_start_at = COALESCE(scheduled_start_at, shift_started_at),
            scheduled_end_at = COALESCE(scheduled_end_at, shift_ended_at),
            clock_in_at = COALESCE(clock_in_at, shift_started_at),
            clock_out_at = COALESCE(clock_out_at, shift_ended_at),
            shift_type = COALESCE(shift_type, 'standard')
        WHERE scheduled_start_at IS NULL
           OR scheduled_end_at IS NULL
           OR clock_in_at IS NULL
           OR clock_out_at IS NULL;
        """)
        
        conn.commit()
        logger.debug("Database schema initialized successfully")
        
    except psycopg2.Error as e:
        conn.rollback()
        logger.error("Schema initialization error: %s", e)
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
        logger.error("Query execution error: %s", e)
        raise
    finally:
        cursor.close()
        conn.close()

def close_connection(conn):
    """Close database connection."""
    if conn:
        conn.close()
