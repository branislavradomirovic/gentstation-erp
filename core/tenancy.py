from __future__ import annotations

import pandas as pd
from typing import Any, Optional
from core.tenant_context import (
    get_current_tenant_context,
    require_current_tenant_context,
    TenantContext
)

def get_current_tenant_id() -> Optional[int]:
    """Safe accessor for the current tenant ID."""
    context = get_current_tenant_context()
    return context.tenant_id if context else None

def require_tenant() -> int:
    """Returns the current tenant ID or raises TenantContextError."""
    return require_current_tenant_context().tenant_id

def fetch_df_scoped(conn, query: str, params: Optional[tuple[Any, ...]] = None) -> pd.DataFrame:
    """
    Executes a query and returns a DataFrame.
    The query is automatically scoped by PostgreSQL RLS based on the active session.
    """
    # This check ensures we have a context in Python before even hitting the DB
    require_tenant()

    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return pd.DataFrame(rows, columns=columns)
    finally:
        cursor.close()

def execute_scoped(conn, query: str, params: Optional[tuple[Any, ...]] = None) -> int:
    """
    Executes a command (INSERT/UPDATE/DELETE).
    PostgreSQL RLS and triggers enforce that 'tenant_id' is correctly applied.
    """
    require_tenant()

    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        rowcount = cursor.rowcount
        conn.commit()
        return rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
