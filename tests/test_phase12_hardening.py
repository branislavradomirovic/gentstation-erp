from __future__ import annotations

import psycopg2
import pytest
from alembic import command
from alembic.config import Config

from tests.db_test_utils import (
    create_isolated_schema,
    drop_isolated_schema,
    resolve_test_database_url,
)


@pytest.fixture(scope="module")
def hardened_db():
    base_url = resolve_test_database_url()
    try:
        schema_name, scoped_url = create_isolated_schema(base_url, prefix="phase12")
    except Exception as exc:
        pytest.skip(f"Postgres schema setup unavailable: {exc}")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", scoped_url)
    config.set_main_option("script_location", "migrations")
    command.upgrade(config, "head")

    try:
        with psycopg2.connect(scoped_url) as conn:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('app.platform_access', 'on', false)")
                cur.execute(
                    """
                    INSERT INTO tenants (slug, name, status, timezone, locale, retention_days)
                    VALUES
                        ('phase12-a', 'Phase12 A', 'active', 'UTC', 'en', 30),
                        ('phase12-b', 'Phase12 B', 'active', 'UTC', 'en', 30)
                    RETURNING id
                    """
                )
                tenant_a_id, tenant_b_id = [row[0] for row in cur.fetchall()]

                cur.execute(
                    """
                    INSERT INTO stations (tenant_id, name)
                    VALUES (%s, 'A Station'), (%s, 'B Station')
                    RETURNING id
                    """,
                    (tenant_a_id, tenant_b_id),
                )
                station_a_id, station_b_id = [row[0] for row in cur.fetchall()]

                cur.execute(
                    """
                    INSERT INTO integrations (
                        tenant_id, integration_type, provider, display_name, status, config_json, metadata_json, secret_ref, secret_refs_json
                    )
                    VALUES
                        (%s, 'pos', 'Provider A', 'Provider A', 'active', '{}'::jsonb, '{}'::jsonb, 'env://A', '{}'::jsonb),
                        (%s, 'pos', 'Provider B', 'Provider B', 'active', '{}'::jsonb, '{}'::jsonb, 'env://B', '{}'::jsonb)
                    RETURNING id
                    """,
                    (tenant_a_id, tenant_b_id),
                )
                integration_a_id, integration_b_id = [row[0] for row in cur.fetchall()]

                cur.execute(
                    """
                    INSERT INTO integration_station_mappings (
                        tenant_id, integration_id, station_id, external_station_id, metadata_json
                    )
                    VALUES
                        (%s, %s, %s, 'EXT-A', '{}'::jsonb),
                        (%s, %s, %s, 'EXT-B', '{}'::jsonb)
                    """,
                    (tenant_a_id, integration_a_id, station_a_id, tenant_b_id, integration_b_id, station_b_id),
                )

                cur.execute("SELECT set_config('app.platform_access', 'off', false)")
                cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (str(tenant_a_id),))
                cur.execute(
                    """
                    INSERT INTO integration_events (
                        tenant_id, integration_id, external_id, station_id, event_type, occurred_at, payload_json
                    )
                    VALUES (%s, %s, 'EVT-A', %s, 'sale', NOW(), '{}'::jsonb)
                    """,
                    (tenant_a_id, integration_a_id, station_a_id),
                )
            conn.commit()
        yield scoped_url, tenant_a_id, tenant_b_id
    finally:
        drop_isolated_schema(base_url, schema_name)


def test_cross_tenant_integration_rows_remain_isolated(hardened_db):
    scoped_url, tenant_a_id, tenant_b_id = hardened_db
    with psycopg2.connect(scoped_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.platform_access', 'off', false)")
            cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (str(tenant_a_id),))
            cur.execute("SELECT COUNT(*) FROM integration_station_mappings")
            tenant_one_mapping_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM integration_events")
            tenant_one_event_count = cur.fetchone()[0]

            cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (str(tenant_b_id),))
            cur.execute("SELECT COUNT(*) FROM integration_station_mappings")
            tenant_two_mapping_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM integration_events")
            tenant_two_event_count = cur.fetchone()[0]

    assert tenant_one_mapping_count == 1
    assert tenant_one_event_count == 1
    assert tenant_two_mapping_count == 1
    assert tenant_two_event_count == 0
