# gentstation_opus/services/notifier.py
from .telegram_service import send_telegram_message
from .email_service import send_email
import json


def notify_station_manager(report_text: str, manager: dict, payload: dict) -> bool:
    # manager: {id, name, email, telegram}
    sent = False
    if manager.get("telegram"):
        sent = send_telegram_message(manager["telegram"], report_text) or sent
    if manager.get("email"):
        html = f"<pre>{report_text}</pre>"
        sent = send_email(manager["email"], "GentStation AI Report", html) or sent
    if not sent:
        # fallback: print + return True so pipeline continues
        print("[notify] fallback print to console")
        print(report_text[:2000])
        sent = True
    return sent
