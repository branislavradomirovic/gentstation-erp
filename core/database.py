"""
PostgreSQL Database Module for GentStationAI

Handles all database connections and schema management for PostgreSQL.
Supports both local development and Docker deployment.
"""

import os
import logging
import time
import urllib.parse
import psycopg2, sqlalchemy
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from psycopg2 import pool
from core.models import Base
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("SQLALCHEMY_DATABASE_URL")
)
logger = logging.getLogger("gentstation.database")
# Safe diagnostic: log whether DATABASE_URL is present (do not log its value)
logger.info("DATABASE_URL present: %s", bool(DATABASE_URL))
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "gentstation")
DB_USER = os.getenv("DB_USER", "gentstation_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secure_password")
DB_SSLMODE = os.getenv("DB_SSLMODE")
_RESOLVED_DB_HOST = None
_SCHEMA_INITIALIZED = False
_ENGINE = None
_SESSION_FACTORY = None
_START_TIME = time.time()
SLOW_QUERY_THRESHOLD = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", "1.0"))
logger = logging.getLogger("gentstation.database")


def _assert_safe_database_config():
    production_like = bool(os.getenv("HF_SPACE_ID")) or os.getenv(
        "APP_ENV", ""
    ).strip().lower() in {"production", "prod"}
    if not production_like:
        return

    if not DATABASE_URL and DB_PASSWORD in {"", "secure_password", "change_me_for_local_dev"}:
        raise RuntimeError(
            "Production database credentials are not configured. Set DATABASE_URL "
            "or provide DB_HOST/DB_USER/DB_PASSWORD as Hugging Face Space secrets."
        )


def get_sqlalchemy_url():
    """Constructs the SQLAlchemy connection string."""
    if DATABASE_URL:
        # Non-secret diagnostic: note that DATABASE_URL is present and will be used.
        logger.info("get_sqlalchemy_url: using DATABASE_URL (present=%s)", True)
        if DATABASE_URL.startswith("postgres://"):
            return DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
        if DATABASE_URL.startswith("postgresql://"):
            return DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
        return DATABASE_URL

    host = _RESOLVED_DB_HOST or DB_HOST
    encoded_password = urllib.parse.quote_plus(DB_PASSWORD)
    url = f"postgresql+psycopg2://{DB_USER}:{encoded_password}@{host}:{DB_PORT}/{DB_NAME}"
    if DB_SSLMODE:
        url += f"?sslmode={urllib.parse.quote_plus(DB_SSLMODE)}"
    return url


