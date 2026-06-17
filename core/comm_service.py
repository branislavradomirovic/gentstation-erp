import os
import smtplib
import time
import string
import requests
import json
from typing import Optional, Dict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from pathlib import Path
import secrets
import hashlib
import logging
import streamlit as st
from dotenv import load_dotenv
from core.auth import hash_password as hash_password_bcrypt
from core.activity_logger import log_activity
from core.tenant_context import require_current_tenant_context
from core.runtime_config import configured_app_login_url

logger = logging.getLogger("gentstation.comm_service")

# Load variables from .env
load_dotenv()


def _login_url() -> str:
    return configured_app_login_url()


def _bot_handle() -> str:
    return os.getenv("TELEGRAM_BOT_HANDLE", "your_bot_username")


def _smtp_settings():
    return (
        os.getenv("SMTP_SERVER") or os.getenv("SMTP_HOST", "smtp.gmail.com"),
        int(os.getenv("SMTP_PORT", 587)),
        os.getenv("SMTP_USER"),
        os.getenv("SMTP_PASS"),
    )


def _telegram_bot_token() -> Optional[str]:
    return os.getenv("TELEGRAM_BOT_TOKEN")


def _truncate_text(value: str, limit: int = 120) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _risk_band(risk_score: float) -> str:
    if risk_score >= 70:
        return "Visok"
    if risk_score >= 40:
        return "Srednji"
    return "Nizak"


def _short_risk_feedback(risk_score: float, report_data: dict) -> str:
    hazards = report_data.get("hazards") or []
    if isinstance(hazards, str):
        hazards = [hazards]
    top_hazard = _truncate_text(hazards[0], 60) if hazards else ""

    if risk_score >= 70:
        return f"Potrebna je hitna reakcija{': ' + top_hazard if top_hazard else '.'}"
    if risk_score >= 40:
        return f"Uočen je operativni rizik{': ' + top_hazard if top_hazard else '.'}"
    return "Na snimku je uočen nizak nivo vidljivog rizika."


def _safe_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def send_scheduled_report_email(recipient_email: str, payload: Dict) -> bool:
    smtp_server, smtp_port, sender_email, sender_password = _smtp_settings()
    if not recipient_email or not sender_email or not sender_password:
        return False

    hazards = ", ".join(_safe_list(payload.get("hazards"))) or "Nema izdvojenih rizika."
    stock_issues = ", ".join(_safe_list(payload.get("stock_issues"))) or "Nema izdvojenih operativnih problema."
    actions = _safe_list(payload.get("improvement_actions")) or [
        "Nastaviti redovnu kontrolu i pratiti naredni period."
    ]

    msg = MIMEMultipart("alternative")
    msg["From"] = f"GentStationAI <{sender_email}>"
    msg["To"] = recipient_email
    msg["Subject"] = payload.get("title", "GentStationAI izveštaj")

    plain = f"""
{payload.get('title', 'GentStationAI izveštaj')}

Period: {payload.get('period_label', '-')}

{payload.get('summary', '')}

Ukupan rizik: {payload.get('overall_risk_score', 'N/A')}/100
Bezbednost: {payload.get('safety_score', 'N/A')}/10
Čistoća: {payload.get('cleanliness_score', 'N/A')}/10
Zaposleni: {payload.get('staff_score', 'N/A')}/10
Merchandising: {payload.get('merchandising_score', 'N/A')}/10

Ključni rizici: {hazards}
Operativni problemi: {stock_issues}

Preporučene akcije:
- """ + "\n- ".join(actions)

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background:#f5f7fb; color:#1f2937; padding:24px;">
        <div style="max-width:760px; margin:0 auto; background:#fff; border:1px solid #e5e7eb; border-radius:16px; padding:24px;">
          <div style="font-size:12px; letter-spacing:0.08em; text-transform:uppercase; color:#0b5ed7; font-weight:700;">GentStationAI</div>
          <h2 style="margin:8px 0 6px 0;">{payload.get('title', 'GentStationAI izveštaj')}</h2>
          <p style="color:#6b7280; margin:0 0 16px 0;">Period: {payload.get('period_label', '-')}</p>
          <div style="background:#f3f7ff; border:1px solid #dbe7ff; border-radius:12px; padding:16px; margin-bottom:18px;">
            {payload.get('summary', '')}
          </div>
          <table style="width:100%; border-collapse:collapse; margin-bottom:18px;">
            <tr>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Ukupan rizik</strong><br>{payload.get('overall_risk_score', 'N/A')}/100</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Bezbednost</strong><br>{payload.get('safety_score', 'N/A')}/10</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Čistoća</strong><br>{payload.get('cleanliness_score', 'N/A')}/10</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Zaposleni</strong><br>{payload.get('staff_score', 'N/A')}/10</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Merch.</strong><br>{payload.get('merchandising_score', 'N/A')}/10</td>
            </tr>
          </table>
          <h3>Ključni rizici</h3>
          <p>{hazards}</p>
          <h3>Operativni problemi</h3>
          <p>{stock_issues}</p>
          <h3>Preporučene akcije</h3>
          <ul>
            {''.join(f'<li>{item}</li>' for item in actions)}
          </ul>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error("Scheduled report email failed for %s: %s", recipient_email, e)
        return False


