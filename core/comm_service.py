import os
import smtplib
import time
import string
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

logger = logging.getLogger("gentstation.comm_service")

# Load variables from .env
load_dotenv()


def send_activation_email(conn, user_id: int, reset_password: bool = False):
    """
    Sends a full activation email with account details and Telegram bot activation link.
    If reset_password=True, generates a fresh temporary password and stores its hash.
    """
    user_row = conn.execute(
        """
        SELECT id, username, email, role, is_active, station_id, region_id, name, surname
        FROM users
        WHERE id = %s
        """,
        (user_id,),
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

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    sender_email = os.getenv("SMTP_USER")
    sender_password = os.getenv("SMTP_PASS")
    bot_handle = os.getenv("TELEGRAM_BOT_HANDLE", "BaneTest_Bot")
    login_url = os.getenv("APP_LOGIN_URL", "https://gentstation-erp.streamlit.app")

    if not sender_email or not sender_password:
        return False, "SMTP credentials missing in .env."

    temp_password = None
    if reset_password:
        alphabet = string.ascii_letters + string.digits
        temp_password = "".join(secrets.choice(alphabet) for _ in range(10))
        conn.execute(
            "UPDATE users SET password_hash = %s, updated_at = NOW() WHERE id = %s",
            (hash_password_bcrypt(temp_password), uid),
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
        log_activity(
            conn,
            "SEND_ACTIVATION_EMAIL",
            f"Activation email sent to user_id={uid}, email={email}, reset_password={reset_password}",
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
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = os.getenv("SMTP_USER")
    SENDER_PASSWORD = os.getenv("SMTP_PASS")
    SUPPORT_RECIPIENT = "support@opus.rs"  # Admin/Support email address

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error(
            "System email is not configured. Please contact support directly at support@opus.rs."
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
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = os.getenv("SMTP_USER")
    SENDER_PASSWORD = os.getenv("SMTP_PASS")

    # 2. Build the Telegram Deep Link
    # Note: Use your actual bot handle here
    bot_handle = "BaneTest_Bot"
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
    Login URL: https://gentstation-erp.streamlit.app
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
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SENDER_EMAIL = os.getenv("SMTP_USER")
    SENDER_PASSWORD = os.getenv("SMTP_PASS")

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.debug("SMTP credentials missing. AI report email skipped.")
        return

    # 3. Prepare Email Content
    msg = MIMEMultipart()
    msg["From"] = f"GentStation AI Auditor <{SENDER_EMAIL}>"
    msg["To"] = manager_email
    msg["Subject"] = f"🚨 New AI Audit Report for {station_name}"

    body = f"""
    A new video submission for {station_name} has been analyzed by the AI Auditor.

    --- EXECUTIVE SUMMARY ---
    {report_data.get('summary', 'N/A')}

    --- KEY METRICS ---
    - Cleanliness Score: {report_data.get('cleanliness_score', 'N/A')} / 10
    - Safety Score:      {report_data.get('safety_score', 'N/A')} / 10
    - Staff Score:       {report_data.get('staff_score', 'N/A')} / 10

    Detected Hazards: {', '.join(report_data.get('hazards', ['None']))}

    You can view the full details in the GentStation Opus ERP dashboard.
    """
    msg.attach(MIMEText(body, "plain"))

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
    Finds a user by email, generates a new password, updates the DB, and sends it.
    Checks both users and employees tables to ensure they stay in sync.
    """
    if not email:
        st.error("Please enter an email address.")
        return

    email = email.strip()

    # Bot handle (matches core/bot_worker.py)
    bot_handle = os.getenv(
        "TELEGRAM_BOT_HANDLE", "BaneTest_Bot"
    )  # Ensure this matches your bot's username
    reporting_roles = ["Employee", "Gas Station Supervisor"]

    # 1. Verify user exists (Case-insensitive)
    user_row = conn.execute(
        "SELECT id, username, role FROM users WHERE LOWER(email) = LOWER(%s)", (email,)
    ).fetchone()

    if not user_row:
        st.error("No account found with that email address.")
        return

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
        return

    user_id, username, role = user_row

    # 2. Generate new password
    import string

    alphabet = string.ascii_letters + string.digits
    new_pw = "".join(secrets.choice(alphabet) for _ in range(10))

    # 3. Hash and update databases
    try:
        # Update users table (bcrypt)
        new_bcrypt_hash = hash_password_bcrypt(new_pw)
        conn.execute(
            "UPDATE users SET password_hash = %s, force_password_change = TRUE WHERE id = %s",
            (new_bcrypt_hash, user_id),
        )

        conn.commit()
    except Exception as e:
        st.error(f"Database error during password reset: {e}")
        return

    # 4. Send the email
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
    SENDER_EMAIL = os.getenv("SMTP_USER")
    SENDER_PASSWORD = os.getenv("SMTP_PASS")

    if not SENDER_EMAIL or not SENDER_PASSWORD:
        st.error("SMTP service not configured. Cannot send reset email.")
        return

    msg = MIMEMultipart("related")
    msg["From"] = f"GentStation System <{SENDER_EMAIL}>"
    msg["To"] = email
    msg["Subject"] = "Your Password Has Been Reset"

    html_body = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="text-align: center; padding: 20px;">
                <img src="cid:company_logo" alt="GentStation Logo" width="150" style="margin-bottom: 10px;">
                <h2 style="color: #2c3e50;">Password Reset</h2>
            </div>
            <p>Hello <strong>{username}</strong>,</p>
            <p>A password reset was requested for your account.</p>

            <div style="background-color: #f9f9f9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Login URL:</strong> <a href="https://gentstation-erp.streamlit.app">https://gentstation-erp.streamlit.app</a></p>
                <p><strong>Username:</strong> {email}</p>
                <p><strong>New Temporary Password:</strong> <code style="background: #e0e0e0; padding: 4px 8px; border-radius: 4px; font-size: 1.1em;">{new_pw}</code></p>
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
        log_activity(conn, "RESET_REQUEST", f"Password reset email sent to {email}")
        st.success(
            "Password reset successful. Please check your email for a new temporary password."
        )
    except Exception as e:
        st.error(f"Failed to send reset email: {e}")


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
