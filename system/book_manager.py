import os
import json
import shutil
import subprocess
import time
import threading
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

            # 1. Setup Folders
            if book_dir.exists(): 
                log(f"Removing existing directory: {book_dir}")
                shutil.rmtree(book_dir)
            content_dir.mkdir(parents=True)

            # --- STEP 1: EXTRACTION (Calibre) ---
            progress_callback(0.1, "Step 1/3: Extracting Text...")
            log("--- Step 1: Text Extraction ---")
            
            temp_dir = Path("temp_extraction")
            if temp_dir.exists(): shutil.rmtree(temp_dir)
            
            # Unpack EPUB
            log(f"Unpacking EPUB to {temp_dir}...")
            cmd = [CALIBRE_PATH, str(epub_file), str(temp_dir)]
            log(f"Command: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode != 0:
                log(f"Calibre Error: {result.stderr}")
                return False
            else:
                log("Unpack successful.")
            
            # Find and Clean HTML files
            html_files = sorted(list(temp_dir.rglob("*.html")) + list(temp_dir.rglob("*.xhtml")))
            log(f"Found {len(html_files)} HTML/XHTML files.")
            chapter_count = 0
            
            for i, html in enumerate(html_files):
                if html.stat().st_size < 300: 
                    log(f"Skipping small file: {html.name} ({html.stat().st_size} bytes)")
                    continue 
                
                chapter_count += 1
                out_txt = content_dir / f"ch_{chapter_count:03d}.txt"
                log(f"Converting {html.name} -> {out_txt.name}")
                
                subprocess.run([
                    CALIBRE_PATH, str(html), str(out_txt), 
                    "--txt-output-format=plain", "--smarten-punctuation"
                ], shell=True, capture_output=True)

            shutil.rmtree(temp_dir)
            log(f"Extraction complete. {chapter_count} chapters prepared.")

            # --- STEP 2: AUDIO GENERATION (Supertonic) ---
            progress_callback(0.4, "Step 2/3: Synthesizing Audio (GPU)...")
            log("--- Step 2: Audio Synthesis ---")
            
            # We import here to avoid loading heavy libraries if just listing books
            log("Importing Supertonic engine...")
            from generate_audiobook_supertonic import init_tts_engine
            
            tts = init_tts_engine() # Assumes your supertonic script is importable or adapted
            txt_files = sorted(content_dir.glob("*.txt"))
            log(f"Found {len(txt_files)} text chapters to synthesize with voice '{voice}'.")
            
            for i, txt in enumerate(txt_files):
                pct = 0.4 + (0.3 * (i / len(txt_files)))
                progress_callback(pct, f"Synthesizing Ch {i+1}...")
                
                out_wav = content_dir / f"{txt.stem}.wav"
                
                log(f"Synthesizing {txt.name}...")
                with open(txt, 'r', encoding='utf-8') as f:
                    text_content = f.read()
                
                # Using the logic from your script
                # (You might need to adapt the generate function call based on your exact script structure)
                # For MVP, assuming a direct synthesis call:
                voice_style = tts.get_voice_style(voice)
                wav, _ = tts.synthesize(text_content, voice_style=voice_style)
                tts.save_audio(wav, str(out_wav))
                log(f"Saved audio: {out_wav.name}")

            # --- STEP 3: TIMESTAMPS (WhisperX) ---
            progress_callback(0.7, "Step 3/3: Aligning Text...")
            log("--- Step 3: Timestamp Alignment (WhisperX) ---")
            import whisperx
            import torch
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            log(f"Using device: {device}")
            model = whisperx.load_model("small", device, compute_type="int8")
            
            wav_files = sorted(content_dir.glob("*.wav"))
            log(f"Aligning {len(wav_files)} audio files...")
            
            for i, wav in enumerate(wav_files):
                pct = 0.7 + (0.3 * (i / len(wav_files)))
                progress_callback(pct, f"Aligning Ch {i+1}...")
                log(f"Aligning {wav.name}...")
                
                # Transcribe
                audio = whisperx.load_audio(str(wav))
                result = model.transcribe(audio, batch_size=16)
                
                # Align
                model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=device)
                aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, device, return_char_alignments=False)
                
                # Save JSON
                word_list = []
                for segment in aligned_result["segments"]:
                    for word in segment["words"]:
                        if 'start' in word:
                            word_list.append({
                                "word": word["word"],
                                "start": word["start"],
                                "end": word["end"]
                            })
                            
                out_json = content_dir / f"{wav.stem}.json"
                with open(out_json, "w", encoding='utf-8') as f:
                    json.dump(word_list, f, indent=2)
                log(f"Saved timestamps: {out_json.name}")

            # --- FINALIZE METADATA ---
            log("Finalizing metadata...")
            meta = {
                "title": epub_file.stem,
                "author": "Unknown",
                "voice": voice,
                "total_chapters": len(wav_files),
                "last_chapter": 1,   # 1-based index
                "last_timestamp": 0.0
            }
            
            with open(book_dir / "metadata.json", "w") as f:
                json.dump(meta, f, indent=2)
                
            progress_callback(1.0, "Ready!")
            log("Import process completed successfully.")
            return True

        except Exception as e:
            log(f"Pipeline Error: {e}")
            import traceback
            log(traceback.format_exc())
            return False
