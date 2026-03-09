import os
import sqlite3
import json
import re
import traceback
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL = "models/gemini-2.5-flash"


# ==========================================================
# ENTERPRISE GEMINI PROMPT
# ==========================================================

def build_prompt(video_descriptions):

    return f"""
You are an **AI operational auditor for a multinational fuel retail chain**.

Analyze the following **video and voice reports submitted by station employees**.

Focus on these operational domains:

1. Safety compliance
2. Cleanliness and maintenance
3. Staff professionalism
4. Customer experience
5. Operational efficiency
6. Incident detection

Video reports:

{video_descriptions}

-----------------------------------------------------

Perform the following analysis:

• Transcribe spoken employee commentary  
• Detect operational issues  
• Detect safety violations  
• Identify customer service problems  
• Evaluate cleanliness  
• Identify incidents or hazards  

-----------------------------------------------------

Score each station (1–10):

Safety  
Cleanliness  
Staff professionalism  
Operational efficiency  
Customer experience  

-----------------------------------------------------

Perform sentiment analysis of employee voice reports:

Sentiment range:

-1.0 extremely negative  
0 neutral  
+1.0 extremely positive  

-----------------------------------------------------

Detect incidents and provide:

timestamp  
description  
severity (low / medium / high)

-----------------------------------------------------

REPORT STRUCTURE

Generate FOUR report levels:

[ROLE_REPORT: Gas Station Manager]

Operational report for a single station including:

• operational observations
• incidents
• staff behavior
• corrective actions


[ROLE_REPORT: Region Manager]

Regional report including:

• comparison of stations
• best performing station
• worst performing station
• operational risks


[ROLE_REPORT: Region Director]

Strategic report across regions including:

• regional performance
• systemic risks
• operational improvements


[ROLE_REPORT: General Manager]

Executive company report including:

• overall company operational health
• global sentiment
• top risks
• strategic recommendations

-----------------------------------------------------

At the end output VALID JSON:

{{
"stations":[
{{
"station_id":1,
"safety":8,
"cleanliness":7,
"staff":9,
"efficiency":6,
"customer_experience":7,
"sentiment":0.4,
"incidents":[
{{"timestamp":"00:01:22","desc":"fuel spill","severity":"high"}}
],
"trend":"stable"
}}
],
"regions":[
{{
"region_id":1,
"avg_safety":7.5,
"avg_cleanliness":7.1,
"avg_staff":8.0
}}
],
"company":{{
"global_sentiment":0.3,
"top_risks":["safety incidents"],
"top_recommendations":[
"increase safety inspections",
"improve staff training"
]
}}
}}
"""


# ==========================================================
# JSON EXTRACTION
# ==========================================================

def extract_json(text):

    try:
        # Case 1: JSON inside ```json block
        match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # Case 2: any JSON object in text
        match = re.search(r"(\{[\s\S]*\"stations\"[\s\S]*\})", text)
        if match:
            return json.loads(match.group(1))

        # Case 3: fallback – last JSON object
        start = text.rfind("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return json.loads(text[start:end+1])

    except Exception as e:
        print("JSON parse error:", e)

    return None


# ==========================================================
# SAVE REPORT
# ==========================================================

def save_report(conn, role, station_id, region_id, report_text, metrics):

    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO ai_reports(
        created_at,
        report_role,
        station_id,
        region_id,
        report_text,
        sentiment,
        safety_score,
        cleanliness_score,
        staff_score,
        efficiency_score,
        customer_score,
        incidents_json,
        trend
    )
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (

        datetime.utcnow().isoformat(),
        role,
        station_id,
        region_id,
        report_text,
        metrics.get("sentiment"),
        metrics.get("safety"),
        metrics.get("cleanliness"),
        metrics.get("staff"),
        metrics.get("efficiency"),
        metrics.get("customer_experience"),
        json.dumps(metrics.get("incidents")),
        metrics.get("trend")

    ))

    conn.commit()


# ==========================================================
# GEMINI ANALYSIS
# ==========================================================

def analyze_reports(prompt):

    model = genai.GenerativeModel(MODEL)

    response = model.generate_content(prompt)

    return response.text


# ==========================================================
# MAIN SUMMARIZER
# ==========================================================

def run_hourly_summarizer():

    conn = sqlite3.connect("company.db")

    cursor = conn.cursor()

    submissions = cursor.execute("""
    SELECT id, station_id, video_path, role
    FROM submissions
    WHERE processed = 0
    """).fetchall()

    if not submissions:

        print("No new submissions")

        return

    video_descriptions = ""

    for sub in submissions:

        sid, station_id, path, role = sub

        video_descriptions += f"""
Station ID: {station_id}
Reported by: {role}
Video file: {path}
"""

    prompt = build_prompt(video_descriptions)

    print("Running Gemini analysis...")

    response = analyze_reports(prompt)

    json_block = extract_json(response)

    if not json_block:

        print("JSON parsing failed")

        return

    print("AI analysis complete")

    # -------------------------------------------------
    # Extract role reports
    # -------------------------------------------------

    role_reports = {}

    roles = [
        "Gas Station Manager",
        "Region Manager",
        "Region Director",
        "General Manager"
    ]

    for role in roles:

        pattern = rf"\[ROLE_REPORT:\s*{role}\](.*?)(?=\[ROLE_REPORT:|\Z)"

        m = re.search(pattern, response, re.DOTALL)

        if m:

            role_reports[role] = m.group(1).strip()

    # -------------------------------------------------
    # SAVE STATION REPORTS
    # -------------------------------------------------

    for station in json_block.get("stations", []):

        save_report(
            conn,
            "Gas Station Manager",
            station.get("station_id"),
            None,
            role_reports.get("Gas Station Manager", ""),
            station
        )

    # -------------------------------------------------
    # SAVE REGION REPORTS
    # -------------------------------------------------

    for region in json_block.get("regions", []):

        save_report(
            conn,
            "Region Manager",
            None,
            region.get("region_id"),
            role_reports.get("Region Manager", ""),
            region
        )

    # -------------------------------------------------
    # SAVE REGION DIRECTOR REPORT
    # -------------------------------------------------

    save_report(
        conn,
        "Region Director",
        None,
        None,
        role_reports.get("Region Director", ""),
        json_block.get("company", {})
    )

    # -------------------------------------------------
    # SAVE GENERAL MANAGER REPORT
    # -------------------------------------------------

    save_report(
        conn,
        "General Manager",
        None,
        None,
        role_reports.get("General Manager", ""),
        json_block.get("company", {})
    )

    # -------------------------------------------------
    # MARK SUBMISSIONS PROCESSED
    # -------------------------------------------------

    for sub in submissions:

        cursor.execute(
            "UPDATE submissions SET processed=1 WHERE id=?",
            (sub[0],)
        )

    conn.commit()

    conn.close()

    print("Reports saved to database")


# ==========================================================
# ENTRY POINT
# ==========================================================

if __name__ == "__main__":

    try:

        run_hourly_summarizer()

    except Exception:

        print("Hourly summarizer failed")

        traceback.print_exc()