import os
import sqlite3
import time
import re
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)

try:
    from modules.notifier import send_complex_reports
except ImportError:
    print("⚠️ Greška: modules.notifier nije pronađen.")

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def generate_consolidated_hourly_report():
    conn = sqlite3.connect('company.db')
    cursor = conn.cursor()

    # 1. Prikupljanje svih neobrađenih snimaka sa svih stanica
    all_pending = cursor.execute("""
        SELECT id, station_id, video_path, role 
        FROM submissions 
        WHERE processed = 0
    """).fetchall()

    if not all_pending:
        print("📭 Red je prazan. Nema novih snimaka.")
        conn.close()
        return

    # Grupisanje podataka radi lakšeg snalaženja
    station_ids = list(set([row[1] for row in all_pending]))
    google_files = []
    video_map_for_prompt = ""

    print(f"📊 Priprema batch analize za {len(station_ids)} stanica...")

    try:
        # 2. Upload svih fajlova u jednom nizu
        for r_id, s_id, path, role in all_pending:
            if os.path.exists(path):
                print(f"📡 Otpremanje: {os.path.basename(path)} (Stanica {s_id})")
                g_file = genai.upload_file(path=path)
                google_files.append(g_file)
                video_map_for_prompt += f"- Snimak sa stanice ID {s_id} (Uloga: {role})\n"

        # Čekanje na procesiranje fajlova
        time.sleep(10)

        # 3. Konfiguracija modela sa strogim instrukcijama za formatiranje
        model = genai.GenerativeModel(
            model_name="models/gemini-2.5-flash",
            system_instruction=(
                "Vi ste profesionalni revizor benzinskih stanica. Vaš JEDINI jezik je SRPSKI. "
                "Dobićete snimke sa više različitih stanica. "
                "OBAVEZNO koristite format [STATION_ID: broj] pre svakog izveštaja kako bih mogao da razvrstam tekst. "
                "Pišite kratko, direktno i isključivo na srpskoj latinici."
            )
        )

        # 4. Prompt koji traži jedan odgovor za sve stanice
        prompt = f"""
        ZADATAK: Napravi pojedinačne izveštaje za sledeće stanice: {station_ids}.
        
        Za svaku stanicu uradi sledeće:
        1. Počni deo sa [STATION_ID: broj_stanice]
        2. Analiziraj bezbednost, čistoću i osoblje na osnovu njenih snimaka.
        3. Daj ocenu od 1-10.
        
        Evo liste snimaka koje si primio:
        {video_map_for_prompt}
        
        IZVEŠTAJ MORA BITI NA SRPSKOM JEZIKU.
        """

        print("🧠 [AI] Pokretanje jedinstvene batch analize (Trošim 1 kredit)...")
        response = model.generate_content([*google_files, prompt])
        full_response_text = response.text

        # 5. Razvrstavanje odgovora i slanje mejlova
        for s_id in station_ids:
            # Koristimo Regex da izvučemo deo teksta koji pripada toj stanici
            pattern = rf"\[STATION_ID:\s*{s_id}\](.*?)(?=\[STATION_ID:|\Z)"
            match = re.search(pattern, full_response_text, re.DOTALL | re.IGNORECASE)
            
            if match:
                station_report = match.group(1).strip()
                print(f"📧 Šaljem izveštaj menadžeru stanice {s_id}...")
                
                success = send_complex_reports(station_report, s_id)
                if success:
                    cursor.execute("UPDATE submissions SET processed = 1 WHERE station_id = ?", (s_id,))
                    conn.commit()
            else:
                print(f"⚠️ AI nije generisao prepoznatljiv deo za stanicu {s_id}.")

    except Exception as e:
        print(f"❌ Kritična greška: {e}")
    
    finally:
        # Čišćenje Google fajlova
        for f in google_files:
            try:
                genai.delete_file(f.name)
            except:
                pass
        conn.close()

if __name__ == "__main__":
    generate_consolidated_hourly_report()