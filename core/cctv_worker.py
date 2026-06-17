from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta

from core.cctv_analysis import (
    VideoAnalysisProvider,
    aggregate_metrics,
    get_video_analysis_provider,
)
from core.database import get_session
from core.models import CCTVAnalysisJob, CCTVEvent, CCTVCamera
from core.submission_storage import materialize_submission_video
from core.subscription import FEATURE_CCTV_INTELLIGENCE, require_feature
from core.storage import save_event_evidence
from core.tenant_context import TenantContext, tenant_context

logger = logging.getLogger("gentstation.cctv_worker")

CCTV_WORKER_MAX_RETRIES = int(os.getenv("CCTV_WORKER_MAX_RETRIES", "3"))
CCTV_WORKER_STUCK_TIMEOUT_SECONDS = int(os.getenv("CCTV_WORKER_STUCK_TIMEOUT_SECONDS", "600"))


def _select_pending_job(session) -> CCTVAnalysisJob | None:
    return (
        session.query(CCTVAnalysisJob)
        .filter(CCTVAnalysisJob.status == "pending")
        .order_by(CCTVAnalysisJob.id.asc())
        .first()
    )


def _claim_job(session, job: CCTVAnalysisJob) -> None:
    job.status = "processing"
    job.started_at = datetime.utcnow()
    session.commit()


def _mark_job_completed(session, job: CCTVAnalysisJob, provider: VideoAnalysisProvider) -> None:
    job.status = "completed"
    job.completed_at = datetime.utcnow()
    job.provider_name = provider.name
    session.commit()


def _mark_job_failed(session, job: CCTVAnalysisJob, error: Exception, provider: VideoAnalysisProvider) -> None:
    job.retry_count = int(job.retry_count or 0) + 1
    job.error_message = str(error)
    job.provider_name = provider.name
    job.model_version = getattr(provider, "model_version", None)
    job.prompt_version = getattr(provider, "prompt_version", None)
    if job.retry_count >= CCTV_WORKER_MAX_RETRIES:
        job.status = "failed"
    else:
        job.status = "pending"
    session.commit()


def process_cctv_jobs(provider: VideoAnalysisProvider | None = None) -> bool:
    """Consumes and processes one pending CCTV analysis job."""
    provider = provider or get_video_analysis_provider()

    with get_session(platform_access=True) as session:
        job = _select_pending_job(session)
        if not job:
            return False

        _claim_job(session, job)
        tenant_id = job.tenant_id
        camera_id = job.camera_id

        with tenant_context(TenantContext(tenant_id=tenant_id)):
            try:
                require_feature(session.connection(), FEATURE_CCTV_INTELLIGENCE)
                camera = session.get(CCTVCamera, camera_id)
                if not camera:
                    raise ValueError(f"Camera {camera_id} not found")

                zones_context = [
                    {"name": zone.name, "zone_type": zone.zone_type}
                    for zone in camera.zones
                ]
                if getattr(job, "source_blob", None):
                    source_ctx = materialize_submission_video(
                        bytes(job.source_blob),
                        getattr(job, "source_filename", None),
                    )
                else:
                    raise FileNotFoundError(
                        f"Job {job.id} has no database-backed source media"
                    )

                with source_ctx as local_video_path:
                    analysis = provider.analyze(local_video_path, job.job_type, zones_context)
                    evidence_ref = save_event_evidence(local_video_path, job.id)
                if not evidence_ref:
                    raise FileNotFoundError(f"Could not persist evidence for job {job.id}")
                for event in analysis.events:
                    session.add(
                        CCTVEvent(
                            tenant_id=tenant_id,
                            station_id=camera.station_id,
                            job_id=job.id,
                            camera_id=camera_id,
                            event_type=event.event_type,
                            severity=event.severity,
                            confidence=event.confidence,
                            review_required=event.review_required,
                            provider_name=analysis.provider_name,
                            model_version=analysis.model_version,
                            prompt_version=analysis.prompt_version,
                            evidence_path=evidence_ref,
                            metadata_json=event.metadata_json,
                        )
                    )

                aggregate_metrics(
                    session,
                    tenant_id,
                    camera.station_id,
                    camera_id,
                    analysis,
                    occurred_at=datetime.utcnow(),
                )

                job.provider_name = analysis.provider_name
                job.model_version = analysis.model_version
                job.prompt_version = analysis.prompt_version
                _mark_job_completed(session, job, provider)
            except Exception as exc:
                logger.error("Job %s failed: %s", job.id, exc)
                _mark_job_failed(session, job, exc, provider)
        return True


def reset_stuck_jobs(timeout_seconds: int = CCTV_WORKER_STUCK_TIMEOUT_SECONDS) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    reset_count = 0
    with get_session(platform_access=True) as session:
        stuck_jobs = (
            session.query(CCTVAnalysisJob)
            .filter(CCTVAnalysisJob.status == "processing")
            .all()
        )
        for job in stuck_jobs:
            if not job.started_at or job.started_at >= cutoff:
                continue
            job.status = "pending"
            job.retry_count = int(job.retry_count or 0) + 1
            job.error_message = "Reset after stuck processing timeout."
            job.started_at = None
            reset_count += 1
        session.commit()
    return reset_count


def main():
    logger.info("CCTV Worker starting...")
    while True:
        try:
            reset_stuck_jobs()
            if not process_cctv_jobs():
                time.sleep(10)
        except Exception as exc:
            logger.error("Worker loop error: %s", exc)
            time.sleep(5)
