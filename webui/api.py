"""Functions the web reader calls from JavaScript (pywebview js_api).

Books and chapters come from the same library folders the Qt reader uses. Reading
positions use the Qt reader's keys in player_settings.json (book_positions,
book_positions_ms), so both readers resume at the same place. Settings that only the
web reader has live under the "web_reader" key.
"""

import hashlib
import json
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from system.book_manager import LIBRARY_PATH, BookManager
from webui import importer

PLAYER_SETTINGS_FILE = Path("player_settings.json")
WEB_DEFAULTS = {
    "view": "study", "theme": "light", "font_size": 20, "line_height": 1.75,
    "playback_speed": 1.0, "sync_offset_ms": 0, "volume": 1.0,
}
VIEWS = {"study", "page", "focus", "rsvp"}
THEMES = {"light", "sepia", "dark"}
_lock = threading.Lock()


def _load_player_settings():
    try:
        data = json.loads(PLAYER_SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_player_settings(data):
    path = PLAYER_SETTINGS_FILE.resolve()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False,
                                         prefix=".player_settings.", suffix=".tmp") as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, indent=4, ensure_ascii=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _title_from_text(text):
    """A short first line is the chapter heading in Calibre's output."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= 80 and not line.endswith((".", ",", ";")) else None
    return None


class Api:
    def __init__(self, server):
        self._server = server
        self._window = None
        self._samples = importer.Samples()
        self._imports = importer.ImportJob()
        self._previews = {}

    # --- import -------------------------------------------------------------------

    def choose_file(self):
        import webview
        paths = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("Books (*.epub;*.mobi;*.azw3)",))
        return self.preview(paths[0]) if paths else None

    def preview(self, path):
        info = importer.preview(path)
        cover_bytes = info.pop("cover_bytes", None)
        info["cover_url"] = None
        if cover_bytes:
            info["cover_url"] = self._server.media_url(self._store_cover(cover_bytes, info["cover"]))
        if not info["paragraphs"]:
            info["paragraphs"] = [importer.FALLBACK_SAMPLE]
        self._previews[info["path"]] = info
        return info

    def engines(self, language):
        return importer.engines(str(language or ""))

    def sample(self, engine, voice, model, language, text):
        if engine not in {"kokoro", "supertonic"}:
            raise ValueError("Unknown engine.")
        return self._sample_view(self._samples.request(engine, str(voice), model, str(language or ""), text))

    def sample_state(self, key):
        state = self._samples.state(str(key))
        return self._sample_view(state) if state else None

    def _sample_view(self, state):
        view = {"key": state["key"], "state": state["state"], "error": state.get("error")}
        if state["state"] == "ready":
            view["url"] = self._server.media_url(state["path"])
        return view

    def start_import(self, path, engine, voice, model):
        if engine not in {"kokoro", "supertonic"}:
            raise ValueError("Unknown engine.")
        preview = self._previews.get(str(path)) or {}
        # A book already in the library resumes with its stored model, which may predate the current list.
        if engine == "supertonic" and model not in importer.SUPERTONIC_MODELS and not preview.get("exists"):
            raise ValueError("Unknown Supertonic model.")
        title = preview.get("title")
        return self._imports.start(str(path), engine, str(voice), model if engine == "supertonic" else None, title)

    def import_status(self):
        return self._imports.status()

    def cancel_import(self):
        self._imports.cancel()

    # --- library ------------------------------------------------------------------

    def books(self):
        settings = _load_player_settings()
        positions = settings.get("book_positions", {}) if isinstance(settings.get("book_positions"), dict) else {}
        result = []
        for book in BookManager.get_books():
            folder = Path(book["path"])
            total = int(book.get("content_chapters") or 0)
            ready = min(int(book.get("audio_chapters_ready") or 0), int(book.get("aligned_chapters_ready") or 0))
            result.append({
                "id": folder.name,
                "title": book.get("title") or folder.name,
                "author": book.get("author") or "",
                "language": book.get("language") or "",
                "voice": book.get("voice") or "",
                "backend": book.get("tts_backend") or "supertonic",
                "chapters": total, "ready": ready,
                "current_chapter": int(positions.get(str(folder.resolve()), 0) or 0),
                "cover_url": self._cover_url(folder, book),
                "modified": folder.stat().st_mtime,
            })
        return sorted(result, key=lambda item: item["modified"], reverse=True)

    def book(self, book_id):
        folder = self._book_dir(book_id)
        meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        settings = _load_player_settings()
        key = str(folder.resolve())
        chapters = []
        for index, txt in enumerate(sorted((folder / "content").glob("ch_*.txt")), 1):
            wav = folder / "audio" / f"{txt.stem}.wav"
            alignment = folder / "content" / f"{txt.stem}.json"
            ready = wav.is_file() and wav.stat().st_size > 0 and alignment.is_file() and alignment.stat().st_size > 0
            with open(txt, encoding="utf-8") as handle:
                head = handle.read(400)
            chapters.append({
                "stem": txt.stem, "number": index, "ready": ready,
                "title": _title_from_text(head) or f"Chapter {index}",
                "seconds": self._duration(wav) if ready else None,
            })
        positions_ms = settings.get("book_positions_ms", {}).get(key, {}) if isinstance(settings.get("book_positions_ms"), dict) else {}
        resume = int((settings.get("book_positions") or {}).get(key, 0) or 0)
        return {
            "id": folder.name, "title": meta.get("title") or folder.name, "author": meta.get("author") or "",
            "language": meta.get("language") or "", "voice": meta.get("voice") or "",
            "backend": meta.get("tts_backend") or "supertonic", "model": meta.get("tts_model") or "",
            "status": meta.get("status") or "", "cover_url": self._cover_url(folder, meta),
            "chapters": chapters, "resume_chapter": resume if 1 <= resume <= len(chapters) else 1,
            "resume_ms": {stem: int(value) for stem, value in positions_ms.items() if isinstance(value, (int, float))},
        }

    def chapter(self, book_id, stem):
        folder = self._book_dir(book_id)
        if not re.fullmatch(r"ch_\d+", str(stem)):
            raise ValueError("Invalid chapter.")
        alignment = folder / "content" / f"{stem}.json"
        wav = folder / "audio" / f"{stem}.wav"
        if not alignment.is_file() or not wav.is_file():
            raise FileNotFoundError("This chapter is not ready yet.")
        tokens = json.loads(alignment.read_text(encoding="utf-8"))
        clean = []
        for token in tokens:
            word = str(token.get("word", ""))
            start, end = token.get("start"), token.get("end")
            timed = isinstance(start, (int, float)) and isinstance(end, (int, float)) and math.isfinite(start)
            clean.append([word, round(float(start), 3) if timed else None, round(float(end), 3) if timed else None])
        return {"tokens": clean, "audio_url": self._server.media_url(wav)}

    def save_position(self, book_id, stem, position_ms, chapter_number):
        folder = self._book_dir(book_id)
        if not re.fullmatch(r"ch_\d+", str(stem)):
            raise ValueError("Invalid chapter.")
        key = str(folder.resolve())
        with _lock:
            settings = _load_player_settings()
            positions = settings.get("book_positions") if isinstance(settings.get("book_positions"), dict) else {}
            positions[key] = max(1, int(chapter_number))
            by_book = settings.get("book_positions_ms") if isinstance(settings.get("book_positions_ms"), dict) else {}
            chapters = by_book.get(key) if isinstance(by_book.get(key), dict) else {}
            chapters[str(stem)] = max(0, int(position_ms))
            by_book[key] = chapters
            settings["book_positions"], settings["book_positions_ms"] = positions, by_book
            _save_player_settings(settings)

    # --- reader settings ------------------------------------------------------------

    def settings(self):
        stored = _load_player_settings().get("web_reader")
        return dict(WEB_DEFAULTS, **(stored if isinstance(stored, dict) else {}))

    def save_settings(self, changes):
        changes = dict(changes)
        if "view" in changes and changes["view"] not in VIEWS:
            raise ValueError("Unknown view.")
        if "theme" in changes and changes["theme"] not in THEMES:
            raise ValueError("Unknown theme.")
        limits = {"font_size": (14, 36), "line_height": (1.3, 2.2), "playback_speed": (0.5, 2.5),
                  "sync_offset_ms": (-500, 500), "volume": (0, 1)}
        for name, (low, high) in limits.items():
            if name in changes:
                value = float(changes[name])
                if not math.isfinite(value) or not low <= value <= high:
                    raise ValueError(f"{name} must be between {low} and {high}.")
                changes[name] = value
        unknown = set(changes) - set(WEB_DEFAULTS)
        if unknown:
            raise ValueError(f"Unknown settings: {sorted(unknown)}")
        with _lock:
            settings = _load_player_settings()
            current = settings.get("web_reader") if isinstance(settings.get("web_reader"), dict) else {}
            current.update(changes)
            settings["web_reader"] = current
            _save_player_settings(settings)
        return self.settings()

    def report_sync(self, stats):
        """Write highlight timing samples when CADENCE_SYNC_LOG names a file (measurement only)."""
        target = os.getenv("CADENCE_SYNC_LOG", "").strip()
        if not target:
            return False
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(dict(stats, time=time.time())) + "\n")
        return True

    # --- helpers --------------------------------------------------------------------

    def _book_dir(self, book_id):
        root = LIBRARY_PATH.resolve()
        folder = (root / str(book_id)).resolve()
        if folder.parent != root or not (folder / "metadata.json").is_file():
            raise ValueError("Unknown book.")
        return folder

    def _cover_url(self, folder, meta):
        """metadata.json stores the cover's path inside the source EPUB; serve a cached copy of it."""
        cover = str(meta.get("cover") or "").strip()
        if not cover:
            return None
        path = (folder / cover).resolve()
        if path.is_file() and path.is_relative_to(folder):
            return self._server.media_url(path)
        cached = LIBRARY_PATH / ".samples" / "covers" / f"book-{hashlib.sha256(f'{folder.name}|{cover}'.encode()).hexdigest()[:16]}{Path(cover).suffix.lower()}"
        if not cached.is_file():
            data = importer.cover_from_source(folder / "source", cover)
            if not data:
                return None
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(data)
        return self._server.media_url(cached)

    @staticmethod
    def _store_cover(data, name):
        suffix = Path(name).suffix.lower() or ".jpg"
        target = LIBRARY_PATH / ".samples" / "covers" / (hashlib.sha256(data).hexdigest()[:16] + suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        return target

    @staticmethod
    def _duration(wav):
        try:
            import soundfile
            return round(soundfile.info(str(wav)).duration, 1)
        except Exception:
            return None
