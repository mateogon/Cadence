from abc import ABC, abstractmethod


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
