import builtins
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from adapters.kokoro_backend import KokoroBackend, resolve_device, speech_blocks


def token(word, start=0.0, end=0.5):
    return SimpleNamespace(text=word, start_ts=start, end_ts=end)


def piece(word="Hello", duration=1, tokens=None):
    return SimpleNamespace(
        audio=np.zeros(int(duration * 24000), dtype=np.float32),
        tokens=[token(word)] if tokens is None else tokens,
    )


@pytest.fixture
def fake_kokoro(monkeypatch):
    state = SimpleNamespace(models=[], pipelines=[], results=[piece()], calls=[])

    class Model:
        def __init__(self, **kwargs):
            state.models.append(kwargs)

        def to(self, device):
            state.device = device
            return self

        def eval(self):
            return self

    class Pipeline:
        def __init__(self, **kwargs):
            state.pipelines.append(kwargs)

        def __call__(self, text, **kwargs):
            state.calls.append((text, kwargs))
            yield from state.results

    monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KModel=Model, KPipeline=Pipeline))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False)),
    ))
    monkeypatch.delenv("CADENCE_KOKORO_DEVICE", raising=False)
    monkeypatch.delenv("CADENCE_TTS_SPEED", raising=False)
    return state


def test_adapter_and_voice_catalog_need_no_optional_imports():
    code = """
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'torch', 'kokoro'}:
        raise AssertionError('optional import: ' + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from adapters.kokoro_backend import KokoroBackend
backend = KokoroBackend()
assert backend.default_voice('es') == 'ef_dora'
assert backend.list_voices('en-GB')
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=os.getcwd())


def test_missing_extra_reports_install_command(monkeypatch):
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "kokoro":
            raise ImportError("missing kokoro")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(RuntimeError, match="uv sync --extra kokoro"):
        KokoroBackend().ensure_model()


def test_mps_fallback_is_set_before_torch_import(monkeypatch, fake_kokoro):
    monkeypatch.delenv("PYTORCH_ENABLE_MPS_FALLBACK", raising=False)
    original = builtins.__import__

    def checked(name, *args, **kwargs):
        if name == "torch":
            assert os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked)
    KokoroBackend().ensure_model()


@pytest.mark.parametrize("cuda,mps,setting,expected", [
    (True, True, "auto", "cuda"), (False, True, "auto", "mps"),
    (False, False, "auto", "cpu"), (True, True, "cpu", "cpu"),
    (True, True, "mps", "mps"), (False, False, "cuda", "cpu"),
    (False, False, "mps", "cpu"),
])
def test_device_priority_and_unavailable_fallback(monkeypatch, fake_kokoro, cuda, mps, setting, expected):
    torch = sys.modules["torch"]
    torch.cuda.is_available = lambda: cuda
    torch.backends.mps.is_available = lambda: mps
    assert resolve_device(setting) == expected


def test_device_setting_is_validated_and_explicit_device_wins(monkeypatch, fake_kokoro):
    monkeypatch.setenv("CADENCE_KOKORO_DEVICE", "bad")
    with pytest.raises(ValueError, match="CADENCE_KOKORO_DEVICE"):
        KokoroBackend()
    backend = KokoroBackend(device="cpu")
    backend.ensure_model()
    assert fake_kokoro.device == "cpu"


@pytest.mark.parametrize("lang,prefixes", [
    ("en", "ab"), ("en-US", "a"), ("en_GB", "b"),
    ("es-CL", "e"), ("fr-FR", "f"), ("hi", "h"),
    ("it", "i"), ("ja", "j"), ("pt-BR", "p"), ("zh-CN", "z"),
])
def test_voice_catalog_filters_book_language(lang, prefixes):
    voices = KokoroBackend().list_voices(lang)
    assert voices
    assert all(voice[0] in prefixes for voice in voices)


def test_catalog_defaults_and_unknown_language():
    backend = KokoroBackend()
    assert len(backend.list_voices()) == 54
    assert backend.default_voice("na") == "af_heart"
    assert backend.default_voice("en-GB") == "bf_alice"
    assert backend.default_voice("es") == "ef_dora"
    assert backend.list_voices("de") == []
    with pytest.raises(ValueError, match="language"):
        backend.default_voice("de")


def test_speech_blocks_join_lines_preserve_paragraphs_and_bound_long_lines():
    text = "First sentence.\nSecond sentence.\n\n" + "longword " * 140
    blocks = speech_blocks(text).splitlines()
    assert blocks[0] == "First sentence. Second sentence."
    assert all(len(block) <= 450 for block in blocks)
    assert " ".join(blocks[1:]).split() == ("longword " * 140).split()
    assert speech_blocks("X" * 901).splitlines() == ["X" * 450, "X" * 450, "X"]


def test_offsets_include_package_internal_splits_across_two_input_blocks(fake_kokoro):
    fake_kokoro.results = [
        piece("First", duration=1), piece("internal", duration=2),
        piece("Second", duration=1.5),
    ]
    result = KokoroBackend().synthesize("First block.\n\nSecond block.", "af_heart", max_chars=3, lang="en")
    assert len(result.audio) == 108000
    assert result.word_timestamps == [
        {"word": "First", "start": 0.0, "end": 0.5},
        {"word": "internal", "start": 1.0, "end": 1.5},
        {"word": "Second", "start": 3.0, "end": 3.5},
    ]
    assert fake_kokoro.calls == [("First block.\nSecond block.", {
        "voice": "af_heart", "speed": 1.05, "split_pattern": r"\n+",
    })]


@pytest.mark.parametrize("tokens", [
    [], [token("hello", None, None)], [token("hello"), token("missing", None, None)],
    [token("hello", float("nan"), 0.5)], [token("hello", 0, float("inf"))],
    [token("hello", -0.1, 0.5)], [token("hello", 0.6, 0.5)],
    [token("hello", 0, 2)], [token("hello", 0.1, 0.6), token("overlap", 0.5, 0.8)],
])
def test_invalid_or_partial_times_fall_back_for_whole_chapter(fake_kokoro, tokens):
    fake_kokoro.results = [piece("valid"), piece(tokens=tokens)]
    result = KokoroBackend().synthesize("Hello.", "af_heart", lang="en")
    assert len(result.audio) == 48000
    assert result.word_timestamps is None


def test_punctuation_without_times_is_not_a_missing_spoken_word(fake_kokoro):
    fake_kokoro.results = [piece(tokens=[token("Hello"), token("!", None, None)])]
    assert KokoroBackend().synthesize("Hello!", "af_heart").word_timestamps == [
        {"word": "Hello", "start": 0.0, "end": 0.5},
    ]


def test_adjacent_times_with_large_offsets_stay_valid(fake_kokoro):
    fake_kokoro.results = [
        piece(duration=1.01),
        piece(tokens=[token("One", 0, 0.1), token("two", 0.1, 0.5)]),
    ]
    times = KokoroBackend().synthesize("Hello", "af_heart").word_timestamps
    assert times is not None
    assert times[-1] == {"word": "two", "start": 1.11, "end": 1.51}


def test_non_english_without_tokens_returns_audio_for_whisperx(fake_kokoro):
    fake_kokoro.results = [SimpleNamespace(audio=np.zeros(24000), tokens=None)]
    result = KokoroBackend().synthesize("Hola.", "ef_dora", lang="es")
    assert result.word_timestamps is None
    assert len(result.audio) == 24000
    assert fake_kokoro.pipelines[0]["lang_code"] == "e"


def test_model_is_cached_and_shared_between_language_pipelines(fake_kokoro):
    backend = KokoroBackend()
    backend.synthesize("Hello", "af_heart", lang="en")
    backend.synthesize("Hola", "ef_dora", lang="es")
    backend.synthesize("Hi", "bf_alice", lang="en-GB")
    assert fake_kokoro.models == [{"repo_id": "hexgrad/Kokoro-82M"}]
    assert len(fake_kokoro.pipelines) == 3
    assert len({id(kwargs["model"]) for kwargs in fake_kokoro.pipelines}) == 1


@pytest.mark.parametrize("lang,voice,extra,label", [
    ("ja", "jf_alpha", "ja", "Japanese"), ("zh", "zf_xiaobei", "zh", "Chinese"),
])
@pytest.mark.parametrize("error_type", [ImportError, ModuleNotFoundError])
def test_missing_language_tokenizer_reports_actionable_command(
        fake_kokoro, monkeypatch, lang, voice, extra, label, error_type):
    failure = error_type("missing language dependency")

    def missing(**kwargs):
        raise failure

    monkeypatch.setattr(sys.modules["kokoro"], "KPipeline", missing)
    backend = KokoroBackend()
    with pytest.raises(RuntimeError, match=f"{label} tokenizer") as error:
        backend.synthesize("Hello", voice, lang=lang)
    assert f"uv run --extra kokoro --with 'misaki[{extra}]' main.py" in str(error.value)
    assert error.value.__cause__ is failure
    assert not backend._pipelines


def test_language_tokenizer_runtime_errors_are_not_mislabeled(fake_kokoro, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("model runtime failure")

    monkeypatch.setattr(sys.modules["kokoro"], "KPipeline", broken)
    with pytest.raises(RuntimeError, match="^model runtime failure$"):
        KokoroBackend().synthesize("Hello", "jf_alpha", lang="ja")


@pytest.mark.parametrize("voice,lang", [("M3", "en"), ("af_heart", "es"), ("bf_alice", "en-US"), ("af_heart", "de")])
def test_incompatible_or_unknown_voice_is_never_silently_changed(fake_kokoro, voice, lang):
    with pytest.raises(ValueError):
        KokoroBackend().synthesize("Hello", voice, lang=lang)
    assert fake_kokoro.models == []


@pytest.mark.parametrize("speed", ["nan", "bad", "0.6", "2.1"])
def test_speed_is_validated_before_loading_model(monkeypatch, fake_kokoro, speed):
    monkeypatch.setenv("CADENCE_TTS_SPEED", speed)
    with pytest.raises(ValueError, match="CADENCE_TTS_SPEED"):
        KokoroBackend().synthesize("Hello", "af_heart")
    assert fake_kokoro.models == []


def test_speed_does_not_read_supertonic_model_setting(monkeypatch, fake_kokoro):
    monkeypatch.setenv("CADENCE_TTS_MODEL", "invalid-for-supertonic")
    monkeypatch.setenv("CADENCE_TTS_SPEED", "1.2")
    KokoroBackend().synthesize("Hello", "af_heart")
    assert fake_kokoro.calls[0][1]["speed"] == 1.2


@pytest.mark.parametrize("audio", [None, np.array([]), np.zeros((1, 2)), np.array([float("nan")])])
def test_invalid_audio_cannot_produce_success(fake_kokoro, audio):
    fake_kokoro.results = [SimpleNamespace(audio=audio, tokens=[token("hello")])]
    with pytest.raises(ValueError, match="audio"):
        KokoroBackend().synthesize("Hello", "af_heart")


def test_no_yielded_audio_is_an_error(fake_kokoro):
    fake_kokoro.results = []
    with pytest.raises(ValueError, match="audio"):
        KokoroBackend().synthesize("Hello", "af_heart")


def test_empty_text_does_not_load_model(fake_kokoro):
    assert KokoroBackend().synthesize(" \n!\n ", "af_heart").audio is None
    assert fake_kokoro.models == []


def test_atomic_save_preserves_previous_audio_on_failure(tmp_path, monkeypatch):
    import soundfile

    destination = tmp_path / "chapter.wav"
    destination.write_bytes(b"previous")

    def fail(path, wav, sample_rate):
        path.write_bytes(b"partial")
        raise RuntimeError("write failed")

    monkeypatch.setattr(soundfile, "write", fail)
    with pytest.raises(RuntimeError, match="write failed"):
        KokoroBackend().save_audio(np.zeros(20), destination)
    assert destination.read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.part.wav"))


def test_save_audio_writes_mono_24khz(tmp_path):
    import soundfile

    destination = tmp_path / "new" / "chapter.wav"
    KokoroBackend().save_audio(np.zeros(2400), destination)
    info = soundfile.info(destination)
    assert (info.frames, info.samplerate, info.channels) == (2400, 24000, 1)
