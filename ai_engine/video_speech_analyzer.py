# gentstation_opus/ai_engine/video_speech_analyzer.py
import os, json, subprocess
from typing import Dict, Any

def transcribe_audio(audio_path: str) -> Dict[str, Any]:
    """
    Placeholder transcriber. Replace with real ASR.
    Returns {'transcript': str, 'segments':[{'start':0.0,'end':1.2,'text':'...'}]}
    """
    if not audio_path or not os.path.exists(audio_path):
        return {"transcript":"", "segments": []}
    # Simple placeholder: read file size as fake content
    size = os.path.getsize(audio_path)
    transcript = f"[ASR placeholder] audio file size: {size} bytes"
    return {"transcript": transcript, "segments": []}

def analyze_speech_sentiment(transcript: str) -> float:
    """
    Very simple sentiment estimator: returns -1..1 based on naive heuristics.
    Replace with proper sentiment model in production.
    """
    if not transcript:
        return 0.0
    lower = transcript.lower()
    neg = ["bad", "problem", "bad", "fault", "angry", "hate", "spoil", "spill"]
    pos = ["good", "ok", "great", "fine", "thanks", "thank"]
    score = 0
    for w in neg:
        if w in lower:
            score -= 0.4
    for w in pos:
        if w in lower:
            score += 0.3
    if score > 1: score = 1.0
    if score < -1: score = -1.0
    return round(score, 2)