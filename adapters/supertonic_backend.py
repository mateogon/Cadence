import os
from pathlib import Path

from core.tts_backend import TTSBackend
from adapters.generate_audiobook_supertonic import (
    init_tts_engine,
    synthesize_text,
)

from system.runtime_settings import resolve_tts_settings


class SupertonicBackend(TTSBackend):
    def __init__(self, model=None):
        self.model = resolve_tts_settings(model=model)["model"]
        self.tts = None

    def ensure_model(self):
        if self.tts is None:
            self.tts = init_tts_engine(model=self.model)
        return self.tts

    def list_voices(self):
        tts = self.ensure_model()
        return list(tts.voice_style_names)

    def synthesize(self, text, voice, max_chars=1600, lang="na"):
        tts = self.ensure_model()
        try:
            voice_style = tts.get_voice_style(voice)
        except Exception:
            voices = self.list_voices()
            if not voices:
                raise RuntimeError("No voices available from Supertonic backend.")
            voice_style = tts.get_voice_style(voices[0])
        return synthesize_text(tts, text, voice_style, max_chars=max_chars, lang=lang, model=self.model)

    def save_audio(self, wav, output_path):
        tts = self.ensure_model()
        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Keep .wav extension so soundfile can infer output format.
        tmp_path = out_path.with_name(f"{out_path.stem}.part{out_path.suffix}")
        try:
            tts.save_audio(wav, str(tmp_path))
            if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
                raise RuntimeError(f"Temporary audio write failed: {tmp_path}")
            os.replace(str(tmp_path), str(out_path))
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass
