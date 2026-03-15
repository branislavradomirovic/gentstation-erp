
import sqlite3
import time
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.video_processor import parse_station_video # The Gemini logic we discussed
from core.comm_service import send_ai_report_email # New function to send email

DB_PATH = str(Path(__file__).resolve().parents[1] / "company.db")

def process_pending_submissions():
    print("🤖 [ai_worker] Checking for pending submissions...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get unprocessed videos
    pending = cursor.execute("""
        SELECT id, video_path, station_id FROM submissions 
        WHERE processed = 0 AND video_path IS NOT NULL
    """).fetchall()
    
    if not pending:
        print("🤖 [ai_worker] No pending tasks found.")

    for sub_id, v_path, station_id in pending:
        if os.path.exists(v_path):
            print(f"🤖 [ai_worker] Processing submission {sub_id} for station {station_id}...")
            
            try:
                # 2. Call Gemini
                result_json = parse_station_video(v_path)
                
                # 3. Update database with results
                import json
                cursor.execute("""
                    UPDATE submissions 
                    SET data_json = ?, processed = 1 
                    WHERE id = ?
                """, (json.dumps(result_json), sub_id))
                conn.commit()
                print(f"✅ [ai_worker] DB updated for submission {sub_id}.")

                # 3.5 Check for Low Merchandising Score -> Alert
                merch_score = result_json.get("merchandising_score")
                if isinstance(merch_score, (int, float)) and merch_score < 4:
                    alert_msg = f"Low Merchandising Score detected ({merch_score}/10). Check shelves."
                    cursor.execute("""
                        INSERT INTO ai_alerts (station_id, severity, message) 
                        VALUES (?, 'MEDIUM', ?)
                    """, (station_id, alert_msg))
                    conn.commit()
                    print(f"⚠️ [ai_worker] Created MEDIUM alert for station {station_id}")

                # 4. Send email notification to the manager
                send_ai_report_email(conn, station_id, result_json)

            except Exception as e:
                print(f"❌ [ai_worker] FAILED to process submission {sub_id}: {e}")
                # Optionally mark as failed to avoid retrying
                cursor.execute("UPDATE submissions SET processed = -1 WHERE id = ?", (sub_id,))
                conn.commit()
            
    conn.close()

if __name__ == "__main__":
    print("--- AI Worker Started ---")
    while True:
        process_pending_submissions()
        time.sleep(30)