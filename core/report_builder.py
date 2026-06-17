import json
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from core.cctv_reports import get_cctv_summary_for_scope
from core.database import get_session
from core.subscription import FEATURE_CCTV_INTELLIGENCE, is_feature_enabled
from core.tenant_context import TenantContext


BELGRADE_TZ = ZoneInfo("Europe/Belgrade")
REPORT_SEND_HOUR = 20


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_now(now_utc: Optional[datetime] = None) -> datetime:
    now_utc = now_utc or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(BELGRADE_TZ)


def _coerce_timezone(timezone_name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo((timezone_name or "").strip() or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _schedule_local_now(
    schedule: Optional[dict] = None,
    now_utc: Optional[datetime] = None,
) -> datetime:
    now_utc = now_utc or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    tz_name = schedule.get("timezone") if schedule else None
    return now_utc.astimezone(_coerce_timezone(tz_name))


def _scheduled_wall_clock(schedule: Optional[dict], now_local: datetime) -> datetime:
    send_hour = REPORT_SEND_HOUR
    send_minute = 0
    if schedule and schedule.get("send_time") is not None:
        send_time = schedule["send_time"]
        send_hour = int(getattr(send_time, "hour", REPORT_SEND_HOUR))
        send_minute = int(getattr(send_time, "minute", 0))
    return now_local.replace(
        hour=send_hour,
        minute=send_minute,
        second=0,
        microsecond=0,
    )


def cadence_is_due(report_type: str, now_utc: Optional[datetime] = None) -> bool:
    return schedule_is_due({"report_type": report_type}, now_utc=now_utc)


def get_period_window(report_type: str, now_utc: Optional[datetime] = None):
    return get_period_window_for_schedule({"report_type": report_type}, now_utc=now_utc)


def schedule_is_due(schedule: dict, now_utc: Optional[datetime] = None) -> bool:
    report_type = str(schedule.get("report_type") or "")
    now_local = _schedule_local_now(schedule, now_utc)
    scheduled_at_local = _scheduled_wall_clock(schedule, now_local)
    if now_local < scheduled_at_local:
        return False

    if report_type == "daily":
        return True
    if report_type == "weekly":
        return now_local.weekday() == int(schedule.get("weekly_day", 4) or 4)
    if report_type == "monthly":
        if schedule.get("use_last_day"):
            return now_local.day == monthrange(now_local.year, now_local.month)[1]
        monthly_day = int(schedule.get("monthly_day", 1) or 1)
        return now_local.day == monthly_day
    return False


def get_period_window_for_schedule(schedule: dict, now_utc: Optional[datetime] = None):
    report_type = str(schedule.get("report_type") or "")
    now_local = _schedule_local_now(schedule, now_utc)
    period_end_local = _scheduled_wall_clock(schedule, now_local)
    if report_type == "daily":
        period_start_local = period_end_local.replace(hour=0, minute=0)
    elif report_type == "weekly":
        period_start_local = (
            period_end_local - timedelta(days=period_end_local.weekday())
        ).replace(hour=0, minute=0)
    elif report_type == "monthly":
        period_start_local = period_end_local.replace(day=1, hour=0, minute=0)
    else:
        raise ValueError(f"Unsupported report_type: {report_type}")

    return (
        period_start_local.astimezone(timezone.utc).replace(tzinfo=None),
        period_end_local.astimezone(timezone.utc).replace(tzinfo=None),
        period_end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _risk_band(score: float) -> str:
    if score >= 70:
        return "visok"
    if score >= 40:
        return "srednji"
    return "nizak"


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value or default)
    except Exception:
        return float(default)


def _load_json(payload) -> Dict:
    if isinstance(payload, dict):
        return payload
    if not payload:
        return {}
    try:
        return json.loads(payload)
    except Exception:
        return {}


def _rows_for_scope(
    conn,
    tenant_id: int,
    scope_type: str,
    scope_id: Optional[int],
    period_start,
    period_end,
):
    clauses = [
        "sub.tenant_id = %s",
        "sub.processed = 1",
        "sub.data_json IS NOT NULL",
        "sub.timestamp >= %s",
        "sub.timestamp < %s",
    ]
    params: List = [tenant_id, period_start, period_end]

    if scope_type == "employee":
        clauses.append("sub.employee_id = %s")
        params.append(scope_id)
    elif scope_type == "station":
        clauses.append("sub.station_id = %s")
        params.append(scope_id)
    elif scope_type == "region":
        clauses.append("st.region_id = %s")
        params.append(scope_id)

    query = f"""
        SELECT sub.id, sub.station_id, st.name AS station_name, r.name AS region_name, sub.data_json
        FROM submissions sub
        JOIN stations st ON st.id = sub.station_id AND st.tenant_id = sub.tenant_id
        LEFT JOIN regions r ON r.id = st.region_id AND r.tenant_id = sub.tenant_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sub.timestamp DESC
    """
    return conn.execute(query, tuple(params)).fetchall()


def _scope_name(conn, tenant_id: int, scope_type: str, scope_id: Optional[int]) -> str:
    if scope_type == "employee" and scope_id is not None:
        row = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(COALESCE(name,'') || ' ' || COALESCE(surname,'')), ''), email, username)
            FROM users
            WHERE tenant_id = %s AND id = %s
            """,
            (tenant_id, scope_id),
        ).fetchone()
        return f"zaposlenog {row[0]}" if row and row[0] else "zaposlenog"

    if scope_type == "station" and scope_id is not None:
        row = conn.execute(
            "SELECT name FROM stations WHERE tenant_id = %s AND id = %s",
            (tenant_id, scope_id),
        ).fetchone()
        return f"stanicu {row[0]}" if row and row[0] else "stanicu"

    if scope_type == "region" and scope_id is not None:
        row = conn.execute(
            "SELECT name FROM regions WHERE tenant_id = %s AND id = %s",
            (tenant_id, scope_id),
        ).fetchone()
        return f"region {row[0]}" if row and row[0] else "region"

    row = conn.execute(
        "SELECT name FROM tenants WHERE id = %s",
        (tenant_id,),
    ).fetchone()
    return f"kompaniju {row[0]}" if row and row[0] else "kompaniju"


def _aggregate_metrics(rows) -> Dict:
    payloads = [_load_json(row[4]) for row in rows]
    if not payloads:
        return {
            "submission_count": 0,
            "overall_risk_score": 0.0,
            "safety_score": 0.0,
            "cleanliness_score": 0.0,
            "staff_score": 0.0,
            "merchandising_score": 0.0,
            "hazards": [],
            "stock_issues": [],
            "improvement_actions": [],
        }

    metrics = {
        "submission_count": len(payloads),
        "overall_risk_score": round(mean(_safe_float(p.get("overall_risk_score"), 0.0) for p in payloads), 2),
        "safety_score": round(mean(_safe_float(p.get("safety_score"), 0.0) for p in payloads), 2),
        "cleanliness_score": round(mean(_safe_float(p.get("cleanliness_score"), 0.0) for p in payloads), 2),
        "staff_score": round(mean(_safe_float(p.get("staff_score"), 0.0) for p in payloads), 2),
        "merchandising_score": round(mean(_safe_float(p.get("merchandising_score"), 0.0) for p in payloads), 2),
    }

    hazards: List[str] = []
    stock_issues: List[str] = []
    actions: List[str] = []
    for payload in payloads:
        for key, bag in (
            ("hazards", hazards),
            ("stock_issues", stock_issues),
            ("improvement_actions", actions),
        ):
            value = payload.get(key) or []
            if isinstance(value, str):
                value = [value]
            for item in value:
                item_text = str(item).strip()
                if item_text and item_text not in bag:
                    bag.append(item_text)

    metrics["hazards"] = hazards[:5]
    metrics["stock_issues"] = stock_issues[:5]
    metrics["improvement_actions"] = actions[:5]
    return metrics


def _missing_submission_summary(
    conn,
    tenant_id: int,
    scope_type: str,
    scope_id: Optional[int],
    period_start,
    period_end,
) -> Dict:
    if scope_type == "employee" and scope_id is not None:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM submissions
            WHERE tenant_id = %s
              AND employee_id = %s
              AND timestamp >= %s
              AND timestamp < %s
            """,
            (tenant_id, scope_id, period_start, period_end),
        ).fetchone()
        count = int(row[0] or 0) if row else 0
        return {
            "missing_employee_count": 1 if count == 0 else 0,
            "missing_station_count": 0,
            "missing_employee_names": [],
            "missing_station_names": [],
            "employee_missing_submission": count == 0,
        }

    if scope_type == "station" and scope_id is not None:
        rows = conn.execute(
            """
            SELECT COALESCE(NULLIF(TRIM(COALESCE(u.name,'') || ' ' || COALESCE(u.surname,'')), ''), u.email, u.username) AS full_name
            FROM users u
            WHERE u.tenant_id = %s
              AND u.role = 'Employee'
              AND u.station_id = %s
              AND u.is_active = TRUE
              AND NOT EXISTS (
                  SELECT 1
                  FROM submissions sub
                  WHERE sub.tenant_id = u.tenant_id
                    AND sub.employee_id = u.id
                    AND sub.timestamp >= %s
                    AND sub.timestamp < %s
              )
            ORDER BY full_name
            """,
            (tenant_id, scope_id, period_start, period_end),
        ).fetchall()
        names = [row[0] for row in rows if row and row[0]]
        return {
            "missing_employee_count": len(names),
            "missing_station_count": 0,
            "missing_employee_names": names[:10],
            "missing_station_names": [],
            "employee_missing_submission": False,
        }

    station_filter = ""
    params: List = [tenant_id, period_start, period_end]
    if scope_type == "region" and scope_id is not None:
        station_filter = "AND st.region_id = %s"
        params.append(scope_id)

    rows = conn.execute(
        f"""
        SELECT st.name
        FROM stations st
        WHERE st.tenant_id = %s
          {station_filter}
          AND NOT EXISTS (
              SELECT 1
              FROM submissions sub
              WHERE sub.tenant_id = st.tenant_id
                AND sub.station_id = st.id
                AND sub.timestamp >= %s
                AND sub.timestamp < %s
          )
        ORDER BY st.name
        """,
        tuple(params),
    ).fetchall()
    station_names = [row[0] for row in rows if row and row[0]]
    return {
        "missing_employee_count": 0,
        "missing_station_count": len(station_names),
        "missing_employee_names": [],
        "missing_station_names": station_names[:10],
        "employee_missing_submission": False,
    }


