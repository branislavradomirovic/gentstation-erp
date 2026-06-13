from __future__ import annotations

"""
Access Control Module - GentStationAI

Centralizes page configurations and role-based access logic.
"""

import os

from core.subscription import FEATURE_CCTV_INTELLIGENCE, is_feature_enabled
from core.tenant_context import TenantContext, TenantContextError

# List of usernames that bypass all role-based restrictions
SUPERUSERS = os.getenv("GSAI_SUPERUSERS", "admin").split(",")


PAGE_CONFIG = {
    "Dashboard": {
        "id": "Dashboard",
        "icon": "🏠",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
    "Regions": {
        "id": "Regions",
        "icon": "🌍",
        "roles": ["General Manager"],
    },
    "Stations": {
        "id": "Stations",
        "icon": "⛽",
        "roles": ["General Manager", "Region Manager"],
    },
    "Map View": {
        "id": "Map View",
        "icon": "🗺️",
        "roles": ["General Manager", "Region Manager"],
    },
    "Employees": {
        "id": "Employees",
        "icon": "👥",
        "roles": ["General Manager"],
    },
    "AI Reports": {
        "id": "AI Reports",
        "icon": "📈",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
        ],
    },
    "AI Alerts": {
        "id": "AI Alerts",
        "icon": "🚨",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
        ],
    },
    "AI Monitoring": {
        "id": "AI Monitoring",
        "icon": "🖥️",
        "roles": ["General Manager"],
    },
    "CCTV Intelligence": {
        "id": "CCTV Intelligence",
        "icon": "🎥",
        "roles": ["General Manager"],
        "feature_key": FEATURE_CCTV_INTELLIGENCE,
    },
    "Audit Log": {
        "id": "Audit Log",
        "icon": "🛡️",
        "roles": ["General Manager"],
    },
    "Admin Users": {
        "id": "Admin Users",
        "icon": "👤",
        "roles": ["General Manager"],
    },
    "Data Import": {
        "id": "Data Import",
        "icon": "📤",
        "roles": ["General Manager"],
    },
    "Settings": {
        "id": "Settings",
        "icon": "⚙️",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
    "Tenant Plan": {
        "id": "Tenant Plan",
        "icon": "📦",
        "roles": ["General Manager"],
    },
    "Help": {
        "id": "Help",
        "icon": "❓",
        "roles": [
            "General Manager",
            "Region Manager",
            "Gas Station Manager",
            "Gas Station Supervisor",
            "Employee",
        ],
    },
}


def has_access(
    page_id: str,
    user_role: str,
    username: str = None,
    tenant_context: TenantContext | None = None,
    conn=None,
) -> bool:
    """Returns True if the given role has permission to access the page."""
    if not user_role:
        return False

    # Superuser bypass
    if username in SUPERUSERS:
        return True

    config = PAGE_CONFIG.get(page_id)
    if not config:
        return False
    if user_role not in config.get("roles", []):
        return False

    required_feature = config.get("feature_key")
    if not required_feature:
        return True
    if tenant_context is None or conn is None:
        return False
    return is_feature_enabled(
        conn, required_feature, tenant_context=tenant_context
    )


def require_page_access(
    page_id: str,
    tenant_context: TenantContext | None,
    user_role: str,
    username: str | None = None,
    conn=None,
) -> None:
    if tenant_context is None or tenant_context.tenant_id is None:
        raise TenantContextError("Tenant context is required before loading protected pages.")
    if not has_access(page_id, user_role, username, tenant_context=tenant_context, conn=conn):
        raise PermissionError(f"User role {user_role!r} cannot access page {page_id!r}.")


def can_manage_station(tenant_context: TenantContext, station_id: int | None) -> bool:
    if station_id is None:
        return False
    if tenant_context.platform_access or tenant_context.role == "General Manager":
        return True
    return tenant_context.station_id == station_id


def can_manage_region(tenant_context: TenantContext, region_id: int | None) -> bool:
    if region_id is None:
        return False
    if tenant_context.platform_access or tenant_context.role == "General Manager":
        return True
    return tenant_context.region_id == region_id