def send_scheduled_report_telegram(chat_id: str, payload: Dict) -> bool:
    token = _telegram_bot_token()
    if not token or not chat_id:
        return False

    actions = _safe_list(payload.get("improvement_actions"))[:3]
    action_text = "\n".join(f"- {item}" for item in actions) or "- Nema dodatnih akcija."
    message = (
        f"📊 {payload.get('title', 'GentStationAI izveštaj')}\n"
        f"Period: {payload.get('period_label', '-')}\n"
        f"{payload.get('summary', '')}\n"
        f"Ukupan rizik: {payload.get('overall_risk_score', 'N/A')}/100 ({payload.get('risk_band', '-')})\n"
        f"Preporučene akcije:\n{action_text}"
    )
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": str(chat_id), "text": message},
            timeout=10,
        )
        return response.status_code == 200
    except Exception as e:
        logger.error("Scheduled Telegram report failed for chat %s: %s", chat_id, e)
        return False


def send_submission_result_telegram(
    conn,
    submission_id: int,
    report_data: Optional[Dict] = None,
    error_message: Optional[str] = None,
) -> bool:
    """
    Notify the uploader in Telegram when AI processing finishes.
    Sends a short risk-oriented summary on success and a retry-friendly message
    on failure. Returns True when Telegram accepted the message.
    """
    token = _telegram_bot_token()
    if not token:
        logger.debug("Telegram bot token missing. Completion notification skipped.")
        return False

    tenant_id = require_current_tenant_context().tenant_id
    row = conn.execute(
        """
        SELECT u.telegram_chat_id, COALESCE(s.name, 'Unknown Station') AS station_name
        FROM submissions sub
        JOIN users u ON sub.employee_id = u.id
        LEFT JOIN stations s ON sub.station_id = s.id
        WHERE sub.id = %s AND sub.tenant_id = %s
        """,
        (submission_id, tenant_id),
    ).fetchone()
    if not row or not row[0]:
        logger.debug(
            "No Telegram chat linked for submission %s. Completion notification skipped.",
            submission_id,
        )
        return False

    chat_id, station_name = row

    if report_data is not None:
        try:
            from ai_engine.risk_engine import compute_station_risk_from_metrics

            risk_score = compute_station_risk_from_metrics(report_data)
        except Exception:
            safety = float(report_data.get("safety_score", 7) or 7)
            risk_score = max(0.0, min(100.0, round(((10.0 - safety) / 10.0) * 100.0, 2)))

        summary = _truncate_text(report_data.get("summary", ""), 100)
        feedback = _short_risk_feedback(risk_score, report_data)
        message = (
            f"✅ Video za stanicu {station_name} je obrađen.\n"
            f"AI povratna informacija: Rizik {round(risk_score, 1)}/100 ({_risk_band(risk_score)}). {feedback}"
        )
        if summary and summary not in {"No summary provided.", "Sažetak nije dostupan."}:
            message += f"\nSažetak: {summary}"
    else:
        reason = _truncate_text(error_message or "Nepoznata greška pri obradi.", 120)
        message = (
            f"⚠️ Obrada videa za stanicu {station_name} nije uspela.\n"
            f"Razlog: {reason}\n"
            "Fajl je zadržan kako bi mogao ponovo da se obradi."
        )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": str(chat_id), "text": message},
            timeout=10,
        )
        if response.status_code == 200:
            logger.info(
                "Telegram completion notification sent for submission %s to chat %s.",
                submission_id,
                chat_id,
            )
            return True
        logger.warning(
            "Telegram completion notification failed for submission %s: %s %s",
            submission_id,
            response.status_code,
            response.text,
        )
    except Exception as e:
        logger.warning(
            "Telegram completion notification errored for submission %s: %s",
            submission_id,
            e,
        )
    return False


