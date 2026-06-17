import json
import logging
import os
import sys
from contextlib import closing
from pathlib import Path


sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import get_connection


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("gentstation.backfill_default_tenant")

DEFAULT_TENANT_ID = int(os.getenv("DEFAULT_TENANT_ID", "1"))
DEFAULT_TENANT_SLUG = os.getenv("DEFAULT_TENANT_SLUG", "default").strip()
DEFAULT_TENANT_NAME = os.getenv("DEFAULT_TENANT_NAME", "Default Tenant").strip()

TENANT_TABLES = (
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
)


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


def ensure_default_tenant(conn) -> None:
    conn.execute(
        """
        INSERT INTO tenants (id, slug, name, status, timezone, locale, retention_days)
        VALUES (%s, %s, %s, 'active', 'UTC', 'en', 30)
        ON CONFLICT (id) DO UPDATE SET
            slug = EXCLUDED.slug,
            name = EXCLUDED.name
        """,
        (DEFAULT_TENANT_ID, DEFAULT_TENANT_SLUG, DEFAULT_TENANT_NAME),
    )

    conn.execute(
        """
        INSERT INTO tenant_subscriptions (
            tenant_id, tier_code, status, billing_cycle, billing_currency,
            camera_limit, metadata_json
        )
        VALUES (%s, %s, 'active', 'monthly', 'EUR', 0, %s)
        ON CONFLICT (tenant_id) DO NOTHING
        """,
        (
            DEFAULT_TENANT_ID,
            "tier_1_ai_daily_operations",
            json.dumps({"source": "backfill_default_tenant"}),
        ),
    )

    for key, value in (
        ("timezone", "UTC"),
        ("locale", "en"),
        ("retention_days", 30),
    ):
        conn.execute(
            """
            INSERT INTO tenant_settings (tenant_id, key, value_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (tenant_id, key) DO NOTHING
            """,
            (DEFAULT_TENANT_ID, key, json.dumps(value)),
        )

    for feature_key, enabled in (
        ("tier_1_ai_daily_operations", True),
        ("tier_2_cctv_intelligence", False),
        ("telegram_intake", True),
        ("email_notifications", True),
        ("report_scheduler", True),
    ):
        conn.execute(
            """
            INSERT INTO tenant_feature_flags (tenant_id, feature_key, is_enabled, config_json)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, feature_key) DO NOTHING
            """,
            (
                DEFAULT_TENANT_ID,
                feature_key,
                enabled,
                json.dumps({}),
            ),
        )


def backfill_tables(conn) -> None:
    for table_name in TENANT_TABLES:
        if not _column_exists(conn, table_name, "tenant_id"):
            logger.info("Skipping %s because tenant_id is not present yet.", table_name)
            continue
        conn.execute(
            f"UPDATE {table_name} SET tenant_id = %s WHERE tenant_id IS NULL",
            (DEFAULT_TENANT_ID,),
        )
        logger.info("Backfilled tenant_id on %s.", table_name)


def main() -> None:
    with closing(get_connection()) as conn:
        ensure_default_tenant(conn)
        backfill_tables(conn)
        conn.commit()
    logger.info(
        "Default tenant backfill complete for tenant %s (%s).",
        DEFAULT_TENANT_ID,
        DEFAULT_TENANT_SLUG,
    )


if __name__ == "__main__":
    main()
