# gentstation_opus/services/telegram_service.py
import os
import requests
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def send_telegram_message(chat_id: str, text: str) -> bool:
    if not TOKEN or not chat_id:
        print("[telegram] missing token or chat_id. Skipping.")
        return False
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        res = r.json()
        return res.get("ok", False)
    except Exception as e:
        print("Telegram send error:", e)
        return False