def send_activation_email(
    conn, user_id: int, reset_password: bool = False, tenant_id: Optional[int] = None
):
    """
    Sends a full activation email with account details and Telegram bot activation link.
    If reset_password=True, generates a fresh temporary password and stores its hash.
    """
    tenant_id = int(tenant_id) if tenant_id is not None else require_current_tenant_context().tenant_id
    user_row = conn.execute(
        """
        SELECT id, username, email, role, is_active, station_id, region_id, name, surname
        FROM users
        WHERE id = %s AND tenant_id = %s
        """,
        (user_id, tenant_id),
    ).fetchone()
    if not user_row:
        return False, "User not found."

    (
        uid,
        username,
        email,
        role,
        is_active,
        station_id,
        region_id,
        first_name,
        surname,
    ) = user_row

    if not email:
        return False, "User has no email address."

    smtp_server, smtp_port, sender_email, sender_password = _smtp_settings()
    bot_handle = _bot_handle()
    try:
        login_url = _login_url()
    except RuntimeError as exc:
        return False, str(exc)

    if not sender_email or not sender_password:
        return False, "SMTP credentials missing in .env."

    temp_password = None
    if reset_password:
        alphabet = string.ascii_letters + string.digits
        temp_password = "".join(secrets.choice(alphabet) for _ in range(10))
        conn.execute(
            "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE tenant_id = %s AND id = %s",
            (hash_password_bcrypt(temp_password), tenant_id, uid),
        )
        conn.commit()

    tg_link = f"https://t.me/{bot_handle}?start={uid}"
    full_name = f"{first_name or ''} {surname or ''}".strip() or username

    msg = MIMEMultipart("alternative")
    msg["From"] = f"GentStation System <{sender_email}>"
    msg["To"] = email
    msg["Subject"] = "GentStation Account Activation Details"

    temp_pw_block = (
        f"<p><strong>Temporary Password:</strong> <code>{temp_password}</code></p>"
        if temp_password
        else "<p><strong>Password:</strong> Use your current password. If forgotten, use Reset Password.</p>"
    )

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color:#222;">
        <h2>Account Activation</h2>
        <p>Hello <strong>{full_name}</strong>,</p>
        <p>Your GentStation account details:</p>
        <ul>
          <li><strong>User ID:</strong> {uid}</li>
          <li><strong>Username:</strong> {username}</li>
          <li><strong>Email:</strong> {email}</li>
          <li><strong>Role:</strong> {role}</li>
          <li><strong>Active:</strong> {bool(is_active)}</li>
          <li><strong>Station ID:</strong> {station_id if station_id is not None else "N/A"}</li>
          <li><strong>Region ID:</strong> {region_id if region_id is not None else "N/A"}</li>
        </ul>
        <p><strong>Login URL:</strong> <a href="{login_url}">{login_url}</a></p>
        {temp_pw_block}
        <h3>Telegram Bot Activation</h3>
        <p>Use this personal activation link to connect your Telegram account:</p>
        <p><a href="{tg_link}">{tg_link}</a></p>
        <p>After activation, you can submit videos directly to the bot for AI processing.</p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        try:
            log_activity(
                conn,
                "SEND_ACTIVATION_EMAIL",
                f"Activation email sent to user_id={uid}, email={email}, reset_password={reset_password}",
                tenant_id=tenant_id,
            )
        except Exception as exc:
            logger.warning(
                "Activation email audit logging failed for user_id=%s: %s",
                uid,
                exc,
            )
        return True, f"Activation email sent to {email}."
    except Exception as e:
        return False, f"Failed to send email: {e}"


