import math
import os

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import re
from pathlib import Path

import numpy as np

from core.tts_backend import SynthesisResult, TTSBackend

DEFAULT_MODEL = "hexgrad/Kokoro-82M"
SAMPLE_RATE = 24000
SPEECH_BLOCK_CHARS = 450
_SENTENCE_END = re.compile(r"""[.!?…]+["'”’)\]}»]*(?=\s|$)""")
_ABBREVIATION_END = re.compile(r"\b(?:Mr|Mrs|Dr|St|e\.g|i\.e)\.$", re.IGNORECASE)

# Kokoro-82M's voice catalog; listing voices must not load the optional model.
VOICES = (
    "af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica", "af_kore",
    "af_nicole", "af_nova", "af_river", "af_sarah", "af_sky",
    "am_adam", "am_echo", "am_eric", "am_fenrir", "am_liam", "am_michael",
    "am_onyx", "am_puck", "am_santa",
    "bf_alice", "bf_emma", "bf_isabella", "bf_lily",
    "bm_daniel", "bm_fable", "bm_george", "bm_lewis",
    "ef_dora", "em_alex", "em_santa", "ff_siwis",
    "hf_alpha", "hf_beta", "hm_omega", "hm_psi", "if_sara", "im_nicola",
    "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo",
    "pf_dora", "pm_alex", "pm_santa",
    "zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi",
    "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang",
)


def _language_prefixes(lang):
    tag = (lang or "").strip().lower().replace("_", "-")
    if tag in {"", "na"}:
        return "abefhijpz"
    if tag == "en-gb" or tag.startswith("en-gb-"):
        return "b"
    if tag == "en-us" or tag.startswith("en-us-"):
        return "a"
    return {
        "en": "ab", "es": "e", "fr": "f", "hi": "h", "it": "i",
        "ja": "j", "pt": "p", "zh": "z",
    }.get(tag.split("-")[0], "")


def resolve_device(device="auto"):
    if device not in {"auto", "cpu", "cuda", "mps"}:
        raise ValueError("CADENCE_KOKORO_DEVICE must be auto, cpu, cuda or mps.")
    # Torch reads this at import time, before the model can reach an MPS operator.
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import torch

    available = {"cpu": True, "cuda": torch.cuda.is_available(),
                 "mps": torch.backends.mps.is_available()}
    if device == "auto":
        return next(name for name in ("cuda", "mps", "cpu") if available[name])
    if not available[device]:
        print(f"Kokoro: {device} is unavailable; using cpu.")
        return "cpu"
    return device


def _spoken_text(text):
    return bool(re.search(r"[^\W_]", text, re.UNICODE))


def _sentences(paragraph):
    start = 0
    for ending in _SENTENCE_END.finditer(paragraph):
        if _ABBREVIATION_END.search(paragraph, 0, ending.start() + 1):
            continue
        yield paragraph[start:ending.end()].strip()
        start = ending.end()
    tail = paragraph[start:].strip()
    if tail:
        yield tail


def speech_blocks(text):
    """Pack whole sentences; an oversize sentence belongs to Kokoro's own splitter."""
    blocks = []
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())
        if not _spoken_text(paragraph):
            continue
        current = ""
        for sentence in _sentences(paragraph):
            if current and len(current) + 1 + len(sentence) > SPEECH_BLOCK_CHARS:
                blocks.append(current)
                current = ""
            current = f"{current} {sentence}" if current else sentence
        if current:
            blocks.append(current)
    return "\n".join(blocks)


def _token_times(token, duration, previous_end):
    try:
        start, end = float(token.start_ts), float(token.end_ts)
    except (TypeError, ValueError, AttributeError):
        return None
    if (not math.isfinite(start) or not math.isfinite(end)
            or start < previous_end or end <= start or end > duration + 1 / SAMPLE_RATE):
        return None
    return start, end


def _word_timestamps(tokens, duration, offset):
    words = []
    previous_end = 0.0
    for token in tokens or ():
        word = token.text.strip()
        if not _spoken_text(word):
            continue
        times = _token_times(token, duration, previous_end)
        if times is None:
            return None
        start, end = times
        words.append({"word": word, "start": start + offset, "end": end + offset})
        previous_end = end
    return words or None


