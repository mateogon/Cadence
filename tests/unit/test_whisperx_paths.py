"""WhisperX runs in a subprocess whose cwd is the project root, not the caller's cwd."""
import json
from pathlib import Path

import pytest

from system.book_manager import BookManager


class _FakeWhisperX:
    """Stands in for the worker and the CLI: resolves paths against its own cwd, like the real process."""

    def __init__(self, cmd, cwd):
        self.cmd, self.cwd = [str(c) for c in cmd], Path(cwd)
        self.is_worker = self.cmd[1].endswith("whisperx_align_worker.py")
        self.lines = ['{"event":"ready","device":"cpu","resolved_compute_type":"float32"}\n'] if self.is_worker else []
        self.stdin, self.stdout, self.returncode = self, self, 0

    def _align(self, wav, out_json):
        if not (self.cwd / wav).is_file():
            return f"Missing WAV: {wav}"
        (self.cwd / out_json).write_text(json.dumps([{"word": "chapter", "start": 0.0, "end": 0.4}]), encoding="utf-8")
        return None

    # Worker protocol: one JSON command per stdin line, one JSON event per stdout line.
    def write(self, line):
        payload = json.loads(line)
        if payload.get("cmd") == "align":
            error = self._align(payload["wav"], payload["out_json"])
            self.lines.append(json.dumps({"event": "error", "error": error} if error else {"event": "aligned"}) + "\n")

    def flush(self):
        pass

    def readline(self):
        return self.lines.pop(0) if self.lines else ""

    # CLI protocol: arguments in, exit code out.
    def poll(self):
        return 0

    def communicate(self, timeout=None):
        error = self._align(self.cmd[2], self.cmd[self.cmd.index("--output-json") + 1])
        self.returncode = 1 if error else 0
        return ("", error or "")

    def wait(self, timeout=None):
        return 0

    def kill(self):
        pass

    terminate = kill


@pytest.mark.parametrize("worker_starts", [True, False], ids=["worker", "cli-fallback"])
def test_alignment_finds_chapter_files_when_cadence_runs_outside_the_project(tmp_path, monkeypatch, worker_starts):
    project_root = Path(__file__).resolve().parents[2]
    monkeypatch.chdir(tmp_path)
    book_dir = Path("library") / "Book"  # relative, as LIBRARY_PATH is
    content_dir, audio_dir = book_dir / "content", book_dir / "audio"
    content_dir.mkdir(parents=True)
    audio_dir.mkdir()
    (content_dir / "ch_001.txt").write_text("chapter", encoding="utf-8")
    (audio_dir / "ch_001.wav").write_bytes(b"RIFF....WAVEfmt ")

    def fake_popen(cmd, *args, cwd=None, **kwargs):
        assert Path(cwd).resolve() == project_root
        proc = _FakeWhisperX(cmd, cwd)
        if proc.is_worker and not worker_starts:
            proc.lines = []
        return proc

    monkeypatch.setattr("system.book_manager.subprocess.Popen", fake_popen)
    logs = []
    ok = BookManager._run_streaming_pipeline(
        book_dir=book_dir, content_dir=content_dir, audio_dir=audio_dir, voice="M3",
        metadata={"title": "Book", "voice": "M3"}, progress_callback=lambda _pct, _msg: None,
        is_cancelled=lambda: False, log=logs.append,
    )

    assert not any("Missing WAV" in line for line in logs), logs
    assert ok is True
    assert (content_dir / "ch_001.json").is_file()
