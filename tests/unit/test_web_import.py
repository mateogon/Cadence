import json
import time
import zipfile

import numpy as np
import pytest
import soundfile as sf

import system.book_manager as book_manager
import webui.api as web_api
import webui.importer as importer
from webui.api import Api
from webui.server import MediaServer

PARAGRAPH = "It was the best of times, it was the worst of times, it was the age of wisdom, it was the age of foolishness, and the house was quiet."


def _epub(path, language="en-GB"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("META-INF/container.xml", '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", f'''<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/">
          <metadata><dc:title>A Tale</dc:title><dc:creator>Charles Dickens</dc:creator><dc:language>{language}</dc:language></metadata>
          <manifest><item id="c1" href="c1.xhtml"/><item id="cov" href="cover.jpg" properties="cover-image"/></manifest>
          <spine><itemref idref="c1"/></spine></package>''')
        z.writestr("OEBPS/c1.xhtml", f"<html><body><h1>Chapter 1</h1><p>Short.</p><p>{PARAGRAPH}</p></body></html>")
        z.writestr("OEBPS/cover.jpg", b"\xff\xd8\xff fake jpeg")
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    library = tmp_path / "library"
    library.mkdir()
    for module in (book_manager, web_api, importer):
        monkeypatch.setattr(module, "LIBRARY_PATH", library)
    server = MediaServer(lambda: library.resolve()).start()
    yield tmp_path, Api(server)
    server.stop()


def test_preview_reads_metadata_cover_and_paragraphs(env):
    tmp, api = env
    info = api.preview(str(_epub(tmp / "A Tale.epub")))
    assert (info["title"], info["author"], info["language"]) == ("A Tale", "Charles Dickens", "en-GB")
    assert info["book_id"] == "A_Tale" and info["exists"] is False
    assert info["paragraphs"] == [PARAGRAPH]
    assert info["cover_url"].startswith(f"/media/{api._server.token}/.samples/covers/")
    with pytest.raises(ValueError):
        api.preview(str(tmp / "notes.txt"))


def test_preview_of_a_library_book_reports_its_stored_voice(env, monkeypatch):
    tmp, api = env
    monkeypatch.setattr(book_manager.BookManager, "import_book", staticmethod(lambda *args, **kwargs: True))
    book = book_manager.LIBRARY_PATH / "A_Tale"
    book.mkdir()
    (book / "metadata.json").write_text(json.dumps({"tts_backend": "supertonic", "tts_model": "supertonic-1", "voice": "F3"}))
    info = api.preview(str(_epub(tmp / "A Tale.epub")))
    assert info["exists"] is True
    assert info["stored"] == {"engine": "supertonic", "model": "supertonic-1", "voice": "F3"}
    assert api.start_import(info["path"], "supertonic", "F3", "supertonic-1") == "A_Tale"


def test_engines_follow_language_and_installation(env, monkeypatch):
    _, api = env
    monkeypatch.setattr(importer, "kokoro_installed", lambda: True)
    kokoro, supertonic = api.engines("en-GB")
    assert kokoro["available"] and kokoro["voices"][0]["id"] == "bf_emma"
    assert supertonic["available"] and {v["id"] for v in supertonic["voices"]} == {f"{g}{n}" for g in "FM" for n in range(1, 6)}
    assert api.engines("es")[0]["voices"][0]["id"] == "ef_dora"
    assert api.engines("de")[0]["available"] is False
    monkeypatch.setattr(importer, "kokoro_installed", lambda: False)
    assert "uv run --extra kokoro" in api.engines("en")[0]["reason"]


def test_import_job_passes_engine_and_model_to_the_pipeline(env, monkeypatch):
    tmp, api = env
    calls = []

    def fake_import(path, voice, progress, log_callback=None, cancel_check=None, backend=None, model=None):
        calls.append((path, voice, backend, model))
        progress(0.5, "Synthesizing")
        log_callback("halfway")
        return True

    monkeypatch.setattr(book_manager.BookManager, "import_book", staticmethod(fake_import))
    book = _epub(tmp / "A Tale.epub")
    api.preview(str(book))
    assert api.start_import(str(book), "supertonic", "F2", "supertonic-3") == "A_Tale"
    deadline = time.time() + 5
    while api.import_status()["state"] == "running" and time.time() < deadline:
        time.sleep(0.02)
    status = api.import_status()
    assert status["state"] == "done" and status["title"] == "A Tale" and status["log"] == ["halfway"]
    assert calls == [(str(book), "F2", "supertonic", "supertonic-3")]
    with pytest.raises(ValueError):
        api.start_import(str(book), "espeak", "x", None)
    with pytest.raises(ValueError):
        api.start_import(str(book), "supertonic", "F2", "supertonic-9")


def test_cancel_marks_the_import_stopped(env, monkeypatch):
    tmp, api = env

    def slow_import(path, voice, progress, log_callback=None, cancel_check=None, backend=None, model=None):
        while not cancel_check():
            time.sleep(0.01)
        return False

    monkeypatch.setattr(book_manager.BookManager, "import_book", staticmethod(slow_import))
    api.start_import(str(_epub(tmp / "A Tale.epub")), "kokoro", "af_heart", None)
    with pytest.raises(RuntimeError):
        api.start_import(str(tmp / "A Tale.epub"), "kokoro", "af_heart", None)
    api.cancel_import()
    deadline = time.time() + 5
    while api.import_status()["state"] == "running" and time.time() < deadline:
        time.sleep(0.02)
    assert api.import_status()["state"] == "cancelled"


def test_samples_are_synthesized_once_and_served(env, monkeypatch):
    _, api = env
    made = []

    class FakeBackend:
        def synthesize(self, text, voice, lang="na"):
            made.append((voice, lang, text))
            return np.zeros(2400, dtype=np.float32)

        def save_audio(self, audio, path):
            sf.write(path, audio, 24000)

    monkeypatch.setattr(importer.Samples, "_backend", lambda self, engine, model: FakeBackend())
    state = api.sample("kokoro", "af_heart", None, "en", PARAGRAPH)
    deadline = time.time() + 5
    while api.sample_state(state["key"])["state"] == "running" and time.time() < deadline:
        time.sleep(0.02)
    ready = api.sample_state(state["key"])
    assert ready["state"] == "ready" and ready["url"].startswith(f"/media/{api._server.token}/.samples/")
    assert api.sample("kokoro", "af_heart", None, "en", PARAGRAPH)["state"] == "ready"
    assert made == [("af_heart", "en", PARAGRAPH)]
    with pytest.raises(ValueError):
        api.sample("espeak", "x", None, "en", "hi")


def test_sample_folder_is_not_listed_as_a_book(env):
    _, api = env
    (book_manager.LIBRARY_PATH / ".samples").mkdir()
    assert api.books() == []


def test_library_covers_come_from_the_stored_source_epub(env):
    tmp, api = env
    book = book_manager.LIBRARY_PATH / "A_Tale"
    (book / "source").mkdir(parents=True)
    _epub(book / "source" / "A Tale.epub")
    (book / "metadata.json").write_text(json.dumps({"title": "A Tale", "cover": "OEBPS/cover.jpg"}))
    url = api.books()[0]["cover_url"]
    assert url.startswith(f"/media/{api._server.token}/.samples/covers/book-")
    assert url == api.books()[0]["cover_url"]
    (book / "metadata.json").write_text(json.dumps({"title": "A Tale", "cover": "OEBPS/missing.jpg"}))
    assert api.books()[0]["cover_url"] is None
