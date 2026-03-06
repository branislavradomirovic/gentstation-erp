import sqlite3
import os
import logging
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Postavljanje osnovnog logovanja da vidiš greške u terminalu
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 1. Učitavanje tokena iz .env fajla
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ova funkcija se aktivira kada korisnik pritisne START dugme"""
    user_chat_id = update.effective_chat.id
    print(f"---> Bot primio komandu od Chat ID: {user_chat_id}") # DEBUG
    
    # Provera da li link sadrži ID (npr. ?start=5)
    if not context.args:
        print("!!! Link nema parametara") # DEBUG
        await update.message.reply_text("❌ Greška: Link ne sadrži vaš identifikacioni ID.")
        return

    # Uzimanje ID-a iz argumenata
    try:
        emp_id = int(context.args[0])
        print(f"---> Pokušaj povezivanja za Employee ID: {emp_id}") # DEBUG
    except ValueError:
        await update.message.reply_text("❌ Greška: Neispravan format ID-a.")
        return

    try:
        # 2. Povezivanje na bazu - Pazi da putanja bude ista kao u admin_gui.py
        conn = sqlite3.connect('company.db')
        
        # Proveravamo da li zaposleni postoji
        user_exists = conn.execute("SELECT name FROM employees WHERE id = ?", (emp_id,)).fetchone()
        
        if user_exists:
            # Upisujemo telegram_chat_id u tabelu employees
            conn.execute("UPDATE employees SET telegram_chat_id = ? WHERE id = ?", (str(user_chat_id), emp_id))
            conn.commit()
            
            print(f"✅ Uspešno povezan korisnik: {user_exists[0]}") # DEBUG
            await update.message.reply_text(f"✅ Uspešno povezano! Dobrodošli {user_exists[0]}. Od sada ćete ovde primati izveštaje.")
        else:
            print(f"❌ Zaposleni sa ID {emp_id} nije nađen u bazi.") # DEBUG
            await update.message.reply_text(f"❌ Greška: Zaposleni sa ID {emp_id} nije pronađen u bazi.")
        
        conn.close()
    except Exception as e:
        print(f"⚠️ Sistemska greška: {e}") # DEBUG
        await update.message.reply_text(f"⚠️ Sistemska greška pri povezivanju sa bazom.")

# 3. POKRETANJE BOTA (Ovo mora biti van funkcija, na kraju fajla)
if __name__ == '__main__':
    if not TELEGRAM_BOT_TOKEN:
        print("❌ GREŠKA: TELEGRAM_BOT_TOKEN nije definisan u .env fajlu!")
    else:
        print("🚀 Bot se pokreće... Čekam poruke na Telegramu.")
        
        # Inicijalizacija aplikacije
        app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
        
        # Registracija komande /start
        app.add_handler(CommandHandler("start", start))
        
        # Pokretanje bota
        print("🤖 Bot je aktivan i sluša... Pritisni Ctrl+C za prekid.")
        app.run_polling()