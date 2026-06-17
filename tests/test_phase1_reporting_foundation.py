from __future__ import annotations

import json
from datetime import datetime, timedelta

import psycopg2
import pytest
from alembic import command
from alembic.config import Config

from core.report_builder import build_management_report
from core.report_config import seed_default_report_configuration
from core.database import CompatConnection
from tests.db_test_utils import (
    create_isolated_schema,
    drop_isolated_schema,
    resolve_test_database_url,
)


@pytest.fixture(scope="module")
def reporting_foundation_conn():
    base_url = resolve_test_database_url()
    try:
        schema_name, scoped_url = create_isolated_schema(base_url, prefix="phase1")
    except Exception as exc:
        pytest.skip(f"Postgres schema setup unavailable: {exc}")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", scoped_url)
    config.set_main_option("script_location", "migrations")
    command.upgrade(config, "head")

    raw_conn = psycopg2.connect(scoped_url)
    raw_conn.autocommit = False
    conn = CompatConnection(raw_conn)

    try:
        with raw_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tenants (slug, name, status, timezone, locale, retention_days)
                VALUES
                    ('tenant-r1', 'Tenant R1', 'active', 'Europe/Belgrade', 'en', 30),
                    ('tenant-r2', 'Tenant R2', 'active', 'Europe/Belgrade', 'en', 30)
                RETURNING id
                """
            )
            tenant_a_id, tenant_b_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO tenant_subscriptions (tenant_id, tier_code, status)
                VALUES
                    (%s, 'tier_1_ai_daily_operations', 'active'),
                    (%s, 'tier_1_ai_daily_operations', 'active')
                """,
                (tenant_a_id, tenant_b_id),
            )

            cur.execute(
                """
                INSERT INTO regions (tenant_id, name)
                VALUES (%s, 'North A'), (%s, 'North B')
                RETURNING id
                """,
                (tenant_a_id, tenant_b_id),
            )
            region_a_id, region_b_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO stations (tenant_id, region_id, name)
                VALUES
                    (%s, %s, 'Station A'),
                    (%s, %s, 'Station B')
                RETURNING id
                """,
                (tenant_a_id, region_a_id, tenant_b_id, region_b_id),
            )
            station_a_id, station_b_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO users (tenant_id, username, email, password_hash, role, is_active, name, surname, station_id, region_id, created_at, force_password_change)
                VALUES
                    (%s, 'emp-a', 'emp-a@example.com', 'hash', 'Employee', TRUE, 'Emp', 'A', %s, %s, NOW(), FALSE),
                    (%s, 'gm-a', 'gm-a@example.com', 'hash', 'General Manager', TRUE, 'GM', 'A', NULL, NULL, NOW(), FALSE),
                    (%s, 'emp-b', 'emp-b@example.com', 'hash', 'Employee', TRUE, 'Emp', 'B', %s, %s, NOW(), FALSE)
                RETURNING id
                """,
                (tenant_a_id, station_a_id, region_a_id, tenant_a_id, tenant_b_id, station_b_id, region_b_id),
            )
            employee_a_id, gm_a_id, employee_b_id = [row[0] for row in cur.fetchall()]

            report_ts = datetime.utcnow() - timedelta(hours=2)
            cur.execute(
                """
                INSERT INTO submissions (
                    tenant_id, station_id, employee_id, timestamp, processed, status, data_json
                )
                VALUES
                    (%s, %s, %s, %s, 1, 'done', %s),
                    (%s, %s, %s, %s, 1, 'done', %s)
                """,
                (
                    tenant_a_id,
                    station_a_id,
                    employee_a_id,
                    report_ts,
                    json.dumps(
                        {
                            "overall_risk_score": 65,
                            "safety_score": 8,
                            "cleanliness_score": 7,
                            "staff_score": 9,
                            "merchandising_score": 6,
                            "hazards": ["spill"],
                        }
                    ),
                    tenant_b_id,
                    station_b_id,
                    employee_b_id,
                    report_ts,
                    json.dumps(
                        {
                            "overall_risk_score": 10,
                            "safety_score": 5,
                            "cleanliness_score": 5,
                            "staff_score": 5,
                            "merchandising_score": 5,
                            "hazards": ["other-tenant"],
                        }
                    ),
                ),
            )

        raw_conn.commit()
        yield conn, raw_conn, tenant_a_id, tenant_b_id, employee_a_id, gm_a_id
    finally:
        conn.close()
        drop_isolated_schema(base_url, schema_name)


def test_seed_default_report_configuration_creates_expected_defaults(reporting_foundation_conn):
    conn, _, tenant_a_id, _, _, _ = reporting_foundation_conn

    seed_default_report_configuration(conn, tenant_id=tenant_a_id, timezone="Europe/Belgrade")
    conn.commit()

    schedules = conn.execute(
        """
        SELECT report_type, scope_type, timezone
        FROM report_schedules
        WHERE tenant_id = %s
        ORDER BY report_type, scope_type
        """,
        (tenant_a_id,),
    ).fetchall()
    subscriptions = conn.execute(
        """
        SELECT recipient_role, scope_type
        FROM report_subscriptions
        WHERE tenant_id = %s
        ORDER BY recipient_role, scope_type
        """,
        (tenant_a_id,),
    ).fetchall()

    assert len(schedules) == 12
    assert ("daily", "employee", "Europe/Belgrade") in schedules
    assert ("weekly", "employee", "Europe/Belgrade") in schedules
    assert ("monthly", "employee", "Europe/Belgrade") in schedules
    assert ("weekly", "company", "Europe/Belgrade") in schedules
    assert ("monthly", "company", "Europe/Belgrade") in schedules
    assert ("Employee", "employee") in subscriptions
    assert ("Gas Station Manager", "station") in subscriptions
    assert ("Region Manager", "region") in subscriptions
    assert ("General Manager", "company") in subscriptions


def test_build_management_report_filters_by_tenant_and_supports_employee_scope(reporting_foundation_conn):
    conn, _, tenant_a_id, _, employee_a_id, _ = reporting_foundation_conn
    period_start = datetime.utcnow() - timedelta(days=1)
    period_end = datetime.utcnow() + timedelta(days=1)

    payload = build_management_report(
        conn=conn,
        tenant_id=tenant_a_id,
        report_type="daily",
        scope_type="employee",
        scope_id=employee_a_id,
        role="Employee",
        recipient_name="Emp A",
        period_start=period_start,
        period_end=period_end,
    )

    assert payload["submission_count"] == 1
    assert payload["overall_risk_score"] == 65.0
    assert payload["scope_name"] == "zaposlenog Emp A"
    assert "other-tenant" not in payload["hazards"]


def test_build_management_report_resolves_zero_activity_scope_name(reporting_foundation_conn):
    conn, _, tenant_a_id, _, _, gm_a_id = reporting_foundation_conn
    period_start = datetime.utcnow() + timedelta(days=5)
    period_end = datetime.utcnow() + timedelta(days=6)

    payload = build_management_report(
        conn=conn,
        tenant_id=tenant_a_id,
        report_type="monthly",
        scope_type="company",
        scope_id=None,
        role="General Manager",
        recipient_name="GM A",
        period_start=period_start,
        period_end=period_end,
    )

    assert payload["submission_count"] == 0
    assert payload["scope_name"] == "kompaniju Tenant R1"
    assert payload["overall_risk_score"] == 0.0
    assert gm_a_id is not None
