import os
import numpy as np
import re
from pathlib import Path

from core.tts_backend import TTSBackend
from generate_audiobook_supertonic import (
    get_smart_chunks,
    init_tts_engine,
    sanitize_text,
)


class SupertonicBackend(TTSBackend):
    def __init__(self):
        self.tts = None

    def ensure_model(self):
        if self.tts is None:
            self.tts = init_tts_engine()
        return self.tts

    def list_voices(self):
        tts = self.ensure_model()
        return list(tts.voices.keys())

    @staticmethod
    def _is_retryable_onnx_error(exc):
        msg = str(exc).lower()
        return (
            "onnxruntimeerror" in msg
            or "runtime_exception" in msg
            or "broadcastiterator::append" in msg
            or "attempting to broadcast an axis" in msg
        )

    @staticmethod
    def _split_chunk_balanced(text):
        for pattern in (r"(?<=[.!?])\s+", r"(?<=[,;:])\s+", r"\s+"):
            parts = [p.strip() for p in re.split(pattern, text) if p.strip()]
            if len(parts) > 1:
                break
        else:
            parts = [text]

        if len(parts) <= 1:
            mid = max(1, len(text) // 2)
            return [text[:mid].strip(), text[mid:].strip()]

        total = sum(len(p) for p in parts)
        running = 0
        split_at = 0
        for i, part in enumerate(parts):
            running += len(part)
            if running >= total / 2:
                split_at = i + 1
                break

        left = " ".join(parts[:split_at]).strip()
        right = " ".join(parts[split_at:]).strip()
        return [left, right]

    def _synthesize_chunk_with_retry(
        self,
        tts,
        voice_style,
        chunk,
        min_chars=240,
        max_depth=5,
        depth=0,
    ):
        try:
            wav, _ = tts.synthesize(chunk, voice_style=voice_style, lang="en")
            return [wav]
        except Exception as exc:
            if (
                depth >= max_depth
                or len(chunk) <= min_chars
                or not self._is_retryable_onnx_error(exc)
            ):
                raise

            sub_chunks = [s for s in self._split_chunk_balanced(chunk) if s]
            if len(sub_chunks) <= 1:
                raise

            out = []
            for sub in sub_chunks:
                out.extend(
                    self._synthesize_chunk_with_retry(
                        tts,
                        voice_style,
                        sub,
                        min_chars=min_chars,
                        max_depth=max_depth,
                        depth=depth + 1,
                    )
                )
            return out

    def synthesize(self, text, voice, max_chars=1600):
        tts = self.ensure_model()
        try:
            voice_style = tts.get_voice_style(voice)
        except Exception:
            voices = self.list_voices()
            if not voices:
                raise RuntimeError("No voices available from Supertonic backend.")
            voice_style = tts.get_voice_style(voices[0])
        supported_chars = tts.model.text_processor.supported_character_set

        chunks = get_smart_chunks(text, max_chars=max_chars)
        audio_segments = []
        for chunk in chunks:
            clean_chunk = sanitize_text(chunk, supported_chars)
            if not clean_chunk:
                continue
            wav_parts = self._synthesize_chunk_with_retry(tts, voice_style, clean_chunk)
            audio_segments.extend(wav_parts)
        if not audio_segments:
            return None
        return np.concatenate(audio_segments, axis=1)

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
