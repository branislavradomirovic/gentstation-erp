#!/usr/bin/env python3
"""
Migrate the legacy SQLite dataset into the local PostgreSQL database.

This script restores the historical data that was previously stored in
`company.db` and imports it into the current PostgreSQL schema used by the app.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

import bcrypt
import psycopg2
from psycopg2 import sql

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.database import CompatConnection, ensure_schema


LEGACY_DB = PROJECT_ROOT / "company.db"
DEFAULT_ADMIN_USERNAME = "admin"

TABLE_ORDER = [
    "regions",
    "stations",
    "employees",
    "director_regions",
    "users",
    "sessions",
    "activity_logs",
    "ai_alerts",
    "ai_jobs",
    "ai_reports",
    "submissions",
    "system_settings",
]

BOOL_COLUMNS = {
    "users": {"is_active", "dark_mode_enabled"},
}


def _env(name: str, default: str = "") -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _ensure_legacy_source() -> Path:
    if LEGACY_DB.exists() and LEGACY_DB.stat().st_size > 0:
        return LEGACY_DB

    tmp_dir = Path(tempfile.mkdtemp(prefix="gentstation_legacy_"))
    tmp_db = tmp_dir / "company.db"
    with tmp_db.open("wb") as handle:
        subprocess.run(
            ["git", "show", "HEAD:company.db"],
            cwd=str(PROJECT_ROOT),
            check=True,
            stdout=handle,
        )
    return tmp_db


def _pg_conn():
    return psycopg2.connect(
        host=_env("DB_HOST", "localhost"),
        port=int(_env("DB_PORT", "5432")),
        database=_env("DB_NAME", "gentstation"),
        user=_env("DB_USER", "gentstation_user"),
        password=_env("DB_PASSWORD", ""),
    )


def _table_columns_sqlite(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _table_columns_postgres(conn, table: str) -> List[str]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row[0] for row in cur.fetchall()]


def _coerce_value(table: str, column: str, value):
    if value is None:
        return None
    if table in BOOL_COLUMNS and column in BOOL_COLUMNS[table]:
        return bool(value)
    return value


def _fetch_rows(sqlite_conn: sqlite3.Connection, table: str) -> Tuple[List[str], List[Tuple]]:
    cur = sqlite_conn.execute(f'SELECT * FROM "{table}"')
    columns = [desc[0] for desc in cur.description]
    rows = cur.fetchall()
    return columns, rows


def _truncate_tables(pg_conn, tables: Sequence[str]):
    cur = pg_conn.cursor()
    quoted = sql.SQL(", ").join(sql.Identifier(table) for table in tables)
    cur.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(quoted))
    pg_conn.commit()


def _import_table(sqlite_conn: sqlite3.Connection, pg_conn, table: str):
    try:
        source_columns, rows = _fetch_rows(sqlite_conn, table)
    except sqlite3.OperationalError:
        return 0

    if not rows:
        return 0

    dest_columns = _table_columns_postgres(pg_conn, table)
    available_columns = [col for col in source_columns if col in dest_columns]
    if not available_columns:
        return 0

    insert_sql = sql.SQL(
        "INSERT INTO {} ({}) VALUES ({})"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(col) for col in available_columns),
        sql.SQL(", ").join(sql.Placeholder() for _ in available_columns),
    )

    payload = []
    src_index = {name: idx for idx, name in enumerate(source_columns)}
    for row in rows:
        payload.append(
            tuple(
                _coerce_value(table, column, row[src_index[column]])
                for column in available_columns
            )
        )

    cur = pg_conn.cursor()
    cur.executemany(insert_sql, payload)
    pg_conn.commit()
    return len(payload)


def _reset_admin_password(pg_conn, username: str, new_password: str) -> bool:
    if not new_password:
        return False

    password_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
    cur = pg_conn.cursor()
    cur.execute(
        """
        UPDATE users
        SET password_hash = %s,
            failed_attempts = 0,
            locked_until = NULL,
            is_active = TRUE,
            updated_at = CURRENT_TIMESTAMP
        WHERE username = %s
        """,
        (password_hash, username),
    )
    pg_conn.commit()
    return cur.rowcount > 0


def main():
    parser = argparse.ArgumentParser(description="Restore legacy SQLite data into local PostgreSQL.")
    parser.add_argument(
        "--admin-password",
        default=os.getenv("GENTSTATION_ADMIN_PASSWORD", ""),
        help="Optional temporary password to set for the legacy admin user after import.",
    )
    parser.add_argument(
        "--admin-username",
        default=os.getenv("GENTSTATION_ADMIN_USERNAME", DEFAULT_ADMIN_USERNAME),
        help="Username of the legacy admin account to reset when --admin-password is provided.",
    )
    args = parser.parse_args()

    source_db = _ensure_legacy_source()
    print(f"Using legacy source database: {source_db}")

    sqlite_conn = sqlite3.connect(str(source_db))
    sqlite_conn.row_factory = sqlite3.Row

    pg_conn = _pg_conn()
    pg_wrapper = CompatConnection(pg_conn)
    ensure_schema(pg_wrapper)

    _truncate_tables(
        pg_conn,
        [
            "director_regions",
            "sessions",
            "activity_logs",
            "ai_alerts",
            "ai_jobs",
            "ai_reports",
            "submissions",
            "employees",
            "stations",
            "regions",
            "users",
            "system_settings",
        ],
    )

    total = 0
    for table in TABLE_ORDER:
        count = _import_table(sqlite_conn, pg_conn, table)
        print(f"Imported {count} rows from {table}")
        total += count

    if args.admin_password:
        if _reset_admin_password(pg_conn, args.admin_username, args.admin_password):
            print(f"Reset password for user '{args.admin_username}'")
        else:
            print(f"WARNING: Could not find user '{args.admin_username}' to reset password")

    ensure_schema(pg_wrapper)
    pg_conn.close()
    sqlite_conn.close()

    print(f"Migration complete. Total rows imported: {total}")


if __name__ == "__main__":
    main()
