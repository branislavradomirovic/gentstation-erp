from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional, Tuple, Dict

from core.auth import create_user, hash_password
from core.report_config import seed_default_report_configuration
from core.subscription import (
    TIER_1_AI_DAILY_OPERATIONS,
    TIER_2_CCTV_INTELLIGENCE,
    get_tier_definition,
)


@dataclass(frozen=True)
class TenantProvisionResult:
    tenant_id: int
    tenant_slug: str
    tenant_name: str
    tier_code: str
    admin_user_id: int
    admin_username: str
    admin_email: Optional[str]


def slugify_tenant_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "tenant"


def feature_flags_for_tier(tier_code: str) -> dict[str, bool]:
    tier_code = str(tier_code or TIER_1_AI_DAILY_OPERATIONS)
    return {
        TIER_1_AI_DAILY_OPERATIONS: True,
        TIER_2_CCTV_INTELLIGENCE: tier_code == TIER_2_CCTV_INTELLIGENCE,
        "telegram_intake": True,
        "email_notifications": True,
        "report_scheduler": True,
    }


def default_limits_for_tier(tier_code: str) -> Dict[str, Optional[int]]:
    tier = get_tier_definition(tier_code)
    return {
        "station_limit": tier.default_limits.get("stations"),
        "employee_limit": tier.default_limits.get("employees"),
        "camera_limit": tier.default_limits.get("cameras"),
    }


def _tenant_exists(conn, slug: str) -> bool:
    row = conn.execute(
        "SELECT id FROM tenants WHERE slug = %s",
        (slug,),
    ).fetchone()
    return bool(row)


