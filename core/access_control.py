from __future__ import annotations

"""
Access Control Module - GentStationAI

Centralizes page configurations and role-based access logic.
"""

import os
from typing import Optional, List

from core.subscription import (
    FEATURE_CCTV_INTELLIGENCE,
    is_feature_enabled,
    FeatureGateError,
    FEATURE_DEFINITIONS
)
from core.tenant_context import TenantContext, TenantContextError

# List of usernames that bypass all role-based restrictions
SUPERUSERS = os.getenv("GSAI_SUPERUSERS", "admin").split(",")


def is_platform_superadmin(username: Optional[str]) -> bool:
    clean_username = (username or "").strip()
    return bool(clean_username) and clean_username in {
        user.strip() for user in SUPERUSERS if user.strip()
    }


def require_platform_superadmin(username: Optional[str]) -> None:
    if not is_platform_superadmin(username):
        raise PermissionError("Platform superadmin access is required for this page.")


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
    "Review Center": {
        "id": "Review Center",
        "icon": "🎬",
        "roles": ["General Manager"],
        "feature_key": FEATURE_CCTV_INTELLIGENCE,
    },
    "CCTV Intelligence": {
        "id": "CCTV Intelligence",
        "icon": "🎥",
        "roles": ["General Manager"],
        "feature_key": FEATURE_CCTV_INTELLIGENCE,
    },
    "Camera Registry": {
        "id": "Camera Registry",
        "icon": "📷",
        "roles": ["General Manager"],
        "feature_key": FEATURE_CCTV_INTELLIGENCE,
    },
    "Benchmarking": {
        "id": "Benchmarking",
        "icon": "📊",
        "roles": ["General Manager", "Region Manager"],
        "feature_key": FEATURE_CCTV_INTELLIGENCE,
    },
    "Integrations": {
        "id": "Integrations",
        "icon": "🔌",
        "roles": ["General Manager"],
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
    "Platform Admin": {
        "id": "Platform Admin",
        "icon": "🧭",
        "roles": ["General Manager"],
        "platform_superadmin_only": True,
    },
    "Platform Health": {
        "id": "Platform Health",
        "icon": "🏥",
        "roles": ["General Manager"],
        "platform_superadmin_only": True,
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
    username: Optional[str] = None,
    tenant_context: Optional[TenantContext] = None,
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
    if config.get("platform_superadmin_only"):
        return is_platform_superadmin(username)
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
    tenant_context: Optional[TenantContext],
    user_role: str,
    username: Optional[str] = None,
    conn=None,
) -> None:
    if tenant_context is None or tenant_context.tenant_id is None:
        raise TenantContextError("Tenant context is required before loading protected pages.")

    # 1. Platform Superadmin bypass
    if is_platform_superadmin(username):
        return

    config = PAGE_CONFIG.get(page_id)
    if not config:
        raise PermissionError(f"Page {page_id!r} is not configured.")

    # 2. Platform Admin restriction
    if config.get("platform_superadmin_only"):
        require_platform_superadmin(username)

    # 3. Role-based check
    if user_role not in config.get("roles", []):
        raise PermissionError(f"User role {user_role!r} cannot access page {page_id!r}.")

    # 4. Feature-based gate (Tier enforcement)
    required_feature = config.get("feature_key")
    if required_feature:
        if conn is None:
            # Safety check: if code path doesn't provide conn, we can't verify tiers reliably
            raise RuntimeError("Database connection required for feature-gated page access.")

        if not is_feature_enabled(conn, required_feature, tenant_context=tenant_context):
            feature = FEATURE_DEFINITIONS.get(required_feature)
            label = feature.label if feature else required_feature
            raise FeatureGateError(
                f"{label} is a Tier 2 feature and is not enabled for your current tenant plan."
            )


def can_manage_station(tenant_context: TenantContext, station_id: Optional[int]) -> bool:
    if station_id is None:
        return False
    if tenant_context.platform_access or tenant_context.role == "General Manager":
        return True
    return tenant_context.station_id == station_id


def can_manage_region(tenant_context: TenantContext, region_id: Optional[int]) -> bool:
    if region_id is None:
        return False
    if tenant_context.platform_access or tenant_context.role == "General Manager":
        return True
    return tenant_context.region_id == region_id


def can_administer_reporting(user_role: Optional[str]) -> bool:
    return user_role == "General Manager"
