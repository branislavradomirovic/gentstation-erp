from __future__ import annotations

import hashlib
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from core.database import get_connection
from core.tenant_context import require_current_tenant_context


@dataclass(frozen=True)
class EvidencePayload:
    content_bytes: bytes
    mime_type: str
    filename: str
    size_bytes: int
    checksum: str


class EvidenceStorageBackend:
    def save(self, tenant_id: int, source_file: str, job_id: int) -> Optional[str]:
        raise NotImplementedError

    def resolve(self, tenant_id: int, reference: str) -> Optional[bytes]:
        raise NotImplementedError


class DatabaseEvidenceStorage(EvidenceStorageBackend):
    ref_prefix = "db://cctv_analysis_jobs/"

    def _load_payload(self, source_file: str) -> EvidencePayload:
        with open(source_file, "rb") as handle:
            content_bytes = handle.read()
        filename = Path(source_file).name
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        checksum = hashlib.sha256(content_bytes).hexdigest()
        return EvidencePayload(
            content_bytes=content_bytes,
            mime_type=mime_type,
            filename=filename,
            size_bytes=len(content_bytes),
            checksum=checksum,
        )

    def save(self, tenant_id: int, source_file: str, job_id: int) -> Optional[str]:
        if not os.path.exists(source_file):
            return None

        payload = self._load_payload(source_file)
        with get_connection(platform_access=True) as conn:
            conn.execute(
                """
                UPDATE cctv_analysis_jobs
                SET evidence_filename = %s,
                    evidence_mime_type = %s,
                    evidence_size_bytes = %s,
                    evidence_checksum = %s,
                    evidence_blob = %s
                WHERE tenant_id = %s AND id = %s
                """,
                (
                    payload.filename,
                    payload.mime_type,
                    payload.size_bytes,
                    payload.checksum,
                    payload.content_bytes,
                    tenant_id,
                    job_id,
                ),
            )
            conn.commit()

        try:
            os.remove(source_file)
        except OSError:
            pass
        return f"{self.ref_prefix}{job_id}"

    def resolve(self, tenant_id: int, reference: str) -> Optional[bytes]:
        if not reference or not reference.startswith(self.ref_prefix):
            return None

        job_id_text = reference[len(self.ref_prefix) :]
        try:
            job_id = int(job_id_text)
        except ValueError:
            return None

        with get_connection(platform_access=True) as conn:
            row = conn.execute(
                """
                SELECT evidence_blob
                FROM cctv_analysis_jobs
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, job_id),
            ).fetchone()
        if not row or not row[0]:
            return None
        return bytes(row[0])


def get_evidence_storage_backend() -> EvidenceStorageBackend:
    return DatabaseEvidenceStorage()


def save_event_evidence(source_file: str, job_id: int) -> Optional[str]:
    tenant_id = require_current_tenant_context().tenant_id
    return get_evidence_storage_backend().save(tenant_id, source_file, job_id)


def get_evidence_url(reference: str) -> Optional[bytes]:
    tenant_id = require_current_tenant_context().tenant_id
    return get_evidence_storage_backend().resolve(tenant_id, reference)
