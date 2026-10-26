"""Functions the web reader calls from JavaScript (pywebview js_api).

Books and chapters come from the same library folders the Qt reader uses. Reading
positions use the Qt reader's keys in player_settings.json (book_positions,
book_positions_ms), so both readers resume at the same place. Settings that only the
web reader has live under the "web_reader" key.
"""

import json
import math
import os
import re
import tempfile
import threading
import time
from pathlib import Path

from system.book_manager import LIBRARY_PATH, BookManager

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
        cover = str(meta.get("cover") or "").strip()
        if not cover:
            return None
        path = (folder / cover).resolve()
        return self._server.media_url(path) if path.is_file() else None

    @staticmethod
    def _duration(wav):
        try:
            import soundfile
            return round(soundfile.info(str(wav)).duration, 1)
        except Exception:
            return None