def send_support_email(from_user: str, subject: str, message: str) -> bool:
    """
    Sends a support request email to the admin address.
    Returns True on success, False on failure.
    """
    # 1. Credentials from .env
    SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD = _smtp_settings()
    SUPPORT_RECIPIENT = os.getenv("SUPPORT_RECIPIENT", "support@example.com")

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error(
            f"System email is not configured. Please contact support directly at {SUPPORT_RECIPIENT}."
        )
        return False

    # 2. Prepare Email Content
    msg = MIMEMultipart()
    msg["From"] = f"GentStation Support Form <{SENDER_EMAIL}>"
    msg["To"] = SUPPORT_RECIPIENT
    msg["Subject"] = f"[Support Request] {subject}"

    body = f"""
    A new support request has been submitted from the GentStation Opus ERP.

    --- DETAILS ---
    From User: {from_user}
    Subject: {subject}

    Message:
    {message}
    ----------------
    """
    msg.attach(MIMEText(body, "plain"))

    # 3. Actual Transmission
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"❌ SMTP Error: Could not send email. {str(e)}")
        return False


def send_welcome_comms(user_data):
    """
    Handles real SMTP email delivery and returns Telegram link if applicable.
    """
    # 1. Credentials from .env
    SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD = _smtp_settings()

    # 2. Build the Telegram Deep Link
    # Note: Use your actual bot handle here
    bot_handle = _bot_handle()
    reporting_roles = ["Employee", "Gas Station Supervisor"]

    tg_link = None
    if user_data["role"] in reporting_roles:
        tg_link = f"https://t.me/{bot_handle}?start={user_data['id']}"

    # 3. Prepare Email Content
    msg = MIMEMultipart()
    msg["From"] = f"GentStation Opus ERP <{SENDER_EMAIL}>"
    msg["To"] = user_data["email"]
    msg["Subject"] = "🚀 Account Created: GentStation Opus ERP"

    body = f"""
    Hello {user_data['name']},

    Your account has been successfully created in the GentStation Opus ERP system.

    --- YOUR ACCESS DETAILS ---
    Login URL: {_login_url()}
    Username: {user_data['email']}
    Temporary Password: {user_data['password_plain']}
    ---------------------------
    """

    if tg_link:
        body += f"""

📲 ACTION REQUIRED:
Because your role is {user_data['role']}, you must connect your Telegram account
to our automated reporting bot to send video reports.

Please click the link below to register:
{tg_link}
        """

    body += "\n\nRegards,\nSystem Administration"
    msg.attach(MIMEText(body, "plain"))

    # 4. Actual Transmission
    try:
        # If credentials are missing, skip and just return the link for UI display
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            st.warning("SMTP credentials missing in .env. Email skipped.")
            return tg_link

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        st.toast(f"✅ Email sent to {user_data['email']}", icon="📧")
        return tg_link

    except Exception as e:
        st.error(f"❌ SMTP Error: {str(e)}")
        # We still return the link so the admin can give it to the user manually
        return tg_link


