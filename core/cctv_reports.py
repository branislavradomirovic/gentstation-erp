from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import and_, case, func, select

from core.models import CCTVEvent, CCTVMetricHourly, Region, Station
from core.subscription import FEATURE_CCTV_INTELLIGENCE, is_feature_enabled


def _window_bounds(
    *,
    days: Optional[int] = None,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> tuple[datetime, datetime]:
    if period_start and period_end:
        return period_start, period_end

    end_ts = period_end or datetime.utcnow()
    start_ts = period_start or (end_ts - timedelta(days=days or 7))
    return start_ts, end_ts


def _station_scope_filter(model, scope_type: str, scope_id: Optional[int]):
    if scope_type == "station" and scope_id is not None:
        return model.station_id == scope_id
    return None


def _region_scope_join_and_filter(stmt, model, scope_type: str, scope_id: Optional[int]):
    if scope_type == "region" and scope_id is not None:
        return stmt.join(Station, model.station_id == Station.id).where(
            Station.region_id == scope_id
        )
    return stmt


def get_cctv_summary_for_scope(
    session,
    tenant_id: int,
    *,
    scope_type: str,
    scope_id: Optional[int],
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
    conn=None,
) -> Dict[str, Any]:
    """Build a tenant-scoped Tier 2 CCTV summary for reports and dashboards."""
    if conn is not None and not is_feature_enabled(conn, FEATURE_CCTV_INTELLIGENCE):
        return {"enabled": False}

    start_ts, end_ts = _window_bounds(
        period_start=period_start,
        period_end=period_end,
    )
    start_date = start_ts.date()
    end_date = end_ts.date()

    metric_stmt = (
        select(
            CCTVMetricHourly.metric_key,
            func.avg(CCTVMetricHourly.metric_value).label("avg_value"),
            func.avg(CCTVMetricHourly.confidence).label("avg_confidence"),
            func.sum(CCTVMetricHourly.metric_value).label("total_value"),
        )
        .where(
            and_(
                CCTVMetricHourly.tenant_id == tenant_id,
                CCTVMetricHourly.metric_date >= start_date,
                CCTVMetricHourly.metric_date <= end_date,
            )
        )
        .group_by(CCTVMetricHourly.metric_key)
    )
    station_filter = _station_scope_filter(CCTVMetricHourly, scope_type, scope_id)
    if station_filter is not None:
        metric_stmt = metric_stmt.where(station_filter)
    metric_stmt = _region_scope_join_and_filter(
        metric_stmt, CCTVMetricHourly, scope_type, scope_id
    )

    metric_rows = session.execute(metric_stmt).all()
    average_metrics = {
        row.metric_key: round(float(row.avg_value or 0), 2) for row in metric_rows
    }
    confidence_by_metric = {
        row.metric_key: round(float(row.avg_confidence or 0), 2) for row in metric_rows
    }
    volume_summary = {
        row.metric_key: round(float(row.total_value or 0), 2) for row in metric_rows
    }

    event_stmt = select(
        func.count(CCTVEvent.id).label("total_events"),
        func.sum(case((CCTVEvent.review_required.is_(True), 1), else_=0)).label(
            "review_required_events"
        ),
        func.sum(case((CCTVEvent.status.in_(("new", "acknowledged")), 1), else_=0)).label(
            "open_events"
        ),
        func.sum(case((CCTVEvent.severity == "high", 1), else_=0)).label(
            "high_severity_events"
        ),
    ).where(
        and_(
            CCTVEvent.tenant_id == tenant_id,
            CCTVEvent.occurred_at >= start_ts,
            CCTVEvent.occurred_at < end_ts,
        )
    )
    station_filter = _station_scope_filter(CCTVEvent, scope_type, scope_id)
    if station_filter is not None:
        event_stmt = event_stmt.where(station_filter)
    event_stmt = _region_scope_join_and_filter(
        event_stmt, CCTVEvent, scope_type, scope_id
    )

    event_row = session.execute(event_stmt).one()

    return {
        "enabled": True,
        "period_start": start_ts.isoformat(),
        "period_end": end_ts.isoformat(),
        "average_metrics": average_metrics,
        "confidence_by_metric": confidence_by_metric,
        "volume_summary": volume_summary,
        "event_summary": {
            "total_events": int(event_row.total_events or 0),
            "review_required_events": int(event_row.review_required_events or 0),
            "open_events": int(event_row.open_events or 0),
            "high_severity_events": int(event_row.high_severity_events or 0),
        },
    }


def get_station_benchmark_rows(
    session,
    tenant_id: int,
    metric_key: str,
    *,
    region_name: Optional[str] = None,
):
    stmt = (
        select(
            Station.name.label("station"),
            func.sum(CCTVMetricHourly.metric_value).label("value"),
            func.avg(CCTVMetricHourly.confidence).label("confidence"),
        )
        .join(Station, CCTVMetricHourly.station_id == Station.id)
        .where(
            and_(
                CCTVMetricHourly.tenant_id == tenant_id,
                CCTVMetricHourly.metric_key == metric_key,
            )
        )
        .group_by(Station.name)
        .order_by(func.sum(CCTVMetricHourly.metric_value).desc())
    )
    if region_name and region_name != "All Regions":
        stmt = stmt.join(Region, Station.region_id == Region.id).where(
            Region.name == region_name
        )
    return session.execute(stmt).all()


def get_region_benchmark_rows(session, tenant_id: int, metric_key: str):
    stmt = (
        select(
            Region.name.label("region"),
            func.sum(CCTVMetricHourly.metric_value).label("value"),
            func.avg(CCTVMetricHourly.confidence).label("confidence"),
        )
        .join(Station, CCTVMetricHourly.station_id == Station.id)
        .join(Region, Station.region_id == Region.id)
        .where(
            and_(
                CCTVMetricHourly.tenant_id == tenant_id,
                CCTVMetricHourly.metric_key == metric_key,
            )
        )
        .group_by(Region.name)
        .order_by(func.sum(CCTVMetricHourly.metric_value).desc())
    )
    return session.execute(stmt).all()
