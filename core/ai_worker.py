
import sqlite3
import time
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from core.video_processor import parse_station_video # The Gemini logic we discussed

DB_PATH = "company.db"

def process_pending_submissions():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Get unprocessed videos
    pending = cursor.execute("""
        SELECT id, video_path FROM submissions 
        WHERE processed = 0 AND video_path IS NOT NULL
    """).fetchall()
    
    for sub_id, v_path in pending:
        if os.path.exists(v_path):
            print(f"🤖 Processing submission {sub_id}...")
            
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
            print(f"✅ Submission {sub_id} updated.")
            
    conn.close()

if __name__ == "__main__":
    while True:
        process_pending_submissions()
        time.sleep(30) # Check every 30 seconds