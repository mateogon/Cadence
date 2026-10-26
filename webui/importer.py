"""Import support for the web reader: book preview, engines and voices, samples, import jobs.

The import itself is BookManager.import_book, the same pipeline the Qt app runs.
"""

import hashlib
import importlib.util
import json
import re
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath

from system.book_manager import LIBRARY_PATH, BookManager

SUPPORTED = {".epub", ".mobi", ".azw3"}
SUPERTONIC_MODELS = ["supertonic-3", "supertonic-2"]
KOKORO_ACCENTS = {"a": "US English", "b": "UK English", "e": "Spanish", "f": "French", "h": "Hindi",
                  "i": "Italian", "j": "Japanese", "p": "Portuguese", "z": "Chinese"}
# Quality grades from Kokoro's VOICES.md; voices without a published grade are omitted.
KOKORO_GRADES = {
    "af_heart": "A", "af_bella": "A-", "af_nicole": "B-", "af_aoede": "C+", "af_kore": "C+", "af_sarah": "C+",
    "af_alloy": "C", "af_nova": "C", "af_sky": "C-", "am_fenrir": "C+", "am_michael": "C+", "am_puck": "C+",
    "bf_emma": "B-", "bf_isabella": "C", "bm_fable": "C", "bm_george": "C", "bm_lewis": "D+", "ff_siwis": "B-",
    "hf_alpha": "C", "hf_beta": "C", "hm_omega": "C", "hm_psi": "C", "if_sara": "C", "im_nicola": "C",
    "jf_alpha": "C+", "jf_gongitsune": "C", "jf_tebukuro": "C",
}
FALLBACK_SAMPLE = "This is how this voice will read your book."


class _Paragraphs(HTMLParser):
    """Collect the text of <p> elements from one XHTML document."""

    def __init__(self):
        super().__init__()
        self.depth = 0
        self.current = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            self.depth += 1
            self.current = []

    def handle_endtag(self, tag):
        if tag == "p" and self.depth:
            self.depth -= 1
            text = " ".join("".join(self.current).split())
            if text:
                self.paragraphs.append(text)

    def handle_data(self, data):
        if self.depth:
            self.current.append(data)


def base_language(tag):
    return (tag or "").strip().lower().replace("_", "-").split("-")[0]


def preview(path):
    """Read title, author, language, cover and sample paragraphs without importing."""
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED or not source.is_file():
        raise ValueError("Choose an EPUB, MOBI or AZW3 file.")
    info = {"path": str(source), "file": source.name, "book_id": source.stem.replace(" ", "_"),
            "title": source.stem.replace("_", " "), "author": "", "language": "", "paragraphs": [], "cover": None}
    metadata_path = LIBRARY_PATH / info["book_id"] / "metadata.json"
    info["exists"] = metadata_path.is_file()
    if info["exists"]:
        # import_book resumes an existing book with its stored engine, model and voice.
        stored = json.loads(metadata_path.read_text(encoding="utf-8"))
        info["stored"] = {"engine": stored.get("tts_backend") or "supertonic", "model": stored.get("tts_model") or None,
                          "voice": stored.get("voice") or None}
    if source.suffix.lower() != ".epub":
        return info  # MOBI/AZW3 need Calibre; the import converts them.
    with zipfile.ZipFile(source) as archive:
        container = ET.fromstring(archive.read("META-INF/container.xml"))
        opf_path = container.find(".//{*}rootfile").get("full-path")
        opf_text = archive.read(opf_path).decode("utf-8", errors="replace")
        root = ET.fromstring(re.sub(r' xmlns="[^"]+"', "", opf_text, count=1))
        manifest = {item.get("id"): item.get("href") for item in root.findall(".//manifest/item")}
        meta = BookManager._extract_opf_metadata(root, manifest)
        info.update(title=meta["title"] or info["title"], author=meta["author"], language=meta["language"])
        opf_dir = PurePosixPath(opf_path).parent
        if meta["cover"]:
            info["cover"] = str(opf_dir / meta["cover"])
            try:
                info["cover_bytes"] = archive.read(info["cover"])
            except KeyError:
                info["cover"] = None
        names = set(archive.namelist())
        for idref in [ref.get("idref") for ref in root.findall(".//spine/itemref")]:
            href = manifest.get(idref)
            member = str(opf_dir / href) if href else None
            if not member or member not in names:
                continue
            parser = _Paragraphs()
            parser.feed(archive.read(member).decode("utf-8", errors="replace"))
            info["paragraphs"].extend(p for p in parser.paragraphs if 25 <= len(p.split()) <= 80)
            if len(info["paragraphs"]) >= 12:
                break
    return info


def kokoro_installed():
    return importlib.util.find_spec("kokoro") is not None


