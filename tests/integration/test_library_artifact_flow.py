import json

from system import book_manager as bm


def _write_book(base, name, total_chapters, with_audio, with_json):
    book_dir = base / name
    content = book_dir / "content"
    audio = book_dir / "audio"
    source = book_dir / "source"
    content.mkdir(parents=True)
    audio.mkdir(parents=True)
    source.mkdir(parents=True)

    for i in range(1, total_chapters + 1):
        stem = f"ch_{i:03d}"
        (content / f"{stem}.txt").write_text(f"chapter {i} text", encoding="utf-8")
        if i <= with_audio:
            (audio / f"{stem}.wav").write_bytes(b"RIFF....WAVEfmt ")
        if i <= with_json:
            (content / f"{stem}.json").write_text(
                '[{"word": "chapter", "start": 0.0, "end": 0.2}]',
                encoding="utf-8",
            )

    meta = {
        "title": name.replace("_", " "),
        "author": "Unknown",
        "status": "processing",
        "voice": "M3",
        "chapters": total_chapters,
        "total_chapters": total_chapters,
        "last_chapter": min(with_audio, with_json),
        "cover": "",
        "source_epub": f"source/{name}.epub",
    }
    (book_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    (source / f"{name}.epub").write_text("epub", encoding="utf-8")


def test_get_books_reports_ready_counts_and_incomplete_flags(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(bm, "LIBRARY_PATH", library)

    _write_book(library, "Book_Complete", total_chapters=2, with_audio=2, with_json=2)
    _write_book(library, "Book_Incomplete", total_chapters=3, with_audio=2, with_json=1)

    books = bm.BookManager.get_books()
    by_title = {b["title"]: b for b in books}

    complete = by_title["Book Complete"]
    assert complete["content_chapters"] == 2
    assert complete["audio_chapters_ready"] == 2
    assert complete["aligned_chapters_ready"] == 2
    assert complete["audio_missing"] == 0
    assert complete["aligned_missing"] == 0
    assert complete["is_incomplete"] is False
    assert complete["stored_epub_exists"] is True

    incomplete = by_title["Book Incomplete"]
    assert incomplete["content_chapters"] == 3
    assert incomplete["audio_chapters_ready"] == 2
    assert incomplete["aligned_chapters_ready"] == 1
    assert incomplete["audio_missing"] == 1
    assert incomplete["aligned_missing"] == 2
    assert incomplete["is_incomplete"] is True
    assert incomplete["stored_epub_exists"] is True


def test_get_books_ignores_invalid_book_directories(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(bm, "LIBRARY_PATH", library)

    # Missing metadata.json -> not a valid book entry
    (library / "No_Metadata" / "content").mkdir(parents=True)

    # Bad metadata content -> should be skipped safely
    bad = library / "Bad_Metadata"
    bad.mkdir()
    (bad / "metadata.json").write_text("{not json", encoding="utf-8")

    books = bm.BookManager.get_books()
    assert books == []
