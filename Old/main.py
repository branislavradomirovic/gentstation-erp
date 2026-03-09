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
    """Povezuje Telegram nalog sa zaposlenim preko ID-a iz linka uz proveru duplikata"""
    user_chat_id = update.effective_chat.id
    
    if not context.args:
        await update.message.reply_text("👋 Dobrodošli u GentStation! Molimo koristite link iz vašeg pozivnog mejla.")
        return

    try:
        emp_id = int(context.args[0])
        
        with sqlite3.connect('company.db') as conn:
            # 1. PROVERA: Da li je ovaj Telegram nalog već povezan sa nekim DRUGIM korisnikom
            already_linked = conn.execute(
                "SELECT name, surname FROM employees WHERE telegram_chat_id = ? AND id != ?", 
                (str(user_chat_id), emp_id)
            ).fetchone()

            if already_linked:
                await update.message.reply_text(
                    f"⚠️ Ovaj Telegram nalog je već povezan sa korisnikom: {already_linked[0]} {already_linked[1]}.\n"
                    "Jedan Telegram nalog ne može biti povezan sa više zaposlenih istovremeno."
                )
                print(f"!!! Prevented duplicate linking for Chat ID {user_chat_id}")
                return

            # 2. PROVERA: Da li zaposleni na kojeg link ukazuje postoji
            user = conn.execute("SELECT name, surname FROM employees WHERE id = ?", (emp_id,)).fetchone()
            
            if user:
                # Upisujemo telegram_chat_id (kolona koju koristi admin_gui.py)
                conn.execute("UPDATE employees SET telegram_chat_id = ? WHERE id = ?", (str(user_chat_id), emp_id))
                conn.commit()
                await update.message.reply_text(f"✅ Uspešno povezano! Dobrodošli {user[0]} {user[1]}. Ovde ćete primati izveštaje.")
                print(f"--- Linked Employee {emp_id} to Chat ID {user_chat_id}")
            else:
                await update.message.reply_text(f"❌ Greška: Zaposleni sa ID {emp_id} nije pronađen.")
                
    except Exception as e:
        print(f"Error in start: {e}")
        await update.message.reply_text("❌ Greška pri aktivaciji linka.")

# --- VIDEO HANDLER ---
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    
    with sqlite3.connect('company.db') as conn:
        # Proveravamo ko šalje video koristeći telegram_chat_id
        user = conn.execute("""
            SELECT e.role, s.name, s.id, e.name
            FROM employees e 
            LEFT JOIN stations s ON e.station_id = s.id 
            WHERE e.telegram_chat_id = ?
        """, (chat_id,)).fetchone()
    
    if not user:
        await update.message.reply_text("🚫 Vaš nalog nije povezan ili je ID dodeljen drugom korisniku. Kliknite na link iz mejla ponovo.")
        return

    role, station_name, s_id, emp_name = user
    station_display = station_name if station_name else "Opšta/Terenska"

    # Provera formata fajla
    video = update.message.video or update.message.document
    if update.message.document and not (update.message.document.mime_type and update.message.document.mime_type.startswith('video/')):
        await update.message.reply_text("❌ Molimo pošaljite validan video snimak.")
        return

    file_path = f"downloads/{uuid.uuid4()}.mp4"
    status_msg = await update.message.reply_text(f"⏳ Primanje snimka od: {emp_name}...")
    
    try:
        new_file = await context.bot.get_file(video.file_id)
        await new_file.download_to_drive(file_path)

        with sqlite3.connect('company.db') as conn:
            conn.execute("""
                INSERT INTO submissions (station_id, chat_id, video_path, role, timestamp, processed)
                VALUES (?, ?, ?, ?, ?, 0)
            """, (s_id, chat_id, file_path, role, datetime.now()))
            
            if s_id:
                conn.execute("UPDATE stations SET last_submission = ? WHERE id = ?", (datetime.now(), s_id))
            conn.commit()
        
        await status_msg.edit_text(
            f"📥 Izveštaj uspešno primljen!\n"
            f"📍 Stanica: {station_display}\n"
            f"👤 Poslao: {emp_name}"
        )
    except Exception as e:
        print(f"❌ Error during video processing: {e}")
        await status_msg.edit_text("⚠️ Sistemska greška pri obradi snimka.")

# --- EXECUTION ---
if __name__ == '__main__':
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("❌ Token missing in .env file!")
        sys.exit(1)

    app = ApplicationBuilder().token(token).build()
    
    # Komande i handleri
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    
    print("🚀 GentStation UNIFIED Bot is online (Security Mode).")
    app.run_polling()