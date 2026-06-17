from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import core.cctv_worker as cctv_worker
import core.cctv_analysis as cctv_analysis
from core.cctv_analysis import NormalizedCCTVEvent, NormalizedCCTVMetric, VideoAnalysisResult
from core.models import CCTVAnalysisJob, CCTVCamera


class FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model

    def filter(self, *args):
        del args
        return self

    def filter_by(self, **kwargs):
        self.session.last_filter_by = kwargs
        return self

    def order_by(self, *args):
        del args
        return self

    def first(self):
        if self.model is CCTVAnalysisJob:
            for job in self.session.jobs:
                if job.status == "pending":
                    return job
        return None

    def all(self):
        if self.model is CCTVAnalysisJob:
            return [job for job in self.session.jobs if job.status == "processing"]
        return []


class FakeSession:
    def __init__(self, jobs, camera):
        self.jobs = jobs
        self.camera = camera
        self.added = []
        self.commits = 0
        self.last_filter_by = {}

    def query(self, model):
        return FakeQuery(self, model)

    def get(self, model, obj_id):
        del model, obj_id
        return self.camera

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def connection(self):
        return self


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeProvider:
    name = "ollama"
    model_version = "bakllava:latest"
    prompt_version = "ollama-cctv-v1"

    def __init__(self, should_fail=False):
        self.should_fail = should_fail

    def analyze(self, video_path, job_type, zones_context=None):
        del video_path, job_type, zones_context
        if self.should_fail:
            raise RuntimeError("provider failure")
        return VideoAnalysisResult(
            provider_name=self.name,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            events=[
                NormalizedCCTVEvent(
                    event_type="cctv_analysis_summary",
                    severity="high",
                    confidence=0.87,
                    review_required=True,
                    metadata_json={"summary": "demo"},
                )
            ],
            metrics=[
                NormalizedCCTVMetric(
                    metric_key="safety_score",
                    metric_value=8.0,
                    confidence=0.87,
                    metadata_json={"summary": "demo"},
                )
            ],
            raw_payload={"summary": "demo"},
        )


def test_ollama_provider_normalizes_parse_payload(monkeypatch):
    monkeypatch.setattr(
        cctv_analysis,
        "parse_station_video",
        lambda video_path: {
            "confidence": 0.92,
            "safety_score": 9,
            "cleanliness_score": 8,
            "staff_score": 7,
            "merchandising_score": 6,
            "overall_risk_score": 74,
            "hazards": ["spill"],
            "stock_issues": ["low stock"],
            "summary": "demo summary",
            "customer_activity": "high",
            "_vision_model": "bakllava:latest",
        },
    )

    provider = cctv_analysis.OllamaVisionProvider(prompt_version="prompt-v2")
    result = provider.analyze("/tmp/demo.mp4", "clip_analysis", zones_context=[{"name": "A"}])

    assert result.provider_name == "ollama"
    assert result.model_version == "bakllava:latest"
    assert result.prompt_version == "prompt-v2"
    assert provider.model_version == "bakllava:latest"
    assert any(event.event_type == "cctv_analysis_summary" for event in result.events)
    assert any(event.event_type == "cctv_hazard_detected" for event in result.events)
    assert any(metric.metric_key == "overall_risk_score" for metric in result.metrics)
    summary_event = next(event for event in result.events if event.event_type == "cctv_analysis_summary")
    overall_risk_metric = next(metric for metric in result.metrics if metric.metric_key == "overall_risk_score")
    assert summary_event.review_required is True
    assert summary_event.confidence == 0.92
    assert overall_risk_metric.confidence == 0.92


def _fake_job(retry_count=0, status="pending", started_at=None):
    return SimpleNamespace(
        id=101,
        tenant_id=7,
        camera_id=33,
        job_type="clip_analysis",
        video_path="/tmp/demo.mp4",
        source_filename="demo.mp4",
        source_blob=b"fake-video-bytes",
        status=status,
        retry_count=retry_count,
        error_message=None,
        started_at=started_at,
        completed_at=None,
        provider_name=None,
        model_version=None,
        prompt_version=None,
    )


def _fake_camera():
    return SimpleNamespace(
        station_id=44,
        zones=[SimpleNamespace(name="Entrance", zone_type="entrance")],
    )


