from __future__ import annotations

from core.integration_service import (
    build_csv_import_preview,
    queue_csv_import_placeholder,
    register_external_payload,
    resolve_station_id_from_external,
    upsert_integration,
    upsert_station_mapping,
)
from core.models import IntegrationEvent


class _FakeQuery:
    def __init__(self, session, target):
        self.session = session
        self.target = target
        self.filters = []

    def filter(self, *criteria):
        self.filters.extend(criteria)
        return self

    def one_or_none(self):
        if getattr(self.target, "__name__", "") == "Integration":
            return self.session.integration
        if getattr(self.target, "__name__", "") == "IntegrationStationMapping":
            if self.session.mapping_lookup_mode == "station":
                return self.session.mapping_by_station
            return self.session.mapping_tuple
        if getattr(self.target, "key", "") == "station_id":
            return self.session.mapping_tuple
        return None


class _FakeSession:
    def __init__(self):
        self.integration = None
        self.mapping_by_station = None
        self.mapping_tuple = None
        self.mapping_lookup_mode = "station"
        self.added = []

    def query(self, target):
        return _FakeQuery(self, target)

    def add(self, obj):
        self.added.append(obj)


def test_upsert_integration_stores_metadata_and_secret_refs():
    session = _FakeSession()

    integration = upsert_integration(
        session,
        tenant_id=7,
        integration_type="pos",
        provider="Acme POS",
        display_name="Acme Registers",
        config_json={"mode": "pull"},
        metadata_json={"supports_csv": True},
        secret_ref="env://POS_TOKEN",  # pragma: allowlist secret
        secret_refs_json={"api_key": "env://POS_API_KEY"},  # pragma: allowlist secret
    )

    assert integration.integration_type == "pos"
    assert integration.display_name == "Acme Registers"
    assert integration.metadata_json["supports_csv"] is True
    assert integration.secret_ref == "env://POS_TOKEN"  # pragma: allowlist secret
    assert integration.secret_refs_json["api_key"] == "env://POS_API_KEY"  # pragma: allowlist secret
    assert session.added[-1] is integration


def test_station_mapping_resolves_external_station_id():
    session = _FakeSession()

    mapping = upsert_station_mapping(
        session,
        tenant_id=7,
        integration_id=11,
        station_id=22,
        external_station_id="EXT-001",
        external_location_id="LOC-9",
        metadata_json={"source": "csv"},
    )
    session.mapping_by_station = mapping
    session.mapping_lookup_mode = "external"
    session.mapping_tuple = (22,)

    station_id = resolve_station_id_from_external(
        session,
        tenant_id=7,
        integration_id=11,
        external_station_id="EXT-001",
    )

    assert mapping.external_station_id == "EXT-001"
    assert mapping.external_location_id == "LOC-9"
    assert station_id == 22


def test_register_external_payload_uses_mapping_when_station_id_missing():
    session = _FakeSession()
    session.mapping_lookup_mode = "external"
    session.mapping_tuple = (44,)

    event = register_external_payload(
        session,
        tenant_id=9,
        integration_id=5,
        integration_type="pos",
        raw_payload={
            "transaction_id": "TX-1",
            "timestamp": "2026-06-17T10:00:00",
            "station_external_id": "POS-44",
            "amount": 123.45,
        },
    )

    assert isinstance(event, IntegrationEvent)
    assert event.station_id == 44
    assert event.external_id == "TX-1"
    assert event.event_type == "sale"


def test_queue_csv_import_placeholder_stores_blob_and_preview():
    session = _FakeSession()
    content = b"station_id,amount\nA1,10\nA2,20\n"

    preview = build_csv_import_preview("sales.csv", content)
    batch = queue_csv_import_placeholder(
        session,
        tenant_id=4,
        integration_id=8,
        filename="sales.csv",
        content_bytes=content,
        metadata_json={"uploaded_by": "tester"},
    )

    assert preview.row_count == 2
    assert preview.columns == ["station_id", "amount"]
    assert batch.status == "pending_mapping"
    assert batch.source_filename == "sales.csv"
    assert batch.source_blob == content
    assert batch.metadata_json["uploaded_by"] == "tester"
    assert batch.metadata_json["preview"]["row_count"] == 2