def _synthesis_speed():
    try:
        speed = float(os.getenv("CADENCE_TTS_SPEED", "1.05"))
    except ValueError as exc:
        raise ValueError("CADENCE_TTS_SPEED must be a number between 0.7 and 2.0.") from exc
    if not math.isfinite(speed) or not 0.7 <= speed <= 2.0:
        raise ValueError("CADENCE_TTS_SPEED must be a number between 0.7 and 2.0.")
    return speed


def _audio_array(audio):
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    if audio is None:
        raise ValueError("Kokoro returned missing audio.")
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim != 1 or not audio.size or not np.isfinite(audio).all():
        raise ValueError("Kokoro returned empty, non-finite or non-mono audio.")
    return np.clip(audio, -1, 1)


class KokoroBackend(TTSBackend):
    def __init__(self, model=DEFAULT_MODEL, device=None):
        self.model = model or DEFAULT_MODEL
        self.device = device if device is not None else os.getenv("CADENCE_KOKORO_DEVICE", "auto")
        if self.device not in {"auto", "cpu", "cuda", "mps"}:
            raise ValueError("CADENCE_KOKORO_DEVICE must be auto, cpu, cuda or mps.")
        self.tts = None
        self._pipelines = {}

    def ensure_model(self):
        if self.tts is None:
            try:
                device = resolve_device(self.device)
                from kokoro import KModel
            except ImportError as exc:
                raise RuntimeError("Kokoro is unavailable. Install it with: uv sync --extra kokoro") from exc
            self.tts = KModel(repo_id=self.model).to(device).eval()
        return self.tts

    def list_voices(self, lang=None):
        prefixes = _language_prefixes(lang)
        return [voice for voice in VOICES if voice[0] in prefixes]

    def default_voice(self, lang=None):
        voices = self.list_voices(lang)
        if not voices:
            raise ValueError(f"Kokoro does not support language {lang!r}.")
        return {"a": "af_heart", "b": "bf_emma"}.get(voices[0][0], voices[0])

    def _pipeline(self, lang_code):
        model = self.ensure_model()
        if lang_code not in self._pipelines:
            from kokoro import KPipeline

            try:
                self._pipelines[lang_code] = KPipeline(
                    lang_code=lang_code, repo_id=self.model, model=model,
                )
            except ImportError as exc:
                tokenizer = {"j": ("Japanese", "ja"), "z": ("Chinese", "zh")}.get(lang_code)
                if tokenizer is None:
                    raise
                label, extra = tokenizer
                raise RuntimeError(
                    f"Kokoro's {label} tokenizer dependencies are unavailable. Start Cadence with: "
                    f"uv run --extra kokoro --with 'misaki[{extra}]' main.py"
                ) from exc
        return self._pipelines[lang_code]

    def synthesize(self, text, voice, max_chars=1600, lang="na"):
        text = speech_blocks(text)
        if not text:
            return SynthesisResult(audio=None)
        if voice not in self.list_voices(lang):
            raise ValueError(f"Kokoro voice {voice!r} is unavailable for language {lang!r}.")
        speed = _synthesis_speed()
        audio_parts, words = [], []
        frames = 0
        for result in self._pipeline(voice[0])(text, voice=voice, speed=speed, split_pattern=r"\n+"):
            audio = _audio_array(result.audio)
            audio_parts.append(audio)
            # The package can split one input block into several yielded audio pieces.
            piece_words = _word_timestamps(
                getattr(result, "tokens", None), len(audio) / SAMPLE_RATE, frames / SAMPLE_RATE,
            )
            if piece_words is None:
                words = None
            if words is not None:
                words.extend(piece_words)
            frames += len(audio)
        if not audio_parts:
            raise ValueError("Kokoro produced no audio.")
        return SynthesisResult(audio=np.concatenate(audio_parts), word_timestamps=words)

    def save_audio(self, wav, output_path):
        import soundfile

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_name(f"{out_path.stem}.part{out_path.suffix}")
        try:
            soundfile.write(tmp_path, wav, SAMPLE_RATE)
            if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
                raise RuntimeError(f"Temporary audio write failed: {tmp_path}")
            os.replace(tmp_path, out_path)
        finally:
            tmp_path.unlink(missing_ok=True)
