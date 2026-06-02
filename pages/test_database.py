import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models import Base, Region, Station

# Use a separate test database from environment or default
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://gentstation_user:change_me_for_local_dev@localhost:5432/gentstation_test",
)  # pragma: allowlist secret

@pytest.fixture(scope="module")
def engine():
    return create_engine(TEST_DATABASE_URL)

@pytest.fixture(scope="module")
def tables(engine):
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)

@pytest.fixture
def dbsession(engine, tables):
    """Returns an sqlalchemy session, and rolls back every change after the test is done."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()

    yield session

    session.close()
    transaction.rollback()
    connection.close()

def test_create_region_and_station(dbsession):
    # Test creating a region
    new_region = Region(name="Balkans", email="balkans@gentstation.com")
    dbsession.add(new_region)
    dbsession.flush()

    # Test creating a station linked via relationship
    new_station = Station(name="Novi Sad 1", region=new_region)
    dbsession.add(new_station)
    dbsession.commit()

    assert new_station.region_id == new_region.id
    assert new_region.stations[0].name == "Novi Sad 1"
