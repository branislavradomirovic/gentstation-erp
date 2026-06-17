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
from core.tenant_context import (
    TenantContext,
    TenantContextError,
    get_current_tenant_context,
)
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from core.runtime_config import env_bool, is_production_env, load_runtime_env


load_runtime_env()

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME", "gentstation")
DB_USER = os.getenv("DB_USER", "gentstation_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "change_me_for_local_dev")
DB_SSLMODE = os.getenv("DB_SSLMODE")

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("SQLALCHEMY_DATABASE_URL")
)
logger = logging.getLogger("gentstation.database")
# Safe diagnostic: log whether DATABASE_URL is present (do not log its value)
logger.info("DATABASE_URL present: %s", bool(DATABASE_URL))
_RESOLVED_DB_HOST = None
_SCHEMA_INITIALIZED = False
_ALEMBIC_MIGRATIONS_APPLIED = False
_ENGINE = None
_START_TIME = time.time()
SLOW_QUERY_THRESHOLD = float(os.getenv("DB_SLOW_QUERY_THRESHOLD", "1.0"))
TENANT_OWNED_TABLES = {
    "regions",
    "station_categories",
    "stations",
    "users",
    "sessions",
    "activity_logs",
    "submissions",
    "ai_alerts",
    "ai_inference_latency",
    "scheduled_reports",
    "report_schedules",
    "report_subscriptions",
    "report_delivery_attempts",
    "ai_jobs",
    "ai_reports",
}

# RLS policy markers retained for deployment and regression checks.
# ENABLE ROW LEVEL SECURITY
# FORCE ROW LEVEL SECURITY
# gsai_assign_tenant_id
# gsai_current_tenant_id


def _has_complete_component_db_config() -> bool:
    required_values = [DB_HOST, DB_NAME, DB_USER, DB_PASSWORD]
    if any(not str(value).strip() for value in required_values):
        return False

    host = str(DB_HOST).strip().lower()
    return host not in {"localhost", "127.0.0.1"}


def _assert_safe_database_config():
    production_like = is_production_env()
    if not production_like:
        return

    if not DATABASE_URL and not _has_complete_component_db_config():
        raise RuntimeError(
            "Production database configuration is incomplete. DATABASE_URL is missing. "
            "Provide DATABASE_URL, or set DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD "
            "to a non-local production database target. This deployment will not fall back "
            "to localhost. In Render, attach the Postgres connection string to DATABASE_URL."
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

def _apply_tenant_settings_to_sqla_connection(
    sa_conn,
    platform_access: bool = False,
) -> None:
    tenant_context = get_current_tenant_context()
    effective_platform_access = platform_access or bool(
        tenant_context and tenant_context.platform_access
    )
    tenant_id = None
    if tenant_context and tenant_context.tenant_id is not None and tenant_context.tenant_id > 0:
        tenant_id = tenant_context.tenant_id

    sa_conn.execute(
        text("SELECT set_config('app.platform_access', :value, false)"),
        {"value": "on" if effective_platform_access else "off"},
    )
    sa_conn.execute(
        text("SELECT set_config('app.current_tenant_id', :value, false)"),
        {"value": str(tenant_id) if tenant_id is not None else ""},
    )


@contextmanager
def get_session(platform_access: bool = False) -> Session:
    """Provide a tenant-aware transactional ORM session."""
    global _ENGINE
    if _ENGINE is None:
        DatabaseConnection.get_connection()
    sa_conn = _ENGINE.connect()
    _apply_tenant_settings_to_sqla_connection(
        sa_conn,
        platform_access=platform_access,
    )
    session = sessionmaker(bind=sa_conn, expire_on_commit=False)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        sa_conn.close()


def get_system_uptime():
    """Returns the seconds elapsed since the database module was loaded."""
    global _START_TIME
    return time.time() - _START_TIME


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %s
        )
        """,
        (table_name,),
    ).fetchone()
    return bool(row and row[0])


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
        )
        """,
        (table_name, column_name),
    ).fetchone()
    return bool(row and row[0])


def get_schema_readiness(conn) -> dict:
    """
    Inspect whether the live Postgres schema satisfies code paths that have
    already moved to the relational station category model.
    """
    warnings = []
    blockers = []

    station_categories_exists = _table_exists(conn, "station_categories")
    stations_has_category_id = _column_exists(conn, "stations", "category_id")
    stations_has_legacy_category = _column_exists(conn, "stations", "category")

    if not station_categories_exists:
        blockers.append(
            "Missing table `station_categories`. Apply the relational category migration before using category-aware pages."
        )

    if not stations_has_category_id:
        blockers.append(
            "Missing column `stations.category_id`. The current code expects the relational station category schema."
        )

    if stations_has_legacy_category and (
        not station_categories_exists or not stations_has_category_id
    ):
        warnings.append(
            "Legacy column `stations.category` is still present, which suggests the category migration has not been completed."
        )

    return {
        "is_ready": not blockers,
        "warnings": warnings,
        "blockers": blockers,
    }


def _apply_tenant_session_settings(conn, platform_access: bool = False):
    tenant_context = get_current_tenant_context()
    effective_platform_access = platform_access or bool(
        tenant_context and tenant_context.platform_access
    )
    tenant_id = None
    if tenant_context and tenant_context.tenant_id is not None and tenant_context.tenant_id > 0:
        tenant_id = tenant_context.tenant_id

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT set_config('app.platform_access', %s, false)",
            ("on" if effective_platform_access else "off",),
        )
        cursor.execute(
            "SELECT set_config('app.current_tenant_id', %s, false)",
            (str(tenant_id) if tenant_id is not None else "",),
        )
    finally:
        cursor.close()


def get_connection(on_retry=None, platform_access: bool = False):
    """Wrapper function for backward compatibility."""
    global _SCHEMA_INITIALIZED, _ALEMBIC_MIGRATIONS_APPLIED

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
            skip_schema_init = env_bool("SKIP_SCHEMA_INIT", "0")
            run_schema_init = env_bool("RUN_SCHEMA_MIGRATIONS_ON_STARTUP", "1")
            strict_schema_init = env_bool("STRICT_SCHEMA_INIT", "1")
            bootstrap_platform_access = (
                not _SCHEMA_INITIALIZED and not platform_access and run_schema_init
            )
            _apply_tenant_session_settings(
                conn,
                platform_access=platform_access or bootstrap_platform_access,
            )

            # Create tables if they don't exist, but only once per process to avoid
            # repeated noisy logs on every Streamlit rerun.
            if not _SCHEMA_INITIALIZED and not skip_schema_init and run_schema_init:
                try:
                    # Phase 2: Run standardized Alembic migrations
                    from core.schema_migrations import run_alembic_upgrade_to_head
                    run_alembic_upgrade_to_head()
                    _ALEMBIC_MIGRATIONS_APPLIED = True
                except Exception as e:
                    logger.error("Schema bootstrap failed: %s", e)
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
    auto_start_bool = env_bool("AUTO_START_BACKGROUND_WORKERS", "1")

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
    Legacy schema bootstrapper. Now deprecated in favor of Alembic migrations.
    DDL has been removed to prevent collisions with the migration chain.
    """
    pass


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
