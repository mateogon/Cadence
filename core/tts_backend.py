from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class SynthesisResult:
    """Audio plus optional chapter-relative word times from the synthesizer."""

    audio: Any
    word_timestamps: list[dict] | None = None


class TTSBackend(ABC):
    @abstractmethod
    def ensure_model(self):
        raise NotImplementedError

    @abstractmethod
    def list_voices(self):
        raise NotImplementedError

    @abstractmethod
    def synthesize(self, text, voice):
        raise NotImplementedError

    @abstractmethod
    def save_audio(self, wav, output_path):
        raise NotImplementedError
