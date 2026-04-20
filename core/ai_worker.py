import time
import os
import sys, json
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import get_connection
from core.video_processor import parse_station_video
from core.comm_service import send_ai_report_email

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)
logger = logging.getLogger("gentstation.ai_worker")

def update_processing_status(conn, status_dict):
    """Helper to update the AI processing status in the database."""
    conn.execute(
        """
        INSERT INTO system_settings (key, value)
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        ("ai_processing_status", json.dumps(status_dict))
    )
    conn.commit()

def has_pending_submissions():
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM submissions WHERE processed = 0 AND video_path IS NOT NULL"
        ).fetchone()
        return bool(row and row[0])
    finally:
        conn.close()

def process_pending_submissions():
    logger.debug("Checking for pending submissions...")
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Get unprocessed videos
    pending = cursor.execute("""
        SELECT id, video_path, station_id FROM submissions 
        WHERE processed = 0 AND video_path IS NOT NULL
    """).fetchall()
    
    if not pending:
        logger.debug("No pending tasks found.")
        update_processing_status(conn, {"status": "idle", "last_run_ts": time.time()})
        conn.close()
        return

    total_tasks = len(pending)
    logger.info("Starting AI batch with %s pending tasks.", total_tasks)
    update_processing_status(conn, {"status": "processing", "total": total_tasks, "current": 0})

    for i, (sub_id, v_path, station_id) in enumerate(pending):
        if os.path.exists(v_path):
            logger.debug("Processing submission %s for station %s...", sub_id, station_id)
            
            try:
                # 2. Call Gemini
                result_json = parse_station_video(v_path)
                
                # 3. Update database with results
                cursor.execute("""
                    UPDATE submissions 
                    SET data_json = %s, processed = 1 
                    WHERE id = %s
                """, (json.dumps(result_json), sub_id))
                conn.commit()
                logger.debug("DB updated for submission %s.", sub_id)

                # 3.5 Check for Low Merchandising Score -> Alert
                merch_score = result_json.get("merchandising_score")
                if isinstance(merch_score, (int, float)) and merch_score < 4:
                    alert_msg = f"Low Merchandising Score detected ({merch_score}/10). Check shelves."
                    cursor.execute(
                        "INSERT INTO ai_alerts (station_id, severity, message) VALUES (%s, 'MEDIUM', %s)",
                        (station_id, alert_msg)
                    )
                    conn.commit()
                    logger.info("Created MEDIUM alert for station %s.", station_id)

                # 4. Send email notification to the manager
                send_ai_report_email(conn, station_id, result_json)

            except Exception as e:
                logger.error("FAILED to process submission %s: %s", sub_id, e)
                cursor.execute("UPDATE submissions SET processed = -1 WHERE id = %s", (sub_id,))
                conn.commit()
        
        # Update progress after each item
        update_processing_status(conn, {"status": "processing", "total": total_tasks, "current": i + 1})
        logger.debug("Progress: %s/%s", i + 1, total_tasks)

    conn.close()

if __name__ == "__main__":
    logger.info("AI worker started (batch mode).")
    last_run_time = 0
    BATCH_INTERVAL = 3600  # keep as a safety throttle for empty queues / forced retries

    while True:
        # Check for manual trigger from Settings
        force_run = False
        try:
            conn = get_connection()
            row = conn.execute("SELECT value FROM system_settings WHERE key='force_ai_processing'").fetchone()
            if row and row[0] == '1':
                force_run = True
                # Reset the flag immediately
                conn.execute(
                    """
                    INSERT INTO system_settings (key, value)
                    VALUES (%s, '0')
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                    """,
                    ("force_ai_processing",)
                )
                conn.commit()
                logger.info("Manual force run detected.")
            conn.close()
        except Exception as e:
            logger.warning("DB check error: %s", e)

        pending_exists = False
        try:
            pending_exists = has_pending_submissions()
        except Exception as e:
            logger.warning("Pending-submission check failed: %s", e)

        # Run if forced, if new pending work exists, or if the hourly safety interval has passed
        if force_run or pending_exists or (time.time() - last_run_time >= BATCH_INTERVAL):
            process_pending_submissions()
            last_run_time = time.time()
        
        time.sleep(10) # Check for trigger frequently