def _connect(host: str):
    if DATABASE_URL:
        kwargs = {"connect_timeout": 5}
        if DB_SSLMODE and "sslmode=" not in DATABASE_URL:
            kwargs["sslmode"] = DB_SSLMODE
        return psycopg2.connect(DATABASE_URL, **kwargs)

    kwargs = {
        "host": host,
        "port": DB_PORT,
        "database": DB_NAME,
        "user": DB_USER,
        "password": DB_PASSWORD,
        "connect_timeout": 5,
    }
    if DB_SSLMODE:
        kwargs["sslmode"] = DB_SSLMODE
    return psycopg2.connect(
        **kwargs,
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
        start_time = time.time()
        try:
            if params is None:
                self._cursor.execute(query)
            else:
                self._cursor.execute(query, params)
        finally:
            duration = time.time() - start_time
            if duration > SLOW_QUERY_THRESHOLD:
                query_snippet = query.strip().replace("\n", " ")
                logger.warning(
                    "DB SLOW QUERY (%.2fs): %s | Params: %s",
                    duration,
                    query_snippet,
                    params,
                )
                # Persist slow query to database (avoid logging the log itself)
                if "INSERT INTO slow_query_logs" not in query:
                    try:
                        # Use a savepoint so slow-log write failures do not poison
                        # the caller transaction with "current transaction is aborted".
                        with self._connection._conn.cursor() as log_cur:
                            log_cur.execute("SAVEPOINT slow_query_log_sp")
                            log_cur.execute(
                                "INSERT INTO slow_query_logs (query_text, duration_seconds, params) VALUES (%s, %s, %s)",
                                (query_snippet, duration, str(params)),
                            )
                            log_cur.execute("RELEASE SAVEPOINT slow_query_log_sp")
                    except Exception:
                        try:
                            with self._connection._conn.cursor() as log_cur:
                                log_cur.execute(
                                    "ROLLBACK TO SAVEPOINT slow_query_log_sp"
                                )
                                log_cur.execute("RELEASE SAVEPOINT slow_query_log_sp")
                        except Exception:
                            pass

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

    def __init__(self, conn, pool=None):
        self._conn = conn
        self._pool = pool

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
        if self._pool is not None:
            self._pool.putconn(self._conn)
        else:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


class DatabaseConnection:
    """PostgreSQL connection manager with connection pooling support."""

    _connection = None

    @staticmethod
    def get_connection():
        """Get a database engine and connection (singleton pattern)."""
        global _RESOLVED_DB_HOST, _ENGINE

        if _ENGINE is None:
            _assert_safe_database_config()
            # Resolve host first
            host_to_use = DB_HOST
            try:
                test_conn = _connect(DB_HOST)
                test_conn.close()
                _RESOLVED_DB_HOST = DB_HOST
            except (psycopg2.Error, Exception):
                if DB_HOST == "postgres":
                    try:
                        test_conn = _connect("localhost")
                        test_conn.close()
                        _RESOLVED_DB_HOST = "localhost"
                        host_to_use = "localhost"
                    except (psycopg2.Error, Exception) as e:
                        logger.error("Database connection failed: %s", e)
                        raise
                else:
                    raise
            # Non-secret diagnostic: report which host will be used and whether DATABASE_URL exists
            logger.info(
                "Database init: using host_to_use=%s, resolved_host=%s, DATABASE_URL_present=%s",
                host_to_use,
                _RESOLVED_DB_HOST,
                bool(DATABASE_URL),
            )
            # Initialize SQLAlchemy Engine with pooling
            _ENGINE = create_engine(
                get_sqlalchemy_url(),
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True
            )
            logger.info("SQLAlchemy Engine initialized with pooling.")

        if _ENGINE is None:
            raise RuntimeError("Failed to initialize SQLAlchemy Engine.")

        return _ENGINE.raw_connection()

@contextmanager
def get_session() -> Session:
    """Provide a transactional scope around a series of operations."""
    global _SESSION_FACTORY, _ENGINE
    if _ENGINE is None:
        DatabaseConnection.get_connection()
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=_ENGINE)

    session = _SESSION_FACTORY()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_system_uptime():
    """Returns the seconds elapsed since the database module was loaded."""
    global _START_TIME
    return time.time() - _START_TIME


def get_connection(on_retry=None):
    """Wrapper function for backward compatibility."""
    global _SCHEMA_INITIALIZED

    # Increase retries and delay to allow more time for DB startup (e.g., 20 * 5 = 100 seconds)
    max_retries = 20
    retry_delay = 5  # seconds

    for attempt in range(max_retries):
        try:
            # Get raw connection from SQLAlchemy engine
            raw_conn = DatabaseConnection.get_connection()
            # Compatibility adapter to keep existing code working
            conn = CompatConnection(raw_conn)

            # Allow workers to skip schema migrations to avoid cross-process DDL deadlocks.
            skip_schema_init = os.getenv("SKIP_SCHEMA_INIT", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            run_schema_init = os.getenv(
                "RUN_SCHEMA_MIGRATIONS_ON_STARTUP", "1"
            ).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            strict_schema_init = os.getenv(
                "STRICT_SCHEMA_INIT", "1"
            ).strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

            # Create tables if they don't exist, but only once per process to avoid
            # repeated noisy logs on every Streamlit rerun.
            if not _SCHEMA_INITIALIZED and not skip_schema_init and run_schema_init:
                # For now, we still use ensure_schema to handle triggers.
                # In a future update, move triggers to Alembic and use:
                # Base.metadata.create_all(_ENGINE)
                try:
                    ensure_schema(conn)
                except Exception as e:
                    logger.error("Legacy ensure_schema failed: %s", e)
                    if strict_schema_init:
                        raise
                _SCHEMA_INITIALIZED = True
            return conn

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Database connection attempt %d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    e,
                    retry_delay,
                )
                for i in range(retry_delay, 0, -1):
                    if on_retry:
                        on_retry(attempt + 1, max_retries, i, e)
                    time.sleep(1)
            else:
                logger.error(
                    "Database connection failed after %d attempts: %s", max_retries, e
                )
                raise


