import importlib.util
import sys
import types
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "adapters" / "generate_audiobook_supertonic.py"


class _FakeOrt:
    @staticmethod
    def get_available_providers():
        return ["CPUExecutionProvider"]

    @staticmethod
    def set_default_logger_severity(_level):
        return None


class _FakeTTS:
    def __init__(self, auto_download=True):
        self.auto_download = auto_download


def _load_module_with_stubs(monkeypatch):
    fake_supertonic = types.ModuleType("supertonic")
    fake_supertonic.TTS = _FakeTTS

    monkeypatch.setitem(sys.modules, "onnxruntime", _FakeOrt)
    monkeypatch.setitem(sys.modules, "supertonic", fake_supertonic)

    spec = importlib.util.spec_from_file_location("_test_supertonic_mod", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sanitize_text_handles_unicode_punctuation(monkeypatch):
    mod = _load_module_with_stubs(monkeypatch)

    supported_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ,-.")
    text = "Don’t wait—now…"

    out = mod.sanitize_text(text, supported_chars)

    assert out == "Dont wait, now..."


def test_get_smart_chunks_splits_long_text(monkeypatch):
    mod = _load_module_with_stubs(monkeypatch)

    text = "One short sentence. " + ("part, " * 30) + "end."
    chunks = mod.get_smart_chunks(text, max_chars=60)

    assert len(chunks) >= 2
    assert all(len(c) <= 60 for c in chunks)
    assert all(c.strip() for c in chunks)
