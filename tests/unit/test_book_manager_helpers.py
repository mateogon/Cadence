from system.book_manager import BookManager


def test_get_extract_worker_count_defaults_when_env_missing(monkeypatch):
    monkeypatch.delenv("CADENCE_EXTRACT_WORKERS", raising=False)
    value = BookManager._get_extract_worker_count()
    assert isinstance(value, int)
    assert value >= 1
    assert value <= 4


def test_get_extract_worker_count_clamps_to_min_one(monkeypatch):
    monkeypatch.setenv("CADENCE_EXTRACT_WORKERS", "0")
    assert BookManager._get_extract_worker_count() == 1


def test_get_extract_worker_count_ignores_invalid(monkeypatch):
    monkeypatch.delenv("CADENCE_EXTRACT_WORKERS", raising=False)
    fallback = BookManager._get_extract_worker_count()
    monkeypatch.setenv("CADENCE_EXTRACT_WORKERS", "abc")
    assert BookManager._get_extract_worker_count() == fallback


def test_get_tts_max_chunk_chars_defaults_and_floor(monkeypatch):
    monkeypatch.delenv("CADENCE_TTS_MAX_CHARS", raising=False)
    assert BookManager._get_tts_max_chunk_chars() == 800

    monkeypatch.setenv("CADENCE_TTS_MAX_CHARS", "100")
    assert BookManager._get_tts_max_chunk_chars() == 400


def test_get_whisperx_batch_size_defaults_and_validation(monkeypatch):
    monkeypatch.delenv("CADENCE_WHISPERX_BATCH_SIZE", raising=False)
    assert BookManager._get_whisperx_batch_size() == 16

    monkeypatch.setenv("CADENCE_WHISPERX_BATCH_SIZE", "8")
    assert BookManager._get_whisperx_batch_size() == 8

    monkeypatch.setenv("CADENCE_WHISPERX_BATCH_SIZE", "bad")
    assert BookManager._get_whisperx_batch_size() == 16


def test_get_calibre_executable_prefers_explicit_command(monkeypatch):
    monkeypatch.setenv("CADENCE_CALIBRE_PATH", "ebook-convert-custom")
    monkeypatch.setattr(
        "system.book_manager.shutil.which",
        lambda name: "/tmp/ebook-convert" if name == "ebook-convert-custom" else None,
    )
    assert BookManager._get_calibre_executable() == "/tmp/ebook-convert"


def test_get_calibre_executable_uses_default_path(monkeypatch, tmp_path):
    monkeypatch.delenv("CADENCE_CALIBRE_PATH", raising=False)
    calibre = tmp_path / "ebook-convert.exe"
    calibre.write_text("bin", encoding="utf-8")
    monkeypatch.setattr("system.book_manager.CALIBRE_PATH", str(calibre))
    monkeypatch.setattr("system.book_manager.shutil.which", lambda _name: None)
    assert BookManager._get_calibre_executable() == str(calibre)


def test_get_calibre_executable_returns_none_when_missing(monkeypatch):
    monkeypatch.setenv("CADENCE_CALIBRE_PATH", "/missing/ebook-convert.exe")
    monkeypatch.setattr("system.book_manager.shutil.which", lambda _name: None)
    assert BookManager._get_calibre_executable() is None


def test_normalize_source_to_epub_noop_for_epub(tmp_path):
    source = tmp_path / "book.epub"
    source.write_text("epub-bytes", encoding="utf-8")
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    epub_file, stored_name = BookManager._normalize_source_to_epub(
        source_file=source,
        source_ext=".epub",
        source_dir=source_dir,
        calibre_exe="ebook-convert",
        log=lambda _msg: None,
    )

    assert epub_file == source
    assert stored_name == "book.epub"


def test_finalize_metadata_sets_complete_status(tmp_path):
    book_dir = tmp_path / "Book"
    content_dir = book_dir / "content"
    audio_dir = book_dir / "audio"
    content_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)
    (content_dir / "ch_001.txt").write_text("hello", encoding="utf-8")
    (content_dir / "ch_001.json").write_text("[]", encoding="utf-8")
    (audio_dir / "ch_001.wav").write_bytes(b"RIFF....WAVEfmt ")

    metadata = {"title": "Book", "voice": "M3"}
    out = BookManager._finalize_metadata(book_dir, content_dir, audio_dir, metadata)

    assert out["status"] == "complete"
    assert out["total_chapters"] == 1
    assert out["last_chapter"] == 1


def test_resolve_book_target_for_new_source(tmp_path, monkeypatch):
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr("system.book_manager.LIBRARY_PATH", library)

    source = tmp_path / "My Book.epub"
    source.write_text("epub", encoding="utf-8")

    book_dir, book_name = BookManager._resolve_book_target(source)
    assert book_name == "My_Book"
    assert book_dir == library / "My_Book"


def test_resolve_book_target_for_stored_library_source(tmp_path, monkeypatch):
    library = tmp_path / "library"
    source_dir = library / "Book_A" / "source"
    source_dir.mkdir(parents=True)
    monkeypatch.setattr("system.book_manager.LIBRARY_PATH", library)

    source = source_dir / "Book_A.epub"
    source.write_text("epub", encoding="utf-8")

    book_dir, book_name = BookManager._resolve_book_target(source)
    assert book_name == "Book_A"
    assert book_dir == library / "Book_A"


def test_extract_chapter_texts_returns_none_on_unpack_failure(tmp_path, monkeypatch):
    content_dir = tmp_path / "content"
    content_dir.mkdir(parents=True)
    epub = tmp_path / "book.epub"
    epub.write_text("epub", encoding="utf-8")

    class _FailedRunResult:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr("system.book_manager.subprocess.run", lambda *args, **kwargs: _FailedRunResult())

    out = BookManager._extract_chapter_texts(
        epub_file=epub,
        content_dir=content_dir,
        calibre_exe="ebook-convert",
        is_cancelled=lambda: False,
        log=lambda _msg: None,
    )
    assert out is None


def test_tokenize_for_alignment_normalizes_curly_punctuation():
    tokens = BookManager.tokenize_for_alignment("Don’t stop — now")

    cleaned_words = [t["clean"] for t in tokens if t["clean"]]
    assert cleaned_words == ["dont", "stop", "now"]


def test_align_timestamps_exact_word_match_preserves_word_text():
    txt = "Hello world!"
    json_words = [
        {"word": "hello", "start": 0.0, "end": 0.3},
        {"word": "world", "start": 0.3, "end": 0.8},
    ]

    aligned = BookManager.align_timestamps(txt, json_words)

    assert [item["word"] for item in aligned] == ["Hello", " ", "world!"]
    assert aligned[0]["start"] == 0.0
    assert aligned[0]["end"] == 0.3
    assert aligned[2]["start"] == 0.3
    assert aligned[2]["end"] == 0.8


def test_align_timestamps_replace_block_distributes_times():
    txt = "alpha beta gamma"
    json_words = [
        {"word": "alpha", "start": 0.0, "end": 0.2},
        {"word": "delta", "start": 0.2, "end": 0.4},
        {"word": "gamma", "start": 0.4, "end": 0.6},
    ]

    aligned = BookManager.align_timestamps(txt, json_words)
    words = [item for item in aligned if item["word"].strip()]

    assert [w["word"] for w in words] == ["alpha", "beta", "gamma"]
    assert words[1]["start"] == 0.2
    assert words[1]["end"] == 0.4
