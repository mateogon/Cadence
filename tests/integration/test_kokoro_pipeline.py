import json
import sys
import types
from pathlib import Path

import pytest

from core.tts_backend import SynthesisResult
from system import book_manager as bm


@pytest.fixture
def kokoro_import(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(bm, "LIBRARY_PATH", library)
    monkeypatch.setenv("CADENCE_TTS_BACKEND", "kokoro")
    monkeypatch.setenv("CADENCE_TTS_MODEL", "supertonic-3")
    monkeypatch.setattr(bm.BookManager, "_get_calibre_executable", staticmethod(lambda: "ebook-convert"))
    monkeypatch.setattr(bm.BookManager, "_detect_gpu_free_memory_mib", staticmethod(lambda: None))
    source = tmp_path / "Native.epub"
    source.write_text("source", encoding="utf-8")
    state = {"native": True, "calls": [], "processes": [], "language": "en"}

    def extract(**kwargs):
        for number in (1, 2):
            (kwargs["content_dir"] / f"ch_{number:03d}.txt").write_text("Hello world", encoding="utf-8")
        return 2, {"title": "Native", "language": state["language"]}

    monkeypatch.setattr(bm.BookManager, "_extract_chapter_texts", staticmethod(extract))

    class FakeKokoro:
        def __init__(self, model=None):
            state["calls"].append(("model", model))

        def list_voices(self, lang=None):
            return ["ef_dora"] if str(lang).startswith("es") else ["af_heart"]

        def default_voice(self, lang=None):
            return self.list_voices(lang)[0]

        def ensure_model(self):
            if state.get("missing_extra"):
                raise RuntimeError("Kokoro is not installed. Run uv sync --extra kokoro.")
            return self

        def synthesize(self, text, voice, max_chars=800, lang="na"):
            if voice not in self.list_voices(lang):
                raise ValueError(f"Invalid Kokoro voice '{voice}' for {lang}")
            state["calls"].append(("synthesize", voice, lang))
            words = [
                {"word": "Hello", "start": 0.0, "end": 0.4},
                {"word": "world", "start": 0.8, "end": 1.2},
            ] if state["native"] else None
            if state.get("invalid_times"):
                words[0]["end"] = -1
            return SynthesisResult(b"audio", words)

        def save_audio(self, audio, output_path):
            assert audio == b"audio"
            Path(output_path).write_bytes(b"native-audio")

    fake_kokoro = types.ModuleType("adapters.kokoro_backend")
    fake_kokoro.KokoroBackend = FakeKokoro
    monkeypatch.setitem(sys.modules, "adapters.kokoro_backend", fake_kokoro)
    fake_supertonic = types.ModuleType("adapters.supertonic_backend")

    class UnexpectedSupertonic:
        def __init__(self, model=None):
            raise AssertionError("Stored/selected Kokoro must not instantiate Supertonic")

    fake_supertonic.SupertonicBackend = UnexpectedSupertonic
    monkeypatch.setitem(sys.modules, "adapters.supertonic_backend", fake_supertonic)

    class AlignedProcess:
        returncode = 0

        def poll(self):
            return 0

        def communicate(self, timeout=None):
            return "", ""

    def popen(cmd, **kwargs):
        state["processes"].append(cmd)
        if str(cmd[1]).endswith("whisperx_align_worker.py"):
            raise OSError("Use the simulated CLI fallback")
        output = Path(cmd[cmd.index("--output-json") + 1])
        output.write_text('[{"word":"Hello","start":0,"end":1}]', encoding="utf-8")
        return AlignedProcess()

    monkeypatch.setattr(bm.subprocess, "Popen", popen)
    state.update(source=source, book_dir=library / "Native")
    return state


@pytest.mark.parametrize("workers", [1, 2])
def test_kokoro_native_timestamps_skip_whisperx_and_keep_resume_identity(kokoro_import, monkeypatch, workers):
    state = kokoro_import
    monkeypatch.setenv("CADENCE_SYNTH_WORKERS", str(workers))
    logs = []
    progress = []

    assert bm.BookManager.import_book(
        str(state["source"]), "M3", lambda pct, msg: progress.append((pct, msg)), log_callback=logs.append
    )

    book_dir = state["book_dir"]
    metadata = json.loads((book_dir / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["tts_backend"] == "kokoro"
    assert metadata["tts_model"] == "hexgrad/Kokoro-82M"
    assert metadata["voice"] == "af_heart"
    assert metadata["status"] == "complete"
    assert metadata["last_chapter"] == 2
    assert state["processes"] == []
    assert progress[-1] == (1.0, "Ready!")
    assert any("af_heart" in line and "M3" in line for line in logs)
    aligned = json.loads((book_dir / "content" / "ch_001.json").read_text(encoding="utf-8"))
    assert [word["word"] for word in aligned] == ["Hello", " ", "world"]
    assert aligned[-1]["start"] == 0.8
    assert aligned[-1]["end"] == 1.2
    assert not list((book_dir / "content").glob("*.part.json"))

    (book_dir / "audio" / "ch_002.wav").unlink()
    (book_dir / "content" / "ch_002.json").unlink()
    monkeypatch.setenv("CADENCE_TTS_BACKEND", "supertonic")
    state["calls"].clear()
    assert bm.BookManager.import_book(str(state["source"]), "ef_dora", lambda pct, msg: None)
    assert ("synthesize", "af_heart", "en") in state["calls"]
    assert state["processes"] == []
    assert (book_dir / "audio" / "ch_001.wav").read_bytes() == b"native-audio"


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("invalid_times", [False, True])
def test_kokoro_missing_or_invalid_timestamps_fall_back_to_whisperx(kokoro_import, monkeypatch, workers, invalid_times):
    state = kokoro_import
    state["native"] = invalid_times
    state["invalid_times"] = invalid_times
    monkeypatch.setenv("CADENCE_SYNTH_WORKERS", str(workers))
    logs = []

    assert bm.BookManager.import_book(str(state["source"]), "af_heart", lambda pct, msg: None, log_callback=logs.append)

    assert len([cmd for cmd in state["processes"] if str(cmd[1]).endswith("whisperx_align_cli.py")]) == 2
    assert any("falling back to WhisperX" in line for line in logs)
    metadata = json.loads((state["book_dir"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["status"] == "complete"
    assert metadata["last_chapter"] == 2


def test_kokoro_pending_alignment_keeps_existing_audio(kokoro_import):
    state = kokoro_import
    assert bm.BookManager.import_book(str(state["source"]), "auto", lambda pct, msg: None)
    (state["book_dir"] / "content" / "ch_001.json").unlink()
    state["calls"].clear()

    assert bm.BookManager.import_book(str(state["source"]), "auto", lambda pct, msg: None)

    assert state["calls"] == []
    assert state["processes"]
    assert (state["book_dir"] / "audio" / "ch_001.wav").read_bytes() == b"native-audio"


def test_kokoro_explicit_invalid_voice_fails_without_replacing_it(kokoro_import):
    state = kokoro_import
    state["language"] = "es"
    logs = []

    assert not bm.BookManager.import_book(str(state["source"]), "af_heart", lambda pct, msg: None, log_callback=logs.append)

    assert not any(call[0] == "synthesize" for call in state["calls"])
    assert any("af_heart" in line and "es" in line for line in logs)
    assert not list(state["book_dir"].glob("audio/*.wav"))
    metadata = json.loads((state["book_dir"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["tts_backend"] == "kokoro"
    assert not metadata.get("voice")

    assert bm.BookManager.import_book(str(state["source"]), "auto", lambda pct, msg: None)
    metadata = json.loads((state["book_dir"] / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["voice"] == "ef_dora"


@pytest.mark.parametrize("workers", [1, 2])
def test_kokoro_missing_extra_reports_install_command(kokoro_import, monkeypatch, workers):
    state = kokoro_import
    state["missing_extra"] = True
    monkeypatch.setenv("CADENCE_SYNTH_WORKERS", str(workers))
    logs = []

    assert not bm.BookManager.import_book(str(state["source"]), "auto", lambda pct, msg: None, log_callback=logs.append)

    assert any("uv sync --extra kokoro" in line for line in logs)


def test_kokoro_native_json_failure_resumes_without_replacing_saved_audio(kokoro_import, monkeypatch):
    state = kokoro_import
    monkeypatch.setenv("CADENCE_SYNTH_WORKERS", "1")
    replace = bm.os.replace

    def fail_native_json_once(source, destination):
        if str(destination).endswith("ch_001.json"):
            raise OSError("Simulated interrupted native JSON save")
        return replace(source, destination)

    monkeypatch.setattr(bm.os, "replace", fail_native_json_once)
    assert not bm.BookManager.import_book(str(state["source"]), "auto", lambda pct, msg: None)
    saved_audio = state["book_dir"] / "audio" / "ch_001.wav"
    assert saved_audio.read_bytes() == b"native-audio"
    assert not (state["book_dir"] / "content" / "ch_001.json").exists()
    assert not list((state["book_dir"] / "content").glob("*.part.json"))
    state["calls"].clear()
    monkeypatch.setattr(bm.os, "replace", replace)

    assert bm.BookManager.import_book(str(state["source"]), "auto", lambda pct, msg: None)

    assert len([call for call in state["calls"] if call[0] == "synthesize"]) == 1
    assert saved_audio.read_bytes() == b"native-audio"
    assert len([cmd for cmd in state["processes"] if str(cmd[1]).endswith("whisperx_align_cli.py")]) == 1
