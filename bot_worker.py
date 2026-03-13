import os
import sqlite3
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from dotenv import load_dotenv
from telegram.ext import MessageHandler, filters
from pathlib import Path

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[bot_worker] handle_video called")
    chat_id = update.effective_chat.id
    
    # 1. Identify which employee is sending the video
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    emp = cursor.execute("SELECT id, station_id FROM employees WHERE telegram_chat_id = ?", (chat_id,)).fetchone()
    print(f"[bot_worker] DB_PATH: {DB_PATH}, chat_id: {chat_id}, emp: {emp}")
    
    if not emp:
        await update.message.reply_text("❌ Your Telegram is not linked. Please use the link from your email.")
        return

    emp_id, station_id = emp

    # 2. Download the video
    video_file = await update.message.video.get_file()
    # Save locally or to a cloud bucket
    os.makedirs("uploads", exist_ok=True)
    file_path = f"uploads/vid_{update.message.message_id}.mp4"
    await video_file.download_to_drive(file_path)

    # 3. Save submission to DB for AI processing

    try:
        cursor.execute("""
            INSERT INTO submissions (station_id, employee_id, video_path, processed) 
            VALUES (?, ?, ?, 0)
        """, (station_id, emp_id, file_path))
        conn.commit()
        print(f"[bot_worker] Inserted submission: station_id={station_id}, emp_id={emp_id}, file_path={file_path}")
    except Exception as e:
        print(f"[bot_worker] Error inserting submission: {e}")
    finally:
        conn.close()

    await update.message.reply_text("✅ Video received and queued for AI analysis! You will see the results in the Dashboard shortly.")

# In your main block, add the handler:
# app.add_handler(MessageHandler(filters.VIDEO, handle_video))

print("[bot_worker] Starting bot_worker.py...")
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Use absolute path for DB_PATH to match app and avoid duplicate DBs
DB_PATH = str(Path(__file__).resolve().parents[0] / "company.db")
print(f"[bot_worker] Using DB_PATH: {DB_PATH}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    # Check if this is a deep link: /start [employee_id]
    if context.args:
        emp_id = context.args[0]
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Update the employee record
            cursor.execute("UPDATE employees SET telegram_chat_id = ? WHERE id = ?", (chat_id, emp_id))
            conn.commit()
            
            # Check if we actually updated a row
            if cursor.rowcount > 0:
                await update.message.reply_text(f"✅ Registration Successful!\nEmployee ID {emp_id} is now linked to this chat.")
            else:
                await update.message.reply_text("❌ Error: Employee ID not found in database.")
            
            conn.close()
        except Exception as e:
            await update.message.reply_text(f"⚠️ Database Error: {e}")
    else:
        await update.message.reply_text("Welcome! Please use the link from your registration email to link your account.")

if __name__ == "__main__":
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
    else:
        print("🤖 Bot is starting (Polling)...")
        app = ApplicationBuilder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.VIDEO, handle_video))
        print("[bot_worker] Video handler registered.")
        app.run_polling()