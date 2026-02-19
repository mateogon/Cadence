import json
import os
from pathlib import Path

SETTINGS_PATH = Path("cadence_settings.json")

DEFAULTS = {
    "CADENCE_EXTRACT_WORKERS": "4",
    "CADENCE_SYNTH_WORKERS": "1",
    "CADENCE_TTS_MAX_CHARS": "800",
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
}


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
