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
        if not LIBRARY_PATH.exists(): return []
        
        for folder in LIBRARY_PATH.iterdir():
            meta_path = folder / "metadata.json"
            if folder.is_dir() and meta_path.exists():
                try:
                    with open(meta_path, "r") as f:
                        data = json.load(f)
                        data["path"] = str(folder)
                        books.append(data)
                except:
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
    def import_book(epub_path, voice, progress_callback, log_callback=None):
        """
        Runs the full pipeline in a background thread.
        1. Extract EPUB -> 2. Generate Audio -> 3. Align Timestamps
        """
        def log(msg):
            if log_callback: log_callback(msg)
            print(msg)

        try:
            epub_file = Path(epub_path)
            book_name = epub_file.stem.replace(" ", "_") # Clean name
            book_dir = LIBRARY_PATH / book_name
            content_dir = book_dir / "content"

            log(f"Starting import for: {epub_file.name}")
            log(f"Target directory: {book_dir}")

            # 1. Setup Folders & Check Resume
            extract_needed = True
            if book_dir.exists(): 
                meta_path = book_dir / "metadata.json"
                if meta_path.exists():
                    try:
                        with open(meta_path, 'r') as f:
                            existing_meta = json.load(f)
                        
                        # Resume if text is ready or audio is partially done
                        status = existing_meta.get("status")
                        if status in ["text_only", "synthesized", "complete"]:
                            log(f"Resuming import for: {book_name} (Status: {status})")
                            extract_needed = False
                    except:
                        pass
                
                if extract_needed:
                    log(f"Removing existing directory: {book_dir}")
                    shutil.rmtree(book_dir)
                    content_dir.mkdir(parents=True)
            else:
                content_dir.mkdir(parents=True)

            # --- STEP 1: EXTRACTION (Calibre) ---
            if extract_needed:
                progress_callback(0.1, "Step 1/3: Extracting Text...")
                log("--- Step 1: Text Extraction ---")
                
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
                
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace')
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
                max_workers = min(os.cpu_count() or 4, 8)
                log(f"Starting parallel extraction with {max_workers} workers...")
                
                def convert_chunk(args):
                    idx, html_path = args
                    chunk_name = f"chunk_{idx:04d}{html_path.suffix}"
                    isolated_html = neutral_zone / chunk_name
                    shutil.copy(html_path, isolated_html)
                    
                    out_txt_name = f"ch_{idx+1:03d}.txt"
                    out_txt = content_dir / out_txt_name
                    
                    log(f"Converting {html_path.name} -> {out_txt_name}")
                    subprocess.run([
                        CALIBRE_PATH, str(isolated_html), str(out_txt), 
                        "--txt-output-format=plain", "--smarten-punctuation"
                    ], shell=True, capture_output=True, encoding='utf-8', errors='replace')
                    return idx + 1

                tasks = [(i, h) for i, h in enumerate(html_files) if h.stat().st_size >= 300]
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    results = list(executor.map(convert_chunk, tasks))
                
                chapter_count = len(results)

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
                    "cover": ""
                }
                with open(book_dir / "metadata.json", "w") as f:
                    json.dump(metadata, f, indent=4)
            else:
                chapter_count = len(list(content_dir.glob("*.txt")))
                log(f"Skipped extraction. Found {chapter_count} existing chapters.")
                # Load existing metadata
                with open(book_dir / "metadata.json", "r") as f:
                    metadata = json.load(f)

            # --- STEP 2: AUDIO GENERATION (Supertonic) ---
            progress_callback(0.4, "Step 2/3: Synthesizing audio...")
            log("--- Step 2: Audio Synthesis ---")

            from adapters.supertonic_backend import SupertonicBackend

            txt_files = sorted(content_dir.glob("*.txt"))
            log(f"Found {len(txt_files)} text chapters for voice '{voice}'.")

            audio_dir = book_dir / "audio"
            audio_dir.mkdir(exist_ok=True)

            if not txt_files:
                log("No text chapters found for synthesis.")
            else:
                worker_count = BookManager._get_synthesis_worker_count()
                tts_max_chars = BookManager._get_tts_max_chunk_chars()
                free_mib = BookManager._detect_gpu_free_memory_mib()
                if free_mib is not None:
                    log(f"GPU free memory: {free_mib} MiB")
                log(f"Using {worker_count} synthesis worker(s).")
                log(f"TTS max chunk size: {tts_max_chars} chars.")

                skipped_count = 0
                synth_targets = []
                for txt in txt_files:
                    out_wav = audio_dir / f"{txt.stem}.wav"
                    if out_wav.exists() and out_wav.stat().st_size > 0:
                        log(f"Skipping {txt.name} (Audio exists)")
                        skipped_count += 1
                        continue
                    synth_targets.append((txt, out_wav))

                total_files = len(txt_files)
                completed_count = skipped_count

                def update_synth_progress(chapter_label):
                    pct = 0.4 + (0.3 * (completed_count / max(total_files, 1)))
                    progress_callback(
                        pct,
                        f"Step 2/3: Synthesizing ({completed_count}/{total_files}) {chapter_label}",
                    )

                if worker_count <= 1 or len(synth_targets) <= 1:
                    backend = SupertonicBackend()
                    backend.ensure_model()
                    for txt, out_wav in synth_targets:
                        log(f"Synthesizing {txt.name}...")
                        with open(txt, "r", encoding="utf-8") as f:
                            text_content = f.read().strip()
                        if text_content:
                            wav = backend.synthesize(text_content, voice, max_chars=tts_max_chars)
                            if wav is not None:
                                backend.save_audio(wav, out_wav)
                                log(f"Saved audio: {out_wav.name}")
                        completed_count += 1
                        update_synth_progress(txt.stem)
                else:
                    thread_local = threading.local()

                    def get_thread_backend():
                        if not hasattr(thread_local, "backend"):
                            backend = SupertonicBackend()
                            backend.ensure_model()
                            thread_local.backend = backend
                        return thread_local.backend

                    def synthesize_task(task):
                        txt_path, out_wav_path = task
                        with open(txt_path, "r", encoding="utf-8") as f:
                            text_content = f.read().strip()
                        if not text_content:
                            return ("empty", txt_path.name, out_wav_path.name)
                        backend = get_thread_backend()
                        wav_data = backend.synthesize(text_content, voice, max_chars=tts_max_chars)
                        if wav_data is None:
                            return ("empty", txt_path.name, out_wav_path.name)
                        backend.save_audio(wav_data, out_wav_path)
                        return ("saved", txt_path.name, out_wav_path.name)

                    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                        futures = {
                            executor.submit(synthesize_task, task): task
                            for task in synth_targets
                        }
                        for future in concurrent.futures.as_completed(futures):
                            txt, _ = futures[future]
                            try:
                                status, txt_name, wav_name = future.result()
                                if status == "saved":
                                    log(f"Saved audio: {wav_name}")
                                else:
                                    log(f"Skipped {txt_name} (Empty text)")
                            except Exception as e:
                                log(f"Error synthesizing {txt.name}: {e}")
                            completed_count += 1
                            update_synth_progress(txt.stem)

            # Update status to 'audio_ready' but NOT complete yet
            metadata["status"] = "synthesized"
            with open(book_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=4)

            # --- STEP 3: TIMESTAMPS (WhisperX) ---
            progress_callback(0.7, "Step 3/3: Aligning text...")
            log("--- Step 3: Timestamp Alignment (WhisperX) ---")
            whisperx_python = BookManager._get_whisperx_python()
            whisperx_model_name = BookManager._get_whisperx_model_name()
            whisperx_batch_size = BookManager._get_whisperx_batch_size()
            whisperx_compute_type = BookManager._get_whisperx_compute_type()
            whisperx_device = os.getenv("CADENCE_WHISPERX_DEVICE", "auto").strip() or "auto"
            log(f"WhisperX python: {whisperx_python}")
            log(
                f"WhisperX config: model={whisperx_model_name}, "
                f"compute_type={whisperx_compute_type}, batch_size={whisperx_batch_size}, "
                f"device={whisperx_device}"
            )
            whisperx_script = Path(__file__).resolve().parent / "whisperx_align_cli.py"
            if not whisperx_script.exists():
                raise FileNotFoundError(f"WhisperX alignment script not found: {whisperx_script}")
            
            wav_files = sorted(audio_dir.glob("*.wav"))
            total_wavs = len(wav_files)
            log(f"Aligning {len(wav_files)} audio files...")
            
            for i, wav in enumerate(wav_files):
                pct = 0.7 + (0.3 * (i / max(total_wavs, 1)))
                progress_callback(
                    pct,
                    f"Step 3/3: Aligning ({i + 1}/{total_wavs}) {wav.stem}",
                )
                
                out_json = content_dir / f"{wav.stem}.json"
                if out_json.exists() and out_json.stat().st_size > 0:
                     log(f"Skipping {wav.name} (Timestamps exist)")
                     continue

                source_txt = content_dir / f"{wav.stem}.txt"
                if not source_txt.exists():
                    raise FileNotFoundError(f"Missing source text for {wav.name}: {source_txt}")

                log(f"Aligning {wav.name} with {source_txt.name}...")
                chapter_report = content_dir / f"{wav.stem}.whisperx_report.json"
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
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if result.returncode != 0:
                    log(f"WhisperX failed for {wav.name}")
                    log(result.stdout[-2000:] if result.stdout else "")
                    log(result.stderr[-2000:] if result.stderr else "")
                    continue

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
                log(f"Saved timestamps: {out_json.name}")

            # --- FINALIZE METADATA ---
            log("Finalizing metadata...")
            metadata["status"] = "complete"
            metadata["total_chapters"] = len(wav_files)
            with open(book_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=4)
                
            progress_callback(1.0, "Ready!")
            log("Import process completed successfully.")
            return True

        except Exception as e:
            log(f"Pipeline Error: {e}")
            import traceback
            log(traceback.format_exc())
            return False
