from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from core.tenant_context import TenantContext, require_current_tenant_context


def require_tenant_scope() -> int:
    return require_current_tenant_context().tenant_id


def require_tenant_context() -> TenantContext:
    return require_current_tenant_context()


def tenant_clause(column_name: str = "tenant_id") -> str:
    require_tenant_scope()
    return f"{column_name} = %s"


def tenant_params(params: Optional[tuple[Any, ...]] = None) -> tuple[Any, ...]:
    return (require_tenant_scope(),) + tuple(params or ())


def fetch_df_tenant(conn, query: str, params: Optional[tuple[Any, ...]] = None) -> pd.DataFrame:
    require_tenant_scope()
    cursor = conn.cursor()
    try:
        cursor.execute(query, params or ())
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        return pd.DataFrame(rows, columns=columns)
    finally:
        cursor.close()


def execute_tenant(conn, query: str, params: Optional[tuple[Any, ...]] = None):
    require_tenant_scope()
    cursor = conn.cursor()
    cursor.execute(query, params or ())
    return cursor.rowcount
