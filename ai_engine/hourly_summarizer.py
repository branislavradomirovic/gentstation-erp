# gentstation_opus/ai_engine/hourly_summarizer.py
import os, json, time, traceback
from datetime import datetime
from ..core.database import get_connection
from .video_speech_analyzer import transcribe_audio, analyze_speech_sentiment
from .gemini_client import generate_from_prompt, extract_json_block
from ..services.notifier import notify_station_manager
from ..core.activity_logger import log_activity

# Build enterprise prompt (concise helper)
def build_prompt(video_map_text: str):
    return f"""
You are an AI operational auditor for a global fuel retail chain.
Analyze provided video/audio metadata and transcribed speech (if any).
Be concise, produce FOUR role reports and APPEND a JSON block in a fenced ```json block as described.

Input:
{video_map_text}

Instructions:
- For each station produce [STATION_ID: X] block.
- Produce [ROLE_REPORT: Gas Station Manager], [ROLE_REPORT: Region Manager], [ROLE_REPORT: Region Director], [ROLE_REPORT: General Manager]
- At the END include a fenced ```json block with keys: stations, regions, company
"""

# Simple risk score based on metrics (lower = better)
def compute_risk_score(metrics: dict) -> float:
    # risk: combine safety, incidents, sentiment. Higher means more risk.
    safety = metrics.get("safety", 7)
    incidents = len(metrics.get("incidents", []) or [])
    sentiment = metrics.get("sentiment", 0.0)  # -1..1
    # normalized
    risk = max(0, 10 - safety) + incidents*2 + (1 - sentiment) * 2
    return round(risk, 2)

# Simple anomaly detection by looking for large deviations vs historical average
def detect_anomaly(conn, station_id, metric_key, value):
    # query last N entries for same station
    cur = conn.cursor()
    rows = cur.execute("SELECT kpi_json FROM ai_reports WHERE station_id = ? ORDER BY created_at DESC LIMIT 20", (station_id,)).fetchall()
    vals = []
    for r in rows:
        try:
            j = json.loads(r[0])
            v = j.get(metric_key)
            if isinstance(v, (int, float)):
                vals.append(v)
        except:
            continue
    if not vals:
        return False, None
    avg = sum(vals)/len(vals)
    if avg == 0:
        return False, None
    # z-score like
    dev = abs(value - avg) / (avg if avg else 1)
    if dev > 0.5:  # 50% change threshold — tuneable
        return True, {"avg": avg, "current": value, "dev": round(dev, 2)}
    return False, {"avg": avg, "current": value, "dev": round(dev, 2)}

