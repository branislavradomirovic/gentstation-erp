# gentstation_opus/ai_engine/gemini_client.py
import os, re, json
from dotenv import load_dotenv
load_dotenv()

# Attempt to import Google generative AI client; if missing, use fallback
try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    HAS_GEMINI = True
except Exception as e:
    print("genai client not available, using fallback:", e)
    HAS_GEMINI = False

MODEL_NAME = "models/gemini-pro"

def generate_from_prompt(prompt: str, file_objs: list = None, timeout: int = 120) -> str:
    """
    Calls Gemini generate_content with the prompt and optional files.
    If Gemini client is not available, returns None (caller should handle).
    """
    if not HAS_GEMINI:
        print("[gemini] no client available; returning fallback sample.")
        return fallback_sample_response(prompt)
    try:
        model = genai.GenerativeModel(model_name=MODEL_NAME)
        if file_objs:
            # many genai wrappers accept files before prompt; adapt if necessary
            response = model.generate_content([*file_objs, prompt])
        else:
            response = model.generate_content([prompt])
        text = getattr(response, "text", None) or str(response)
        return text
    except Exception as e:
        print("gemini generate error:", e)
        return fallback_sample_response(prompt)

def fallback_sample_response(prompt: str) -> str:
    # Minimal sample that includes JSON block for dev/testing
    sample_json = {
        "stations": [
            {
                "station_id": 1,
                "safety": 8,
                "cleanliness": 7,
                "staff": 8,
                "efficiency": 7,
                "customer_experience": 7,
                "sentiment": 0.2,
                "incidents": [],
                "trend": "stable"
            }
        ],
        "regions": [],
        "company": {
            "global_sentiment": 0.1,
            "top_risks": [],
            "top_recommendations": []
        }
    }
    human = ("[ROLE_REPORT: Gas Station Manager]\nExample station report.\n\n"
             "[ROLE_REPORT: Region Manager]\nExample region report.\n\n"
             "[ROLE_REPORT: Region Director]\nExample region director report.\n\n"
             "[ROLE_REPORT: General Manager]\nExample GM report.\n\n"
             "```json\n" + json.dumps(sample_json, indent=2, ensure_ascii=False) + "\n```")
    return human

# Robust JSON extractor
def extract_json_block(text: str):
    if not text:
        return None
    # Try fenced json block first
    m = re.search(r"```json\s*(\{[\s\S]*\})\s*```", text, re.IGNORECASE)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Try any JSON that contains "stations" root
    m = re.search(r"(\{[\s\S]*\"stations\"[\s\S]*\})", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Last-curly heuristic: find the last balanced JSON object
    last_open = text.rfind("{")
    if last_open != -1:
        snippet = text[last_open:]
        depth = 0
        for i, ch in enumerate(snippet):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = snippet[:i+1]
                    try:
                        return json.loads(candidate)
                    except Exception:
                        break
    return None