def test_redis_connection(on_retry=None, timeout=2) -> bool:
    """Test if Redis server is running and responding."""
    # If background workers are disabled or REDIS_URL is not set, skip Redis checks.
    auto_start = os.getenv("AUTO_START_BACKGROUND_WORKERS", "1")
    try:
        auto_start_bool = auto_start.strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        auto_start_bool = True

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not auto_start_bool or not redis_url:
        logger.info("Redis checks disabled (AUTO_START_BACKGROUND_WORKERS=%s, REDIS_URL=%s)", auto_start, bool(redis_url))
        return False

    try:
        import redis
    except ImportError:
        logger.info("Redis library not installed; skipping Redis checks.")
        return False

    max_retries = 5
    retry_delay = 3

    for attempt in range(max_retries):
        try:
            r = redis.from_url(redis_url, socket_connect_timeout=timeout)
            r.ping()
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Redis connection attempt %d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    e,
                    retry_delay,
                )
                for i in range(retry_delay, 0, -1):
                    if on_retry:
                        on_retry(attempt + 1, max_retries, i, e)
                    time.sleep(1)
            else:
                logger.error(
                    "Redis connection failed after %d attempts: %s", max_retries, e
                )
                return False


def get_pool_stats():
    """Returns statistics about the database connection pool."""
    global _ENGINE
    if _ENGINE is None:
        return None
    p = _ENGINE.pool
    # Total capacity is size + max_overflow
    # Default max_overflow is often 10 if not specified
    size = getattr(p, '_size', 10)
    overflow = getattr(p, '_max_overflow', 20)
    total_capacity = size + overflow
    checked_out = p.checkedout()

    usage_pct = (checked_out / total_capacity) * 100 if total_capacity > 0 else 0

    return {
        "size": size,
        "overflow": overflow,
        "total_capacity": total_capacity,
        "checkedin": p.checkedin(),
        "checkedout": checked_out,
        "usage_pct": round(usage_pct, 2)
    }


def check_pool_health():
    """Logs a warning if database pool usage exceeds 90%."""
    stats = get_pool_stats()
    if stats and stats["usage_pct"] >= 90:
        logger.warning(
            "CRITICAL: Database connection pool usage at %s%% (%s/%s)",
            stats["usage_pct"], stats["checkedout"], stats["total_capacity"]
        )

def sync_identity_sequences():
    """
    Generic SQLAlchemy utility to synchronize all IDENTITY sequences
    based on the models defined in core.models.Base.
    """
    with get_session() as session:
        for table_name, table in Base.metadata.tables.items():
            for column in table.columns:
                if isinstance(column.server_default, sqlalchemy.schema.Identity):
                    col_name = column.name
                    try:
                        # Identify current max ID and restart sequence
                        sync_sql = text(f"""
                            DO $$
                            DECLARE
                                max_id integer;
                            BEGIN
                                EXECUTE 'SELECT COALESCE(MAX("{col_name}"), 0) + 1 FROM "{table_name}"' INTO max_id;
                                EXECUTE 'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" RESTART WITH ' || max_id;
                            END $$;
                        """)
                        session.execute(sync_sql)
                        logger.debug(f"Synced sequence for {table_name}.{col_name}")
                    except Exception as e:
                        logger.error(f"Failed to sync sequence for {table_name}: {e}")

