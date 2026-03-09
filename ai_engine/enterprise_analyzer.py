# gentstation_opus/ai_engine/enterprise_analyzer.py
"""
Enterprise Gemini Video + Speech Analyzer

Responsibilities:
- Accept submissions (video + audio metadata) from `submissions` table
- Run light pre-processing (ASR transcription via video_speech_analyzer)
- Build an enterprise-grade prompt for Gemini Vision & LLM
- Call gemini_client.generate_from_prompt (which supports file upload variants)
- Parse model output into structured station-level metrics:
    - employee_behaviour: [list of tags e.g. ['rude','helpful','distracted']]
    - customer_interactions: counts & keywords
    - cleanliness_score: 1-10
    - safety_violations: list (timestamp, desc, severity)
    - queue_estimate: integer estimate of queue length / avg
    - keywords: list
- Return structured dict for each station, and optionally save into DB or forward downstream.
- Robust to missing Gemini client (uses fallback)
"""

import os
import json
import re
import time
from typing import List, Dict, Any, Optional
from datetime import datetime

from gentstation_opus.ai_engine.video_speech_analyzer import transcribe_audio, analyze_speech_sentiment
from gentstation_opus.ai_engine.gemini_client import generate_from_prompt, extract_json_block
from gentstation_opus.core.database import get_connection

