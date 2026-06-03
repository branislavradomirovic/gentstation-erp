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
from typing import Any, Dict, List, Optional
import numpy as np

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
_single_model_env = (
    os.getenv("OLLAMA_VISION_MODEL")
    or os.getenv("OLLAMA_MODEL")
    or "bakllava:latest"
).strip()
OLLAMA_MODEL = _single_model_env or "bakllava:latest"
OLLAMA_VISION_MODEL = OLLAMA_MODEL
OLLAMA_LOCAL_ONLY = os.getenv("OLLAMA_LOCAL_ONLY", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
FRAME_SAMPLES = int(os.getenv("VIDEO_FRAME_SAMPLES", "6"))
MAX_FRAME_DIMENSION = int(os.getenv("VIDEO_MAX_FRAME_DIMENSION", "640"))

DEFAULT_PROMPT_TEMPLATE = """
Ti si ekspert za operativnu reviziju fuel retail objekata i analiziraš video snimak benzinske stanice.

METAPODACI O VIDEU:
- Fajl: {file_name}
- Veličina: {file_size_bytes} bajtova
- Dekoder: {decoder}
- FPS: {fps}
- Broj frejmova: {frame_count}
- Trajanje: {duration_s} sekundi

UZORKOVANI FREJMOVI:
{frame_lines}

{analysis_mode}

Proceni i bezbednost i komercijalnu izvedbu isključivo na osnovu vidljivih dokaza.

BEZBEDNOSNA KONTROLNA LISTA (prioritet imaju visoki rizici):
- Opasnosti od klizanja i spoticanja (prosipanja, nered, blokirani prolazi, kablovi, mokar pod)
- Požarni i gorivni rizici (pušenje, otvoren plamen, nebezbedno rukovanje gorivom)
- PPE i usklađenost sa pravilima (uniforma/PPE, disciplina u zabranjenim zonama)
- Spremnost za vanredne situacije (vidljivi aparati, čisti izlazi, slobodan pristup)
- Bezbednost platoa i saobraćaja (sukob vozila i pešaka, nebezbedno parkiranje)

KOMERCIJALNA KONTROLNA LISTA:
- Dostupnost robe i urednost rafova u ključnim kategorijama
- Vidljivi out-of-stock i low-stock problemi
- Izvedba promocija (pozicija signalizacije, vidljivost kampanje)
- Protok na kasi / u redu i spremnost usluge
- Opšti utisak prodajnog prostora koji utiče na konverziju

Oceni sledeće KPI-jeve na skali 1-10 (10 je najbolje):
- cleanliness_score: čistoća i vizuelni red
- safety_score: kontrola rizika i usklađenost
- staff_score: profesionalnost, spremnost i disciplina zaposlenih
- merchandising_score: dostupnost robe, urednost i promo izvedba

Vrati ISKLJUČIVO validan JSON sa tačno ovim ključevima.
Sva tekstualna polja moraju biti na srpskom jeziku, latinica, kratko i operativno.

Vrati samo ovaj JSON:
{{
  "cleanliness_score": <int from 1-10>,
  "safety_score": <int from 1-10>,
  "staff_score": <int from 1-10>,
  "merchandising_score": <int from 1-10>,
  "overall_risk_score": <float from 0-100 where higher is worse>,
  "hazards": ["<konkretna opasnost 1>", "<konkretna opasnost 2>"],
  "stock_issues": ["<prazna pozicija>", "<artikl sa niskim stanjem>"],
  "improvement_actions": ["<kratka akcija 1>", "<kratka akcija 2>", "<kratka akcija 3>"],
  "customer_activity": "<low|medium|high>",
  "confidence": <float from 0.0-1.0>,
  "summary": "<izvršni sažetak od 2-3 kratke rečenice>"
}}

Pravila ocenjivanja:
- Snažno obori safety_score kada su vidljivi kritični bezbednosni rizici.
- Obori merchandising_score kada su stanje robe ili promo izvedba slabi.
- Hazards i stock_issues moraju biti konkretni i operativni, bez generičkih formulacija.
- Ako su dokazi slabi ili kadar nije jasan, smanji confidence i to naglasi u sažetku.
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

        with get_connection() as conn:
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
        "Uz zahtev su priloženi uzorkovani frejmovi."
        if use_images
        else "Izdvajanje frejmova nije bilo dostupno, zato analizu radiš samo na osnovu metapodataka i eventualnog dostupnog konteksta."
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

    defaults = {
        "cleanliness_score": 5,
        "safety_score": 5,
        "staff_score": 5,
        "merchandising_score": 5,
        "overall_risk_score": None,
        "hazards": [],
        "stock_issues": [],
        "improvement_actions": [],
        "customer_activity": "low",
        "confidence": 0.5,
        "summary": "Sažetak nije dostupan.",
    }
    for field, default_value in defaults.items():
        if field not in result:
            result[field] = default_value

    for score_field in [
        "cleanliness_score",
        "safety_score",
        "staff_score",
        "merchandising_score",
    ]:
        score = result[score_field]
        try:
            result[score_field] = max(1, min(10, int(float(score))))
        except Exception:
            result[score_field] = 5

    if isinstance(result["confidence"], list):
        numeric_values = [float(v) for v in result["confidence"] if isinstance(v, (int, float))]
        result["confidence"] = (
            sum(numeric_values) / len(numeric_values) if numeric_values else 0.5
        )
    elif not isinstance(result["confidence"], (int, float)):
        result["confidence"] = 0.5
    else:
        result["confidence"] = max(0.0, min(1.0, float(result["confidence"])))

    try:
        if result.get("overall_risk_score") is not None:
            result["overall_risk_score"] = max(
                0.0, min(100.0, float(result["overall_risk_score"]))
            )
    except Exception:
        result["overall_risk_score"] = None

    return result


def _derived_risk_score(result: Dict[str, Any]) -> float:
    safety = float(result.get("safety_score", 5) or 5)
    cleanliness = float(result.get("cleanliness_score", 5) or 5)
    staff = float(result.get("staff_score", 5) or 5)
    merchandising = float(result.get("merchandising_score", 5) or 5)
    hazards = result.get("hazards") or []
    stock_issues = result.get("stock_issues") or []
    hazard_penalty = min(25.0, len(hazards) * 9.0)
    stock_penalty = min(12.0, len(stock_issues) * 4.0)
    base = (
        ((10.0 - safety) / 10.0) * 42.0
        + ((10.0 - cleanliness) / 10.0) * 18.0
        + ((10.0 - staff) / 10.0) * 18.0
        + ((10.0 - merchandising) / 10.0) * 22.0
    )
    return round(min(100.0, max(0.0, base + hazard_penalty + stock_penalty)), 2)


def _synthesized_summary(result: Dict[str, Any]) -> str:
    safety = int(result.get("safety_score", 5) or 5)
    cleanliness = int(result.get("cleanliness_score", 5) or 5)
    staff = int(result.get("staff_score", 5) or 5)
    merchandising = int(result.get("merchandising_score", 5) or 5)
    risk = float(result.get("overall_risk_score") or _derived_risk_score(result))
    hazards = result.get("hazards") or []
    stock_issues = result.get("stock_issues") or []

    biggest_gap = min(
        [
            ("bezbednosna disciplina", safety),
            ("standardi čistoće", cleanliness),
            ("spremnost zaposlenih", staff),
            ("merchandising izvedba", merchandising),
        ],
        key=lambda item: item[1],
    )[0]

    first_sentence = (
        f"Ukupan operativni rizik iznosi {risk:.1f}/100, a najviše ga podiže {biggest_gap}."
    )
    if hazards:
        second_sentence = f"Najvažniji uočeni rizik: {str(hazards[0]).strip()}."
    elif stock_issues:
        second_sentence = f"Ključni komercijalni problem: {str(stock_issues[0]).strip()}."
    else:
        second_sentence = (
            "Nije izdvojen jedan dominantan rizik, ali snimak i dalje zahteva menadžersku proveru."
        )
    return f"{first_sentence} {second_sentence}"


def _derived_improvement_actions(result: Dict[str, Any]) -> List[str]:
    actions: List[str] = []
    safety = int(result.get("safety_score", 5) or 5)
    cleanliness = int(result.get("cleanliness_score", 5) or 5)
    staff = int(result.get("staff_score", 5) or 5)
    merchandising = int(result.get("merchandising_score", 5) or 5)
    hazards = result.get("hazards") or []
    stock_issues = result.get("stock_issues") or []

    if safety <= 7:
        actions.append("Pregledaj plato i ukloni sve neposredne bezbednosne rizike pre naredne smene.")
    if cleanliness <= 7:
        actions.append("Sprovedi ciljano čišćenje kritičnih tačaka, prosipanja i površina vidljivih kupcima.")
    if staff <= 7:
        actions.append("Usmeri zaposlene u smeni na disciplinu rada, PPE i očekivani nivo usluge.")
    if merchandising <= 7:
        actions.append("Doteraj rafove i ispravi low-stock ili promašaje u promo izvedbi na prioritetnim pozicijama.")
    if hazards:
        actions.append(f"Prvo otkloni prijavljeni rizik: {str(hazards[0]).strip()}.")
    if stock_issues:
        actions.append(f"Dopuni robu ili ispravi najuočljiviji problem: {str(stock_issues[0]).strip()}.")

    if not actions:
        actions.append("Zadrži postojeći standard i nastavi sa rutinskim operativnim proverama.")
    while len(actions) < 3:
        actions.append("Obavi menadžerski obilazak i potvrdi korekciju na sledećem snimku.")
    return actions[:3]


def _is_low_information_result(result: Dict[str, Any], response_text: str) -> bool:
    response_trimmed = (response_text or "").strip()
    scores = [
        int(result.get("cleanliness_score", 5) or 5),
        int(result.get("safety_score", 5) or 5),
        int(result.get("staff_score", 5) or 5),
        int(result.get("merchandising_score", 5) or 5),
    ]
    hazards = result.get("hazards") or []
    stock_issues = result.get("stock_issues") or []
    summary = str(result.get("summary", "") or "").strip()
    return (
        response_trimmed in {"", "{}", "null"}
        or (
            summary in {"", "No summary provided.", "Sažetak nije dostupan."}
            and all(score == 5 for score in scores)
            and not hazards
            and not stock_issues
        )
    )


def _build_retry_prompt(
    metadata: Dict[str, Any], frames: List[VideoFrame], use_images: bool, previous_response: str
) -> str:
    frame_lines = (
        "\n".join(
            f"- Frame {frame.index} at {frame.timestamp_s:.2f}s" for frame in frames
        )
        or "- No extractable frames were available."
    )
    analysis_mode = (
        "Koristi priložene slike kao primarni dokaz."
        if use_images
        else "Slike frejmova nisu dostupne, zato odgovor zasnivaj samo na metapodacima i delimično dostupnim dokazima."
    )
    return f"""
U prethodnom pokušaju vratio si nepotpun odgovor:
{previous_response[:400] or "<empty response>"}

Ponovo analiziraj ovaj snimak benzinske stanice i vrati ISKLJUČIVO JSON.

VIDEO:
- Fajl: {metadata.get('file_name')}
- Veličina: {metadata.get('file_size_bytes')} bajtova
- Dekoder: {metadata.get('decoder')}
- FPS: {metadata.get('fps', 'unknown')}
- Broj frejmova: {metadata.get('frame_count', 'unknown')}
- Trajanje: {metadata.get('duration_s', 'unknown')} sekundi

UZORKOVANI FREJMOVI:
{frame_lines}

{analysis_mode}

Zahtevi:
- Ne vraćaj prazan objekat.
- Ne izmišljaj sigurnost. Ako nisi siguran, smanji confidence, ali ipak daj najbolju procenu.
- summary mora imati 2 kratke rečenice na srpskom.
- improvement_actions mora sadržati tačno 3 kratke akcije na srpskom.

Vrati tačno ovu JSON šemu:
{{
  "cleanliness_score": 1-10,
  "safety_score": 1-10,
  "staff_score": 1-10,
  "merchandising_score": 1-10,
  "overall_risk_score": 0-100,
  "hazards": ["item 1", "item 2"],
  "stock_issues": ["item 1", "item 2"],
  "improvement_actions": ["action 1", "action 2", "action 3"],
  "customer_activity": "low|medium|high",
  "confidence": 0.0-1.0,
  "summary": "rečenica jedan. rečenica dva."
}}
"""


def _normalize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    for key in ("hazards", "stock_issues", "improvement_actions"):
        value = result.get(key, [])
        if isinstance(value, str):
            result[key] = [value]
        elif not isinstance(value, list):
            result[key] = []
    result["customer_activity"] = str(
        result.get("customer_activity", "low") or "low"
    ).strip().lower()
    if result["customer_activity"] not in {"low", "medium", "high"}:
        result["customer_activity"] = "low"
    if result.get("overall_risk_score") in (None, ""):
        result["overall_risk_score"] = _derived_risk_score(result)
    result["summary"] = str(result.get("summary", "")).strip() or _synthesized_summary(
        result
    )
    if result["summary"] in {"No summary provided.", "Sažetak nije dostupan."}:
        result["summary"] = _synthesized_summary(result)
    if not result.get("improvement_actions"):
        result["improvement_actions"] = _derived_improvement_actions(result)
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

    model = _select_model(True)
    vision_ready = cv2 is not None and bool(model)
    frames: List[VideoFrame] = []
    if vision_ready:
        frames = sample_frames(video_path, FRAME_SAMPLES)
    elif cv2 is None:
        logger.debug("OpenCV is not installed; using metadata-only analysis.")
    elif not model:
        logger.debug(
            "No Ollama model is configured; using metadata-only analysis."
        )

    use_images = bool(frames) and vision_ready
    prompt = _build_prompt(metadata, frames if use_images else [], use_images)
    images = [f.image_b64 for f in frames] if use_images else None

    try:
        response_text = call_ollama(prompt, model, images)
        model_output = _normalize_result(_parse_result(response_text))
        if _is_low_information_result(model_output, response_text):
            retry_prompt = _build_retry_prompt(
                metadata, frames if use_images else [], use_images, response_text
            )
            retry_response = call_ollama(retry_prompt, model, images)
            retry_output = _normalize_result(_parse_result(retry_response))
            if not _is_low_information_result(retry_output, retry_response):
                response_text = retry_response
                model_output = retry_output
        model_output["_model_used"] = model
        model_output["_raw_response"] = response_text
    except Exception as e:
        raise RuntimeError(f"Ollama analysis failed for model '{model}': {e}") from e

    result = dict(model_output)
    result["_model_used"] = model
    result["_vision_model"] = model
    result["_vision_output"] = model_output if use_images else None
    result["_vision_error"] = None
    result["_llm_model"] = model
    result["_llm_output"] = None if use_images else model_output
    result["_llm_error"] = None
    result["_analysis_metadata"] = {
        "vision_used": bool(use_images),
        "frames_sampled": len(frames),
        "decoder": metadata.get("decoder"),
    }
    return result


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
