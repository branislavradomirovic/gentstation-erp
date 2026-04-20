import os
import sys
import logging
import time
import threading
import json
import asyncio
import atexit
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import NetworkError

from dotenv import load_dotenv
from telegram.ext import MessageHandler, filters
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from core.database import get_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger("bot_worker")
BOT_STATUS_KEY = "telegram_bot_status"
BOT_HEARTBEAT_INTERVAL = 30
bot_running_event = threading.Event()
LOCK_FILE = Path("/tmp/gentstationai_bot_worker.lock")


def update_bot_status(status: str, details: str = None):
    try:
        conn = get_connection()
        payload = {
            "status": status,
            "last_update_ts": time.time(),
        }
        if details:
            payload["details"] = details

        conn.execute(
            """
            INSERT INTO system_settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (BOT_STATUS_KEY, json.dumps(payload)),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.debug("Could not update bot status: %s", e)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_lock() -> bool:
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as fh:
            fh.write(str(os.getpid()))
        return True
    except FileExistsError:
        try:
            existing_pid = int(LOCK_FILE.read_text().strip())
            if _pid_alive(existing_pid):
                logger.error("Bot worker already running in PID %s. Exiting duplicate instance.", existing_pid)
                return False
        except Exception:
            pass

        try:
            LOCK_FILE.unlink()
        except Exception:
            pass

        return acquire_lock()


def release_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


atexit.register(release_lock)


def heartbeat_loop():
    while True:
        if bot_running_event.is_set():
            update_bot_status("online")
        time.sleep(BOT_HEARTBEAT_INTERVAL)


def _is_video_document(message) -> bool:
    document = getattr(message, "document", None)
    if not document:
        return False
    mime_type = (document.mime_type or "").lower()
    name = (document.file_name or "").lower()
    return mime_type.startswith("video/") or name.endswith((".mp4", ".mov", ".mkv", ".webm"))


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.debug("handle_media called")
    chat_id = str(update.effective_chat.id)
    message = update.effective_message
    
    if not message:
        return

    # 1. Identify which employee is sending the media
    conn = get_connection()
    cursor = conn.cursor()
    emp = cursor.execute(
        "SELECT id, station_id FROM employees WHERE telegram_chat_id = %s",
        (chat_id,),
    ).fetchone()
    logger.debug("chat_id=%s emp=%s", chat_id, emp)
    
    if not emp:
        await update.message.reply_text("❌ Your Telegram is not linked. Please use the link from your email.")
        return

    emp_id, station_id = emp

    # 2. Download the video or video document
    if message.video:
        media = message.video
    elif _is_video_document(message):
        media = message.document
    else:
        await message.reply_text("❌ Please send a video file (mp4/mov/webm) to queue it for AI analysis.")
        return

    video_file = await media.get_file()
    # Save locally or to a cloud bucket
    UPLOADS_DIR = PROJECT_ROOT / "uploads"
    UPLOADS_DIR.mkdir(exist_ok=True)
    file_name = getattr(media, "file_name", None) or f"vid_{message.message_id}.mp4"
    file_path = UPLOADS_DIR / file_name
    if file_path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".webm"}:
        file_path = file_path.with_suffix(".mp4")

    await video_file.download_to_drive(str(file_path))

    # 3. Save submission to DB for AI processing
    try:
        cursor.execute("""
            INSERT INTO submissions (station_id, employee_id, video_path, processed) 
            VALUES (%s, %s, %s, 0)
        """, (station_id, emp_id, str(file_path)))
        conn.commit()
        logger.info("Queued submission for station %s and employee %s.", station_id, emp_id)
    except Exception as e:
        logger.exception("Error inserting submission: %s", e)
        await message.reply_text("⚠️ I received the file, but could not queue it for analysis.")
        conn.close()
        return
    finally:
        conn.close()

    await message.reply_text("✅ Video received and queued for AI analysis. You will see the results in the Dashboard shortly.")

# In your main block, add the handler:
# app.add_handler(MessageHandler(filters.VIDEO, handle_video))

logger.debug("Starting bot_worker.py...")
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    
    # Check if this is a deep link: /start [employee_id]
    if context.args:
        emp_id = context.args[0]
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Update the employee record
            cursor.execute(
                "UPDATE employees SET telegram_chat_id = %s WHERE id = %s",
                (chat_id, emp_id),
            )
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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.exception("Unhandled bot error: %s", context.error)

def build_application():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    media_filter = (
        filters.VIDEO
        | filters.Document.VIDEO
        | filters.Document.MimeType("video/mp4")
        | filters.Document.MimeType("video/quicktime")
        | filters.Document.MimeType("video/webm")
    )
    app.add_handler(MessageHandler(media_filter, handle_media))
    app.add_error_handler(error_handler)
    return app


def run_bot_with_retry():
    """
    Keep the bot process alive even when Telegram is temporarily unreachable.
    """
    while True:
        try:
            app = build_application()
            bot_running_event.set()
            update_bot_status("starting")
            logger.info("Starting Telegram polling loop...")
            app.run_polling(
                drop_pending_updates=True,
                stop_signals=None,
                close_loop=False,
            )
            bot_running_event.clear()
            update_bot_status("stopped")
            logger.warning("Telegram polling loop exited unexpectedly. Retrying in 30s.")
        except NetworkError as e:
            bot_running_event.clear()
            update_bot_status("error", str(e))
            logger.error("Telegram network error: %s", e)
            logger.error("Check outbound access to https://api.telegram.org or configure a proxy/VPN.")
            logger.debug("Retrying Telegram startup in 30s...")
            time.sleep(30)
            continue
        except KeyboardInterrupt:
            bot_running_event.clear()
            update_bot_status("stopped")
            logger.info("Telegram bot stopped by user.")
            break
        except Exception as e:
            bot_running_event.clear()
            update_bot_status("error", str(e))
            logger.exception("Telegram bot crashed: %s", e)
            logger.debug("Retrying Telegram startup in 30s...")
            time.sleep(30)
            continue

if __name__ == "__main__":
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found in .env")
    elif not acquire_lock():
        logger.error("Telegram bot worker lock could not be acquired; another instance is active.")
    else:
        logger.info("Bot is starting (Polling)...")
        threading.Thread(target=heartbeat_loop, daemon=True).start()
        run_bot_with_retry()
