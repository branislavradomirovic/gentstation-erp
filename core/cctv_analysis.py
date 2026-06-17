from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Optional

from core.video_processor import parse_station_video

DEFAULT_PROMPT_VERSION = "ollama-cctv-v1"
DEFAULT_PROVIDER_NAME = "ollama"


@dataclass(frozen=True)
class NormalizedCCTVEvent:
    event_type: str
    severity: str
    confidence: float
    review_required: bool
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NormalizedCCTVMetric:
    metric_key: str
    metric_value: float
    confidence: float
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoAnalysisResult:
    provider_name: str
    model_version: str
    prompt_version: str
    events: list[NormalizedCCTVEvent] = field(default_factory=list)
    metrics: list[NormalizedCCTVMetric] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)


class VideoAnalysisProvider(ABC):
    name: str = "base"
    model_version: str = "unknown"
    prompt_version: str = DEFAULT_PROMPT_VERSION

    @abstractmethod
    def analyze(
        self,
        video_path: str,
        job_type: str,
        zones_context: Optional[Iterable[dict[str, Any]]] = None,
    ) -> VideoAnalysisResult:
        raise NotImplementedError


def _severity_from_risk(risk_score: float) -> str:
    if risk_score >= 70:
        return "high"
    if risk_score >= 35:
        return "medium"
    return "low"


def _confidence(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, numeric))


def _metric_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _build_normalized_result(payload: dict[str, Any]) -> tuple[list[NormalizedCCTVEvent], list[NormalizedCCTVMetric]]:
    confidence = _confidence(payload.get("confidence"))
    safety_score = _metric_value(payload.get("safety_score"))
    cleanliness_score = _metric_value(payload.get("cleanliness_score"))
    staff_score = _metric_value(payload.get("staff_score"))
    merchandising_score = _metric_value(payload.get("merchandising_score"))
    overall_risk = _metric_value(payload.get("overall_risk_score"))
    hazards = [str(item).strip() for item in (payload.get("hazards") or []) if str(item).strip()]
    stock_issues = [str(item).strip() for item in (payload.get("stock_issues") or []) if str(item).strip()]
    summary = str(payload.get("summary") or "").strip()
    customer_activity = str(payload.get("customer_activity") or "low").strip().lower()

    severity = _severity_from_risk(overall_risk)
    review_required = bool(hazards or stock_issues or severity in {"medium", "high"})
    base_metadata = {
        "summary": summary,
        "hazards": hazards,
        "stock_issues": stock_issues,
        "customer_activity": customer_activity,
        "raw": payload,
    }

    events: list[NormalizedCCTVEvent] = [
        NormalizedCCTVEvent(
            event_type="cctv_analysis_summary",
            severity=severity,
            confidence=confidence,
            review_required=review_required,
            metadata_json=base_metadata,
        )
    ]
    for hazard in hazards:
        events.append(
            NormalizedCCTVEvent(
                event_type="cctv_hazard_detected",
                severity="high" if severity == "high" else "medium",
                confidence=confidence,
                review_required=True,
                metadata_json={"hazard": hazard, "summary": summary},
            )
        )
    for issue in stock_issues:
        events.append(
            NormalizedCCTVEvent(
                event_type="cctv_stock_issue",
                severity="medium" if severity != "high" else "high",
                confidence=confidence,
                review_required=review_required,
                metadata_json={"issue": issue, "summary": summary},
            )
        )

    metrics = [
        NormalizedCCTVMetric("cleanliness_score", cleanliness_score, confidence, {"summary": summary}),
        NormalizedCCTVMetric("safety_score", safety_score, confidence, {"summary": summary}),
        NormalizedCCTVMetric("staff_score", staff_score, confidence, {"summary": summary}),
        NormalizedCCTVMetric("merchandising_score", merchandising_score, confidence, {"summary": summary}),
        NormalizedCCTVMetric("overall_risk_score", overall_risk, confidence, {"summary": summary}),
    ]
    return events, metrics


class OllamaVisionProvider(VideoAnalysisProvider):
    name = DEFAULT_PROVIDER_NAME

    def __init__(self, prompt_version: str = DEFAULT_PROMPT_VERSION):
        self.prompt_version = prompt_version
        self.model_version = "ollama:unknown"

    def analyze(
        self,
        video_path: str,
        job_type: str,
        zones_context: Optional[Iterable[dict[str, Any]]] = None,
    ) -> VideoAnalysisResult:
        del job_type, zones_context
        payload = parse_station_video(video_path)
        model_version = str(payload.get("_vision_model") or payload.get("_model_used") or "ollama:unknown")
        self.model_version = model_version
        events, metrics = _build_normalized_result(payload)
        return VideoAnalysisResult(
            provider_name=self.name,
            model_version=model_version,
            prompt_version=self.prompt_version,
            events=events,
            metrics=metrics,
            raw_payload=payload,
        )


def get_video_analysis_provider(job_type: str | None = None) -> VideoAnalysisProvider:
    del job_type
    return OllamaVisionProvider()


def aggregate_metrics(
    session,
    tenant_id: int,
    station_id: int,
    camera_id: int,
    result: VideoAnalysisResult,
    occurred_at: Optional[datetime] = None,
) -> None:
    from core.models import CCTVMetricHourly

    ts = occurred_at or datetime.utcnow()
    metric_date = ts.date()
    hour = ts.hour
    for metric in result.metrics:
        session.add(
            CCTVMetricHourly(
                tenant_id=tenant_id,
                station_id=station_id,
                camera_id=camera_id,
                metric_date=metric_date,
                hour=hour,
                metric_key=metric.metric_key,
                metric_value=metric.metric_value,
                confidence=metric.confidence,
                provider_name=result.provider_name,
                model_version=result.model_version,
                prompt_version=result.prompt_version,
            )
        )
