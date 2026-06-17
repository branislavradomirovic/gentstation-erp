from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import get_connection
from core.platform_admin import (
    TIER_1_AI_DAILY_OPERATIONS,
    TIER_2_CCTV_INTELLIGENCE,
    create_tenant_with_company_admin,
    seed_demo_hierarchy,
)


DEMO_TENANTS = (
    {
        "tenant_name": "Tier 1 Alpha",
        "tenant_slug": "tier-1-alpha",
        "tier_code": TIER_1_AI_DAILY_OPERATIONS,
        "billing_email": "billing@t1alpha.com",
        "timezone": "Europe/Belgrade",
        "locale": "en",
        "station_limit": 5,
        "employee_limit": 20,
        "camera_limit": 0,
        "admin_username": "alpha_admin",
        "admin_password": "password123",  # pragma: allowlist secret
        "admin_email": "admin@t1alpha.com",
        "admin_first_name": "Alpha",
        "admin_surname": "Manager",
        "region_name": "North",
        "station_name": "Alpha Station 1",
        "station_email": "station1@t1alpha.com",
        "region_manager_email": "rm_north@t1alpha.com",
        "station_manager_email": "sm_alpha1@t1alpha.com",
        "employee_email": "emp_alpha1@t1alpha.com",
    },
    {
        "tenant_name": "Tier 2 Beta",
        "tenant_slug": "tier-2-beta",
        "tier_code": TIER_2_CCTV_INTELLIGENCE,
        "billing_email": "billing@t2beta.com",
        "timezone": "Europe/Belgrade",
        "locale": "en",
        "station_limit": 50,
        "employee_limit": 200,
        "camera_limit": 100,
        "admin_username": "beta_admin",
        "admin_password": "password123",  # pragma: allowlist secret
        "admin_email": "admin@t2beta.com",
        "admin_first_name": "Beta",
        "admin_surname": "Director",
        "region_name": "Central",
        "station_name": "Beta Station 1",
        "station_email": "station1@t2beta.com",
        "region_manager_email": "rm_central@t2beta.com",
        "station_manager_email": "sm_beta1@t2beta.com",
        "employee_email": "emp_beta1@t2beta.com",
    },
)


def _tenant_id_by_slug(conn, slug: str) -> int | None:
    row = conn.execute("SELECT id FROM tenants WHERE slug = %s", (slug,)).fetchone()
    return int(row[0]) if row else None


def _seed_demo_tenant(conn, payload: dict) -> None:
    slug = payload["tenant_slug"]
    print(f"🏢 Provisioning '{payload['tenant_name']}'...")

    tenant_id = _tenant_id_by_slug(conn, slug)
    if tenant_id is None:
        result = create_tenant_with_company_admin(
            conn,
            tenant_name=payload["tenant_name"],
            tenant_slug=slug,
            tier_code=payload["tier_code"],
            billing_email=payload["billing_email"],
            timezone=payload["timezone"],
            locale=payload["locale"],
            station_limit=payload["station_limit"],
            employee_limit=payload["employee_limit"],
            camera_limit=payload["camera_limit"],
            admin_username=payload["admin_username"],
            admin_password=payload["admin_password"],
            admin_email=payload["admin_email"],
            admin_first_name=payload["admin_first_name"],
            admin_surname=payload["admin_surname"],
            metadata_json={"source": "seed_demo_tenants"},
        )
        conn.commit()
        tenant_id = result.tenant_id
        print(f"✅ Created tenant {payload['tenant_name']} ({tenant_id})")
    else:
        print(f"ℹ️ Tenant '{payload['tenant_name']}' already exists as ID {tenant_id}; reusing it.")

    seed_demo_hierarchy(
        conn,
        tenant_id=tenant_id,
        tenant_name=payload["tenant_name"],
        region_name=payload["region_name"],
        station_name=payload["station_name"],
        station_email=payload["station_email"],
        region_manager_email=payload["region_manager_email"],
        station_manager_email=payload["station_manager_email"],
        employee_email=payload["employee_email"],
        demo_password=payload["admin_password"],
    )
    conn.commit()

    if payload["tier_code"] == TIER_2_CCTV_INTELLIGENCE:
        station_row = conn.execute(
            "SELECT id FROM stations WHERE tenant_id = %s AND name = %s",
            (tenant_id, payload["station_name"]),
        ).fetchone()
        if station_row:
            station_id = int(station_row[0])
            conn.execute(
                """
                INSERT INTO cctv_cameras (tenant_id, station_id, name, stream_url_secret_ref, camera_type, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (
                    tenant_id,
                    station_id,
                    "Front Forecourt Camera",
                    "demo/beta/front-forecourt",
                    "dome",
                    "active",
                ),
            )
            conn.commit()


def seed() -> None:
    print("🌱 Seeding demo tenants...")
    with get_connection(platform_access=True) as conn:
        for payload in DEMO_TENANTS:
            try:
                _seed_demo_tenant(conn, payload)
            except Exception as exc:
                conn.rollback()
                print(f"⚠️ Skip/Error for {payload['tenant_name']}: {exc}")
    print("✨ Seeding complete.")


if __name__ == "__main__":
    seed()
