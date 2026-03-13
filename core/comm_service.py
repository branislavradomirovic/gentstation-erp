import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import streamlit as st
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

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
    if user_data['role'] in reporting_roles:
        tg_link = f"https://t.me/{bot_handle}?start={user_data['id']}"

    # 3. Prepare Email Content
    msg = MIMEMultipart()
    msg['From'] = f"GentStation Opus ERP <{SENDER_EMAIL}>"
    msg['To'] = user_data['email']
    msg['Subject'] = "🚀 Account Created: GentStation Opus ERP"

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
    msg.attach(MIMEText(body, 'plain'))

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