import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def parse_station_video(video_path):
    """Sends video to Gemini and returns structured JSON."""
    model = genai.GenerativeModel('models/gemini-pro')
    
    # Upload the file to Google's temporary storage
    sample_file = genai.upload_file(path=video_path)
    
    prompt = """
    Analyze this gas station footage. 
    Return ONLY a JSON object (no extra text) with:
    {
      "pumps_count": int,
      "cleanliness_score": int(1-10),
      "safety_hazards": list,
      "customer_activity": "low|medium|high",
      "summary": "short description"
    }
    """
    
    response = model.generate_content([sample_file, prompt])
    
    # Remove markdown formatting if Gemini adds it (```json ... ```)
    raw_text = response.text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
            
    return json.loads(raw_text)