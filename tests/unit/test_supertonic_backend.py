from types import SimpleNamespace

import numpy as np
import pytest

from adapters import generate_audiobook_supertonic as generator
from adapters.supertonic_backend import SupertonicBackend


class FakeProcessor:
    def validate_text(self, text):
        unsupported = sorted(set(text) & {"☃", "'"})
        return not unsupported, unsupported


class FakeTTS:
    voice_style_names = ["M3", "F1"]

    def __init__(self):
        self.model = SimpleNamespace(text_processor=FakeProcessor())
        self.calls = []

    def get_voice_style(self, voice):
        if voice not in self.voice_style_names:
            raise FileNotFoundError(voice)
        return f"style:{voice}"

    def synthesize(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.ones((1, 4)), np.array([0.1])


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.delenv("CADENCE_TTS_MODEL", raising=False)
    monkeypatch.delenv("CADENCE_TTS_SPEED", raising=False)
    monkeypatch.delenv("CADENCE_TTS_STEPS", raising=False)
    backend = SupertonicBackend()
    backend.tts = FakeTTS()
    return backend


def test_lists_voice_style_names(backend):
    assert backend.list_voices() == ["M3", "F1"]


def test_synthesis_passes_language_settings_and_package_chunking(backend, monkeypatch):
    monkeypatch.setenv("CADENCE_TTS_SPEED", "1.2")
    monkeypatch.setenv("CADENCE_TTS_STEPS", "12")
    wav = backend.synthesize("Don’t wait—ahora ☃.", "M3", max_chars=300, lang="es-CL")
    assert wav.shape == (1, 4)
    assert backend.tts.calls == [("Dont wait, ahora .", {
        "voice_style": "style:M3", "lang": "es", "max_chunk_length": 300,
        "speed": 1.2, "total_steps": 12,
    })]


@pytest.mark.parametrize("lang", ["", "xx", None])
def test_unknown_language_uses_na(backend, lang):
    backend.synthesize("Hello", "M3", lang=lang)
    assert backend.tts.calls[0][1]["lang"] == "na"


def test_synthesis_defaults_and_voice_fallback(backend):
    backend.synthesize("Hello", "missing")
    assert backend.tts.calls[0][1] == {
        "voice_style": "style:M3", "lang": "na", "max_chunk_length": 1600,
        "speed": 1.05, "total_steps": 8,
    }


def test_empty_sanitized_text_does_not_synthesize(backend):
    assert backend.synthesize("☃", "M3") is None
    assert backend.tts.calls == []


@pytest.mark.parametrize("speed", ["0.6", "2.1", "nan", "bad"])
def test_invalid_speed_rejected(backend, monkeypatch, speed):
    monkeypatch.setenv("CADENCE_TTS_SPEED", speed)
    with pytest.raises(ValueError, match="CADENCE_TTS_SPEED"):
        backend.synthesize("Hello", "M3")
    assert backend.tts.calls == []


@pytest.mark.parametrize("steps", ["0", "101", "1.2", "bad"])
def test_invalid_steps_rejected(backend, monkeypatch, steps):
    monkeypatch.setenv("CADENCE_TTS_STEPS", steps)
    with pytest.raises(ValueError, match="CADENCE_TTS_STEPS"):
        backend.synthesize("Hello", "M3")


def test_explicit_model_wins_over_setting(monkeypatch):
    monkeypatch.setenv("CADENCE_TTS_MODEL", "supertonic-2")
    calls = []
    monkeypatch.setattr("adapters.supertonic_backend.init_tts_engine", lambda model: calls.append(model) or FakeTTS())
    assert SupertonicBackend().model == "supertonic-2"
    backend = SupertonicBackend(model="supertonic")
    backend.ensure_model()
    assert calls == ["supertonic"]
    monkeypatch.setenv("CADENCE_TTS_MODEL", "invalid-current-setting")
    backend.synthesize("Hello", "M3")
    assert backend.tts.calls


def test_process_folder_uses_current_api(tmp_path, monkeypatch):
    source = tmp_path / "input"
    source.mkdir()
    (source / "one.txt").write_text("Hola", encoding="utf-8")
    tts = FakeTTS()
    saved = []
    tts.save_audio = lambda wav, path: saved.append(path)
    monkeypatch.setattr(generator, "init_tts_engine", lambda model=None: tts)
    generator.process_folder(source, tmp_path / "output", "M3", lang="es_ES")
    assert tts.calls[0][1]["lang"] == "es"
    assert len(saved) == 1


def test_list_voices_cli_needs_no_folder(monkeypatch, capsys):
    monkeypatch.setattr(generator, "init_tts_engine", lambda model=None: FakeTTS())
    generator.main(["--list-voices"])
    assert "M3, F1" in capsys.readouterr().out


def test_long_chapter_respects_package_per_call_limit(backend):
    from supertonic.config import MAX_TEXT_LENGTH

    text = "A complete sentence. " * 6000
    wav = backend.synthesize(text, "M3", max_chars=800)
    assert len(backend.tts.calls) == 2
    assert all(len(text) <= MAX_TEXT_LENGTH for text, _ in backend.tts.calls)
    assert all(kwargs["max_chunk_length"] == 800 for _, kwargs in backend.tts.calls)
    assert wav.shape == (1, 8)


@pytest.mark.parametrize("force_cpu, expected", [
    ("0", ["CUDAExecutionProvider", "CPUExecutionProvider"]),
    ("1", ["CPUExecutionProvider"]),
])
def test_provider_patch_reaches_real_loader(tmp_path, monkeypatch, capsys, force_cpu, expected):
    import supertonic.loader as loader

    monkeypatch.setenv("CADENCE_FORCE_CPU", force_cpu)
    monkeypatch.setenv("CADENCE_CUDA_ONLY", "0")
    monkeypatch.setenv("CADENCE_USE_TENSORRT", "0")
    monkeypatch.setattr(loader, "DEFAULT_ONNX_PROVIDERS", list(loader.DEFAULT_ONNX_PROVIDERS))
    monkeypatch.setattr(generator.ort, "get_available_providers", lambda: [
        "CUDAExecutionProvider", "CPUExecutionProvider",
    ])
    captured = []

    def session(path, sess_options, providers):
        captured.append(providers)
        return SimpleNamespace(get_providers=lambda: providers)

    monkeypatch.setattr(generator.ort, "InferenceSession", session)
    for path in loader.get_all_onnx_module_relative_paths():
        (tmp_path / path).parent.mkdir(exist_ok=True)
        (tmp_path / path).touch()

    def tts(model, auto_download):
        assert model == "supertonic-3"
        assert auto_download is True
        sessions = loader.load_onnx_modules(tmp_path)
        return SimpleNamespace(model=SimpleNamespace(**dict(zip(
            ["dp_ort", "text_enc_ort", "vector_est_ort", "vocoder_ort"], sessions,
        ))))

    monkeypatch.setattr(generator, "TTS", tts)
    generator.init_tts_engine(model="supertonic-3")
    assert captured == [expected] * 4
    output = capsys.readouterr().out
    assert "Supertonic active providers per session:" in output
    assert str(tuple(expected)) in output