def test_cctv_worker_creates_normalized_events_and_metrics(monkeypatch):
    session = FakeSession([_fake_job()], _fake_camera())
    monkeypatch.setattr(cctv_worker, "get_session", lambda platform_access=False: FakeSessionContext(session))
    monkeypatch.setattr(cctv_worker, "require_feature", lambda *args, **kwargs: None)
    monkeypatch.setattr(cctv_worker, "save_event_evidence", lambda source_file, event_id: f"evidence/7/{event_id}.mp4")
    monkeypatch.setattr(cctv_worker, "get_video_analysis_provider", lambda job_type=None: FakeProvider())

    processed = cctv_worker.process_cctv_jobs()

    assert processed is True
    assert session.jobs[0].status == "completed"
    assert session.jobs[0].provider_name == "ollama"
    assert session.jobs[0].model_version == "bakllava:latest"
    assert session.jobs[0].prompt_version == "ollama-cctv-v1"
    assert any(obj.__class__.__name__ == "CCTVEvent" for obj in session.added)
    assert any(obj.__class__.__name__ == "CCTVMetricHourly" for obj in session.added)
    event = next(obj for obj in session.added if obj.__class__.__name__ == "CCTVEvent")
    metric = next(obj for obj in session.added if obj.__class__.__name__ == "CCTVMetricHourly")
    assert event.review_required is True
    assert event.model_version == "bakllava:latest"
    assert metric.metric_key == "safety_score"
    assert metric.model_version == "bakllava:latest"


def test_cctv_worker_retries_failed_jobs_before_marking_failed(monkeypatch):
    job = _fake_job(retry_count=0)
    session = FakeSession([job], _fake_camera())
    monkeypatch.setattr(cctv_worker, "get_session", lambda platform_access=False: FakeSessionContext(session))
    monkeypatch.setattr(cctv_worker, "require_feature", lambda *args, **kwargs: None)
    monkeypatch.setattr(cctv_worker, "save_event_evidence", lambda source_file, event_id: f"evidence/7/{event_id}.mp4")
    monkeypatch.setattr(cctv_worker, "get_video_analysis_provider", lambda job_type=None: FakeProvider(should_fail=True))
    monkeypatch.setattr(cctv_worker, "CCTV_WORKER_MAX_RETRIES", 3)

    processed = cctv_worker.process_cctv_jobs()

    assert processed is True
    assert job.status == "pending"
    assert job.retry_count == 1
    assert job.error_message == "provider failure"
    assert job.provider_name == "ollama"
    assert job.model_version == "bakllava:latest"
    assert job.prompt_version == "ollama-cctv-v1"


def test_cctv_worker_marks_jobs_failed_after_max_retries(monkeypatch):
    job = _fake_job(retry_count=2)
    session = FakeSession([job], _fake_camera())
    monkeypatch.setattr(cctv_worker, "get_session", lambda platform_access=False: FakeSessionContext(session))
    monkeypatch.setattr(cctv_worker, "require_feature", lambda *args, **kwargs: None)
    monkeypatch.setattr(cctv_worker, "save_event_evidence", lambda source_file, event_id: f"evidence/7/{event_id}.mp4")
    monkeypatch.setattr(cctv_worker, "get_video_analysis_provider", lambda job_type=None: FakeProvider(should_fail=True))
    monkeypatch.setattr(cctv_worker, "CCTV_WORKER_MAX_RETRIES", 3)

    processed = cctv_worker.process_cctv_jobs()

    assert processed is True
    assert job.status == "failed"
    assert job.retry_count == 3


def test_cctv_worker_resets_stuck_jobs(monkeypatch):
    stuck_job = _fake_job(status="processing", retry_count=1, started_at=datetime.utcnow() - timedelta(minutes=30))
    recent_job = _fake_job(status="processing", retry_count=0, started_at=datetime.utcnow() - timedelta(seconds=30))
    session = FakeSession([stuck_job, recent_job], _fake_camera())
    monkeypatch.setattr(cctv_worker, "get_session", lambda platform_access=False: FakeSessionContext(session))

    reset_count = cctv_worker.reset_stuck_jobs(timeout_seconds=60)

    assert reset_count == 1
    assert stuck_job.status == "pending"
    assert stuck_job.retry_count == 2
    assert stuck_job.started_at is None
    assert "stuck processing timeout" in stuck_job.error_message.lower()
    assert recent_job.status == "processing"
