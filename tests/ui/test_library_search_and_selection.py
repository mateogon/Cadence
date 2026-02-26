import json

import qt.main_window as mw


def _build_window(monkeypatch, books, stub_chapter_selected=True):
    monkeypatch.setattr(mw.BookManager, "get_books", staticmethod(lambda: list(books)))
    monkeypatch.setattr(mw.MainWindow, "_apply_profile_card_shadows", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_apply_profile_button_depths", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_apply_profile_header_theme", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_apply_player_settings", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_init_media_player", lambda self: None)
    monkeypatch.setattr(mw.MainWindow, "_layout_bottom_cap_divider", lambda self: None)
    if stub_chapter_selected:
        monkeypatch.setattr(mw.MainWindow, "_on_player_chapter_selected", lambda self, row: None)
    return mw.MainWindow(debug=False)


def _layout_cards(window):
    cards = []
    for i in range(window.books_layout.count()):
        item = window.books_layout.itemAt(i)
        widget = item.widget() if item is not None else None
        if isinstance(widget, mw.BookCard):
            cards.append(widget)
    return cards


def test_refresh_library_filters_by_title(qapp, monkeypatch):
    books = [
        {
            "title": "Dune",
            "path": "library/Dune",
            "is_incomplete": False,
            "last_chapter": 1,
            "total_chapters": 1,
            "content_chapters": 1,
            "audio_chapters_ready": 1,
            "aligned_chapters_ready": 1,
        },
        {
            "title": "The Hobbit",
            "path": "library/The_Hobbit",
            "is_incomplete": False,
            "last_chapter": 1,
            "total_chapters": 1,
            "content_chapters": 1,
            "audio_chapters_ready": 1,
            "aligned_chapters_ready": 1,
        },
    ]
    window = _build_window(monkeypatch, books)

    window.search.setText("hob")
    window.refresh_library()

    cards = _layout_cards(window)
    assert len(cards) == 1
    assert cards[0].book["title"] == "The Hobbit"

    window.close()


def test_refresh_library_filters_by_author_and_voice(qapp, monkeypatch):
    books = [
        {
            "title": "Dune",
            "author": "Frank Herbert",
            "voice": "M3",
            "path": "library/Dune",
            "is_incomplete": False,
            "last_chapter": 1,
            "total_chapters": 1,
            "content_chapters": 1,
            "audio_chapters_ready": 1,
            "aligned_chapters_ready": 1,
        },
        {
            "title": "Project Hail Mary",
            "author": "Andy Weir",
            "voice": "F1",
            "path": "library/Project_Hail_Mary",
            "is_incomplete": False,
            "last_chapter": 1,
            "total_chapters": 1,
            "content_chapters": 1,
            "audio_chapters_ready": 1,
            "aligned_chapters_ready": 1,
        },
    ]
    window = _build_window(monkeypatch, books)

    window.search.setText("weir")
    window.refresh_library()
    cards = _layout_cards(window)
    assert len(cards) == 1
    assert cards[0].book["title"] == "Project Hail Mary"

    window.search.setText("m3")
    window.refresh_library()
    cards = _layout_cards(window)
    assert len(cards) == 1
    assert cards[0].book["title"] == "Dune"

    window.close()


def test_refresh_library_prioritizes_incomplete_books(qapp, monkeypatch):
    books = [
        {
            "title": "Complete Book",
            "path": "library/complete",
            "is_incomplete": False,
            "last_chapter": 2,
            "total_chapters": 2,
            "content_chapters": 2,
            "audio_chapters_ready": 2,
            "aligned_chapters_ready": 2,
        },
        {
            "title": "Incomplete Book",
            "path": "library/incomplete",
            "is_incomplete": True,
            "last_chapter": 1,
            "total_chapters": 2,
            "content_chapters": 2,
            "audio_chapters_ready": 1,
            "aligned_chapters_ready": 1,
        },
    ]
    window = _build_window(monkeypatch, books)

    window.refresh_library()
    cards = _layout_cards(window)

    assert len(cards) == 2
    assert cards[0].book["title"] == "Incomplete Book"
    assert cards[1].book["title"] == "Complete Book"

    window.close()


def test_refresh_library_filter_dropdown_incomplete_complete(qapp, monkeypatch):
    books = [
        {
            "title": "Complete Book",
            "path": "library/complete",
            "is_incomplete": False,
            "last_chapter": 2,
            "total_chapters": 2,
            "content_chapters": 2,
            "audio_chapters_ready": 2,
            "aligned_chapters_ready": 2,
        },
        {
            "title": "Incomplete Book",
            "path": "library/incomplete",
            "is_incomplete": True,
            "last_chapter": 1,
            "total_chapters": 2,
            "content_chapters": 2,
            "audio_chapters_ready": 1,
            "aligned_chapters_ready": 1,
        },
    ]
    window = _build_window(monkeypatch, books)

    window.library_filter.setCurrentText("Incomplete")
    window.refresh_library()
    cards = _layout_cards(window)
    assert len(cards) == 1
    assert cards[0].book["title"] == "Incomplete Book"

    window.library_filter.setCurrentText("Complete")
    window.refresh_library()
    cards = _layout_cards(window)
    assert len(cards) == 1
    assert cards[0].book["title"] == "Complete Book"

    window.close()