def ensure_schema(conn):
    """
    Create all necessary tables and schema for GentStationAI.
    Uses idempotent CREATE TABLE IF NOT EXISTS statements.
    """
    cursor = conn.cursor()

    try:
        # Regions table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS regions (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

        # Stations table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS stations (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
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
        """
        )

        # Users table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            username VARCHAR(255) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE,
            password_hash TEXT NOT NULL,
            role VARCHAR(100) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            name VARCHAR(255),
            surname VARCHAR(255),
            station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL,
            region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL,
            telegram_chat_id VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            failed_attempts INTEGER DEFAULT 0,
            locked_until TIMESTAMP,
            dark_mode_enabled BOOLEAN DEFAULT FALSE,
            force_password_change BOOLEAN DEFAULT FALSE
        );
        """
        )

        # Migration support: Add columns to users table if they are missing from an older version
        cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS surname VARCHAR(255);"
        )
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL;"
        )
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS region_id INTEGER REFERENCES regions(id) ON DELETE SET NULL;"
        )
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(255);"
        )
        cursor.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS force_password_change BOOLEAN DEFAULT FALSE;"
        )
        cursor.execute(
            """
            CREATE OR REPLACE FUNCTION enforce_user_assignment_integrity()
            RETURNS TRIGGER
            AS $$
            DECLARE
                station_region_id INTEGER;
            BEGIN
                IF NEW.role IN ('Employee', 'Gas Station Supervisor', 'Gas Station Manager') THEN
                    IF NEW.station_id IS NULL THEN
                        RAISE EXCEPTION 'Role % requires station_id', NEW.role;
                    END IF;

                    SELECT region_id INTO station_region_id
                    FROM stations
                    WHERE id = NEW.station_id;

                    IF station_region_id IS NULL THEN
                        RAISE EXCEPTION 'Assigned station % must exist and belong to a region', NEW.station_id;
                    END IF;

                    NEW.region_id := station_region_id;
                ELSIF NEW.role = 'Region Manager' THEN
                    IF NEW.region_id IS NULL THEN
                        RAISE EXCEPTION 'Region Manager requires region_id';
                    END IF;
                    NEW.station_id := NULL;
                END IF;

                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        cursor.execute(
            """
            DROP TRIGGER IF EXISTS trg_enforce_user_assignment_integrity ON users;
            CREATE TRIGGER trg_enforce_user_assignment_integrity
            BEFORE INSERT OR UPDATE ON users
            FOR EACH ROW
            EXECUTE FUNCTION enforce_user_assignment_integrity();
            """
        )

        # Cleanup: Remove the old employees table if it still exists
        cursor.execute("DROP TABLE IF EXISTS employees CASCADE;")

        # Sessions table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS sessions (
            token VARCHAR(500) PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        );
        """
        )

        # Activity logs table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_name VARCHAR(255),
            action VARCHAR(255),
            details TEXT,
            ip_address VARCHAR(45)
        );
        """
        )

        # Submissions table (video/audio reports)
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            station_id INTEGER REFERENCES stations(id) ON DELETE CASCADE,
            employee_id INTEGER REFERENCES users(id) ON DELETE SET NULL, -- Renamed from employee_id to user_id in logic, but keeping column name for now
            video_path TEXT,
            audio_path TEXT,
            role VARCHAR(100),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed INTEGER DEFAULT 0,
            status VARCHAR(50) DEFAULT 'pending',
            processing_started_ts TIMESTAMP,
            retry_count INTEGER DEFAULT 0,
            processed_ts TIMESTAMP,
            data_json JSONB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

        cursor.execute(
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS file_unique_id TEXT;"
        )
        cursor.execute(
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';"
        )
        cursor.execute(
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS processing_started_ts TIMESTAMP;"
        )
        cursor.execute(
            "ALTER TABLE submissions ADD COLUMN IF NOT EXISTS error_message TEXT;"
        )
        # Drop old employee_id if it exists and is not referencing users.id
        # This is a complex migration, for simplicity we assume it's either new or will be handled manually if issues arise.
        # For a real migration, you'd need to copy data from employees to users first.

        # Employee shift logs table
        cursor.execute(
            """
        ALTER TABLE submissions ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0;
        """
        )
        cursor.execute(
            """
        ALTER TABLE submissions ADD COLUMN IF NOT EXISTS processed_ts TIMESTAMP;
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS employee_shifts (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            employee_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
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
        """
        )

        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS station_id INTEGER REFERENCES stations(id) ON DELETE SET NULL;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS shift_type VARCHAR(50) DEFAULT 'standard';
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS scheduled_start_at TIMESTAMP;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS scheduled_end_at TIMESTAMP;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS clock_in_at TIMESTAMP;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS clock_out_at TIMESTAMP;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS created_by INTEGER REFERENCES users(id) ON DELETE SET NULL;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS break_started_at TIMESTAMP;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS break_ended_at TIMESTAMP;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS break_duration_minutes INTEGER DEFAULT 15;
        """
        )
        cursor.execute(
            """
        ALTER TABLE employee_shifts
        ADD COLUMN IF NOT EXISTS is_on_break BOOLEAN DEFAULT FALSE;
        """
        )

        # AI Alerts table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS ai_alerts (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            station_id INTEGER REFERENCES stations(id) ON DELETE CASCADE,
            severity VARCHAR(50),
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status VARCHAR(50) DEFAULT 'new',
            resolved_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

        # System settings table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS system_settings (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

        # Redis Health Logs table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS redis_health_logs (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_online BOOLEAN NOT NULL,
            details TEXT
        );
        """
        )

        # AI Inference Latency table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS ai_inference_latency (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            model_name VARCHAR(255),
            latency_seconds DECIMAL(10, 2),
            submission_id INTEGER REFERENCES submissions(id) ON DELETE SET NULL
        );
        """
        )

        # Worker Health Logs table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS worker_health_logs (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            worker_name VARCHAR(50),
            cpu_percent DECIMAL(5, 2),
            memory_mb DECIMAL(10, 2)
        );
        """
        )

        # Slow Query Logs table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS slow_query_logs (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            query_text TEXT,
            duration_seconds DECIMAL(10, 4),
            params TEXT
        );
        """
        )

        # AI Jobs table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS ai_jobs (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
            job_type VARCHAR(100),
            status VARCHAR(50) DEFAULT 'pending',
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        )

        # AI Reports table
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS ai_reports (
            id INTEGER PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
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
        """
        )

        # Create indexes for better query performance
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_submissions_station_id
        ON submissions(station_id);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_submissions_processed
        ON submissions(processed);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_employee_id
        ON employee_shifts(employee_id);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_status
        ON employee_shifts(status);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_started_at
        ON employee_shifts(shift_started_at);
        """
        )
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_scheduled_start_at
        ON employee_shifts(scheduled_start_at);
        """
        )
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_employee_shifts_station_id
        ON employee_shifts(station_id);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_station_id
        ON ai_alerts(station_id);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_ai_alerts_created_at
        ON ai_alerts(created_at);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_activity_logs_timestamp
        ON activity_logs(timestamp);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_users_username
        ON users(username);
        """
        )
        cursor.execute(
            """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_users_telegram_chat_id_not_null
        ON users(telegram_chat_id)
        WHERE telegram_chat_id IS NOT NULL;
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_ai_jobs_status
        ON ai_jobs(status);
        """
        )

        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_ai_reports_station_id
        ON ai_reports(station_id);
        """
        )
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_redis_health_logs_timestamp
        ON redis_health_logs(timestamp);
        """
        )
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_ai_latency_timestamp
        ON ai_inference_latency(timestamp);
        """
        )
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_worker_health_timestamp
        ON worker_health_logs(timestamp);
        """
        )
        cursor.execute(
            """
        CREATE INDEX IF NOT EXISTS idx_slow_queries_timestamp
        ON slow_query_logs(timestamp);
        """
        )

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
            "users",
            "activity_logs",
            "submissions",
            "employee_shifts",
            "ai_alerts",
            "ai_jobs",
            "ai_reports",
            "redis_health_logs",
            "ai_inference_latency",
            "worker_health_logs",
            "slow_query_logs",
        ):
            sync_serial_sequence(table_name)

        cursor.execute(
            """
        UPDATE employee_shifts es -- Update station_id in shifts from the new users table
        SET station_id = u.station_id
        FROM users u
        WHERE es.station_id IS NULL
          AND es.employee_id = u.id
          AND u.station_id IS NOT NULL;
        """
        )
        cursor.execute(
            """
        UPDATE employee_shifts -- Ensure scheduled times are set if missing
        SET scheduled_start_at = COALESCE(scheduled_start_at, shift_started_at),
            scheduled_end_at = COALESCE(scheduled_end_at, shift_ended_at),
            clock_in_at = COALESCE(clock_in_at, shift_started_at),
            clock_out_at = COALESCE(clock_out_at, shift_ended_at),
            shift_type = COALESCE(shift_type, 'standard')
        WHERE scheduled_start_at IS NULL
           OR scheduled_end_at IS NULL
           OR clock_in_at IS NULL
           OR clock_out_at IS NULL;
        """
        )

        admin_password = os.getenv("INITIAL_ADMIN_PASSWORD", "").strip()
        if admin_password:
            admin_username = os.getenv("INITIAL_ADMIN_USERNAME", "admin").strip()
            admin_email = os.getenv("INITIAL_ADMIN_EMAIL", "").strip() or None
            admin_name = os.getenv("INITIAL_ADMIN_NAME", "Initial").strip()
            admin_surname = os.getenv("INITIAL_ADMIN_SURNAME", "Admin").strip()
            existing_admin = cursor.execute(
                "SELECT id FROM users WHERE username = %s OR LOWER(email) = LOWER(%s)",
                (admin_username, admin_email or ""),
            ).fetchone()
            if not existing_admin:
                import bcrypt

                password_hash = bcrypt.hashpw(
                    admin_password.encode("utf-8"), bcrypt.gensalt(rounds=12)
                ).decode("utf-8")
                cursor.execute(
                    """
                    INSERT INTO users (
                        username, email, password_hash, role, is_active,
                        force_password_change, name, surname
                    )
                    VALUES (%s, %s, %s, 'General Manager', TRUE, TRUE, %s, %s)
                    """,
                    (
                        admin_username,
                        admin_email,
                        password_hash,
                        admin_name or None,
                        admin_surname or None,
                    ),
                )
                logger.info("Initial General Manager user created: %s", admin_username)

        conn.commit()
        logger.debug("Database schema initialized successfully")

    except Exception as e:
        conn.rollback()
        logger.error("Schema initialization error: %s", e)
        logger.error("Failed to ensure schema: %s", e)
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
    conn = None
    cursor = None
    try:
        conn = get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
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
    except (psycopg2.Error, Exception) as e:
        if conn:
            conn.rollback()
        logger.error("Query execution error: %s", e)
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def close_connection(conn):
    """Close database connection."""
    if conn:
        conn.close()


def fetch_df(conn, query, params=None):
    """
    Utility to execute a query and return a pandas DataFrame.
    Uses the provided connection (CompatConnection or native).
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return pd.DataFrame(rows, columns=columns)
    finally:
        cursor.close()