def _user_exists(conn, username: Optional[str], email: Optional[str]) -> bool:
    if username:
        row = conn.execute(
            "SELECT id FROM users WHERE username = %s",
            (username,),
        ).fetchone()
        if row:
            return True
    if email:
        row = conn.execute(
            "SELECT id FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        ).fetchone()
        if row:
            return True
    return False


def provision_tenant(
    conn,
    *,
    tenant_name: str,
    tenant_slug: Optional[str] = None,
    tier_code: str = TIER_1_AI_DAILY_OPERATIONS,
    billing_email: Optional[str] = None,
    timezone: str = "UTC",
    locale: str = "en",
    retention_days: int = 30,
    station_limit: Optional[int] = None,
    employee_limit: Optional[int] = None,
    camera_limit: Optional[int] = None,
    metadata_json: Optional[Dict[str, Any]] = None,
) -> Tuple[int, str]:
    clean_name = (tenant_name or "").strip()
    if not clean_name:
        raise ValueError("Tenant name is required.")

    clean_slug = slugify_tenant_name(tenant_slug or clean_name)
    if _tenant_exists(conn, clean_slug):
        raise ValueError(f"Tenant slug '{clean_slug}' already exists.")

    tier_code = str(tier_code or TIER_1_AI_DAILY_OPERATIONS)
    limit_defaults = default_limits_for_tier(tier_code)

    row = conn.execute(
        """
        INSERT INTO tenants (
            slug, name, status, timezone, locale, billing_email, retention_days, metadata_json
        )
        VALUES (%s, %s, 'active', %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            clean_slug,
            clean_name,
            timezone,
            locale,
            billing_email,
            int(retention_days),
            json.dumps(metadata_json or {}),
        ),
    ).fetchone()
    tenant_id = int(row[0])

    conn.execute(
        """
        INSERT INTO tenant_subscriptions (
            tenant_id, tier_code, status, billing_cycle, billing_currency,
            station_limit, employee_limit, camera_limit, metadata_json
        )
        VALUES (%s, %s, 'active', 'monthly', 'EUR', %s, %s, %s, %s)
        """,
        (
            tenant_id,
            tier_code,
            station_limit if station_limit is not None else limit_defaults["station_limit"],
            employee_limit if employee_limit is not None else limit_defaults["employee_limit"],
            camera_limit if camera_limit is not None else limit_defaults["camera_limit"],
            json.dumps(metadata_json or {}),
        ),
    )

    for key, value in (
        ("timezone", timezone),
        ("locale", locale),
        ("retention_days", int(retention_days)),
        ("branding", {"company_name": clean_name}),
    ):
        conn.execute(
            """
            INSERT INTO tenant_settings (tenant_id, key, value_json)
            VALUES (%s, %s, %s)
            """,
            (tenant_id, key, json.dumps(value)),
        )

    for feature_key, enabled in feature_flags_for_tier(tier_code).items():
        conn.execute(
            """
            INSERT INTO tenant_feature_flags (tenant_id, feature_key, is_enabled, config_json)
            VALUES (%s, %s, %s, %s)
            """,
            (tenant_id, feature_key, enabled, json.dumps({})),
        )

    seed_default_report_configuration(conn, tenant_id=tenant_id, timezone=timezone)

    return tenant_id, clean_slug


def create_company_admin(
    conn,
    *,
    tenant_id: int,
    username: str,
    password: str,
    email: Optional[str],
    first_name: Optional[str] = None,
    surname: Optional[str] = None,
) -> dict[str, Any]:
    clean_username = (username or "").strip()
    clean_email = (email or "").strip() or None
    if not clean_username:
        raise ValueError("Admin username is required.")
    if not password:
        raise ValueError("Admin password is required.")
    if _user_exists(conn, clean_username, clean_email):
        raise ValueError("Admin username or email already exists.")

    # Use the create_user function from core.auth to handle hashing and insertion
    user_data = create_user(
        username=clean_username,
        password=password,
        email=clean_email,
        role="General Manager",
        name=first_name,
        surname=surname,
        tenant_id=tenant_id,
    )
    return user_data


def create_tenant_with_company_admin(
    conn,
    *,
    tenant_name: str,
    tenant_slug: Optional[str],
    tier_code: str,
    billing_email: Optional[str],
    timezone: str,
    locale: str,
    station_limit: Optional[int],
    employee_limit: Optional[int],
    camera_limit: Optional[int],
    admin_username: str,
    admin_password: str,
    admin_email: Optional[str],
    admin_first_name: Optional[str],
    admin_surname: Optional[str],
    metadata_json: Optional[Dict[str, Any]] = None,
) -> TenantProvisionResult:
    tenant_id, clean_slug = provision_tenant(
        conn,
        tenant_name=tenant_name,
        tenant_slug=tenant_slug,
        tier_code=tier_code,
        billing_email=billing_email,
        timezone=timezone,
        locale=locale,
        station_limit=station_limit,
        employee_limit=employee_limit,
        camera_limit=camera_limit,
        metadata_json=metadata_json,
    )
    admin_user = create_company_admin(
        conn,
        tenant_id=tenant_id,
        username=admin_username,
        password=admin_password,
        email=admin_email,
        first_name=admin_first_name,
        surname=admin_surname,
    )
    return TenantProvisionResult(
        tenant_id=tenant_id,
        tenant_slug=clean_slug,
        tenant_name=(tenant_name or "").strip(),
        tier_code=tier_code,
        admin_user_id=admin_user["id"],
        admin_username=admin_user["username"],
        admin_email=admin_user["email"],
    )


def seed_demo_hierarchy(
    conn,
    *,
    tenant_id: int,
    tenant_name: str,
    region_name: str,
    station_name: str,
    station_email: str,
    region_manager_email: str,
    station_manager_email: str,
    employee_email: str,
    demo_password: str,
) -> None:
    region_row = conn.execute(
        """
        INSERT INTO regions (tenant_id, name, email)
        VALUES (%s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (tenant_id, region_name, region_manager_email),
    ).fetchone()
    if region_row:
        region_id = int(region_row[0])
    else:
        region_id = int(
            conn.execute(
                "SELECT id FROM regions WHERE tenant_id = %s AND name = %s",
                (tenant_id, region_name),
            ).fetchone()[0]
        )

    station_row = conn.execute(
        """
        INSERT INTO stations (tenant_id, name, region_id, physical_address, email)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        (
            tenant_id,
            station_name,
            region_id,
            f"{station_name}, demo address",
            station_email,
        ),
    ).fetchone()
    if station_row:
        station_id = int(station_row[0])
    else:
        station_id = int(
            conn.execute(
                "SELECT id FROM stations WHERE tenant_id = %s AND name = %s",
                (tenant_id, station_name),
            ).fetchone()[0]
        )

    for username, email, role, station_id_value, region_id_value, manager_user_id in (
        (
            region_manager_email,
            region_manager_email,
            "Region Manager",
            None,
            region_id,
            _gm_id_for_tenant(conn, tenant_id),
        ),
        (
            station_manager_email,
            station_manager_email,
            "Gas Station Manager",
            station_id,
            region_id,
            _region_manager_id(conn, tenant_id, region_id),
        ),
        (
            employee_email,
            employee_email,
            "Employee",
            station_id,
            region_id,
            _station_manager_id(conn, tenant_id, station_id),
        ),
    ):
        if _user_exists(conn, username, email):
            continue
        conn.execute(
            """
            INSERT INTO users (
                tenant_id, username, email, password_hash, role, is_active, created_at,
                force_password_change, name, surname, station_id, region_id, manager_user_id
            )
            VALUES (%s, %s, %s, %s, %s, TRUE, NOW(), TRUE, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                username,
                email,
                hash_password(demo_password),
                role,
                tenant_name,
                role,
                station_id_value,
                region_id_value,
                manager_user_id,
            ),
        )


def _gm_id_for_tenant(conn, tenant_id: int) -> int:
    return int(
        conn.execute(
            """
            SELECT id FROM users
            WHERE tenant_id = %s AND role = 'General Manager'
            ORDER BY id
            LIMIT 1
            """,
            (tenant_id,),
        ).fetchone()[0]
    )


def _region_manager_id(conn, tenant_id: int, region_id: int) -> int:
    row = conn.execute(
        """
        SELECT id FROM users
        WHERE tenant_id = %s AND role = 'Region Manager' AND region_id = %s
        ORDER BY id
        LIMIT 1
        """,
        (tenant_id, region_id),
    ).fetchone()
    return int(row[0]) if row else _gm_id_for_tenant(conn, tenant_id)


def _station_manager_id(conn, tenant_id: int, station_id: int) -> int:
    row = conn.execute(
        """
        SELECT id FROM users
        WHERE tenant_id = %s AND role = 'Gas Station Manager' AND station_id = %s
        ORDER BY id
        LIMIT 1
        """,
        (tenant_id, station_id),
    ).fetchone()
    return int(row[0]) if row else _gm_id_for_tenant(conn, tenant_id)