def send_ai_report_email(conn, station_id: int, report_data: dict):
    """
    Sends an AI report summary to the relevant Gas Station Manager.
    """
    # 1. Find the manager for the station
    cur = conn.cursor()
    manager_query = cur.execute(
        """ -- Manager email is now directly in the users table
        SELECT u.email, s.name as station_name
        FROM users u
        JOIN stations s ON u.station_id = s.id
        WHERE u.role = 'Gas Station Manager' AND u.station_id = %s AND u.email IS NOT NULL
    """,
        (station_id,),
    ).fetchone()

    if not manager_query:
        logger.debug("No manager found for station %s. Skipping email.", station_id)
        return

    manager_email, station_name = manager_query

    # 2. Credentials from .env
    SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD = _smtp_settings()

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.debug("SMTP credentials missing. AI report email skipped.")
        return

    # 3. Prepare Email Content
    msg = MIMEMultipart()
    msg["From"] = f"GentStation AI Auditor <{SENDER_EMAIL}>"
    msg["To"] = manager_email
    msg["Subject"] = f"AI izveštaj za stanicu {station_name}"

    hazards = report_data.get("hazards", ["Nema"])
    if not isinstance(hazards, list):
        hazards = [hazards]
    hazard_text = ", ".join(str(item) for item in hazards if str(item).strip()) or "Nema"
    stock_issues = report_data.get("stock_issues", ["Nema"])
    if not isinstance(stock_issues, list):
        stock_issues = [stock_issues]
    stock_text = ", ".join(str(item) for item in stock_issues if str(item).strip()) or "Nema"
    actions = report_data.get("improvement_actions") or []
    if not isinstance(actions, list):
        actions = [actions]
    action_markup = "".join(
        f"<li>{str(item).strip()}</li>" for item in actions if str(item).strip()
    ) or "<li>Nema dodatnih preporuka.</li>"
    risk_score = report_data.get("overall_risk_score", "N/A")
    summary_text = report_data.get("summary", "Sažetak nije dostupan.")

    plain_body = f"""
    Novi video izveštaj za stanicu {station_name} je obrađen.

    SAŽETAK
    {summary_text}

    KLJUČNI REZULTATI
    - Ukupan rizik: {risk_score}/100
    - Čistoća: {report_data.get('cleanliness_score', 'N/A')} / 10
    - Bezbednost: {report_data.get('safety_score', 'N/A')} / 10
    - Zaposleni: {report_data.get('staff_score', 'N/A')} / 10
    - Merchandising: {report_data.get('merchandising_score', 'N/A')} / 10

    UOČENI RIZICI
    {hazard_text}

    STOCK / IZVRŠENJE
    {stock_text}

    PREPORUČENE AKCIJE
    - """ + "\n    - ".join(
        [str(item).strip() for item in actions if str(item).strip()] or ["Nema dodatnih preporuka."]
    ) + """

    Kompletan izveštaj je dostupan u GentStationAI aplikaciji.
    """

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color:#1f2937; background:#f7f9fc; padding:16px;">
        <div style="max-width:720px; margin:0 auto; background:#ffffff; border:1px solid #e5e7eb; border-radius:16px; padding:24px;">
          <div style="font-size:12px; letter-spacing:0.08em; text-transform:uppercase; color:#0b5ed7; font-weight:700;">GentStationAI</div>
          <h2 style="margin:10px 0 6px 0; color:#111827;">AI izveštaj za stanicu {station_name}</h2>
          <p style="margin:0 0 18px 0; color:#4b5563;">Video je uspešno analiziran i pripremljen za menadžerski pregled.</p>

          <div style="background:#f3f7ff; border:1px solid #dbe7ff; border-radius:12px; padding:14px 16px; margin-bottom:18px;">
            <div style="font-size:12px; text-transform:uppercase; color:#0b5ed7; font-weight:700; margin-bottom:6px;">Sažetak</div>
            <div style="font-size:15px; line-height:1.6; color:#111827;">{summary_text}</div>
          </div>

          <table style="width:100%; border-collapse:collapse; margin-bottom:18px;">
            <tr>
              <td style="padding:10px; border:1px solid #e5e7eb; border-radius:10px;"><strong>Ukupan rizik</strong><br>{risk_score}/100</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Čistoća</strong><br>{report_data.get('cleanliness_score', 'N/A')} / 10</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Bezbednost</strong><br>{report_data.get('safety_score', 'N/A')} / 10</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Zaposleni</strong><br>{report_data.get('staff_score', 'N/A')} / 10</td>
              <td style="padding:10px; border:1px solid #e5e7eb;"><strong>Merch.</strong><br>{report_data.get('merchandising_score', 'N/A')} / 10</td>
            </tr>
          </table>

          <h3 style="margin:0 0 8px 0; color:#111827;">Uočeni rizici</h3>
          <p style="margin:0 0 16px 0; color:#374151;">{hazard_text}</p>

          <h3 style="margin:0 0 8px 0; color:#111827;">Stock / izvršenje</h3>
          <p style="margin:0 0 16px 0; color:#374151;">{stock_text}</p>

          <h3 style="margin:0 0 8px 0; color:#111827;">Preporučene akcije</h3>
          <ul style="margin:0 0 16px 18px; color:#374151; line-height:1.6;">
            {action_markup}
          </ul>

          <p style="margin:0; color:#6b7280;">Kompletan izveštaj možete pregledati u GentStationAI aplikaciji.</p>
        </div>
      </body>
    </html>
    """
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    # 4. Actual Transmission
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            logger.info(
                "AI report sent to %s for station %s.", manager_email, station_id
            )
    except Exception as e:
        logger.error("SMTP error sending AI report: %s", e)


def send_station_qr_email(
    station_name: str, recipient_email: str, bot_link: str, qr_url: str
):
    """
    Sends the QR code link and bot instructions to the station manager.
    """
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = os.getenv("SMTP_USER")
    SENDER_PASSWORD = os.getenv("SMTP_PASS")

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error("SMTP credentials missing.")
        return

    msg = MIMEMultipart()
    msg["From"] = f"GentStation Operations <{SENDER_EMAIL}>"
    msg["To"] = recipient_email
    msg["Subject"] = f"📲 Setup Instructions: {station_name}"

    body = f"""
    Hello,

    Here are the mobile access instructions for {station_name}.

    1. Employees must install Telegram.
    2. Register using the invite link in their welcome email.
    3. To submit reports, they can scan the station QR code or use this link:
       {bot_link}

    Direct QR Code Link:
    {qr_url}

    Please print the QR code and display it in a secure staff area.
    """
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            st.toast(f"Instructions sent to {recipient_email}", icon="📧")
    except Exception as e:
        st.error(f"Failed to send email: {e}")


def send_password_reset_email(conn, email: str):
    """
    Finds a user by email, generates a new temporary password, updates the DB,
    and emails it to the user.
    """
    if not email:
        st.error("Please enter an email address.")
        return False, "Please enter an email address."

    email = email.strip()

    # Bot handle (matches core/bot_worker.py)
    bot_handle = os.getenv(
        "TELEGRAM_BOT_HANDLE", "your_bot_username"
    )  # Ensure this matches your bot's username
    reporting_roles = ["Employee", "Gas Station Supervisor"]

    # 1. Verify user exists (Case-insensitive)
    user_row = conn.execute(
        """
        SELECT id, username, role, tenant_id, password_hash, force_password_change, lifecycle_state
        FROM users
        WHERE LOWER(email) = LOWER(%s)
        """,
        (email,),
    ).fetchone()

    if not user_row:
        st.error("No account found with that email address.")
        return False, "No account found with that email address."

    # 1.5 Rate Limit Check (Prevent abuse)
    # Check if a reset was requested for this email in the last 15 minutes
    last_request = conn.execute(
        """
        SELECT timestamp FROM activity_logs
        WHERE action = 'RESET_REQUEST' AND details LIKE %s AND timestamp >= NOW() - INTERVAL '15 MINUTES'
    """,
        (f"%{email}%",),
    ).fetchone()
    if last_request:
        st.error(
            "A password reset was already requested recently. Please check your email or wait 15 minutes."
        )
        return False, "A password reset was already requested recently."

    (
        user_id,
        username,
        role,
        tenant_id,
        old_password_hash,
        old_force_password_change,
        old_lifecycle_state,
    ) = user_row

    # 2. Validate email delivery configuration before changing credentials.
    SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD = _smtp_settings()

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error("SMTP service not configured. Cannot send reset email.")
        return False, "SMTP service not configured. Cannot send reset email."

    try:
        login_url = _login_url()
    except RuntimeError as exc:
        st.error(str(exc))
        return False, str(exc)

    # 3. Generate new password
    import string

    alphabet = string.ascii_letters + string.digits
    new_pw = "".join(secrets.choice(alphabet) for _ in range(10))

    # 4. Hash and update databases
    try:
        # Update users table (bcrypt)
        new_bcrypt_hash = hash_password_bcrypt(new_pw)
        conn.execute(
            """
            UPDATE users
            SET password_hash = %s, force_password_change = TRUE, lifecycle_state = 'password_reset_required'
            WHERE tenant_id = %s AND id = %s
            """,
            (new_bcrypt_hash, tenant_id, user_id),
        )

        conn.commit()
    except Exception as e:
        st.error(f"Database error during password reset: {e}")
        return False, f"Database error during password reset: {e}"

    msg = MIMEMultipart("related")
    msg["From"] = f"GentStation System <{SENDER_EMAIL}>"
    msg["To"] = email
    msg["Subject"] = "Your Temporary Password for GentStationAI"

    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="text-align: center; padding: 20px;">
                <img src="cid:company_logo" alt="GentStation Logo" width="150" style="margin-bottom: 10px;">
                <h2 style="color: #2c3e50;">Temporary Password Request</h2>
            </div>
            <p>Hello <strong>{username}</strong>,</p>
            <p>A temporary password was requested for your account.</p>

            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Login URL:</strong> <a href="{login_url}">{login_url}</a></p>
                <p><strong>Username:</strong> {email}</p>
                <p><strong>Temporary Password:</strong> <code style="background: #e0e0e0; padding: 4px 8px; border-radius: 4px; font-size: 1.1em;">{new_pw}</code></p>
            </div>

            """
    if user_row and user_row[2] in reporting_roles:  # user_row[2] is role
        tg_link = (
            f"https://t.me/{bot_handle}?start={user_row[0]}"  # user_row[0] is user_id
        )
        html_body += f"""
            <p><strong>📲 Telegram Registration:</strong> If your role requires submitting reports via Telegram, please ensure your account is linked by clicking here: <a href="{tg_link}">Link Telegram Account</a></p>
            """

    html_body += f"""
            <p>Please log in and change this password immediately from the Settings page.</p>
            <p style="font-size: 0.9em; color: #777;">If you did not request this reset, please contact support.</p>
        </body>
    </html>
    """
    msg.attach(MIMEText(html_body, "html"))

    # Attach Logo
    logo_path = Path(__file__).resolve().parents[1] / "assets" / "GSAI_Logo.png"
    if logo_path.exists():
        try:
            with open(logo_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-ID", "<company_logo>")
                img.add_header("Content-Disposition", "inline")
                msg.attach(img)
        except Exception as e:
            logger.debug("Error attaching logo to email: %s", e)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        try:
            conn.execute(
                """
                UPDATE users
                SET password_hash = %s, force_password_change = %s, lifecycle_state = %s
                WHERE tenant_id = %s AND id = %s
                """,
                (
                    old_password_hash,
                    old_force_password_change,
                    old_lifecycle_state,
                    tenant_id,
                    user_id,
                ),
            )
            conn.commit()
        except Exception as rollback_exc:
            logger.error(
                "Failed to restore password after reset email failure for user_id=%s: %s",
                user_id,
                rollback_exc,
            )
        st.error(f"Failed to send temporary password email: {e}")
        return False, f"Failed to send temporary password email: {e}"

    try:
        log_activity(
            conn,
            "RESET_REQUEST",
            f"Temporary password email sent to {email}",
            tenant_id=tenant_id,
        )
    except Exception as exc:
        logger.warning(
            "Password reset audit logging failed for user_id=%s: %s",
            user_id,
            exc,
        )

    st.success(
        "Temporary password sent. Please check your email and sign in with it before changing your password."
    )
    return True, "Temporary password email sent."


def test_smtp_connection(on_retry=None) -> bool:
    """Test if SMTP server is reachable and credentials are valid."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    # Skip test if credentials are not configured yet
    if not smtp_user or not smtp_pass:
        return False

    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=5) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                return True
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "SMTP connection attempt %d failed: %s. Retrying in %ds...",
                    attempt + 1,
                    e,
                    retry_delay,
                )
                for i in range(retry_delay, 0, -1):
                    if on_retry:
                        on_retry(attempt + 1, max_retries, i, e)
                    time.sleep(1)
            else:
                logger.error(
                    "SMTP connection failed after %d attempts: %s", max_retries, e
                )
                return False