def run_batch_once():
    conn = get_connection()
    cur = conn.cursor()
    subs = cur.execute("SELECT id, station_id, employee_id, video_path, audio_path, role, timestamp FROM submissions WHERE processed = 0").fetchall()
    if not subs:
        print("No pending submissions.")
        return
    # prepare metadata and transcriptions
    video_map = ""
    per_station = {}
    for s in subs:
        sid, station_id, employee_id, video_path, audio_path, role, ts = s
        if station_id is None:
            continue
        # transcribe audio if present
        asr = transcribe_audio(audio_path) if audio_path else {"transcript":"", "segments":[]}
        sentiment = analyze_speech_sentiment(asr.get("transcript",""))
        entry = {
            "submission_id": sid,
            "station_id": station_id,
            "employee_id": employee_id,
            "role": role,
            "video": video_path,
            "audio": audio_path,
            "timestamp": ts,
            "transcript": asr.get("transcript",""),
            "sentiment": sentiment
        }
        per_station.setdefault(station_id, []).append(entry)
        video_map += f"- station {station_id} | file: {os.path.basename(video_path) if video_path else 'N/A'} | role: {role} | ts: {ts}\\n"
        if asr.get("transcript"):
            video_map += f"  TRANSCRIPT: {asr.get('transcript')[:300]}\\n"
    prompt = build_prompt(video_map)
    print("Calling Gemini / prompt model...")
    response_text = generate_from_prompt(prompt)
    print("Model returned, extracting JSON...")
    parsed = extract_json_block(response_text)
    if not parsed:
        print("No JSON parsed. Saving raw model output as General Manager report.")
        # save raw output as fallback report
        now = datetime.utcnow().isoformat()
        cur.execute("INSERT INTO ai_reports (created_at, report_role, station_id, region_id, report_text) VALUES (?,?,?,?,?)",
                    (now, "General Manager", None, None, response_text))
        conn.commit()
        # mark submissions processed to avoid loop (or choose not to)
        for s in subs:
            cur.execute("UPDATE submissions SET processed=1 WHERE id=?", (s[0],))
        conn.commit()
        return
    # parsed contains stations list etc.
    stations = parsed.get("stations", [])
    regions = parsed.get("regions", [])
    company = parsed.get("company", {})
    # store station reports and send notifications
    for st in stations:
        station_id = st.get("station_id")
        metrics = {
            "safety": st.get("safety"),
            "cleanliness": st.get("cleanliness"),
            "staff": st.get("staff"),
            "efficiency": st.get("efficiency"),
            "customer_experience": st.get("customer_experience"),
            "sentiment": st.get("sentiment"),
            "incidents": st.get("incidents", []),
            "trend": st.get("trend")
        }
        risk = compute_risk_score(metrics)
        kpi_json = json.dumps(metrics, ensure_ascii=False)
        now = datetime.utcnow().isoformat()
        cur.execute("""
            INSERT INTO ai_reports (created_at, report_role, station_id, region_id, report_text,
                                    sentiment, safety_score, cleanliness_score, staff_score,
                                    efficiency_score, customer_score, incidents_json, kpi_json, trend)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (now, "Gas Station Manager", station_id, None, "", metrics.get("sentiment"),
              metrics.get("safety"), metrics.get("cleanliness"), metrics.get("staff"),
              metrics.get("efficiency"), metrics.get("customer_experience"),
              json.dumps(metrics.get("incidents")), kpi_json, metrics.get("trend")))
        conn.commit()
        # anomaly detection example: check safety score anomaly
        anomaly, details = detect_anomaly(conn, station_id, "safety", metrics.get("safety") or 0)
        if anomaly:
            alert_text = f"Anomaly detected for station {station_id}: safety changed. Details: {details}"
            # notify station manager (find manager)
            mgr = cur.execute("SELECT id, name, email, telegram_chat_id FROM employees WHERE station_id = ? AND role = 'Gas Station Manager' LIMIT 1", (station_id,)).fetchone()
            mgr_dict = {"id": None, "name": None, "email": None, "telegram": None}
            if mgr:
                mgr_dict = {"id": mgr[0], "name": mgr[1], "email": mgr[2], "telegram": mgr[3]}
            notify_station_manager(alert_text, mgr_dict, {"anomaly": details})
        # notify with full station summary (payload building omitted for brevity)
        # find station manager
        mgr = cur.execute("SELECT id, name, email, telegram_chat_id FROM employees WHERE station_id = ? AND role = 'Gas Station Manager' LIMIT 1", (station_id,)).fetchone()
        mgr_dict = {"id": None, "name": None, "email": None, "telegram": None}
        if mgr:
            mgr_dict = {"id": mgr[0], "name": mgr[1], "email": mgr[2], "telegram": mgr[3]}
        # compose short human report from metrics
        human_report = f"Station {station_id} report:\\nSafety: {metrics.get('safety')}\\nCleanliness: {metrics.get('cleanliness')}\\nStaff: {metrics.get('staff')}\\nSentiment: {metrics.get('sentiment')}\\nIncidents: {len(metrics.get('incidents',[]))}"
        notify_station_manager(human_report, mgr_dict, metrics)
    # Save region-level reports
    now = datetime.utcnow().isoformat()
    # Region storage: save one consolidated region report per region entry
    for reg in regions:
        cur.execute("INSERT INTO ai_reports (created_at, report_role, station_id, region_id, report_text, kpi_json) VALUES (?,?,?,?,?,?)",
                    (now, "Region Manager", None, reg.get("region_id"), json.dumps(reg, ensure_ascii=False), json.dumps(reg)))
    # Save GM-level
    cur.execute("INSERT INTO ai_reports (created_at, report_role, station_id, region_id, report_text, kpi_json) VALUES (?,?,?,?,?,?)",
                (now, "General Manager", None, None, json.dumps(company, ensure_ascii=False), json.dumps(company)))
    # mark submissions processed
    for s in subs:
        cur.execute("UPDATE submissions SET processed=1 WHERE id=?", (s[0],))
    conn.commit()
    print("Batch processing complete and saved.")