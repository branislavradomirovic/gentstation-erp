from __future__ import annotations

import json
from datetime import datetime, timedelta
from contextlib import contextmanager

import psycopg2
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import core.report_builder as report_builder
from core.report_builder import build_management_report
from core.database import CompatConnection
from tests.db_test_utils import (
    create_isolated_schema,
    drop_isolated_schema,
    resolve_test_database_url,
)


@pytest.fixture(scope="module")
def report_conn():
    base_url = resolve_test_database_url()
    try:
        schema_name, scoped_url = create_isolated_schema(base_url, prefix="phase9")
    except Exception as exc:
        pytest.skip(f"Postgres schema setup unavailable: {exc}")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", scoped_url)
    config.set_main_option("script_location", "migrations")
    command.upgrade(config, "head")

    raw_conn = psycopg2.connect(scoped_url)
    raw_conn.autocommit = False
    conn = CompatConnection(raw_conn)
    engine = create_engine(scoped_url)
    SessionLocal = sessionmaker(bind=engine)

    try:
        with raw_conn.cursor() as cur:
            cur.execute("SELECT set_config('app.platform_access', 'on', false)")

            cur.execute(
                """
                INSERT INTO tenants (slug, name, status, timezone, locale, retention_days)
                VALUES
                    ('tenant-a', 'Tenant A', 'active', 'UTC', 'en', 30),
                    ('tenant-b', 'Tenant B', 'active', 'UTC', 'en', 30)
                RETURNING id
                """
            )
            tenant_a_id, tenant_b_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO tenant_subscriptions (tenant_id, tier_code, status)
                VALUES
                    (%s, 'tier_2_cctv_intelligence', 'active'),
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
                    (%s, %s, 'Station A1'),
                    (%s, %s, 'Station B1')
                RETURNING id
                """,
                (tenant_a_id, region_a_id, tenant_b_id, region_b_id),
            )
            station_a_id, station_b_id = [row[0] for row in cur.fetchall()]

            cur.execute(
                """
                INSERT INTO cctv_cameras (tenant_id, station_id, name)
                VALUES
                    (%s, %s, 'Cam A'),
                    (%s, %s, 'Cam B')
                RETURNING id
                """,
                (tenant_a_id, station_a_id, tenant_b_id, station_b_id),
            )
            camera_a_id, camera_b_id = [row[0] for row in cur.fetchall()]

            report_ts = datetime.utcnow() - timedelta(hours=4)

            cur.execute(
                """
                INSERT INTO submissions (
                    tenant_id, station_id, timestamp, processed, status, data_json
                )
                VALUES
                    (%s, %s, %s, 1, 'done', %s),
                    (%s, %s, %s, 1, 'done', %s)
                """,
                (
                    tenant_a_id,
                    station_a_id,
                    report_ts,
                    json.dumps(
                        {
                            "overall_risk_score": 80,
                            "safety_score": 9,
                            "cleanliness_score": 8,
                            "staff_score": 7,
                            "merchandising_score": 6,
                            "hazards": ["spill"],
                        }
                    ),
                    tenant_b_id,
                    station_b_id,
                    report_ts,
                    json.dumps(
                        {
                            "overall_risk_score": 15,
                            "safety_score": 5,
                            "cleanliness_score": 5,
                            "staff_score": 5,
                            "merchandising_score": 5,
                            "hazards": ["other-tenant"],
                        }
                    ),
                ),
            )

            cur.execute(
                """
                INSERT INTO cctv_metrics_hourly (
                    tenant_id, station_id, camera_id, metric_date, hour, metric_key, metric_value, confidence
                )
                VALUES
                    (%s, %s, %s, CURRENT_DATE, 10, 'overall_risk_score', 88, 0.91),
                    (%s, %s, %s, CURRENT_DATE, 10, 'safety_score', 9, 0.95),
                    (%s, %s, %s, CURRENT_DATE, 10, 'overall_risk_score', 12, 0.44)
                """,
                (
                    tenant_a_id,
                    station_a_id,
                    camera_a_id,
                    tenant_a_id,
                    station_a_id,
                    camera_a_id,
                    tenant_b_id,
                    station_b_id,
                    camera_b_id,
                ),
            )

            cur.execute(
                """
                INSERT INTO cctv_events (
                    tenant_id, station_id, job_id, camera_id, event_type, severity, confidence, status, review_required, occurred_at
                )
                VALUES
                    (%s, %s, NULL, %s, 'cctv_analysis_summary', 'high', 0.90, 'new', TRUE, NOW()),
                    (%s, %s, NULL, %s, 'cctv_analysis_summary', 'low', 0.30, 'new', TRUE, NOW())
                """,
                (
                    tenant_a_id,
                    station_a_id,
                    camera_a_id,
                    tenant_b_id,
                    station_b_id,
                    camera_b_id,
                ),
            )
        raw_conn.commit()
        yield conn, raw_conn, engine, SessionLocal, tenant_a_id, tenant_b_id
    finally:
        conn.close()
        engine.dispose()
        drop_isolated_schema(base_url, schema_name)


def test_company_report_includes_only_active_tenant_cctv_data(report_conn, monkeypatch):
    conn, raw_conn, _, SessionLocal, tenant_a_id, _ = report_conn
    period_start = datetime.utcnow() - timedelta(days=2)
    period_end = datetime.utcnow() + timedelta(days=1)

    with raw_conn.cursor() as cur:
        cur.execute("SELECT set_config('app.platform_access', 'off', false)")
        cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (str(tenant_a_id),))
    raw_conn.commit()

    @contextmanager
    def _session_override():
        session = SessionLocal()
        try:
            session.connection().exec_driver_sql(
                "SELECT set_config('app.platform_access', 'off', false)"
            )
            session.connection().exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', :tenant_id, false)",
                {"tenant_id": str(tenant_a_id)},
            )
            yield session
        finally:
            session.close()

    monkeypatch.setattr(report_builder, "get_session", _session_override)

    payload = build_management_report(
        conn=conn,
        tenant_id=tenant_a_id,
        report_type="weekly",
        scope_type="company",
        scope_id=None,
        role="General Manager",
        recipient_name="GM A",
        period_start=period_start,
        period_end=period_end,
    )

    assert payload["submission_count"] == 1
    assert payload["overall_risk_score"] == 80.0
    assert payload["cctv_intelligence"]["enabled"] is True
    assert payload["cctv_intelligence"]["average_metrics"]["overall_risk_score"] == 88.0
    assert payload["cctv_intelligence"]["event_summary"]["review_required_events"] == 1


def test_tier_1_company_report_preserves_tier_1_payload_shape(report_conn, monkeypatch):
    conn, raw_conn, _, SessionLocal, _, tenant_b_id = report_conn
    period_start = datetime.utcnow() - timedelta(days=2)
    period_end = datetime.utcnow() + timedelta(days=1)

    with raw_conn.cursor() as cur:
        cur.execute("SELECT set_config('app.platform_access', 'off', false)")
        cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (str(tenant_b_id),))
    raw_conn.commit()

    @contextmanager
    def _session_override():
        session = SessionLocal()
        try:
            session.connection().exec_driver_sql(
                "SELECT set_config('app.platform_access', 'off', false)"
            )
            session.connection().exec_driver_sql(
                "SELECT set_config('app.current_tenant_id', :tenant_id, false)",
                {"tenant_id": str(tenant_b_id)},
            )
            yield session
        finally:
            session.close()

    monkeypatch.setattr(report_builder, "get_session", _session_override)

    payload = build_management_report(
        conn=conn,
        tenant_id=tenant_b_id,
        report_type="daily",
        scope_type="company",
        scope_id=None,
        role="General Manager",
        recipient_name="GM B",
        period_start=period_start,
        period_end=period_end,
    )

    assert payload["submission_count"] == 1
    assert payload["overall_risk_score"] == 15.0
    assert "cctv_intelligence" not in payload
