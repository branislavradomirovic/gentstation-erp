import os
import json
import time
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def parse_station_video(video_path):
    """Sends video to Gemini and returns structured JSON."""
    # Upload the file to Google's temporary storage
    sample_file = genai.upload_file(path=video_path)
    
    # Wait for the file to be processed
    while sample_file.state.name == "PROCESSING":
        time.sleep(2)
        sample_file = genai.get_file(sample_file.name)
        
    if sample_file.state.name == "FAILED":
        raise ValueError("Video processing failed.")
    
    prompt = """
    You are an expert Fuel Retail Operations Auditor. 
    Analyze this CCTV footage from a gas station.
    
    Assess the following KPIs (1-10 scale, 10 is best):
    - Cleanliness: Status of forecourt, pumps, and bins.
    - Safety: adherence to protocols, fire risks, traffic safety.
    - Staff: Presence, uniform compliance, activity level.
    - Merchandising: Shelf stock levels, product availability, shelf organization.

    Return ONLY a raw JSON object (no markdown formatting) with these keys:
    {
      "cleanliness_score": int(1-10),
      "safety_score": int(1-10),
      "staff_score": int(1-10),
      "merchandising_score": int(1-10),
      "hazards": ["list", "of", "issues"],
      "stock_issues": ["list", "of", "empty shelves", "or products"],
      "customer_activity": "low|medium|high",
      "confidence": float(0.0-1.0),
      "summary": "Brief executive summary of the footage"
    }
    """
    
    model_name = "gemini-2.0-flash"
    print(f"🤖 [video_processor] Attempting analysis with {model_name}...")

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content([sample_file, prompt])
        
        # Remove markdown formatting if Gemini adds it (```json ... ```)
        raw_text = response.text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        
        return json.loads(raw_text)
    except Exception as e:
        print(f"❌ [video_processor] {model_name} failed: {e}")
        # Re-raise the exception to be handled by the worker
        raise RuntimeError(f"Gemini model {model_name} failed to process video. Error: {e}") from e