import os
import json
import shutil
import subprocess
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
            progress_callback(0.4, "Step 2/3: Synthesizing Audio...")
            log("--- Step 2: Audio Synthesis ---")
            
            from generate_audiobook_supertonic import init_tts_engine, get_smart_chunks, sanitize_text
            tts = init_tts_engine() 
            txt_files = sorted(content_dir.glob("*.txt"))
            log(f"Found {len(txt_files)} text chapters for voice '{voice}'.")
            
            supported_chars = tts.model.text_processor.supported_character_set
            
            audio_dir = book_dir / "audio"
            audio_dir.mkdir(exist_ok=True)

            import numpy as np
            for i, txt in enumerate(txt_files):
                pct = 0.4 + (0.3 * (i / len(txt_files)))
                progress_callback(pct, f"Synthesizing Ch {i+1}...")
                
                out_wav = audio_dir / f"{txt.stem}.wav"
                
                # Check if audio already exists (Resume capability)
                if out_wav.exists() and out_wav.stat().st_size > 0:
                    log(f"Skipping {txt.name} (Audio exists)")
                    continue

                log(f"Synthesizing {txt.name}...")
                
                with open(txt, 'r', encoding='utf-8') as f:
                    text_content = f.read().strip()
                
                if not text_content: continue

                # Chunking matches the CLI script for better stability/quality
                chunks = get_smart_chunks(text_content)
                audio_segments = []
                
                try:
                    voice_style = tts.get_voice_style(voice)
                except:
                    voice_style = tts.get_voice_style(list(tts.voices.keys())[0])

                for chunk in chunks:
                    # Use the library's own sanitization + my extra map if needed?
                    # Actually sanitize_text from generator is quite thorough
                    clean_chunk = sanitize_text(chunk, supported_chars)
                    if not clean_chunk: continue
                    
                    wav, _ = tts.synthesize(clean_chunk, voice_style=voice_style, lang="en")
                    audio_segments.append(wav)

                if audio_segments:
                    # Concat and save using the library's method (safer)
                    final_wav = np.concatenate(audio_segments, axis=1)
                    tts.save_audio(final_wav, str(out_wav))
                    log(f"Saved audio: {out_wav.name}")

            # Update status to 'audio_ready' but NOT complete yet
            metadata["status"] = "synthesized"
            with open(book_dir / "metadata.json", "w") as f:
                json.dump(metadata, f, indent=4)

            # --- STEP 3: TIMESTAMPS (WhisperX) ---
            progress_callback(0.7, "Step 3/3: Aligning Text...")
            log("--- Step 3: Timestamp Alignment (WhisperX) ---")
            import whisperx
            import torch
            
            log(f"Torch version: {torch.__version__}")
            log(f"CUDA available: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                log(f"CUDA device: {torch.cuda.get_device_name(0)}")
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            log(f"Using device: {device}")
            try:
                model = whisperx.load_model("small", device, compute_type="int8")
            except:
                log("Failed to load model on GPU, falling back to CPU")
                device = "cpu"
                model = whisperx.load_model("small", device, compute_type="int8")
            
            wav_files = sorted(audio_dir.glob("*.wav"))
            log(f"Aligning {len(wav_files)} audio files...")
            
            for i, wav in enumerate(wav_files):
                pct = 0.7 + (0.3 * (i / len(wav_files)))
                progress_callback(pct, f"Aligning Ch {i+1}...")
                
                out_json = content_dir / f"{wav.stem}.json"
                if out_json.exists() and out_json.stat().st_size > 0:
                     log(f"Skipping {wav.name} (Timestamps exist)")
                     continue

                log(f"Aligning {wav.name}...")
                
                audio = whisperx.load_audio(str(wav))
                result = model.transcribe(audio, batch_size=16)
                
                # WhisperX Alignment
                model_a, alignment_meta = whisperx.load_align_model(language_code=result["language"], device=device)
                aligned_result = whisperx.align(result["segments"], model_a, alignment_meta, audio, device, return_char_alignments=False)
                
                # Extract raw ASR word list with timestamps
                asr_words = []
                for segment in aligned_result["segments"]:
                    for word in segment["words"]:
                        if 'start' in word:
                            asr_words.append({
                                "word": word["word"],
                                "start": word["start"],
                                "end": word["end"]
                            })
                
                # --- ROBUST ALIGNMENT WITH ORIGINAL TEXT ---
                log(f"Aligning ASR data with original text: {txt.name}")
                
                # Read original text
                with open(txt, 'r', encoding='utf-8') as f:
                    original_text = f.read()
                
                # Perform robust alignment
                try:
                    final_word_list = BookManager.align_timestamps(original_text, asr_words)
                    
                    # Calculate coverage stats for log
                    total_chars = len(original_text)
                    timed_chars = sum(len(w['word']) for w in final_word_list if w['end'] > 0)
                    log(f"Alignment coverage (approx): {timed_chars/total_chars:.1%}")
                    
                except Exception as e:
                    log(f"Alignment Verification Failed: {e}. Falling back to ASR output.")
                    print(f"Alignment Verification Failed: {e}. Falling back to ASR output.")
                    final_word_list = asr_words

                with open(out_json, "w", encoding='utf-8') as f:
                    json.dump(final_word_list, f, indent=2)
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
