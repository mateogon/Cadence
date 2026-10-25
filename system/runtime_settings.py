import json
import math
import os
from pathlib import Path

SETTINGS_PATH = Path("cadence_settings.json")

DEFAULTS = {
    "CADENCE_STYLE_PROFILE": "cadence",
    "CADENCE_EXTRACT_WORKERS": "4",
    "CADENCE_SYNTH_WORKERS": "1",
    "CADENCE_TTS_MAX_CHARS": "800",
    "CADENCE_TTS_MODEL": "supertonic-3",
    "CADENCE_TTS_SPEED": "1.05",
    "CADENCE_TTS_STEPS": "8",
    "CADENCE_FORCE_CPU": "0",
    "CADENCE_USE_TENSORRT": "0",
    "CADENCE_CUDA_ONLY": "1",
    "CADENCE_SUPPRESS_ORT_WARNINGS": "1",
    "CADENCE_ADD_SYSTEM_CUDA_DLL_PATH": "0",
    "CADENCE_ORT_LOG_LEVEL": "3",
    "CADENCE_WHISPERX_MODEL": "small",
    "CADENCE_WHISPERX_BATCH_SIZE": "16",
    "CADENCE_WHISPERX_COMPUTE_TYPE": "float16",
    "CADENCE_WHISPERX_DEVICE": "auto",
    "CADENCE_WHISPERX_PYTHON": "",
    "CADENCE_CALIBRE_PATH": "",
}


def resolve_tts_settings(model=None, speed=None, steps=None):
    """Validate the synthesis settings before loading a model or writing audio."""
    model = str(model if model is not None else os.getenv(
        "CADENCE_TTS_MODEL", DEFAULTS["CADENCE_TTS_MODEL"])).strip()
    if model not in ("supertonic", "supertonic-2", "supertonic-3"):
        raise ValueError("CADENCE_TTS_MODEL must be supertonic, supertonic-2 or supertonic-3.")
    try:
        speed = float(speed if speed is not None else os.getenv(
            "CADENCE_TTS_SPEED", DEFAULTS["CADENCE_TTS_SPEED"]))
    except (ValueError, TypeError) as exc:
        raise ValueError("CADENCE_TTS_SPEED must be a number between 0.7 and 2.0.") from exc
    if not math.isfinite(speed) or not 0.7 <= speed <= 2.0:
        raise ValueError("CADENCE_TTS_SPEED must be a number between 0.7 and 2.0.")
    raw_steps = str(steps if steps is not None else os.getenv(
        "CADENCE_TTS_STEPS", DEFAULTS["CADENCE_TTS_STEPS"])).strip()
    try:
        steps = int(raw_steps)
    except (ValueError, TypeError) as exc:
        raise ValueError("CADENCE_TTS_STEPS must be an integer between 1 and 100.") from exc
    if not 1 <= steps <= 100:
        raise ValueError("CADENCE_TTS_STEPS must be an integer between 1 and 100.")
    return {"model": model, "speed": speed, "steps": steps}


def load_settings(path=SETTINGS_PATH):
    settings = dict(DEFAULTS)
    if not path.exists():
        return settings

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return settings

    if not isinstance(raw, dict):
        return settings

    for key in DEFAULTS:
        if key in raw and raw[key] is not None:
            settings[key] = str(raw[key]).strip()
    return settings


def save_settings(settings, path=SETTINGS_PATH):
    payload = {}
    for key, default in DEFAULTS.items():
        payload[key] = str(settings.get(key, default)).strip()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def apply_settings_to_environ(settings, override=True):
    for key, value in settings.items():
        if override or key not in os.environ:
            os.environ[key] = str(value)
