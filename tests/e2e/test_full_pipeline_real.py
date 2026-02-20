import json
import os
from pathlib import Path

import pytest

from system import book_manager as bm


@pytest.mark.e2e
def test_full_pipeline_real(tmp_path, monkeypatch):
    """
    Real end-to-end test: source book -> extraction -> synthesis -> alignment.

    Opt-in only (skipped by default).
    Required env vars:
      CADENCE_RUN_E2E=1
      CADENCE_E2E_BOOK=<absolute path to .epub/.mobi/.azw3>

    Optional:
      CADENCE_E2E_VOICE=M3
    """
    if os.getenv("CADENCE_RUN_E2E", "").strip() != "1":
        pytest.skip("Set CADENCE_RUN_E2E=1 to run real E2E pipeline test.")

    source = os.getenv("CADENCE_E2E_BOOK", "").strip()
    if not source:
        pytest.skip("Set CADENCE_E2E_BOOK to an existing .epub/.mobi/.azw3 file.")

    source_path = Path(source)
    if not source_path.exists():
        pytest.skip(f"CADENCE_E2E_BOOK not found: {source_path}")

    if source_path.suffix.lower() not in {".epub", ".mobi", ".azw3"}:
        pytest.skip("CADENCE_E2E_BOOK must be .epub/.mobi/.azw3")

    monkeypatch.chdir(tmp_path)
    lib = tmp_path / "library"
    lib.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(bm, "LIBRARY_PATH", lib)

    voice = os.getenv("CADENCE_E2E_VOICE", "M3").strip() or "M3"
    skip_extraction = os.getenv("CADENCE_E2E_SKIP_EXTRACTION", "").strip() == "1"
    skip_whisperx = os.getenv("CADENCE_E2E_SKIP_WHISPERX", "").strip() == "1"
    custom_text = os.getenv("CADENCE_E2E_TEXT_TEMPLATE", "").strip()
    import_source = source_path

    if skip_extraction:
        chapters = max(1, int(os.getenv("CADENCE_E2E_TEXT_CHAPTERS", "4") or "4"))
        book_name = source_path.stem.replace(" ", "_")
        book_dir = lib / book_name
        content_dir = book_dir / "content"
        source_dir = book_dir / "source"
        content_dir.mkdir(parents=True, exist_ok=True)
        source_dir.mkdir(parents=True, exist_ok=True)

        for i in range(1, chapters + 1):
            stem = f"ch_{i:03d}"
            if custom_text:
                text = custom_text
            else:
                text = (
                    f"Chapter {i}. This is generated text-only e2e content for synthesis and alignment. "
                    f"Cadence should synthesize and align this chapter successfully. " * 10
                )
            (content_dir / f"{stem}.txt").write_text(text, encoding="utf-8")
            if skip_whisperx:
                # Pre-seed alignment JSON so import skips WhisperX and benchmarks TTS only.
                (content_dir / f"{stem}.json").write_text(
                    json.dumps([{"word": "seed", "start": 0.0, "end": 0.01}]),
                    encoding="utf-8",
                )

        stored_source = source_dir / source_path.name
        stored_source.write_bytes(source_path.read_bytes())

        (book_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "title": book_name.replace("_", " "),
                    "author": "Cadence E2E",
                    "status": "text_only",
                    "voice": voice,
                    "chapters": chapters,
                    "total_chapters": chapters,
                    "last_chapter": 0,
                    "cover": "",
                    "source_epub": f"source/{source_path.name}",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        import_source = stored_source
    else:
        calibre = Path(bm.CALIBRE_PATH)
        if not calibre.exists():
            pytest.skip(f"Calibre not found at configured path: {calibre}")

    progress = []
    logs = []

    ok = bm.BookManager.import_book(
        str(import_source),
        voice,
        lambda pct, msg: progress.append((pct, msg)),
        log_callback=logs.append,
    )

    assert ok is True, "Pipeline failed. Check log output captured in test failure context."
    assert progress and progress[-1] == (1.0, "Ready!")

    books = [p for p in lib.iterdir() if p.is_dir()]
    assert books, "No imported book directory created under temp library."

    book_dir = books[0]
    meta_path = book_dir / "metadata.json"
    assert meta_path.exists(), "metadata.json missing"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta.get("status") == "complete"

    content_dir = book_dir / "content"
    audio_dir = book_dir / "audio"
    txt = sorted(content_dir.glob("ch_*.txt"))
    wav = sorted(audio_dir.glob("ch_*.wav"))
    jsn = sorted(
        p
        for p in content_dir.glob("ch_*.json")
        if p.stem.startswith("ch_")
        and p.stem[3:].isdigit()
        and len(p.stem) == 6
    )

    assert txt, "No chapter text files generated"
    assert wav, "No chapter wav files generated"
    assert jsn, "No chapter alignment json files generated"

    assert len(wav) == len(txt)
    assert len(jsn) == len(txt)

    assert all(p.stat().st_size > 0 for p in wav)
    assert all(p.stat().st_size > 0 for p in jsn)
