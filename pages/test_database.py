import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.models import Base, Region, Station, StationCategory, Tenant
from tests.db_test_utils import (
    create_isolated_schema,
    drop_isolated_schema,
    resolve_test_database_url,
)


@pytest.fixture(scope="module")
def isolated_schema_url():
    base_url = resolve_test_database_url()
    try:
        schema_name, scoped_url = create_isolated_schema(base_url, prefix="page_db")
    except Exception as exc:
        pytest.skip(f"Postgres schema setup unavailable: {exc}")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", scoped_url)
    config.set_main_option("script_location", "migrations")
    command.upgrade(config, "head")

    try:
        yield schema_name, scoped_url
    finally:
        drop_isolated_schema(base_url, schema_name)


@pytest.fixture(scope="module")
def engine(isolated_schema_url):
    _, scoped_url = isolated_schema_url
    return create_engine(scoped_url)


@pytest.fixture
def dbsession(engine):
    connection = engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


def test_create_region_and_station(dbsession):
    tenant = Tenant(slug="test-company", name="Test Company")
    dbsession.add(tenant)
    dbsession.flush()

    new_region = Region(
        tenant_id=tenant.id,
        name="Balkans",
        email="balkans@gentstation.com",
    )
    dbsession.add(new_region)
    dbsession.flush()

    new_station = Station(
        tenant_id=tenant.id,
        name="Novi Sad 1",
        region=new_region,
    )
    dbsession.add(new_station)
    dbsession.commit()

    assert new_station.region_id == new_region.id
    assert new_region.id is not None


def test_station_categories_are_unique_per_tenant(dbsession):
    tenant_a = Tenant(slug="tenant-a", name="Tenant A")
    tenant_b = Tenant(slug="tenant-b", name="Tenant B")
    dbsession.add_all([tenant_a, tenant_b])
    dbsession.flush()

    dbsession.add(StationCategory(tenant_id=tenant_a.id, name="Highway"))
    dbsession.add(StationCategory(tenant_id=tenant_b.id, name="Highway"))
    dbsession.commit()

    dbsession.add(StationCategory(tenant_id=tenant_a.id, name="Highway"))
    with pytest.raises(Exception):
        dbsession.commit()
    dbsession.rollback()


def test_benchmarking_metrics_remain_tenant_scoped(engine):
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.platform_access', 'on', false)"))
        tenant_a_id = conn.execute(
            text(
                "INSERT INTO tenants (slug, name, status, timezone, locale, retention_days) "
                "VALUES ('bench-a', 'Bench A', 'active', 'UTC', 'en', 30) RETURNING id"
            )
        ).scalar_one()
        tenant_b_id = conn.execute(
            text(
                "INSERT INTO tenants (slug, name, status, timezone, locale, retention_days) "
                "VALUES ('bench-b', 'Bench B', 'active', 'UTC', 'en', 30) RETURNING id"
            )
        ).scalar_one()

        conn.execute(
            text("INSERT INTO stations (tenant_id, name) VALUES (:tenant_id, :name)"),
            [{"tenant_id": tenant_a_id, "name": "Station A"}, {"tenant_id": tenant_b_id, "name": "Station B"}],
        )

        station_a_id = conn.execute(
            text("SELECT id FROM stations WHERE tenant_id = :tenant_id AND name = 'Station A'"),
            {"tenant_id": tenant_a_id},
        ).scalar_one()
        station_b_id = conn.execute(
            text("SELECT id FROM stations WHERE tenant_id = :tenant_id AND name = 'Station B'"),
            {"tenant_id": tenant_b_id},
        ).scalar_one()

        conn.execute(
            text(
                "INSERT INTO cctv_cameras (tenant_id, station_id, name) VALUES "
                "(:tenant_a, :station_a, 'Cam A'), (:tenant_b, :station_b, 'Cam B')"
            ),
            {
                "tenant_a": tenant_a_id,
                "station_a": station_a_id,
                "tenant_b": tenant_b_id,
                "station_b": station_b_id,
            },
        )

        camera_a_id = conn.execute(
            text("SELECT id FROM cctv_cameras WHERE tenant_id = :tenant_id AND station_id = :station_id"),
            {"tenant_id": tenant_a_id, "station_id": station_a_id},
        ).scalar_one()

        conn.execute(text("SELECT set_config('app.platform_access', 'off', false)"))
        conn.execute(text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"), {"tenant_id": str(tenant_a_id)})
        conn.execute(
            text(
                """
                INSERT INTO cctv_metrics_hourly (
                    tenant_id, station_id, camera_id, metric_date, hour, metric_key, metric_value
                ) VALUES (:tenant_id, :station_id, :camera_id, DATE '2024-01-01', 10, 'count_vehicle', 100)
                """
            ),
            {"tenant_id": tenant_a_id, "station_id": station_a_id, "camera_id": camera_a_id},
        )

        conn.execute(text("SELECT set_config('app.current_tenant_id', :tenant_id, false)"), {"tenant_id": str(tenant_b_id)})
        count = conn.execute(text("SELECT COUNT(*) FROM cctv_metrics_hourly")).scalar_one()
        assert count == 0