def _period_label(report_type: str, period_start, period_end) -> str:
    start_local = period_start.replace(tzinfo=timezone.utc).astimezone(BELGRADE_TZ)
    end_local = period_end.replace(tzinfo=timezone.utc).astimezone(BELGRADE_TZ)
    if report_type == "daily":
        return start_local.strftime("%d.%m.%Y.")
    if report_type == "weekly":
        return f"{start_local.strftime('%d.%m.%Y.')} - {end_local.strftime('%d.%m.%Y.')}"
    return start_local.strftime("%m/%Y")


def build_management_report(
    conn,
    tenant_id: int,
    report_type: str,
    scope_type: str,
    scope_id: Optional[int],
    role: str,
    recipient_name: str,
    period_start,
    period_end,
) -> Dict:
    rows = _rows_for_scope(conn, tenant_id, scope_type, scope_id, period_start, period_end)
    metrics = _aggregate_metrics(rows)
    missing = _missing_submission_summary(
        conn,
        tenant_id,
        scope_type,
        scope_id,
        period_start,
        period_end,
    )
    risk_score = metrics["overall_risk_score"]
    risk_band = _risk_band(risk_score)
    period_label = _period_label(report_type, period_start, period_end)

    scope_name = _scope_name(conn, tenant_id, scope_type, scope_id)

    if role == "Employee":
        title = f"{report_type.title()} lični izveštaj"
        summary = (
            f"Poštovani {recipient_name}, za {scope_name} u periodu {period_label} obrađeno je "
            f"{metrics['submission_count']} vaših video prijava. Ukupan nivo rizika je {risk_score}/100, što predstavlja {risk_band} nivo rizika."
        )
    elif role == "Gas Station Manager":
        title = f"{report_type.title()} izveštaj za stanicu"
        summary = (
            f"Poštovani {recipient_name}, za {scope_name} u periodu {period_label} obrađeno je "
            f"{metrics['submission_count']} video prijava. Ukupan nivo rizika je {risk_score}/100, što predstavlja {risk_band} nivo rizika."
        )
    elif role == "Region Manager":
        title = f"{report_type.title()} regionalni izveštaj"
        summary = (
            f"Poštovani {recipient_name}, za {scope_name} u periodu {period_label} obrađeno je "
            f"{metrics['submission_count']} video prijava. Prosečan regionalni rizik iznosi {risk_score}/100."
        )
    else:
        title = f"{report_type.title()} izvršni izveštaj"
        summary = (
            f"Poštovani {recipient_name}, za {scope_name} u periodu {period_label} obrađeno je "
            f"{metrics['submission_count']} video prijava. Ukupan rizik kompanije iznosi {risk_score}/100."
        )

    actions = metrics["improvement_actions"] or [
        "Nastaviti redovan menadžerski obilazak i pratiti naredni ciklus izveštavanja."
    ]

    payload = {
        "title": title,
        "summary": summary,
        "period_label": period_label,
        "tenant_id": tenant_id,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "scope_name": scope_name,
        "role": role,
        "submission_count": metrics["submission_count"],
        "overall_risk_score": risk_score,
        "risk_band": risk_band,
        "safety_score": metrics["safety_score"],
        "cleanliness_score": metrics["cleanliness_score"],
        "staff_score": metrics["staff_score"],
        "merchandising_score": metrics["merchandising_score"],
        "hazards": metrics["hazards"],
        "stock_issues": metrics["stock_issues"],
        "improvement_actions": actions,
        "missing_employee_count": missing["missing_employee_count"],
        "missing_station_count": missing["missing_station_count"],
        "missing_employee_names": missing["missing_employee_names"],
        "missing_station_names": missing["missing_station_names"],
        "employee_missing_submission": missing["employee_missing_submission"],
    }

    tenant_context = TenantContext(tenant_id=tenant_id)
    if is_feature_enabled(conn, FEATURE_CCTV_INTELLIGENCE, tenant_context=tenant_context):
        with get_session() as session:
            payload["cctv_intelligence"] = get_cctv_summary_for_scope(
                session,
                tenant_id,
                scope_type=scope_type,
                scope_id=scope_id,
                period_start=period_start,
                period_end=period_end,
                conn=conn,
            )

    return payload
