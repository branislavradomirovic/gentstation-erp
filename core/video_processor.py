"""
Video Processor - Ollama Local LLM Version

Processes gas station CCTV footage using local Ollama LLM.
Samples actual video frames when OpenCV is available, and falls back to
metadata-only analysis when the runtime cannot decode video.
"""

import base64
import json
import os
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from contextlib import closing

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("gentstation.video_processor")

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cv2 = None

# Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:14b-instruct")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "bakllava").strip()
OLLAMA_LOCAL_ONLY = os.getenv("OLLAMA_LOCAL_ONLY", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FRAME_SAMPLES = int(os.getenv("VIDEO_FRAME_SAMPLES", "6"))
MAX_FRAME_DIMENSION = int(os.getenv("VIDEO_MAX_FRAME_DIMENSION", "640"))

DEFAULT_PROMPT_TEMPLATE = """
You are an expert Fuel Retail Operations Auditor analyzing gas-station CCTV.

VIDEO METADATA:
- File: {file_name}
- Size: {file_size_bytes} bytes
- Decoder: {decoder}
- FPS: {fps}
- Frames: {frame_count}
- Duration: {duration_s} seconds

SAMPLED FRAMES:
{frame_lines}

{analysis_mode}

Assess the following KPIs on a 1-10 scale, where 10 is best:
- cleanliness_score
- safety_score
- staff_score
- merchandising_score

Return ONLY valid JSON with exactly these keys:
{{
  "cleanliness_score": <int from 1-10>,
  "safety_score": <int from 1-10>,
  "staff_score": <int from 1-10>,
  "merchandising_score": <int from 1-10>,
  "hazards": ["<specific hazard 1>", "<specific hazard 2>"],
  "stock_issues": ["<empty shelf location>", "<low stock item>"],
  "customer_activity": "<low|medium|high>",
  "confidence": <float from 0.0-1.0>,
  "summary": "<2-3 sentence executive summary>"
}}

If the image evidence is weak or partially obscured, lower confidence accordingly.
"""


@dataclass
class VideoFrame:
    index: int
    timestamp_s: float
    image_b64: str


def _load_video_metadata(video_path: str) -> Dict[str, Any]:
    size_bytes = os.path.getsize(video_path)
    metadata = {
        "file_name": os.path.basename(video_path),
        "file_size_bytes": size_bytes,
        "frames": FRAME_SAMPLES,
    }

    if cv2 is None:
        metadata.update({"decoder": "unavailable"})
        return metadata

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        metadata.update({"decoder": "open_failed"})
        return metadata

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration_s = (frame_count / fps) if fps and frame_count else 0.0
    cap.release()

    metadata.update(
        {
            "decoder": "opencv",
            "fps": round(float(fps), 2) if fps else None,
            "frame_count": frame_count or None,
            "duration_s": round(duration_s, 2) if duration_s else None,
            "width": width or None,
            "height": height or None,
        }
    )
    return metadata


def _resize_frame(frame, max_dimension: int):
    if cv2 is None:
        return frame

    height, width = frame.shape[:2]
    largest_side = max(height, width)
    if largest_side <= max_dimension:
        return frame

    scale = max_dimension / float(largest_side)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)


def _encode_frame_to_base64(frame) -> str:
    if cv2 is None:
        raise RuntimeError("OpenCV is required to encode video frames.")

    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise RuntimeError("Failed to encode a sampled frame as JPEG.")
    return base64.b64encode(buffer.tobytes()).decode("utf-8")


def sample_frames(
    video_path: str, sample_count: int = FRAME_SAMPLES
) -> List[VideoFrame]:
    if cv2 is None:
        return []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frames: List[VideoFrame] = []

    try:
        if frame_count > 0:
            # Skip the first and last 5% to avoid static/transitions
            start_offset = int(frame_count * 0.05)
            end_offset = int(frame_count * 0.95)
            effective_frames = end_offset - start_offset

            indices = sorted(
                {
                    min(
                        end_offset,
                        max(
                            start_offset,
                            start_offset
                            + int(
                                round(
                                    i
                                    * (effective_frames - 1)
                                    / max(1, sample_count - 1)
                                )
                            ),
                        ),
                    )
                    for i in range(sample_count)
                }
            )
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue

                # Check for "dead" frames (too dark/empty)
                mean_brightness = np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
                if mean_brightness < 10:  # Threshold for near-black frames
                    continue

                frame = _resize_frame(frame, MAX_FRAME_DIMENSION)
                timestamp_s = (idx / fps) if fps else float(idx)
                frames.append(
                    VideoFrame(
                        index=idx,
                        timestamp_s=round(timestamp_s, 2),
                        image_b64=_encode_frame_to_base64(frame),
                    )
                )
        else:
            # Fallback for files where the frame count is not reported.
            idx = 0
            while len(frames) < sample_count:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if idx % max(1, int(round((fps or 1.0) / 2.0))) == 0:
                    frame = _resize_frame(frame, MAX_FRAME_DIMENSION)
                    timestamp_s = (idx / fps) if fps else float(idx)
                    frames.append(
                        VideoFrame(
                            index=idx,
                            timestamp_s=round(timestamp_s, 2),
                            image_b64=_encode_frame_to_base64(frame),
                        )
                    )
                idx += 1
    finally:
        cap.release()

    return frames[:sample_count]


