from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from core.database import get_connection
from core.tenant_context import require_current_tenant_context


@dataclass(frozen=True)
class SubmissionMediaPayload:
    content_bytes: bytes
    mime_type: str
    filename: str
    size_bytes: int
    checksum: str


def build_media_payload(
    content_bytes: bytes,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
) -> SubmissionMediaPayload:
    safe_filename = filename or "submission.mp4"
    resolved_mime = (
        mime_type
        or mimetypes.guess_type(safe_filename)[0]
        or "application/octet-stream"
    )
    return SubmissionMediaPayload(
        content_bytes=content_bytes,
        mime_type=resolved_mime,
        filename=Path(safe_filename).name,
        size_bytes=len(content_bytes),
        checksum=hashlib.sha256(content_bytes).hexdigest(),
    )


def save_submission_video(
    submission_id: int,
    content_bytes: bytes,
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    tenant_id: Optional[int] = None,
) -> None:
    payload = build_media_payload(content_bytes, filename=filename, mime_type=mime_type)
    effective_tenant_id = tenant_id or require_current_tenant_context().tenant_id
    with get_connection(platform_access=True) as conn:
        conn.execute(
            """
            UPDATE submissions
            SET video_filename = %s,
                video_mime_type = %s,
                video_size_bytes = %s,
                video_checksum = %s,
                video_blob = %s,
                video_path = NULL
            WHERE tenant_id = %s AND id = %s
            """,
            (
                payload.filename,
                payload.mime_type,
                payload.size_bytes,
                payload.checksum,
                payload.content_bytes,
                effective_tenant_id,
                submission_id,
            ),
        )
        conn.commit()


def get_submission_video_bytes(
    submission_id: int,
    tenant_id: Optional[int] = None,
) -> Optional[bytes]:
    effective_tenant_id = tenant_id or require_current_tenant_context().tenant_id
    with get_connection(platform_access=True) as conn:
        row = conn.execute(
            """
            SELECT video_blob
            FROM submissions
            WHERE tenant_id = %s AND id = %s
            """,
            (effective_tenant_id, submission_id),
        ).fetchone()
    if not row or not row[0]:
        return None
    return bytes(row[0])


@contextmanager
def materialize_submission_video(
    content_bytes: bytes,
    filename: Optional[str] = None,
) -> Iterator[str]:
    suffix = Path(filename or "submission.mp4").suffix or ".mp4"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        handle.write(content_bytes)
        handle.flush()
        handle.close()
        yield handle.name
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
