# gentstation_opus/ai_engine/risk_engine.py
"""
AI Risk Scoring Engine & Anomaly Detection

This module computes a station-level risk score combining:
- video-derived KPIs (cleanliness, safety)
- employee attendance (simple presence / count)
- customer traffic (from ai_reports or submissions)
- sales anomalies (if sales table exists; fallback: none)

It also detects anomalies vs historical KPI baselines and writes ai_alerts
into the DB when thresholds are crossed.
"""

import json
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from core.database import get_connection

# Tunable weights for the risk formula
WEIGHTS = {
    "safety": 0.5,
    "cleanliness": 0.2,
    "staff": 0.15,
    "efficiency": 0.1,
    "sentiment": 0.05,
    "incidents": 0.6,  # per incident multiplier
    "attendance": 0.3,
    "traffic": 0.2,
    "sales_anomaly": 0.8
}

def compute_station_risk_from_metrics(metrics: Dict[str, Any]) -> float:
    """
    Compute risk from a single station metrics dict (as produced by enterprise_analyzer)
    Return risk score on 0..100 (higher = worse)
    """
    # Safety inverse: lower safety -> higher risk
    safety = metrics.get("safety", metrics.get("safety_score", 7)) or 7
    cleanliness = metrics.get("cleanliness_score", metrics.get("cleanliness", 7)) or 7
    staff = metrics.get("staff", metrics.get("staff_score", 7)) or 7
    efficiency = metrics.get("efficiency", 7) or 7
    sentiment = metrics.get("sentiment", 0.0) or 0.0
    incidents = metrics.get("safety_violations") or metrics.get("incidents") or []
    num_incidents = len(incidents)

    # Normalize scales: safety 1-10 -> invert to risk contribution (10->0,1->9)
    safety_risk = (10 - safety) / 10.0
    cleanliness_risk = (10 - cleanliness) / 10.0
    staff_risk = (10 - staff) / 10.0
    efficiency_risk = (10 - efficiency) / 10.0
    sentiment_risk = max(0, -sentiment)  # negative sentiment increases risk

    base_risk = (
        safety_risk * WEIGHTS["safety"] +
        cleanliness_risk * WEIGHTS["cleanliness"] +
        staff_risk * WEIGHTS["staff"] +
        efficiency_risk * WEIGHTS["efficiency"] +
        sentiment_risk * WEIGHTS["sentiment"]
    )

    incident_risk = num_incidents * WEIGHTS["incidents"]
    raw_risk = base_risk + incident_risk

    # scale to 0..100
    score = min(100.0, round(raw_risk * 100, 2))
    return score

def record_ai_alert(conn, station_id: int, severity: str, message: str):
    now = datetime.utcnow().isoformat()
    conn.execute("INSERT INTO ai_alerts (station_id, severity, message, created_at) VALUES (?,?,?,?)", (station_id, severity, message, now))
    conn.commit()

def run_risk_cycle(threshold: float = 60.0) -> Dict[int, Dict[str, Any]]:
    """
    1) Read latest ai_reports for stations (most recent entry per station)
    2) Compute risk score
    3) Persist risk as new ai_reports entry or ai_alerts when risk > threshold
    4) Return mapping station_id -> {risk: float, details: {...}}
    """
    conn = get_connection()
    cur = conn.cursor()

    # Fetch last ai_report per station (group by station_id picking latest)
    rows = cur.execute("""
        SELECT a.station_id, a.kpi_json, a.created_at FROM ai_reports a
        INNER JOIN (
            SELECT station_id, MAX(created_at) as ma FROM ai_reports GROUP BY station_id
        ) sub ON sub.station_id = a.station_id AND sub.ma = a.created_at
        WHERE a.station_id IS NOT NULL
    """).fetchall()

    results = {}
    for station_id, kpi_json, created_at in rows:
        try:
            metrics = json.loads(kpi_json) if kpi_json else {}
        except Exception:
            metrics = {}
        risk = compute_station_risk_from_metrics(metrics)
        results[station_id] = {"risk": risk, "metrics": metrics, "last_seen": created_at}

        # Persist alert if above threshold
        if risk >= threshold:
            msg = f"Station {station_id} risk score {risk} >= threshold {threshold}"
            record_ai_alert(conn, station_id, "HIGH", msg)

            # Optionally also insert a General Manager report or annotate DB; for now we only alert

    return results

# Optional: compute station-level anomalies from historical metric series
def detect_kpi_anomalies(station_id: int, metric_key: str, current_value: float, window: int = 20) -> Tuple[bool, Optional[Dict[str, float]]]:
    """
    Compare current_value with historical average for metric_key (read from ai_reports.kpi_json).
    If relative deviation > 0.5 flag anomaly.
    Return (is_anomaly, details)
    """
    conn = get_connection()
    cur = conn.cursor()
    rows = cur.execute("SELECT kpi_json FROM ai_reports WHERE station_id = ? ORDER BY created_at DESC LIMIT ?", (station_id, window)).fetchall()
    vals = []
    for (kjson,) in rows:
        try:
            j = json.loads(kjson)
            v = None
            # Try various keys
            for k in (metric_key, metric_key + "_score", metric_key + "ness"):
                if isinstance(j.get(k), (int, float)):
                    v = j.get(k); break
            if v is not None:
                vals.append(float(v))
        except:
            continue
    if not vals:
        return False, None
    avg = sum(vals) / len(vals)
    if avg == 0:
        return False, None
    dev = abs(current_value - avg) / (avg if avg else 1)
    if dev > 0.5:
        return True, {"avg": avg, "current": current_value, "dev": dev}
    return False, {"avg": avg, "current": current_value, "dev": dev}