def _build_prompt(
    metadata: Dict[str, Any], frames: List[VideoFrame], use_images: bool
) -> str:
    template = DEFAULT_PROMPT_TEMPLATE
    try:
        from core.database import get_connection

        with closing(get_connection()) as conn:
            row = conn.execute(
                "SELECT value FROM system_settings WHERE key='ai_custom_prompt'"
            ).fetchone()
            if row and row[0]:
                template = row[0]
    except Exception:
        pass

    frame_lines = (
        "\n".join(
            f"- Frame {frame.index} at {frame.timestamp_s:.2f}s" for frame in frames
        )
        or "- No extractable frames were available."
    )

    analysis_mode = (
        "These sampled frames are attached to the request."
        if use_images
        else "Frame extraction was unavailable, so you are analyzing the metadata and any available video context only."
    )

    return template.format(
        file_name=metadata.get("file_name"),
        file_size_bytes=metadata.get("file_size_bytes"),
        decoder=metadata.get("decoder"),
        fps=metadata.get("fps", "unknown"),
        frame_count=metadata.get("frame_count", "unknown"),
        duration_s=metadata.get("duration_s", "unknown"),
        frame_lines=frame_lines,
        analysis_mode=analysis_mode,
    )


def _select_model(use_images: bool) -> str:
    try:
        from core.database import get_connection

        with closing(get_connection()) as conn:
            cur = conn.cursor()

            # 1. Check if Auto-Scale is active
            cur.execute(
                "SELECT value FROM system_settings WHERE key='ai_auto_scale_active'"
            )
            row_scale = cur.fetchone()
            if row_scale and row_scale[0] == "1":
                cur.execute(
                    "SELECT value FROM system_settings WHERE key='ai_auto_scale_down_model'"
                )
                row_failover = cur.fetchone()
                if row_failover and row_failover[0]:
                    return row_failover[0]

            # 2. Check for standard overrides
            if use_images:
                cur.execute(
                    "SELECT value FROM system_settings WHERE key='ollama_vision_model_override'"
                )
                row = cur.fetchone()
                if row and row[0]:
                    return row[0]
                if OLLAMA_VISION_MODEL:
                    return OLLAMA_VISION_MODEL

            cur.execute(
                "SELECT value FROM system_settings WHERE key='ollama_model_override'"
            )
            row = cur.fetchone()
            if row and row[0]:
                return row[0]
    except Exception as e:
        logger.debug("Could not fetch model override from DB: %s", e)

    return OLLAMA_MODEL


def _candidate_base_urls():
    seen = set()

    def add(url: str):
        url = (url or "").rstrip("/")
        if url and url not in seen:
            seen.add(url)
            candidates.append(url)

    candidates: List[str] = []
    add(OLLAMA_BASE_URL)

    # Always include local loopback variants for local development.
    if "localhost" in OLLAMA_BASE_URL:
        add(OLLAMA_BASE_URL.replace("localhost", "127.0.0.1"))
    if "127.0.0.1" in OLLAMA_BASE_URL:
        add(OLLAMA_BASE_URL.replace("127.0.0.1", "localhost"))
    if "host.docker.internal" in OLLAMA_BASE_URL:
        add(OLLAMA_BASE_URL.replace("host.docker.internal", "localhost"))
        add(OLLAMA_BASE_URL.replace("host.docker.internal", "127.0.0.1"))

    add("http://localhost:11434")
    add("http://127.0.0.1:11434")

    # Optional Docker-specific fallback, disabled by default for local-first development.
    if not OLLAMA_LOCAL_ONLY:
        if "localhost" in OLLAMA_BASE_URL:
            add(OLLAMA_BASE_URL.replace("localhost", "host.docker.internal"))
        if "127.0.0.1" in OLLAMA_BASE_URL:
            add(OLLAMA_BASE_URL.replace("127.0.0.1", "host.docker.internal"))
        add("http://host.docker.internal:11434")
    return candidates


def call_ollama(
    prompt: str, model: str, images: Optional[List[str]] = None, is_json: bool = True
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "temperature": 0.2,
    }
    if is_json:
        payload["format"] = "json"

    if images:
        payload["images"] = images

    logger.info("Calling Ollama model '%s' at %s...", model, OLLAMA_BASE_URL)
    for base_url in _candidate_base_urls():
        try:
            response = requests.post(
                f"{base_url}/api/generate",
                json=payload,
                timeout=300,
            )

            if response.status_code != 200:
                raise RuntimeError(
                    f"Ollama API error {response.status_code}: {response.text}"
                )

            response_data = response.json()
            return (response_data.get("response") or "").strip()
        except Exception as e:
            last_error = e
            logger.debug("Ollama request failed for %s: %s", base_url, e)

    raise RuntimeError(
        f"Cannot connect to Ollama server at {OLLAMA_BASE_URL}. "
        f"Tried: {', '.join(_candidate_base_urls())}. "
        f"Last error: {last_error}. "
        "For local development, ensure Ollama is running: `ollama serve`."
    )


