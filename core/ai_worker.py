
import sqlite3
import time
import os
import sys, json
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.video_processor import parse_station_video # The Gemini logic we discussed
from core.comm_service import send_ai_report_email # New function to send email

DB_PATH = str(Path(__file__).resolve().parents[1] / "company.db")

def update_processing_status(conn, status_dict):
    """Helper to update the AI processing status in the database."""
    conn.execute(
        "INSERT OR REPLACE INTO system_settings (key, value) VALUES ('ai_processing_status', ?)",
        (json.dumps(status_dict),)
    )
    conn.commit()

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
        update_processing_status(conn, {"status": "idle", "last_run_ts": time.time()})
        conn.close()
        return

    total_tasks = len(pending)
    print(f"🤖 [ai_worker] Starting batch of {total_tasks} tasks.")
    update_processing_status(conn, {"status": "processing", "total": total_tasks, "current": 0})

    for i, (sub_id, v_path, station_id) in enumerate(pending):
        if os.path.exists(v_path):
            print(f"🤖 [ai_worker] Processing submission {sub_id} for station {station_id}...")
            
            try:
                # 2. Call Gemini
                result_json = parse_station_video(v_path)
                
                # 3. Update database with results
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
                    cursor.execute("INSERT INTO ai_alerts (station_id, severity, message) VALUES (?, 'MEDIUM', ?)", (station_id, alert_msg))
                    conn.commit()
                    print(f"⚠️ [ai_worker] Created MEDIUM alert for station {station_id}")

                # 4. Send email notification to the manager
                send_ai_report_email(conn, station_id, result_json)

            except Exception as e:
                print(f"❌ [ai_worker] FAILED to process submission {sub_id}: {e}")
                cursor.execute("UPDATE submissions SET processed = -1 WHERE id = ?", (sub_id,))
                conn.commit()
        
        # Update progress after each item
        update_processing_status(conn, {"status": "processing", "total": total_tasks, "current": i + 1})
        print(f"🤖 [ai_worker] Progress: {i + 1}/{total_tasks}")

    conn.close()

if __name__ == "__main__":
    print("--- AI Worker Started (Batch Mode) ---")
    last_run_time = 0
    BATCH_INTERVAL = 3600  # 1 hour in seconds

    while True:
        # Check for manual trigger from Settings
        force_run = False
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute("SELECT value FROM system_settings WHERE key='force_ai_processing'").fetchone()
            if row and row[0] == '1':
                force_run = True
                # Reset the flag immediately
                conn.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('force_ai_processing', '0')")
                conn.commit()
                print("🤖 [ai_worker] Manual force run detected!")
            conn.close()
        except Exception as e:
            print(f"⚠️ [ai_worker] DB Check Error: {e}")

        # Run if forced OR if interval has passed
        if force_run or (time.time() - last_run_time >= BATCH_INTERVAL):
            process_pending_submissions()
            last_run_time = time.time()
        
        time.sleep(10) # Check for trigger frequently