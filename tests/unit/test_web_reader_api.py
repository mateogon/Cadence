import json
import urllib.error
import urllib.request

import numpy as np
import pytest
import soundfile as sf

import system.book_manager as book_manager
import webui.api as web_api
from webui.api import Api
from webui.server import MediaServer


def _make_book(library, name="book", chapters=2, title="A test book"):
    folder = library / name
    (folder / "content").mkdir(parents=True)
    (folder / "audio").mkdir()
    (folder / "metadata.json").write_text(json.dumps({
        "title": title, "author": "Someone", "language": "en", "voice": "af_heart",
        "tts_backend": "kokoro", "status": "complete", "chapters": chapters, "total_chapters": chapters,
    }))
    for n in range(1, chapters + 1):
        stem = f"ch_{n:03d}"
        (folder / "content" / f"{stem}.txt").write_text(f"Heading {n}\n\nHello world.", encoding="utf-8")
        tokens = [{"word": f"Heading {n}", "start": 0.0, "end": 0.4}, {"word": "\n\n", "start": 0.4, "end": 0.4},
                  {"word": "Hello", "start": 0.5, "end": 0.8}, {"word": " ", "start": 0.8, "end": 0.8},
                  {"word": "world.", "start": 0.8, "end": 1.2}]
        (folder / "content" / f"{stem}.json").write_text(json.dumps(tokens))
        sf.write(folder / "audio" / f"{stem}.wav", np.zeros(24000 * 2, dtype=np.float32), 24000)
    return folder


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    monkeypatch.setattr(book_manager, "LIBRARY_PATH", library)
    monkeypatch.setattr(web_api, "LIBRARY_PATH", library)
    server = MediaServer(lambda: library.resolve()).start()
    yield library, Api(server), server
    server.stop()


def test_books_and_chapters_come_from_library(env):
    library, api, _ = env
    _make_book(library)
    [book] = api.books()
    assert book["id"] == "book" and book["chapters"] == 2 and book["ready"] == 2
    detail = api.book("book")
    assert [c["title"] for c in detail["chapters"]] == ["Heading 1", "Heading 2"]
    assert detail["chapters"][0]["seconds"] == 2.0 and detail["resume_chapter"] == 1
    chapter = api.chapter("book", "ch_001")
    assert chapter["tokens"][2] == ["Hello", 0.5, 0.8]
    assert chapter["audio_url"].startswith(f"/media/{api._server.token}/book/audio/ch_001.wav")


def test_positions_use_the_qt_reader_keys(env):
    library, api, _ = env
    folder = _make_book(library)
    api.save_position("book", "ch_002", 1500, 2)
    settings = json.loads((library.parent / "player_settings.json").read_text())
    key = str(folder.resolve())
    assert settings["book_positions"][key] == 2
    assert settings["book_positions_ms"][key]["ch_002"] == 1500
    detail = api.book("book")
    assert detail["resume_chapter"] == 2 and detail["resume_ms"]["ch_002"] == 1500


def test_saving_positions_keeps_other_qt_settings(env):
    library, api, _ = env
    _make_book(library)
    (library.parent / "player_settings.json").write_text(json.dumps({"font_family": "Arial", "sync_offset": 0.1}))
    api.save_position("book", "ch_001", 10, 1)
    api.save_settings({"view": "focus", "theme": "sepia"})
    settings = json.loads((library.parent / "player_settings.json").read_text())
    assert settings["font_family"] == "Arial" and settings["sync_offset"] == 0.1
    assert settings["web_reader"] == {"view": "focus", "theme": "sepia"}
    assert api.settings()["view"] == "focus" and api.settings()["font_size"] == 20


@pytest.mark.parametrize("changes", [{"view": "grid"}, {"theme": "neon"}, {"font_size": 90},
                                     {"sync_offset_ms": 9000}, {"unknown": 1}])
def test_invalid_settings_are_rejected(env, changes):
    _, api, _ = env
    with pytest.raises(ValueError):
        api.save_settings(changes)


def test_unknown_books_and_chapters_are_rejected(env):
    library, api, _ = env
    _make_book(library)
    for book_id in ("../outside", "missing", ""):
        with pytest.raises(ValueError):
            api.book(book_id)
    with pytest.raises(ValueError):
        api.chapter("book", "../metadata")
    (library / "book" / "audio" / "ch_002.wav").unlink()
    assert api.book("book")["chapters"][1]["ready"] is False
    with pytest.raises(FileNotFoundError):
        api.chapter("book", "ch_002")


def test_media_server_requires_token_and_supports_range(env):
    library, api, server = env
    _make_book(library)
    url = f"http://127.0.0.1:{server.port}" + api.chapter("book", "ch_001")["audio_url"]
    request = urllib.request.Request(url, headers={"Range": "bytes=0-9"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 206 and len(response.read()) == 10
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(url.replace(server.token, "wrong"), timeout=5)
    assert error.value.code == 403


def test_sync_report_is_written_only_when_requested(env, tmp_path, monkeypatch):
    _, api, _ = env
    assert api.report_sync({"n": 1}) is False
    log = tmp_path / "sync.jsonl"
    monkeypatch.setenv("CADENCE_SYNC_LOG", str(log))
    assert api.report_sync({"n": 1, "median_ms": 5}) is True
    assert json.loads(log.read_text().splitlines()[0])["median_ms"] == 5
