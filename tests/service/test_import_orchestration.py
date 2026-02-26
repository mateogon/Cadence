import json
import sys
import types
from pathlib import Path

from system import book_manager as bm


def _progress_collector():
    events = []

    def cb(pct, msg):
        events.append((pct, msg))

    return events, cb


def test_import_book_returns_false_for_missing_source(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "LIBRARY_PATH", tmp_path / "library")
    bm.LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    events, progress = _progress_collector()
    ok = bm.BookManager.import_book(
        str(tmp_path / "missing.epub"),
        "M3",
        progress,
    )

    assert ok is False
    assert events == []


def test_import_book_returns_false_for_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "LIBRARY_PATH", tmp_path / "library")
    bm.LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    bad = tmp_path / "book.txt"
    bad.write_text("hello", encoding="utf-8")

    events, progress = _progress_collector()
    ok = bm.BookManager.import_book(str(bad), "M3", progress)

    assert ok is False
    assert events == []


def test_import_book_returns_false_when_calibre_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "LIBRARY_PATH", tmp_path / "library")
    bm.LIBRARY_PATH.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bm.BookManager, "_get_calibre_executable", staticmethod(lambda: None))

    source = tmp_path / "demo.epub"
    source.write_text("epub-bytes", encoding="utf-8")

    logs = []
    events, progress = _progress_collector()
    ok = bm.BookManager.import_book(
        str(source),
        "M3",
        progress,
        log_callback=logs.append,
    )

    assert ok is False
    assert events == []
    assert any("CADENCE_CALIBRE_PATH" in line for line in logs)


def test_import_book_extraction_failure_returns_false(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(bm, "LIBRARY_PATH", tmp_path / "library")
    bm.LIBRARY_PATH.mkdir(parents=True, exist_ok=True)

    source = tmp_path / "demo.epub"
    source.write_text("epub-bytes", encoding="utf-8")

    class _FailedRunResult:
        returncode = 1
        stdout = ""
        stderr = "calibre failed"

    monkeypatch.setattr(bm.subprocess, "run", lambda *args, **kwargs: _FailedRunResult())

    logs = []
    events, progress = _progress_collector()
    ok = bm.BookManager.import_book(
        str(source),
        "M3",
        progress,
        log_callback=logs.append,
    )

    assert ok is False
    assert any("Step 1/3: Extracting Text" in msg for _, msg in events)
    assert any("Calibre Error" in line for line in logs)


def test_import_book_resume_with_ready_artifacts_finishes_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "LIBRARY_PATH", tmp_path / "library")
    bm.LIBRARY_PATH.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bm.BookManager, "_detect_gpu_free_memory_mib", staticmethod(lambda: None))

    book_dir = bm.LIBRARY_PATH / "Sample_Book"
    source_dir = book_dir / "source"
    content_dir = book_dir / "content"
    audio_dir = book_dir / "audio"
    source_dir.mkdir(parents=True)
    content_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)

    source_epub = source_dir / "Sample_Book.epub"
    source_epub.write_text("epub", encoding="utf-8")

    (content_dir / "ch_001.txt").write_text("hello world", encoding="utf-8")
    (content_dir / "ch_001.json").write_text('[{"word": "hello", "start": 0.0, "end": 0.2}]', encoding="utf-8")
    (audio_dir / "ch_001.wav").write_bytes(b"RIFF....WAVEfmt ")

    (book_dir / "metadata.json").write_text(
        json.dumps(
            {
                "title": "Sample Book",
                "author": "Unknown",
                "status": "complete",
                "voice": "M3",
                "chapters": 1,
                "total_chapters": 1,
                "last_chapter": 1,
                "cover": "",
                "source_epub": "source/Sample_Book.epub",
            }
        ),
        encoding="utf-8",
    )

    fake_mod = types.ModuleType("adapters.supertonic_backend")

    class _BombBackend:
        def __init__(self):
            raise AssertionError("SupertonicBackend should not be created when all chapters are ready")

    fake_mod.SupertonicBackend = _BombBackend
    monkeypatch.setitem(sys.modules, "adapters.supertonic_backend", fake_mod)

    logs = []
    events, progress = _progress_collector()
    ok = bm.BookManager.import_book(
        str(source_epub),
        "F1",
        progress,
        log_callback=logs.append,
    )

    assert ok is True
    assert any("Step 2/3: Streaming synthesis + alignment" in msg for _, msg in events)
    assert events[-1] == (1.0, "Ready!")

    updated = json.loads((book_dir / "metadata.json").read_text(encoding="utf-8"))
    assert updated["status"] == "complete"
    assert updated["last_chapter"] == 1
    assert updated["voice"] == "M3"
    assert any("Resuming import for" in line for line in logs)


def test_import_book_uses_extracted_opf_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "LIBRARY_PATH", tmp_path / "library")
    bm.LIBRARY_PATH.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bm.BookManager, "_get_calibre_executable", staticmethod(lambda: "ebook-convert"))
    monkeypatch.setattr(
        bm.BookManager,
        "_extract_chapter_texts",
        staticmethod(lambda **kwargs: (2, {"title": "Canonical Title", "author": "Author X", "cover": "cover.jpg"})),
    )
    monkeypatch.setattr(bm.BookManager, "_run_streaming_pipeline", staticmethod(lambda **kwargs: True))
    monkeypatch.setattr(
        bm.BookManager,
        "_finalize_metadata",
        staticmethod(lambda book_dir, content_dir, audio_dir, metadata: metadata),
    )

    source = tmp_path / "demo.epub"
    source.write_text("epub-bytes", encoding="utf-8")

    events, progress = _progress_collector()
    ok = bm.BookManager.import_book(
        str(source),
        "M3",
        progress,
    )

    assert ok is True
    book_dir = bm.LIBRARY_PATH / "demo"
    saved = json.loads((book_dir / "metadata.json").read_text(encoding="utf-8"))
    assert saved["title"] == "Canonical Title"
    assert saved["author"] == "Author X"
    assert saved["cover"] == "cover.jpg"
