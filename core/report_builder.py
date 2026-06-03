import json
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo


BELGRADE_TZ = ZoneInfo("Europe/Belgrade")
REPORT_SEND_HOUR = 20


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_now(now_utc: Optional[datetime] = None) -> datetime:
    now_utc = now_utc or utc_now()
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(BELGRADE_TZ)


def cadence_is_due(report_type: str, now_utc: Optional[datetime] = None) -> bool:
    now_local = _local_now(now_utc)
    if now_local.hour < REPORT_SEND_HOUR:
        return False
    if report_type == "daily":
        return True
    if report_type == "weekly":
        return now_local.weekday() == 4
    if report_type == "monthly":
        return now_local.day == monthrange(now_local.year, now_local.month)[1]
    return False


def get_period_window(report_type: str, now_utc: Optional[datetime] = None):
    now_local = _local_now(now_utc)
    period_end_local = now_local.replace(
        hour=REPORT_SEND_HOUR, minute=0, second=0, microsecond=0
    )
    if report_type == "daily":
        period_start_local = period_end_local.replace(hour=0)
    elif report_type == "weekly":
        period_start_local = (
            period_end_local - timedelta(days=period_end_local.weekday())
        ).replace(hour=0)
    elif report_type == "monthly":
        period_start_local = period_end_local.replace(day=1, hour=0)
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


def _rows_for_scope(conn, scope_type: str, scope_id: Optional[int], period_start, period_end):
    clauses = [
        "sub.processed = 1",
        "sub.data_json IS NOT NULL",
        "sub.timestamp >= %s",
        "sub.timestamp < %s",
    ]
    params: List = [period_start, period_end]

    if scope_type == "station":
        clauses.append("sub.station_id = %s")
        params.append(scope_id)
    elif scope_type == "region":
        clauses.append("st.region_id = %s")
        params.append(scope_id)

    query = f"""
        SELECT sub.id, sub.station_id, st.name AS station_name, r.name AS region_name, sub.data_json
        FROM submissions sub
        JOIN stations st ON st.id = sub.station_id
        LEFT JOIN regions r ON r.id = st.region_id
        WHERE {' AND '.join(clauses)}
        ORDER BY sub.timestamp DESC
    """
    return conn.execute(query, tuple(params)).fetchall()


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
    report_type: str,
    scope_type: str,
    scope_id: Optional[int],
    role: str,
    recipient_name: str,
    period_start,
    period_end,
) -> Dict:
    rows = _rows_for_scope(conn, scope_type, scope_id, period_start, period_end)
    metrics = _aggregate_metrics(rows)
    risk_score = metrics["overall_risk_score"]
    risk_band = _risk_band(risk_score)
    period_label = _period_label(report_type, period_start, period_end)

    scope_name = "kompaniju"
    if scope_type == "station" and rows:
        scope_name = f"stanicu {rows[0][2]}"
    elif scope_type == "region" and rows:
        scope_name = f"region {rows[0][3]}"

    if role == "Gas Station Manager":
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

    return {
        "title": title,
        "summary": summary,
        "period_label": period_label,
        "scope_type": scope_type,
        "scope_id": scope_id,
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
    }

