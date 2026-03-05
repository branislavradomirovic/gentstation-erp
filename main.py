import os
import sqlite3
import uuid
import sys
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
from dotenv import load_dotenv

load_dotenv()

# --- INITIALIZATION ---
if not os.path.exists("downloads"):
    os.makedirs("downloads")

# --- START / LINKING LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if context.args:
        station_id = context.args[0]
        try:
            with sqlite3.connect('company.db') as conn:
                cursor = conn.execute(
                    "UPDATE employees SET chat_id = ? WHERE station_id = ? AND chat_id IS NULL", 
                    (chat_id, station_id)
                )
                conn.commit()
                if cursor.rowcount > 0:
                    await update.message.reply_text("✅ Device successfully linked to Station Hierarchy!")
                else:
                    await update.message.reply_text("⚠️ Link failed. Station already linked or invalid ID.")
        except Exception as e:
            await update.message.reply_text("❌ Database linking error.")
    else:
        await update.message.reply_text("👋 Welcome to GentStation. Please use the link provided in your invitation email.")

# --- THE CORRECT VIDEO HANDLER (QUEUE ONLY) ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    
    with sqlite3.connect('company.db') as conn:
        user = conn.execute("""
            SELECT e.role, s.name, s.id 
            FROM employees e 
            JOIN stations s ON e.station_id = s.id 
            WHERE e.chat_id = ?
        """, (chat_id,)).fetchone()
    
    if not user:
        await update.message.reply_text("🚫 Device not registered.")
        return

    role, station_name, s_id = user

    # Download Video
    video = update.message.video or update.message.document
    if update.message.document and not update.message.document.mime_type.startswith('video/'):
        await update.message.reply_text("❌ Please upload a valid video file.")
        return

    file_path = f"downloads/{uuid.uuid4()}.mp4"
    status_msg = await update.message.reply_text("⏳ Primanje snimka...")
    
    new_file = await context.bot.get_file(video.file_id)
    await new_file.download_to_drive(file_path)

    # SAVE TO DATABASE FOR HOURLY SUMMARIZER
    try:
        with sqlite3.connect('company.db') as conn:
            conn.execute("""
                INSERT INTO submissions (station_id, chat_id, video_path, role, timestamp, processed)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (s_id, chat_id, file_path, role, datetime.now()))
            
            # Update last activity
            conn.execute("UPDATE stations SET last_submission = ? WHERE id = ?", (datetime.now(), s_id))
            conn.commit()
        
        await status_msg.edit_text(
            f"📥 Izveštaj primljen! Snimak je u redu za analizu na srpskom jeziku.\n"
            f"Stanica: {station_name}"
        )
    except Exception as e:
        print(f"❌ DB Error: {e}")
        await status_msg.edit_text("⚠️ Greška pri čuvanju snimka.")

# --- EXECUTION ---
if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    
    print("🚀 GentStation Bot is online (Queue Mode).")
    app.run_polling()