def test_book_card_meta_shows_read_and_ready_progress(qapp):
    book = {
        "title": "Progress Book",
        "path": "library/progress",
        "is_incomplete": False,
        "last_chapter": 5,
        "resume_chapter": 3,
        "total_chapters": 6,
        "content_chapters": 6,
        "audio_chapters_ready": 6,
        "aligned_chapters_ready": 5,
        "voice": "M3",
    }

    card = mw.BookCard(book)
    labels = [w.text() for w in card.findChildren(mw.QtWidgets.QLabel)]
    assert any("Read Ch 3/6" in text for text in labels)
    assert any("Ready Ch 5/6" in text for text in labels)
    card.deleteLater()


def test_open_player_page_selects_last_chapter(qapp, monkeypatch, tmp_path):
    book_dir = tmp_path / "Sample_Book"
    content = book_dir / "content"
    content.mkdir(parents=True)
    (content / "ch_001.txt").write_text("chapter 1", encoding="utf-8")
    (content / "ch_002.txt").write_text("chapter 2", encoding="utf-8")

    window = _build_window(monkeypatch, books=[])

    book = {
        "title": "Sample Book",
        "path": str(book_dir),
        "last_chapter": 2,
        "total_chapters": 2,
    }
    window.open_player_page(book)

    assert window.player_chapter_list.count() == 2
    assert window.player_chapter_list.currentRow() == 1
    assert window.player_chapter_meta.text() == "Chapter 2/2"
    assert window.view_stack.currentWidget() is window.player_page

    window.close()


def test_open_player_page_prefers_saved_book_position(qapp, monkeypatch, tmp_path):
    settings_file = tmp_path / "player_settings.json"
    book_dir = tmp_path / "Saved_Book"
    content = book_dir / "content"
    content.mkdir(parents=True)
    (content / "ch_001.txt").write_text("chapter 1", encoding="utf-8")
    (content / "ch_002.txt").write_text("chapter 2", encoding="utf-8")
    (content / "ch_003.txt").write_text("chapter 3", encoding="utf-8")

    book_path_key = str(book_dir.resolve())
    settings_file.write_text(
        json.dumps(
            {
                "reading_view_mode": "context",
                "book_positions": {book_path_key: 3},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(mw, "PLAYER_SETTINGS_FILE", settings_file)

    window = _build_window(monkeypatch, books=[])

    book = {
        "title": "Saved Book",
        "path": str(book_dir),
        "last_chapter": 1,
        "total_chapters": 3,
    }
    window.open_player_page(book)

    assert window.player_chapter_list.currentRow() == 2
    assert window.player_chapter_meta.text() == "Chapter 3/3"

    window.close()


def test_chapter_selection_persists_book_position(qapp, monkeypatch, tmp_path):
    settings_file = tmp_path / "player_settings.json"
    monkeypatch.setattr(mw, "PLAYER_SETTINGS_FILE", settings_file)

    book_dir = tmp_path / "Resume_Book"
    content = book_dir / "content"
    content.mkdir(parents=True)
    (content / "ch_001.txt").write_text("chapter 1", encoding="utf-8")
    (content / "ch_002.txt").write_text("chapter 2", encoding="utf-8")

    window = _build_window(monkeypatch, books=[], stub_chapter_selected=False)
    window.open_player_page(
        {
            "title": "Resume Book",
            "path": str(book_dir),
            "last_chapter": 1,
            "total_chapters": 2,
        }
    )

    window.player_chapter_list.setCurrentRow(1)

    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    key = str(book_dir.resolve())
    assert int(saved.get("book_positions", {}).get(key, 0) or 0) == 2

    window.close()


def test_save_and_get_book_resume_position_ms(qapp, monkeypatch, tmp_path):
    settings_file = tmp_path / "player_settings.json"
    monkeypatch.setattr(mw, "PLAYER_SETTINGS_FILE", settings_file)
    window = _build_window(monkeypatch, books=[])

    book_dir = tmp_path / "Book"
    book_dir.mkdir()
    book = {"title": "Book", "path": str(book_dir)}
    window._active_book = dict(book)

    window._save_book_resume_position_ms("ch_001", 4567, force=True)
    value = window._get_book_resume_position_ms(book, "ch_001")

    assert value == 4567
    saved = settings_file.read_text(encoding="utf-8")
    assert '"book_positions_ms"' in saved
    assert "4567" in saved

    window.close()


def test_restore_chapter_position_updates_seek_and_offsets(qapp, monkeypatch, tmp_path):
    settings_file = tmp_path / "player_settings.json"
    monkeypatch.setattr(mw, "PLAYER_SETTINGS_FILE", settings_file)
    window = _build_window(monkeypatch, books=[])

    book_dir = tmp_path / "Book"
    book_dir.mkdir()
    book = {"title": "Book", "path": str(book_dir)}
    window._active_book = dict(book)
    key = str(book_dir.resolve())
    window._player_settings["book_positions_ms"] = {key: {"ch_001": 2500}}
    window._audio_backend = "pygame"
    window._player_duration_ms = 10000

    window._restore_chapter_position("ch_001")

    assert window._pygame_last_pos_ms == 2500
    assert window.player_seek.value() == 250
    assert window.player_time_meta.text().startswith("00:02")

    window.close()
