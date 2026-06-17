from __future__ import annotations

import csv
import hashlib
import io
import logging
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func

from core.models import (
    Integration,
    IntegrationEvent,
    IntegrationImportBatch,
    IntegrationStationMapping,
)

logger = logging.getLogger("gentstation.integration_service")

INTEGRATION_TYPES = ("pos", "pump", "loyalty", "inventory")


@dataclass(frozen=True)
class CSVImportPreview:
    filename: str
    row_count: int
    columns: list[str]
    sample_rows: list[dict[str, str]]


class ExternalDataProvider:
    integration_type: str = "generic"

    def map_event(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError()


class POSProvider(ExternalDataProvider):
    integration_type = "pos"

    def map_event(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": "sale",
            "external_id": raw_payload.get("transaction_id"),
            "occurred_at": raw_payload.get("timestamp"),
            "station_external_id": raw_payload.get("station_external_id") or raw_payload.get("gs_id"),
            "payload_json": raw_payload,
        }


class PumpProvider(ExternalDataProvider):
    integration_type = "pump"

    def map_event(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": raw_payload.get("event_type") or "fueling_session",
            "external_id": raw_payload.get("session_id"),
            "occurred_at": raw_payload.get("timestamp"),
            "station_external_id": raw_payload.get("station_external_id"),
            "payload_json": raw_payload,
        }


class LoyaltyProvider(ExternalDataProvider):
    integration_type = "loyalty"

    def map_event(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": raw_payload.get("event_type") or "loyalty_activity",
            "external_id": raw_payload.get("member_event_id"),
            "occurred_at": raw_payload.get("timestamp"),
            "station_external_id": raw_payload.get("station_external_id"),
            "payload_json": raw_payload,
        }


class InventoryProvider(ExternalDataProvider):
    integration_type = "inventory"

    def map_event(self, raw_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "event_type": raw_payload.get("event_type") or "stock_update",
            "external_id": raw_payload.get("inventory_event_id"),
            "occurred_at": raw_payload.get("timestamp"),
            "station_external_id": raw_payload.get("station_external_id"),
            "payload_json": raw_payload,
        }


PROVIDER_REGISTRY = {
    "pos": POSProvider,
    "pump": PumpProvider,
    "loyalty": LoyaltyProvider,
    "inventory": InventoryProvider,
}


def normalize_integration_type(integration_type: str) -> str:
    normalized = str(integration_type or "").strip().lower()
    if normalized not in INTEGRATION_TYPES:
        raise ValueError(
            f"Unsupported integration type {integration_type!r}. Expected one of {INTEGRATION_TYPES}."
        )
    return normalized


def list_supported_integration_types() -> list[str]:
    return list(INTEGRATION_TYPES)


def get_provider_for_integration_type(integration_type: str) -> ExternalDataProvider:
    normalized = normalize_integration_type(integration_type)
    return PROVIDER_REGISTRY[normalized]()


def upsert_integration(
    session,
    *,
    tenant_id: int,
    integration_type: str,
    provider: str,
    display_name: Optional[str] = None,
    config_json: Optional[dict[str, Any]] = None,
    metadata_json: Optional[dict[str, Any]] = None,
    secret_ref: Optional[str] = None,
    secret_refs_json: Optional[dict[str, Any]] = None,
    status: str = "active",
) -> Integration:
    normalized_type = normalize_integration_type(integration_type)
    provider_name = str(provider or "").strip()
    if not provider_name:
        raise ValueError("Provider name is required.")

    integration = (
        session.query(Integration)
        .filter(
            Integration.tenant_id == tenant_id,
            Integration.integration_type == normalized_type,
            Integration.provider == provider_name,
        )
        .one_or_none()
    )

    if integration is None:
        integration = Integration(
            tenant_id=tenant_id,
            integration_type=normalized_type,
            provider=provider_name,
        )
        session.add(integration)

    integration.display_name = display_name or provider_name
    integration.status = status
    integration.config_json = config_json or {}
    integration.metadata_json = metadata_json or {}
    integration.secret_ref = (secret_ref or "").strip() or None
    integration.secret_refs_json = secret_refs_json or {}
    return integration


def upsert_station_mapping(
    session,
    *,
    tenant_id: int,
    integration_id: int,
    station_id: int,
    external_station_id: str,
    external_location_id: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
) -> IntegrationStationMapping:
    external_station_id = str(external_station_id or "").strip()
    if not external_station_id:
        raise ValueError("external_station_id is required.")

    mapping = (
        session.query(IntegrationStationMapping)
        .filter(
            IntegrationStationMapping.tenant_id == tenant_id,
            IntegrationStationMapping.integration_id == integration_id,
            IntegrationStationMapping.station_id == station_id,
        )
        .one_or_none()
    )
    if mapping is None:
        mapping = IntegrationStationMapping(
            tenant_id=tenant_id,
            integration_id=integration_id,
            station_id=station_id,
        )
        session.add(mapping)

    mapping.external_station_id = external_station_id
    mapping.external_location_id = (external_location_id or "").strip() or None
    mapping.metadata_json = metadata_json or {}
    return mapping


def resolve_station_id_from_external(
    session,
    *,
    tenant_id: int,
    integration_id: int,
    external_station_id: str,
) -> Optional[int]:
    row = (
        session.query(IntegrationStationMapping.station_id)
        .filter(
            IntegrationStationMapping.tenant_id == tenant_id,
            IntegrationStationMapping.integration_id == integration_id,
            IntegrationStationMapping.external_station_id == str(external_station_id),
        )
        .one_or_none()
    )
    return int(row[0]) if row else None


def _coerce_occurred_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        with_timezone = value.replace("Z", "+00:00")
        return datetime.fromisoformat(with_timezone)
    return datetime.utcnow()


def register_integration_event(
    session,
    tenant_id: int,
    integration_id: int,
    event_data: Dict[str, Any],
) -> IntegrationEvent:
    station_id = event_data.get("station_id")
    if station_id is None and event_data.get("station_external_id"):
        station_id = resolve_station_id_from_external(
            session,
            tenant_id=tenant_id,
            integration_id=integration_id,
            external_station_id=str(event_data["station_external_id"]),
        )

    new_event = IntegrationEvent(
        tenant_id=tenant_id,
        integration_id=integration_id,
        external_id=str(event_data.get("external_id") or "") or None,
        station_id=station_id,
        event_type=str(event_data.get("event_type") or "external_event"),
        occurred_at=_coerce_occurred_at(event_data.get("occurred_at")),
        payload_json=event_data.get("payload_json", {}),
    )
    session.add(new_event)
    return new_event


def register_external_payload(
    session,
    *,
    tenant_id: int,
    integration_id: int,
    integration_type: str,
    raw_payload: Dict[str, Any],
) -> IntegrationEvent:
    provider = get_provider_for_integration_type(integration_type)
    mapped_event = provider.map_event(raw_payload)
    return register_integration_event(
        session,
        tenant_id=tenant_id,
        integration_id=integration_id,
        event_data=mapped_event,
    )


def build_csv_import_preview(
    filename: str,
    content_bytes: bytes,
    *,
    sample_size: int = 5,
) -> CSVImportPreview:
    decoded = content_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))
    rows: list[dict[str, str]] = []
    for index, row in enumerate(reader):
        normalized_row = {str(key): str(value) for key, value in row.items()}
        rows.append(normalized_row)
        if index + 1 >= sample_size:
            break

    column_names = list(reader.fieldnames or [])
    total_rows = len(list(csv.DictReader(io.StringIO(decoded))))
    return CSVImportPreview(
        filename=filename,
        row_count=total_rows,
        columns=column_names,
        sample_rows=rows,
    )