def _parse_result(response_text: str) -> Dict[str, Any]:
    if response_text.startswith("```"):
        response_text = response_text.split("```", 2)[1]
        if response_text.startswith("json"):
            response_text = response_text[4:]
        response_text = response_text.strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        import re

        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            raise RuntimeError(
                f"Failed to parse Ollama response as JSON: {response_text[:500]}"
            )
        result = json.loads(json_match.group())

    required_fields = [
        "cleanliness_score",
        "safety_score",
        "staff_score",
        "merchandising_score",
        "hazards",
        "stock_issues",
        "customer_activity",
        "confidence",
        "summary",
    ]
    for field in required_fields:
        if field not in result:
            raise ValueError(f"Missing required field in response: {field}")

    for score_field in [
        "cleanliness_score",
        "safety_score",
        "staff_score",
        "merchandising_score",
    ]:
        score = result[score_field]
        if not isinstance(score, (int, float)) or not (1 <= score <= 10):
            result[score_field] = max(1, min(10, int(score)))

    if not isinstance(result["confidence"], (int, float)):
        result["confidence"] = 0.5
    else:
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))

    return result


def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("hazards", "stock_issues"):
        value = result.get(key, [])
        if isinstance(value, str):
            result[key] = [value]
        elif not isinstance(value, list):
            result[key] = []
    result["summary"] = str(result.get("summary", "")).strip() or "No summary provided."
    return result


def parse_station_video(video_path: str) -> dict:
    """
    Analyze a gas-station CCTV video and return structured KPI JSON.

    Uses sampled frames if OpenCV is available and the configured Ollama model
    supports images. If frame decoding is unavailable, falls back to metadata-
    only analysis so the pipeline still produces output.
    """

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    logger.debug("Processing video: %s", video_path)
    metadata = _load_video_metadata(video_path)

    vision_ready = cv2 is not None and bool(OLLAMA_VISION_MODEL)
    frames: List[VideoFrame] = []
    if vision_ready:
        frames = sample_frames(video_path, FRAME_SAMPLES)
    elif cv2 is None:
        logger.debug("OpenCV is not installed; using metadata-only analysis.")
    elif not OLLAMA_VISION_MODEL:
        logger.debug(
            "OLLAMA_VISION_MODEL is not configured; using metadata-only analysis."
        )

    use_images = bool(frames) and vision_ready
    model = _select_model(
        use_images
    )  # Still use internal selector for production logic

    logger.debug(
        "Using model: %s (%s)",
        model,
        "frames attached" if use_images else "metadata fallback",
    )

    prompt = _build_prompt(metadata, frames, use_images)

    try:
        image_payload = [frame.image_b64 for frame in frames] if use_images else None
        response_text = call_ollama(prompt, model, image_payload)
        result = _normalize_result(_parse_result(response_text))
        result["_model_used"] = model
        logger.debug(
            "Analysis complete: C=%s S=%s St=%s M=%s",
            result["cleanliness_score"],
            result["safety_score"],
            result["staff_score"],
            result["merchandising_score"],
        )
        return result

    except requests.exceptions.ConnectionError:
        error_msg = (
            f"Cannot connect to Ollama server at {OLLAMA_BASE_URL}. "
            f"Make sure Ollama is running: 'ollama serve'"
        )
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    except requests.exceptions.Timeout:
        error_msg = "Ollama request timed out. The video may be too large or the model may be slow."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    except Exception as e:
        # If we tried a vision model first and it failed, fall back to text-only.
        if use_images:
            try:
                fallback_prompt = _build_prompt(metadata, [], False)
                response_text = call_ollama(fallback_prompt, OLLAMA_MODEL, None)
                result = _normalize_result(_parse_result(response_text))
                result["_model_used"] = OLLAMA_MODEL
                result["summary"] = (
                    f"{result['summary']} (Vision fallback was unavailable; result used metadata-only analysis.)"
                )
                return result
            except Exception:
                pass

        error_msg = f"Ollama analysis failed: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


def test_ollama_connection(on_retry=None) -> bool:
    """Test if Ollama server is running and responding."""
    max_retries = 5
    retry_delay = 3

    for attempt in range(max_retries):
        try:
            connected = False
            last_err = "No responding URLs"
            for base_url in _candidate_base_urls():
                try:
                    response = requests.get(f"{base_url}/api/tags", timeout=2)
                    if response.status_code == 200:
                        connected = True
                        break
                except Exception as e:
                    last_err = str(e)

            if connected:
                return True

            raise RuntimeError(f"Connection refused. {last_err}")

        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(
                    "Ollama connection attempt %d failed: %s. Retrying in %ds...",
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
                    "Ollama connection failed after %d attempts: %s", max_retries, e
                )
                return False
