import os
import json
import shutil
import subprocess
import sys
import time
import threading
import re
import concurrent.futures
import difflib
from pathlib import Path

# --- Configuration ---
# Update these paths to point to your specific tools
CALIBRE_PATH = r"C:\Program Files\Calibre2\ebook-convert.exe"
LIBRARY_PATH = Path("library")
LIBRARY_PATH.mkdir(exist_ok=True)

class BookManager:
    @staticmethod
    def _get_extract_worker_count():
        """
        Select text extraction worker count.
        Override with CADENCE_EXTRACT_WORKERS.
        Keep a moderate default for speed while avoiding excessive process churn.
        """
        env_value = os.getenv("CADENCE_EXTRACT_WORKERS", "").strip()
        if env_value:
            try:
                return max(1, int(env_value))
            except ValueError:
                pass
        cpu = os.cpu_count() or 4
        return max(1, min(cpu, 4))

    @staticmethod
    def _resolve_stored_epub(book_dir, metadata=None):
        book_dir = Path(book_dir)
        source_dir = book_dir / "source"
        if metadata and metadata.get("source_epub"):
            candidate = book_dir / str(metadata.get("source_epub"))
            if candidate.exists():
                return candidate
        if source_dir.exists():
            epubs = sorted(source_dir.glob("*.epub"))
            if epubs:
                return epubs[0]
        return None

    @staticmethod
    def get_stored_epub(book_path):
        book_dir = Path(book_path)
        metadata = {}
        meta_path = book_dir / "metadata.json"
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                metadata = {}
        epub_path = BookManager._resolve_stored_epub(book_dir, metadata=metadata)
        return str(epub_path) if epub_path else ""

    @staticmethod
    def _detect_gpu_free_memory_mib():
        """Best-effort query of free VRAM via nvidia-smi."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if result.returncode != 0:
                return None
            values = []
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    values.append(int(line))
                except ValueError:
                    continue
            if not values:
                return None
            return max(values)
        except Exception:
            return None

    @staticmethod
    def _get_synthesis_worker_count():
        """
        Select chapter synthesis worker count.
        Override with CADENCE_SYNTH_WORKERS.
        """
        env_value = os.getenv("CADENCE_SYNTH_WORKERS", "").strip()
        if env_value:
            try:
                return max(1, int(env_value))
            except ValueError:
                pass
        return 1

    @staticmethod
    def _get_tts_max_chunk_chars():
        """
        Max chars per synthesis chunk.
        Override with CADENCE_TTS_MAX_CHARS.
        """
        env_value = os.getenv("CADENCE_TTS_MAX_CHARS", "").strip()
        if env_value:
            try:
                return max(400, int(env_value))
            except ValueError:
                pass
        return 1600

    @staticmethod
    def _get_whisperx_model_name():
        return os.getenv("CADENCE_WHISPERX_MODEL", "small").strip() or "small"

    @staticmethod
    def _get_whisperx_batch_size():
        env_value = os.getenv("CADENCE_WHISPERX_BATCH_SIZE", "").strip()
        if env_value:
            try:
                return max(1, int(env_value))
            except ValueError:
                pass
        return 24

    @staticmethod
    def _get_whisperx_compute_type():
        env_value = os.getenv("CADENCE_WHISPERX_COMPUTE_TYPE", "").strip()
        if env_value:
            return env_value
        return "float16"

    @staticmethod
    def _get_whisperx_python():
        env_value = os.getenv("CADENCE_WHISPERX_PYTHON", "").strip()
        if env_value:
            return env_value
        # Prefer project-local venv Python so alignment does not accidentally run
        # in conda base/system Python.
        project_root = Path(__file__).resolve().parent.parent
        if os.name == "nt":
            candidate = project_root / "venv" / "Scripts" / "python.exe"
        else:
            candidate = project_root / "venv" / "bin" / "python"
        if candidate.exists():
            return str(candidate)
        return sys.executable

    @staticmethod
    def get_books():
        """Scans library for valid books."""
        books = []
        if not LIBRARY_PATH.exists():
            return []

        for folder in LIBRARY_PATH.iterdir():
            meta_path = folder / "metadata.json"
            if folder.is_dir() and meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    content_dir = folder / "content"
                    audio_dir = folder / "audio"

                    txt_stems = {
                        p.stem
                        for p in content_dir.glob("ch_*.txt")
                        if p.is_file() and p.stat().st_size > 0
                    }
                    content_chapters = len(txt_stems)

                    if content_chapters == 0:
                        # Fallback to metadata if chapter files are not yet present.
                        content_chapters = int(
                            data.get("total_chapters", data.get("chapters", 0)) or 0
                        )

                    audio_ready = sum(
                        1
                        for stem in txt_stems
                        if (audio_dir / f"{stem}.wav").exists()
                        and (audio_dir / f"{stem}.wav").stat().st_size > 0
                    )
                    aligned_ready = sum(
                        1
                        for stem in txt_stems
                        if (content_dir / f"{stem}.json").exists()
                        and (content_dir / f"{stem}.json").stat().st_size > 0
                    )

                    is_incomplete = (
                        content_chapters > 0
                        and (audio_ready < content_chapters or aligned_ready < content_chapters)
                    )

                    data["content_chapters"] = content_chapters
                    data["audio_chapters_ready"] = audio_ready
                    data["aligned_chapters_ready"] = aligned_ready
                    data["audio_missing"] = max(0, content_chapters - audio_ready)
                    data["aligned_missing"] = max(0, content_chapters - aligned_ready)
                    data["is_incomplete"] = is_incomplete
                    stored_epub = BookManager._resolve_stored_epub(folder, metadata=data)
                    data["stored_epub_path"] = str(stored_epub) if stored_epub else ""
                    data["stored_epub_exists"] = bool(stored_epub)
                    data["path"] = str(folder)
                    books.append(data)
                except Exception:
                    continue
        return books

    @staticmethod
    def tokenize_for_alignment(text):
        """Tokenizes text for alignment, preserving structure."""
        splits = re.split(r'(\s+)', text)
        processed = []
        
        # Normalization map for comparison only
        rep = {
            "’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-"
        }
        
        for s in splits:
            if not s: continue
            
            # Clean for comparison
            clean = s.lower()
            for k, v in rep.items():
                clean = clean.replace(k, v)
            clean = re.sub(r'[^\w]', '', clean)
            
            processed.append({"text": s, "clean": clean})
        return processed

    @staticmethod
    def align_timestamps(txt_content, json_data):
        """Aligns clean TXT with noisy JSON timestamps."""
        txt_tokens = BookManager.tokenize_for_alignment(txt_content)
        txt_match_list = [t["clean"] for t in txt_tokens if t["clean"]]
        txt_map = [i for i, t in enumerate(txt_tokens) if t["clean"]]
        
        json_match_list = [re.sub(r'[^\w]', '', t["word"]).lower() for t in json_data]
        
        matcher = difflib.SequenceMatcher(None, txt_match_list, json_match_list)
        
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for k in range(i2 - i1):
                    txt_idx = txt_map[i1 + k]
                    json_idx = j1 + k
                    token = txt_tokens[txt_idx]
                    js_item = json_data[json_idx]
                    token["start"] = js_item["start"]
                    token["end"] = js_item["end"]
                    
            elif tag == 'replace':
                if j2 > j1:
                    start_time = json_data[j1]["start"]
                    end_time = json_data[j2-1]["end"]
                    num_txt = i2 - i1
                    if num_txt > 0:
                        duration = end_time - start_time
                        step = duration / num_txt
                        for k in range(num_txt):
                            txt_idx = txt_map[i1 + k]
                            token = txt_tokens[txt_idx]
                            token["start"] = start_time + (k * step)
                            token["end"] = start_time + ((k + 1) * step)

        # Fill gaps
        last_end = 0.0
        final_output = []
        for token in txt_tokens:
            if "start" in token:
                last_end = token["end"]
                final_output.append(token)
            elif token["clean"]: # Only care about words having timestamps
                # If word missing timestamp, interpolate or snap?
                # Snap to last_end for now to prevent crash
                token["start"] = last_end
                token["end"] = last_end
                final_output.append(token)
            else:
                # Whitespace/Punctuation - don't strictly need timestamps for player
                # But let's include them for completeness in display
                token["start"] = last_end
                token["end"] = last_end
                final_output.append(token)
                
        # We want the output to just be the list of dicts with words and times
        # The player expects: [{"word": "...", "start": ..., "end": ...}]
        # The tokenizer kept whitespace as tokens.
        
        return [{"word": t["text"], "start": t.get("start", 0), "end": t.get("end", 0)} for t in txt_tokens]

    @staticmethod
    def import_book(epub_path, voice, progress_callback, log_callback=None, cancel_check=None):
        """
        Runs the full pipeline in a background thread.
        1. Extract EPUB -> 2. Generate Audio -> 3. Align Timestamps
        """
        def log(msg):
            if log_callback: log_callback(msg)
            print(msg)

        def is_cancelled():
            if cancel_check is None:
                return False
            try:
                return bool(cancel_check())
            except Exception:
                return False

        try:
            source_file = Path(epub_path)
            if not source_file.exists():
                raise FileNotFoundError(f"Book file not found: {source_file}")
            source_ext = source_file.suffix.lower()
            supported_exts = {".epub", ".mobi", ".azw3"}
            if source_ext not in supported_exts:
                raise ValueError(
                    f"Unsupported format: {source_ext}. Supported: .epub, .mobi, .azw3"
                )

            # If using stored source EPUB (library/<book>/source/*.epub), lock to that book folder.
            book_dir = None
            try:
                resolved = source_file.resolve()
                if (
                    resolved.parent.name.lower() == "source"
                    and resolved.parent.parent.parent.resolve() == LIBRARY_PATH.resolve()
                ):
                    book_dir = resolved.parent.parent
            except Exception:
                pass

            if book_dir is None:
                book_name = source_file.stem.replace(" ", "_")  # Clean name
                book_dir = LIBRARY_PATH / book_name
            else:
                book_name = book_dir.name

            content_dir = book_dir / "content"
            source_dir = book_dir / "source"
            content_dir.mkdir(parents=True, exist_ok=True)
            source_dir.mkdir(parents=True, exist_ok=True)

            log(f"Starting import for: {source_file.name}")
            log(f"Target directory: {book_dir}")
            if is_cancelled():
                log("Import canceled before start.")
                return False

            # Normalize all imports to a source EPUB so the existing extraction/alignment
            # pipeline and resume flow stay unchanged.
            if source_ext == ".epub":
                epub_file = source_file
                stored_epub_name = source_file.name
            else:
                stored_epub_name = f"{source_file.stem}.epub"
                epub_file = source_dir / stored_epub_name
                if not (epub_file.exists() and epub_file.stat().st_size > 0):
                    log(f"Converting {source_file.suffix} -> EPUB for import resume support...")
                    convert_cmd = [CALIBRE_PATH, str(source_file), str(epub_file)]
                    convert_result = subprocess.run(
                        convert_cmd,
                        shell=False,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                    )
                    if convert_result.returncode != 0 or not epub_file.exists():
                        err = (convert_result.stderr or "").strip()[-1200:]
                        out = (convert_result.stdout or "").strip()[-800:]
                        if err:
                            log(f"Calibre conversion error: {err}")
                        if out:
                            log(f"Calibre conversion output: {out}")
                        return False
                    log(f"Converted source to EPUB: {epub_file.name}")

            # Keep original source book file for traceability/recovery (if not already inside source/).
            try:
                original_copy = source_dir / source_file.name
                if source_file.resolve() != original_copy.resolve():
                    shutil.copy2(source_file, original_copy)
            except Exception:
                pass

            # 1. Setup Folders & Check Resume
            extract_needed = True
            if book_dir.exists():
                existing_txt = list((book_dir / "content").glob("ch_*.txt")) if (book_dir / "content").exists() else []
                meta_path = book_dir / "metadata.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            existing_meta = json.load(f)

                        # Keep prior voice on resume so chapter output remains consistent.
                        existing_voice = str(existing_meta.get("voice", "")).strip()
                        if existing_voice:
                            if existing_voice != voice:
                                log(
                                    f"Using existing book voice '{existing_voice}' "
                                    f"instead of selected '{voice}' for resume."
                                )
                            voice = existing_voice

                        # Resume if text/audio pipeline already started.
                        status = existing_meta.get("status")
                        if status in ["text_only", "synthesized", "complete"] or existing_txt:
                            log(f"Resuming import for: {book_name} (Status: {status})")
                            extract_needed = False
                    except Exception:
                        pass
                elif existing_txt:
                    log(f"Resuming import for: {book_name} (Detected existing chapter text)")
                    extract_needed = False
            else:
                content_dir.mkdir(parents=True)
            # Keep source EPUB in book folder for one-click resume.
            stored_epub = source_dir / stored_epub_name
            try:
                if stored_epub.resolve() != epub_file.resolve():
                    shutil.copy2(epub_file, stored_epub)
            except Exception:
                # If resolve/copy fails, continue pipeline without blocking.
                pass

            # --- STEP 1: EXTRACTION (Calibre) ---
            if extract_needed:
                progress_callback(0.1, "Step 1/3: Extracting Text...")
                log("--- Step 1: Text Extraction ---")
                if is_cancelled():
                    log("Import canceled during extraction setup.")
                    return False
                
                temp_dir = Path("temp_extraction")
                neutral_zone = Path("temp_isolated_html")
    
                # Clean temp folders
                for d in [temp_dir, neutral_zone]:
                    if d.exists(): shutil.rmtree(d)
                neutral_zone.mkdir()
                temp_dir.mkdir()

                # Unpack EPUB
                log(f"Unpacking EPUB to {temp_dir}...")
                cmd = [CALIBRE_PATH, str(epub_file), str(temp_dir)]
                
                result = subprocess.run(
                    cmd,
                    shell=False,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                )
                if result.returncode != 0:
                    log(f"Calibre Error: {result.stderr}")
                    return False
                
                # Finding reading order
                opf_files = list(temp_dir.rglob("*.opf"))
                ordered_html_files = []
                
                if opf_files:
                    try:
                        opf_path = opf_files[0]
                        log(f"Parsing OPF for reading order: {opf_path.name}")
                        with open(opf_path, 'r', encoding='utf-8', errors='replace') as f:
                            opf_content = f.read()
                        
                        import xml.etree.ElementTree as ET
                        opf_content = re.sub(r' xmlns="[^"]+"', '', opf_content, count=1)
                        root = ET.fromstring(opf_content)
                        
                        manifest = {}
                        for item in root.findall(".//manifest/item"):
                            manifest[item.get("id")] = item.get("href")
                            
                        spine = [itemref.get("idref") for itemref in root.findall(".//spine/itemref")]
                        
                        opf_dir = opf_path.parent
                        for item_id in spine:
                            if item_id in manifest:
                                rel_path = manifest[item_id]
                                full_path = opf_dir / rel_path
                                if full_path.exists():
                                    ordered_html_files.append(full_path)
                                    
                        log(f"Found {len(ordered_html_files)} chapters in spine.")
                    except Exception as e:
                        log(f"Failed to parse OPF: {e}. Falling back to name sort.")
                        ordered_html_files = []

                if not ordered_html_files:
                    ordered_html_files = sorted(list(temp_dir.rglob("*.html")) + list(temp_dir.rglob("*.xhtml")))

                html_files = ordered_html_files
                log(f"Processing {len(html_files)} files...")

                # Parallel Extraction
                max_workers = BookManager._get_extract_worker_count()
                log(f"Starting parallel extraction with {max_workers} workers...")
                
                def convert_chunk(args):
                    if is_cancelled():
                        return None
                    idx, html_path = args
                    chunk_name = f"chunk_{idx:04d}{html_path.suffix}"
                    isolated_html = neutral_zone / chunk_name
                    shutil.copy(html_path, isolated_html)
                    
                    out_txt_name = f"ch_{idx+1:03d}.txt"
                    out_txt = content_dir / out_txt_name
                    # Keep .txt extension so calibre resolves output plugin correctly.
                    out_txt_tmp = content_dir / f"{out_txt.stem}.part.txt"
                    
                    log(f"Converting {html_path.name} -> {out_txt_name}")
                    cmd = [
                        CALIBRE_PATH,
                        str(isolated_html),
                        str(out_txt_tmp),
                        "--txt-output-format=plain",
                        "--smarten-punctuation",
                    ]
                    for attempt in (1, 2):
                        try:
                            result = subprocess.run(
                                cmd,
                                shell=False,
                                capture_output=True,
                                encoding="utf-8",
                                errors="replace",
                            )
                            if result.returncode == 0 and out_txt_tmp.exists() and out_txt_tmp.stat().st_size > 0:
                                os.replace(out_txt_tmp, out_txt)
                                return idx + 1

                            err_tail = (result.stderr or "").strip()[-600:]
                            out_tail = (result.stdout or "").strip()[-300:]
                            log(
                                f"Failed conversion (attempt {attempt}/2): {html_path.name} "
                                f"(rc={result.returncode})"
                            )
                            if err_tail:
                                log(f"stderr: {err_tail}")
                            if out_tail:
                                log(f"stdout: {out_tail}")
                            if out_txt_tmp.exists():
                                try:
                                    out_txt_tmp.unlink()
                                except Exception:
                                    pass
                            if attempt == 1:
                                time.sleep(0.15)
                        except Exception as exc:
                            log(f"Exception converting {html_path.name} (attempt {attempt}/2): {exc}")
                            if attempt == 1:
                                time.sleep(0.15)
                        finally:
                            if out_txt_tmp.exists():
                                try:
                                    out_txt_tmp.unlink()
                                except Exception:
                                    pass
                    return None

                tasks = [(i, h) for i, h in enumerate(html_files) if h.stat().st_size >= 300]
                if max_workers <= 1:
                    results = [r for r in map(convert_chunk, tasks) if r is not None]
                else:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                        results = [r for r in executor.map(convert_chunk, tasks) if r is not None]
                
                chapter_count = len(results)
                if is_cancelled():
                    log("Import canceled during text extraction.")
                    return False

                # Cleanup Temp
                shutil.rmtree(temp_dir)
                shutil.rmtree(neutral_zone)
                log(f"Extraction complete. {chapter_count} chapters prepared.")

                # SAVE METADATA (EARLY)
                metadata = {
                    "title": book_name.replace("_", " "),
                    "author": "Unknown",
                    "status": "text_only",
                    "voice": voice,
                    "chapters": chapter_count,
                    "total_chapters": chapter_count,
                    "last_chapter": 0,
                    "cover": "",
                    "source_epub": str(Path("source") / stored_epub_name),
                }
                with open(book_dir / "metadata.json", "w") as f:
                    json.dump(metadata, f, indent=4)
            else:
                chapter_count = len(list(content_dir.glob("*.txt")))
                log(f"Skipped extraction. Found {chapter_count} existing chapters.")
                # Load existing metadata
                with open(book_dir / "metadata.json", "r") as f:
                    metadata = json.load(f)
                metadata["source_epub"] = str(Path("source") / stored_epub_name)

            # --- STEP 2/3: STREAMING SYNTH + ALIGN ---
            progress_callback(0.4, "Step 2/3: Streaming synthesis + alignment...")
            log("--- Step 2/3: Streaming Chapter Pipeline (TTS -> WhisperX) ---")
            if is_cancelled():
                log("Import canceled before synthesis/alignment.")
                return False

            txt_files = sorted(content_dir.glob("*.txt"))
            log(f"Found {len(txt_files)} text chapters for voice '{voice}'.")

            audio_dir = book_dir / "audio"
            audio_dir.mkdir(exist_ok=True)

            whisperx_python = BookManager._get_whisperx_python()
            whisperx_model_name = BookManager._get_whisperx_model_name()
            whisperx_batch_size = BookManager._get_whisperx_batch_size()
            whisperx_compute_type = BookManager._get_whisperx_compute_type()
            whisperx_device = os.getenv("CADENCE_WHISPERX_DEVICE", "auto").strip() or "auto"
            whisperx_script = Path(__file__).resolve().parent / "whisperx_align_cli.py"
            whisperx_worker_script = Path(__file__).resolve().parent / "whisperx_align_worker.py"
            if not whisperx_script.exists():
                raise FileNotFoundError(f"WhisperX alignment script not found: {whisperx_script}")
            if not whisperx_worker_script.exists():
                raise FileNotFoundError(
                    f"WhisperX alignment worker script not found: {whisperx_worker_script}"
                )
            project_root = Path(__file__).resolve().parent.parent

            if not txt_files:
                log("No text chapters found for synthesis/alignment.")
            else:
                worker_count = BookManager._get_synthesis_worker_count()
                tts_max_chars = BookManager._get_tts_max_chunk_chars()
                free_mib = BookManager._detect_gpu_free_memory_mib()
                if free_mib is not None:
                    log(f"GPU free memory: {free_mib} MiB")
                log(f"Using {worker_count} synthesis worker(s).")
                log(f"TTS max chunk size: {tts_max_chars} chars.")
                log(f"WhisperX python: {whisperx_python}")
                log(
                    f"WhisperX config: model={whisperx_model_name}, "
                    f"compute_type={whisperx_compute_type}, batch_size={whisperx_batch_size}, "
                    f"device={whisperx_device}"
                )

                class WhisperXImportWorker:
                    def __init__(self):
                        self.proc = None
                        self.ready_info = None
                        self.disabled = False
                        self.start_timeout_s = float(
                            os.getenv("CADENCE_WHISPERX_START_TIMEOUT_SEC", "240")
                        )
                        self.job_timeout_s = float(
                            os.getenv("CADENCE_WHISPERX_CHAPTER_TIMEOUT_SEC", "300")
                        )

                    def start(self):
                        if self.disabled or self.proc is not None:
                            return self.proc is not None
                        cmd = [
                            whisperx_python,
                            str(whisperx_worker_script),
                            "--whisper-model",
                            whisperx_model_name,
                            "--whisper-batch-size",
                            str(whisperx_batch_size),
                            "--whisper-compute-type",
                            whisperx_compute_type,
                            "--device",
                            whisperx_device,
                        ]
                        try:
                            log(
                                "Starting WhisperX worker (one-time model load for this import)..."
                            )
                            self.proc = subprocess.Popen(
                                cmd,
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                cwd=str(project_root),
                                bufsize=1,
                            )
                            start_deadline = time.monotonic() + self.start_timeout_s
                            msg = None
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                                future = ex.submit(self.proc.stdout.readline)
                                while time.monotonic() < start_deadline:
                                    if is_cancelled():
                                        raise RuntimeError("startup canceled")
                                    try:
                                        line = future.result(timeout=0.2)
                                    except concurrent.futures.TimeoutError:
                                        continue
                                    if not line:
                                        raise RuntimeError("no ready message from WhisperX worker")
                                    raw = line.strip()
                                    if not raw:
                                        future = ex.submit(self.proc.stdout.readline)
                                        continue
                                    try:
                                        candidate = json.loads(raw)
                                    except Exception:
                                        # Ignore noisy non-JSON stdout lines from dependencies.
                                        future = ex.submit(self.proc.stdout.readline)
                                        continue
                                    if candidate.get("event") == "ready":
                                        msg = candidate
                                        break
                                    # Ignore other messages until ready.
                                    future = ex.submit(self.proc.stdout.readline)
                            if msg is None:
                                raise RuntimeError("no ready event from WhisperX worker")
                            self.ready_info = msg
                            log(
                                "WhisperX worker ready: "
                                f"device={msg.get('device', whisperx_device)} "
                                f"compute={msg.get('resolved_compute_type', whisperx_compute_type)}"
                            )
                            return True
                        except Exception as e:
                            self.disabled = True
                            log(f"WhisperX worker startup failed, using fallback mode: {e}")
                            self.stop()
                            return False

                    def align(self, wav, txt, out_json, report_json, raw_json):
                        if self.disabled:
                            return None
                        if self.proc is None and not self.start():
                            return None
                        if is_cancelled():
                            return None
                        try:
                            payload = {
                                "cmd": "align",
                                "wav": str(wav),
                                "txt": str(txt),
                                "out_json": str(out_json),
                                "report_json": str(report_json),
                                "raw_json": str(raw_json),
                            }
                            self.proc.stdin.write(json.dumps(payload) + "\n")
                            self.proc.stdin.flush()
                            deadline = time.monotonic() + self.job_timeout_s
                            msg = None
                            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                                future = ex.submit(self.proc.stdout.readline)
                                while time.monotonic() < deadline:
                                    if is_cancelled():
                                        return None
                                    try:
                                        line = future.result(timeout=0.2)
                                    except concurrent.futures.TimeoutError:
                                        continue
                                    if not line:
                                        raise RuntimeError("worker produced no response")
                                    raw = line.strip()
                                    if not raw:
                                        future = ex.submit(self.proc.stdout.readline)
                                        continue
                                    try:
                                        candidate = json.loads(raw)
                                    except Exception:
                                        future = ex.submit(self.proc.stdout.readline)
                                        continue
                                    if candidate.get("event") in {"aligned", "error"}:
                                        msg = candidate
                                        break
                                    future = ex.submit(self.proc.stdout.readline)
                            if msg is None:
                                raise RuntimeError("worker timed out waiting for result")
                            event = msg.get("event")
                            if event == "aligned":
                                return msg
                            if event == "error":
                                log(f"WhisperX worker error: {msg.get('error', 'unknown error')}")
                                return None
                            log(f"WhisperX worker unexpected message: {msg}")
                            return None
                        except Exception as e:
                            log(f"WhisperX worker communication failed: {e}")
                            self.disabled = True
                            self.stop()
                            return None

                    def stop(self):
                        proc = self.proc
                        self.proc = None
                        if proc is None:
                            return
                        try:
                            if proc.stdin:
                                proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                                proc.stdin.flush()
                        except Exception:
                            pass
                        try:
                            proc.wait(timeout=3)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass

                chapters = []
                for txt in txt_files:
                    wav_path = audio_dir / f"{txt.stem}.wav"
                    json_path = content_dir / f"{txt.stem}.json"
                    has_audio = wav_path.exists() and wav_path.stat().st_size > 0
                    has_json = json_path.exists() and json_path.stat().st_size > 0
                    chapters.append(
                        {
                            "stem": txt.stem,
                            "txt": txt,
                            "wav": wav_path,
                            "json": json_path,
                            "has_audio": has_audio,
                            "has_json": has_json,
                            "ready": has_audio and has_json,
                        }
                    )

                total_chapters = len(chapters)
                ready_count = sum(1 for c in chapters if c["ready"])
                whisper_worker = WhisperXImportWorker()
                metadata["status"] = "processing"
                metadata["total_chapters"] = total_chapters
                metadata["last_chapter"] = ready_count
                with open(book_dir / "metadata.json", "w", encoding="utf-8") as f:
                    json.dump(metadata, f, indent=4)

                def update_stream_progress(activity="", chapter_stem=""):
                    pct = 0.4 + (0.55 * (ready_count / max(total_chapters, 1)))
                    pct = min(0.95, pct)
                    detail = f"{activity} {chapter_stem}".strip()
                    suffix = f" • {detail}" if detail else ""
                    progress_callback(
                        pct,
                        f"Step 2/3: Processing ({ready_count}/{total_chapters} ready){suffix}",
                    )

                def mark_ready(chapter):
                    nonlocal ready_count
                    if chapter["has_audio"] and chapter["has_json"] and not chapter["ready"]:
                        chapter["ready"] = True
                        ready_count += 1
                        metadata["last_chapter"] = ready_count
                        metadata["status"] = "processing"
                        with open(book_dir / "metadata.json", "w", encoding="utf-8") as f:
                            json.dump(metadata, f, indent=4)
                        update_stream_progress("Ready", chapter["stem"])

                def align_one_chapter(chapter):
                    if is_cancelled():
                        return False
                    if chapter["has_json"]:
                        return True
                    if not chapter["has_audio"]:
                        return False

                    source_txt = chapter["txt"]
                    out_json = chapter["json"]
                    wav = chapter["wav"]
                    chapter_report = content_dir / f"{chapter['stem']}.whisperx_report.json"
                    raw_json = content_dir / f"{chapter['stem']}_raw.json"

                    log(f"Aligning {wav.name} with {source_txt.name}...")
                    worker_msg = whisper_worker.align(
                        wav=wav,
                        txt=source_txt,
                        out_json=out_json,
                        report_json=chapter_report,
                        raw_json=raw_json,
                    )
                    if worker_msg is None:
                        if is_cancelled():
                            return False
                        cmd = [
                            whisperx_python,
                            str(whisperx_script),
                            str(wav),
                            str(source_txt),
                            "--whisper-model",
                            whisperx_model_name,
                            "--whisper-batch-size",
                            str(whisperx_batch_size),
                            "--whisper-compute-type",
                            whisperx_compute_type,
                            "--device",
                            whisperx_device,
                            "--output-json",
                            str(out_json),
                            "--report-json",
                            str(chapter_report),
                            "--raw-json",
                            str(raw_json),
                        ]
                        proc = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            cwd=str(project_root),
                        )
                        try:
                            while proc.poll() is None:
                                if is_cancelled():
                                    try:
                                        proc.terminate()
                                    except Exception:
                                        pass
                                    try:
                                        proc.wait(timeout=2)
                                    except Exception:
                                        try:
                                            proc.kill()
                                        except Exception:
                                            pass
                                    log(f"Canceled WhisperX for {wav.name}")
                                    return False
                                time.sleep(0.2)
                            stdout, stderr = proc.communicate(timeout=2)
                            class _R:
                                returncode = proc.returncode
                            result = _R()
                            result.stdout = stdout
                            result.stderr = stderr
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                            raise
                        if result.returncode != 0:
                            log(f"WhisperX failed for {wav.name}")
                            log(result.stdout[-2000:] if result.stdout else "")
                            log(result.stderr[-2000:] if result.stderr else "")
                            return False

                    if chapter_report.exists():
                        try:
                            rep = json.loads(chapter_report.read_text(encoding="utf-8"))
                            totals = rep.get("timing_seconds", {})
                            used_device = rep.get("device", whisperx_device)
                            log(
                                f"Aligned {wav.name}: "
                                f"device={used_device} "
                                f"whisper={totals.get('whisperx_transcribe_and_align', 0):.2f}s "
                                f"total={totals.get('total', 0):.2f}s"
                            )
                        except Exception:
                            pass

                    if out_json.exists() and out_json.stat().st_size > 0:
                        chapter["has_json"] = True
                        log(f"Saved timestamps: {out_json.name}")
                        mark_ready(chapter)
                        return True
                    return False

                try:
                    # First, align any chapters that already have audio from previous runs.
                    pending_align = [c for c in chapters if c["has_audio"] and not c["has_json"]]
                    for chapter in pending_align:
                        if is_cancelled():
                            log("Import canceled during pending alignment.")
                            break
                        align_one_chapter(chapter)

                    synth_targets = [c for c in chapters if not c["has_audio"]]
                    if worker_count <= 1 or len(synth_targets) <= 1:
                        if synth_targets:
                            from adapters.supertonic_backend import SupertonicBackend

                            backend = SupertonicBackend()
                            backend.ensure_model()
                            for chapter in synth_targets:
                                if is_cancelled():
                                    log("Import canceled during synthesis.")
                                    break
                                log(f"Synthesizing {chapter['txt'].name}...")
                                with open(chapter["txt"], "r", encoding="utf-8") as f:
                                    text_content = f.read().strip()
                                if text_content:
                                    wav = backend.synthesize(text_content, voice, max_chars=tts_max_chars)
                                    if wav is not None:
                                        backend.save_audio(wav, chapter["wav"])
                                        chapter["has_audio"] = (
                                            chapter["wav"].exists() and chapter["wav"].stat().st_size > 0
                                        )
                                        if chapter["has_audio"]:
                                            log(f"Saved audio: {chapter['wav'].name}")
                                else:
                                    log(f"Skipped {chapter['txt'].name} (Empty text)")
                                update_stream_progress("Synth", chapter["stem"])
                                align_one_chapter(chapter)
                    else:
                        thread_local = threading.local()

                        def get_thread_backend():
                            if not hasattr(thread_local, "backend"):
                                from adapters.supertonic_backend import SupertonicBackend

                                backend = SupertonicBackend()
                                backend.ensure_model()
                                thread_local.backend = backend
                            return thread_local.backend

                        def synthesize_task(chapter):
                            if is_cancelled():
                                return ("cancel", chapter)
                            with open(chapter["txt"], "r", encoding="utf-8") as f:
                                text_content = f.read().strip()
                            if not text_content:
                                return ("empty", chapter)
                            backend = get_thread_backend()
                            wav_data = backend.synthesize(text_content, voice, max_chars=tts_max_chars)
                            if wav_data is None:
                                return ("empty", chapter)
                            backend.save_audio(wav_data, chapter["wav"])
                            return ("saved", chapter)

                        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                            futures = {
                                executor.submit(synthesize_task, chapter): chapter
                                for chapter in synth_targets
                            }
                            for future in concurrent.futures.as_completed(futures):
                                if is_cancelled():
                                    log("Import canceled during parallel synthesis.")
                                    for f in futures:
                                        f.cancel()
                                    break
                                chapter = futures[future]
                                try:
                                    status, chapter = future.result()
                                    if status == "saved":
                                        chapter["has_audio"] = (
                                            chapter["wav"].exists() and chapter["wav"].stat().st_size > 0
                                        )
                                        if chapter["has_audio"]:
                                            log(f"Saved audio: {chapter['wav'].name}")
                                    elif status == "cancel":
                                        pass
                                    else:
                                        log(f"Skipped {chapter['txt'].name} (Empty text)")
                                except Exception as e:
                                    log(f"Error synthesizing {chapter['txt'].name}: {e}")
                                update_stream_progress("Synth", chapter["stem"])
                                align_one_chapter(chapter)
                finally:
                    whisper_worker.stop()
                    if is_cancelled():
                        log("Import canceled.")
                        return False

            # --- FINALIZE METADATA ---
            log("Finalizing metadata...")
            final_txt = sorted(content_dir.glob("*.txt"))
            total_chapters = len(final_txt)
            audio_ready = sum(
                1
                for txt in final_txt
                if (audio_dir / f"{txt.stem}.wav").exists()
                and (audio_dir / f"{txt.stem}.wav").stat().st_size > 0
            )
            aligned_ready = sum(
                1
                for txt in final_txt
                if (content_dir / f"{txt.stem}.json").exists()
                and (content_dir / f"{txt.stem}.json").stat().st_size > 0
            )

            if total_chapters > 0 and aligned_ready == total_chapters:
                metadata["status"] = "complete"
            elif total_chapters > 0 and audio_ready == total_chapters:
                metadata["status"] = "synthesized"
            elif total_chapters > 0:
                metadata["status"] = "text_only"
            else:
                metadata["status"] = "empty"

            metadata["total_chapters"] = total_chapters
            metadata["chapters"] = total_chapters
            metadata["last_chapter"] = aligned_ready

            with open(book_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=4)
                
            progress_callback(1.0, "Ready!")
            log("Import process completed successfully.")
            return True

        except Exception as e:
            log(f"Pipeline Error: {e}")
            import traceback
            log(traceback.format_exc())
            return False