def engines(language):
    """Engines that can read this language, with their voices; the first voice is the default."""
    from adapters.kokoro_backend import KokoroBackend

    base = base_language(language) or "en"
    result = []
    kokoro = {"id": "kokoro", "name": "Kokoro", "models": [],
              "summary": "Natural voices. Word timing comes from the voice, so chapters are ready sooner."}
    if not kokoro_installed():
        kokoro.update(available=False, reason="Not installed. Start Cadence with: uv run --extra kokoro --extra web main.py --web")
    else:
        backend = KokoroBackend()
        ids = backend.list_voices(language or "en")
        if not ids:
            kokoro.update(available=False, reason="Kokoro has no voices for this language.")
        else:
            default = backend.default_voice(language or "en")
            ids = [default] + [v for v in ids if v != default]
            kokoro.update(available=True, voices=[_kokoro_voice(v) for v in ids])
    result.append(kokoro)

    from supertonic.config import AVAILABLE_LANGUAGES

    supported = base in AVAILABLE_LANGUAGES
    supertonic = {"id": "supertonic", "name": "Supertonic 3", "models": SUPERTONIC_MODELS,
                  "summary": "31 languages. Word timing is measured after synthesis with WhisperX.",
                  "available": True, "voices": [_supertonic_voice(v) for v in SUPERTONIC_VOICES]}
    if not supported:
        supertonic["summary"] += " This language is read with the generic setting."
    result.append(supertonic)
    return result


# Supertonic 1.3 ships these style names; listing them must not load the model.
SUPERTONIC_VOICES = ["M3", "F1", "F2", "F3", "F4", "F5", "M1", "M2", "M4", "M5"]


def _kokoro_voice(voice_id):
    name = voice_id.split("_", 1)[1].replace("_", " ").title()
    gender = "female" if voice_id[1] == "f" else "male"
    return {"id": voice_id, "name": name, "detail": f"{KOKORO_ACCENTS.get(voice_id[0], '')} · {gender}",
            "grade": KOKORO_GRADES.get(voice_id)}


def _supertonic_voice(voice_id):
    gender = "Female" if voice_id.startswith("F") else "Male"
    return {"id": voice_id, "name": f"{gender} {voice_id[1:]}", "detail": voice_id, "grade": None}


class Samples:
    """Short voice samples of the book's own text, cached on disk inside the library."""

    def __init__(self):
        self.folder = LIBRARY_PATH / ".samples"
        self._state = {}
        self._backends = {}
        self._lock = threading.Lock()
        self._synth_lock = threading.Lock()

    def request(self, engine, voice, model, language, text):
        text = " ".join(str(text).split())[:500] or FALLBACK_SAMPLE
        key = hashlib.sha256(f"{engine}|{model}|{voice}|{language}|{text}".encode()).hexdigest()[:16]
        path = self.folder / f"{key}.wav"
        with self._lock:
            if path.is_file():
                self._state[key] = {"state": "ready", "path": path}
            elif self._state.get(key, {}).get("state") not in {"running", "ready"}:
                self._state[key] = {"state": "running", "path": path}
                threading.Thread(target=self._make, args=(key, engine, voice, model, language, text, path),
                                 daemon=True).start()
            return dict(self._state[key], key=key)

    def state(self, key):
        with self._lock:
            state = self._state.get(key)
            return dict(state, key=key) if state else None

    def _make(self, key, engine, voice, model, language, text, path):
        try:
            with self._synth_lock:
                backend = self._backend(engine, model)
                result = backend.synthesize(text, voice, lang=language or "na")
                audio = getattr(result, "audio", result)
                if audio is None:
                    raise RuntimeError("The voice produced no audio for this text.")
                self.folder.mkdir(parents=True, exist_ok=True)
                backend.save_audio(audio, str(path))
            with self._lock:
                self._state[key] = {"state": "ready", "path": path}
        except Exception as error:
            with self._lock:
                self._state[key] = {"state": "error", "error": str(error)}

    def _backend(self, engine, model):
        from adapters.tts_factory import create_backend

        cache_key = (engine, model)
        if cache_key not in self._backends:
            backend = create_backend(engine, model=model or None)
            backend.ensure_model()
            self._backends[cache_key] = backend
        return self._backends[cache_key]


class ImportJob:
    """One import at a time, run by BookManager.import_book on a background thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self._job = None
        self._cancel = threading.Event()

    def start(self, path, engine, voice, model, title):
        with self._lock:
            if self._job and self._job["state"] == "running":
                raise RuntimeError("Another book is importing. Wait for it or stop it first.")
            source = Path(path)
            if source.suffix.lower() not in SUPPORTED or not source.is_file():
                raise ValueError("Choose an EPUB, MOBI or AZW3 file.")
            self._cancel.clear()
            self._job = {"book_id": source.stem.replace(" ", "_"), "title": title or source.stem, "engine": engine,
                         "voice": voice, "state": "running", "progress": 0.0, "message": "Starting…",
                         "log": [], "started": time.time()}
            threading.Thread(target=self._run, args=(source, engine, voice, model), daemon=True).start()
            return self._job["book_id"]

    def status(self):
        with self._lock:
            if not self._job:
                return None
            job = dict(self._job)
            job["log"] = job["log"][-8:]
            return job

    def cancel(self):
        self._cancel.set()

    def _run(self, source, engine, voice, model):
        def progress(fraction, message):
            with self._lock:
                self._job.update(progress=float(fraction), message=str(message))

        def log(message):
            with self._lock:
                self._job["log"] = (self._job["log"] + [str(message)])[-200:]

        try:
            ok = BookManager.import_book(str(source), voice, progress, log_callback=log,
                                         cancel_check=self._cancel.is_set, backend=engine, model=model or None)
            state = "cancelled" if self._cancel.is_set() else ("done" if ok else "failed")
        except Exception as error:
            log(f"Import failed: {error}")
            state = "failed"
        with self._lock:
            self._job.update(state=state, finished=time.time())
