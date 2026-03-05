import sqlite3
import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def get_hierarchy_emails(station_id):
    emails = {
        "supervisor": None,
        "station_mgr": None,
        "region_mgr": None,
        "directors": [],
        "gm": None
    }
    
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()

    # FORCE TYPE CONVERSION: Telegram/SQLite ID mismatch is the #1 cause of this
    try:
        clean_s_id = int(station_id)
    except:
        clean_s_id = station_id

    # 1. Get Manager & Supervisor for THIS station
    staff = cursor.execute("""
        SELECT email, role FROM employees 
        WHERE station_id = ? AND role IN ('Gas Station Supervisor', 'Gas Station Manager')
    """, (clean_s_id,)).fetchall()
    
    for email, role in staff:
        if role == 'Gas Station Supervisor': emails["supervisor"] = email
        if role == 'Gas Station Manager': emails["station_mgr"] = email

    # DEBUG PRINT: This will show in your terminal when you run hourly_summarizer.py
    print(f"🔍 SQL Match Result for Station {clean_s_id}: Manager={emails['station_mgr']}, Supervisor={emails['supervisor']}")

    # 2. Get Region Info
    region_data = cursor.execute("""
        SELECT r.id, r.name FROM regions r
        JOIN stations s ON s.region_id = r.id
        WHERE s.id = ?
    """, (clean_s_id,)).fetchone()

    region_name = "Unknown"
    if region_data:
        region_id, region_name = region_data
        
        # Region Manager
        reg_mgr = cursor.execute("SELECT email FROM employees WHERE region_id = ? AND role = 'Region Manager'", (region_id,)).fetchone()
        if reg_mgr: emails["region_mgr"] = reg_mgr[0]

        # Directors
        directors = cursor.execute("""
            SELECT e.email FROM employees e
            JOIN director_regions dr ON e.id = dr.employee_id
            WHERE dr.region_id = ? AND e.role = 'Region Director'
        """, (region_id,)).fetchall()
        emails["directors"] = [d[0] for d in directors]

    # 3. General Manager
    gm = cursor.execute("SELECT email FROM employees WHERE role = 'General Manager' LIMIT 1").fetchone()
    if gm: emails["gm"] = gm[0]

    conn.close()
    return emails, region_name if region_data else "Unknown"

def send_complex_reports(report_text, station_id):
    sender = os.getenv("SENDER_EMAIL")
    password = os.getenv("SENDER_PASSWORD")
    
    # Get Hierarchy
    hierarchy, region_name = get_hierarchy_emails(station_id)
    
    # --- FIXED: STRICT RECIPIENT LIST (Only Manager) ---
    to_list = []
    if hierarchy.get("station_mgr"):
        to_list.append(hierarchy["station_mgr"])
    
    # Remove duplicates and Nones
    to_list = list(set([e for e in to_list if e]))

    if not to_list:
        print(f"⚠️ Nema pronađenog menadžera za stanicu {station_id}.")
        return False

    # Create Email
    msg = MIMEMultipart()
    msg['From'] = f"GentStation AI Revizija <{sender}>"
    msg['To'] = ", ".join(to_list)
    # --- FIXED: SUBJECT IN SERBIAN ---
    msg['Subject'] = f"🚨 AI Operativna Revizija: Stanica ID {station_id} ({region_name})"

    # Format the AI output
    formatted_report = report_text.replace("\n", "<br>")

    # --- FIXED: HTML BODY IN SERBIAN ---
    body = f"""
    <html>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; line-height: 1.6;">
        <div style="background-color: #1f77b4; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
            <h1 style="margin: 0;">Izveštaj operativne revizije</h1>
            <p style="margin: 5px 0 0 0;">Stanica ID: {station_id} | Region: {region_name}</p>
        </div>
        <div style="padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 10px 10px; background-color: #fcfcfc;">
            <h2 style="color: #1f77b4; border-bottom: 2px solid #1f77b4; padding-bottom: 10px;">Rezultati AI Analize</h2>
            <div style="background-color: white; padding: 15px; border-radius: 5px; border: 1px solid #eee;">
                {formatted_report}
            </div>
            <p style="font-size: 0.9em; color: #777; margin-top: 20px;">
                <i>Ovo je automatski izveštaj generisan od strane GentStation AI sistema.</i>
            </p>
        </div>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(body, 'html'))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        print(f"🚀 [NOTIFIER] Izveštaj poslat menadžeru: {to_list}")
        return True
    except Exception as e:
        print(f"❌ [NOTIFIER] Slanje mejla nije uspelo: {e}")
        return False