def queue_csv_import_placeholder(
    session,
    *,
    tenant_id: int,
    integration_id: int,
    filename: str,
    content_bytes: bytes,
    metadata_json: Optional[dict[str, Any]] = None,
) -> IntegrationImportBatch:
    preview = build_csv_import_preview(filename, content_bytes)
    mime_type = mimetypes.guess_type(filename)[0] or "text/csv"
    checksum = hashlib.sha256(content_bytes).hexdigest()

    batch = IntegrationImportBatch(
        tenant_id=tenant_id,
        integration_id=integration_id,
        import_type="csv_placeholder",
        status="pending_mapping",
        source_filename=filename,
        source_mime_type=mime_type,
        source_size_bytes=len(content_bytes),
        source_checksum=checksum,
        source_blob=content_bytes,
        metadata_json={
            **(metadata_json or {}),
            "preview": {
                "row_count": preview.row_count,
                "columns": preview.columns,
                "sample_rows": preview.sample_rows,
            },
        },
        result_json={
            "message": "CSV import placeholder queued. Provider-specific mapping is not active yet."
        },
    )
    session.add(batch)
    return batch


def get_integration_stats(session, tenant_id: int) -> Dict[str, Any]:
    provider_count = (
        session.query(func.count(Integration.id))
        .filter_by(tenant_id=tenant_id)
        .scalar()
    )
    event_count = (
        session.query(func.count(IntegrationEvent.id))
        .filter_by(tenant_id=tenant_id)
        .scalar()
    )
    mapping_count = (
        session.query(func.count(IntegrationStationMapping.id))
        .filter_by(tenant_id=tenant_id)
        .scalar()
    )
    import_count = (
        session.query(func.count(IntegrationImportBatch.id))
        .filter_by(tenant_id=tenant_id)
        .scalar()
    )
    return {
        "active_integrations": provider_count or 0,
        "total_events": event_count or 0,
        "mapped_stations": mapping_count or 0,
        "import_batches": import_count or 0,
    }


def list_import_batches(session, tenant_id: int) -> List[IntegrationImportBatch]:
    return (
        session.query(IntegrationImportBatch)
        .filter(IntegrationImportBatch.tenant_id == tenant_id)
        .order_by(IntegrationImportBatch.created_at.desc())
        .all()
    )


def list_station_mappings(session, tenant_id: int) -> List[IntegrationStationMapping]:
    return (
        session.query(IntegrationStationMapping)
        .filter(IntegrationStationMapping.tenant_id == tenant_id)
        .order_by(IntegrationStationMapping.created_at.desc())
        .all()
    )