# Optional: object-detection placeholder (replace with real detector)
def detect_objects_in_video_stub(video_path: str) -> Dict[str, int]:
    """
    Placeholder object 'detector' that returns counts for common objects
    e.g. {'person': 4, 'car': 2}
    Replace with real object detection (YOLO/MediaPipe/Gemini Vision).
    """
    if not video_path or not os.path.exists(video_path):
        return {}
    size = os.path.getsize(video_path)
    # Fake heuristic: larger files -> more people
    people_est = max(1, min(10, int(size / (1024 * 1024 * 2))))
    return {"person": people_est, "car": people_est // 2}


def build_analysis_prompt(station_id: int, entries: List[Dict[str, Any]]) -> str:
    """
    Compose a strong enterprise prompt for Gemini containing:
      - station metadata
      - transcripts
      - object-detection summaries (if any)
    The prompt instructs Gemini to produce a structured response and a JSON block.
    """
    header = (
        "You are an enterprise-grade Fuel Retail Operations Auditor (Shell/BP style).\n"
        "Language: Serbian (srpska latinica).\n"
        "Produce actionable findings and a final JSON block in fenced ```json ... ```.\n"
    )

    body = f"[STATION_ID: {station_id}]\n"
    for e in entries:
        ts = e.get("timestamp") or e.get("timestamp_str") or "N/A"
        body += f"- Submission ID: {e.get('submission_id')} | role: {e.get('role')} | ts: {ts}\n"
        if e.get("video"):
            body += f"  video: {os.path.basename(e.get('video'))}\n"
        if e.get("audio"):
            body += f"  audio: {os.path.basename(e.get('audio'))}\n"
        if e.get("transcript"):
            # include short transcript excerpt
            body += f"  transcript_excerpt: {e['transcript'][:400].replace('\\n',' ')}\n"
        if e.get("object_summary"):
            body += f"  object_summary: {json.dumps(e['object_summary'])}\n"

    instructions = """
Analiza zahteva:
1) Identifikuj ponašanje zaposlenih (npr. 'istreniran', 'nepažljiv', 'rude', 'helpful', 'distracted').
2) Izbroj i opiši interakcije sa kupcima (kratko): brojevi, ključne reči.
3) Proceni čistoću 1-10 i daj kratki dokaz.
4) Detektuj bezbednosne prekršaje (npr. prosipanje goriva, pušenje blizu pumpi, neispravna oprema). Za svaki incident daj: timestamp (ako je moguće), opis, težinu (low/medium/high).
5) Proceni dužinu reda (queue) u proseku tokom snimka: broj ljudi.
6) Navedi ključne reči i confidence procenu.
7) Na kraju generiši VALIDAN JSON u fenced ```json ... ``` formatu sa sledećom strukturom:

{
  "station_id": <int>,
  "employee_behaviour": ["tag1","tag2"],
  "customer_interactions": {"count": <int>, "keywords": ["..."]},
  "cleanliness_score": <1-10>,
  "safety_violations": [{"timestamp":"00:01:23","desc":"...","severity":"high"}],
  "queue_estimate": <int>,
  "keywords": ["..."],
  "confidence": 0.0
}

Obavezno taj JSON stavi unutar ```json ... ``` bloka na kraju odgovora.
"""
    return header + "\n" + body + "\n" + instructions


def analyze_station_batch(sub_entries: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """
    Given a list of submission dicts (with keys: submission_id, station_id, video, audio, role, timestamp),
    perform per-station analysis and return a mapping station_id -> metrics dict.
    """
    # Group by station
    per_station = {}
    for e in sub_entries:
        sid = e.get("station_id")
        per_station.setdefault(sid, []).append(e)

    results = {}
    for station_id, entries in per_station.items():
        # Preprocess: transcribe audio and run simple object detector
        enriched = []
        for e in entries:
            asr = transcribe_audio(e.get("audio")) if e.get("audio") else {"transcript": ""}
            sentiment = analyze_speech_sentiment(asr.get("transcript", ""))
            obj_summary = detect_objects_in_video_stub(e.get("video"))
            enriched.append({
                "submission_id": e.get("submission_id"),
                "station_id": station_id,
                "video": e.get("video"),
                "audio": e.get("audio"),
                "role": e.get("role"),
                "timestamp": e.get("timestamp"),
                "transcript": asr.get("transcript", ""),
                "sentiment": sentiment,
                "object_summary": obj_summary
            })

        # Build prompt and call Gemini (LLM or Vision+LLM)
        prompt = build_analysis_prompt(station_id, enriched)

        # Note: If you have actual file-objects for Gemini Vision, you could pass them via the gemini_client
        # For now we call with prompt-only (gemini_client will fallback if no API)
        response_text = generate_from_prompt(prompt, file_objs=None)

        # Extract JSON from the response
        parsed_json = extract_json_block(response_text)

        if not parsed_json:
            # If no valid JSON, attempt to infer some metrics from the pre-processing
            # Aggregate object counts and transcripts
            total_people = sum([e['object_summary'].get('person', 0) for e in enriched])
            combined_transcripts = " ".join([e['transcript'] for e in enriched])
            keywords = []
            if combined_transcripts:
                keywords = list({w.strip(".,!?").lower() for w in combined_transcripts.split() if len(w) > 4})[:6]
            inferred = {
                "station_id": station_id,
                "employee_behaviour": ["unknown"],
                "customer_interactions": {"count": total_people, "keywords": keywords},
                "cleanliness_score": 7,
                "safety_violations": [],
                "queue_estimate": max(1, total_people // max(1, len(enriched))),
                "keywords": keywords,
                "confidence": 0.2
            }
            results[station_id] = inferred
            continue

        # Normalize parsed JSON keys and ensure types
        parsed_json.setdefault("station_id", station_id)
        # Defensive defaults
        parsed_json.setdefault("employee_behaviour", [])
        parsed_json.setdefault("customer_interactions", {"count": 0, "keywords": []})
        parsed_json.setdefault("cleanliness_score", 5)
        parsed_json.setdefault("safety_violations", [])
        parsed_json.setdefault("queue_estimate", 0)
        parsed_json.setdefault("keywords", [])
        parsed_json.setdefault("confidence", 0.0)

        results[station_id] = parsed_json

    return results


# Helper: read pending submissions from DB and analyze
def run_analyzer_once(save_to_db: bool = True) -> Dict[int, Dict[str, Any]]:
    """
    - Loads unprocessed submissions from DB
    - Calls analyze_station_batch
    - Optionally saves station-level kpi_json into ai_reports table
    - Returns results map
    """
    conn = get_connection()
    cur = conn.cursor()
    subs = cur.execute("SELECT id, station_id, employee_id, video_path, audio_path, role, timestamp FROM submissions WHERE processed = 0").fetchall()
    if not subs:
        return {}
    entries = []
    for s in subs:
        entries.append({
            "submission_id": s[0],
            "station_id": s[1],
            "employee_id": s[2],
            "video": s[3],
            "audio": s[4],
            "role": s[5],
            "timestamp": s[6]
        })

    results = analyze_station_batch(entries)

    # Save each station result as ai_reports record (Gas Station Manager role)
    if save_to_db and results:
        now = datetime.utcnow().isoformat()
        for station_id, metrics in results.items():
            kpi_json = json.dumps(metrics, ensure_ascii=False)
            cur.execute("""
                INSERT INTO ai_reports (created_at, report_role, station_id, region_id, report_text, kpi_json, sentiment)
                VALUES (?,?,?,?,?,?,?)
            """, (now, "Gas Station Manager", station_id, None, "", kpi_json, metrics.get("customer_interactions", {}).get("sentiment") if isinstance(metrics.get("customer_interactions"), dict) else None))
        conn.commit()

        # Optionally mark submissions processed (here we mark all processed)
        cur.execute("UPDATE submissions SET processed = 1 WHERE processed = 0")
        conn.commit()

    return results