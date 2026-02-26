import json
import sys
import types
from pathlib import Path

from system import book_manager as bm


class _RunResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _FakeWorkerStdout:
    def __init__(self, queue):
        self._queue = queue

    def readline(self):
        if self._queue:
            return self._queue.pop(0)
        return ""


class _FakeWorkerStdin:
    def __init__(self, proc):
        self._proc = proc

    def write(self, line):
        payload = json.loads(line.strip())
        cmd = payload.get("cmd")
        if cmd == "align":
            out_json = Path(payload["out_json"])
            report_json = Path(payload["report_json"])
            raw_json = Path(payload["raw_json"])

            out_json.write_text(
                json.dumps([
                    {"word": "Hello", "start": 0.0, "end": 0.25},
                    {"word": "world", "start": 0.25, "end": 0.5},
                ]),
                encoding="utf-8",
            )
            report_json.write_text(
                json.dumps(
                    {
                        "device": "cpu",
                        "timing_seconds": {
                            "whisperx_transcribe_and_align": 0.01,
                            "total": 0.02,
                        },
                    }
                ),
                encoding="utf-8",
            )
            raw_json.write_text("{}", encoding="utf-8")
            self._proc._queue.append('{"event":"aligned"}\n')
        elif cmd == "shutdown":
            self._proc._terminated = True

    def flush(self):
        return None


class _FakeWorkerProc:
    def __init__(self):
        self._queue = ['{"event":"ready","device":"cpu","resolved_compute_type":"float32"}\n']
        self.stdout = _FakeWorkerStdout(self._queue)
        self.stdin = _FakeWorkerStdin(self)
        self._terminated = False

    def wait(self, timeout=None):
        self._terminated = True
        return 0

    def kill(self):
        self._terminated = True


def test_pipeline_generated_short_book(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(bm, "LIBRARY_PATH", library)
    monkeypatch.setattr(bm.BookManager, "_detect_gpu_free_memory_mib", staticmethod(lambda: None))
    monkeypatch.setattr(bm.BookManager, "_get_calibre_executable", staticmethod(lambda: "ebook-convert"))

    # Synthetic source "book" file.
    source_epub = tmp_path / "MiniBook.epub"
    source_epub.write_text("synthetic-epub", encoding="utf-8")

    def _fake_run(cmd, *args, **kwargs):
        # 1) EPUB unpack step: create synthetic HTML chapters.
        if len(cmd) >= 3 and str(cmd[2]).endswith("temp_extraction"):
            out_dir = Path(cmd[2])
            out_dir.mkdir(parents=True, exist_ok=True)
            chapter_text = ("Short chapter text. " * 30).strip()
            (out_dir / "ch1.xhtml").write_text(chapter_text, encoding="utf-8")
            (out_dir / "ch2.xhtml").write_text(chapter_text, encoding="utf-8")
            return _RunResult(returncode=0)

        # 2) HTML -> TXT conversion step.
        if len(cmd) >= 3 and str(cmd[2]).endswith(".part.txt"):
            out_txt_tmp = Path(cmd[2])
            out_txt_tmp.parent.mkdir(parents=True, exist_ok=True)
            out_txt_tmp.write_text("Hello world. This is a generated short chapter.", encoding="utf-8")
            return _RunResult(returncode=0)

        return _RunResult(returncode=0)

    monkeypatch.setattr(bm.subprocess, "run", _fake_run)

    def _fake_popen(cmd, *args, **kwargs):
        # Worker mode only for this test.
        if len(cmd) >= 2 and str(cmd[1]).endswith("whisperx_align_worker.py"):
            return _FakeWorkerProc()
        raise AssertionError(f"Unexpected Popen call in test: {cmd}")

    monkeypatch.setattr(bm.subprocess, "Popen", _fake_popen)

    fake_mod = types.ModuleType("adapters.supertonic_backend")

    class _FakeBackend:
        def ensure_model(self):
            return self

        def synthesize(self, text, voice, max_chars=1600):
            return b"wav-bytes"

        def save_audio(self, wav, output_path):
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"RIFF....WAVEfmt ")

    fake_mod.SupertonicBackend = _FakeBackend
    monkeypatch.setitem(sys.modules, "adapters.supertonic_backend", fake_mod)

    progress_events = []
    logs = []

    ok = bm.BookManager.import_book(
        str(source_epub),
        "M3",
        lambda pct, msg: progress_events.append((pct, msg)),
        log_callback=logs.append,
    )

    assert ok is True
    assert progress_events[-1] == (1.0, "Ready!")

    book_dir = library / "MiniBook"
    meta = json.loads((book_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["status"] == "complete"
    assert meta["total_chapters"] == 2
    assert meta["last_chapter"] == 2

    assert (book_dir / "content" / "ch_001.txt").exists()
    assert (book_dir / "content" / "ch_001.json").exists()
    assert (book_dir / "audio" / "ch_001.wav").exists()
    assert (book_dir / "content" / "ch_002.txt").exists()
    assert (book_dir / "content" / "ch_002.json").exists()
    assert (book_dir / "audio" / "ch_002.wav").exists()

    assert any("Streaming Chapter Pipeline" in line for line in logs)
