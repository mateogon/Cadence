import os
import sys
import re
import argparse
import time
import numpy as np
import soundfile as sf
import onnxruntime as ort
from unicodedata import normalize
from tqdm import tqdm  # pip install tqdm

# Try to import supertonic; handle error if not found
try:
    from supertonic import TTS
except ImportError:
    print("Error: 'supertonic' library not found. Please ensure it is installed.")
    sys.exit(1)

# --- Configuration ---
DEFAULT_VOICE = "M3"  # A solid default voice

# --- CUDA Setup (Windows Specific) ---
# Auto-detects installed CUDA versions and adds the latest to the DLL path
CUDA_BASE_PATH = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA"
if os.path.exists(CUDA_BASE_PATH) and hasattr(os, 'add_dll_directory'):
    # Find all v* directories
    cuda_dirs = []
    try:
        for entry in os.scandir(CUDA_BASE_PATH):
            if entry.is_dir() and entry.name.startswith("v"):
                cuda_dirs.append(entry.path)
    except OSError as e:
        print(f"⚠️  Error scanning CUDA directory: {e}")

    # Sort reverse alphabetically (e.g., v12.8 > v12.4)
    cuda_dirs.sort(reverse=True)
    
    cuda_found = False
    for cuda_dir in cuda_dirs:
        bin_path = os.path.join(cuda_dir, "bin")
        if os.path.exists(bin_path):
            try:
                os.add_dll_directory(bin_path)
                print(f"✅ Added CUDA DLL path: {bin_path}")
                cuda_found = True
                break # Stop after adding the latest valid one
            except OSError:
                print(f"⚠️  Failed to add CUDA DLL path: {bin_path}")
    
    if not cuda_found:
         print(f"⚠️  No valid CUDA v*\\bin directories found in {CUDA_BASE_PATH}")
elif os.name == 'nt':
     print("ℹ️  CUDA base directory not found or add_dll_directory not supported.")

# --- Helper Functions ---

def sanitize_text(text, supported_chars):
    """Cleans text to ensure compatibility with the model."""
    normalized = normalize("NFKD", text)
    output = []
    
    for ch in normalized:
        if ch in supported_chars:
            output.append(ch)
        else:
            # Replace unsupported non-space chars with space to prevent word merging
            if not ch.isspace():
                output.append(" ")
    
    # Collapse multiple spaces into one
    return re.sub(r"\s+", " ", "".join(output)).strip()

def get_smart_chunks(text, max_chars=800):
    """
    Splits text into chunks that fit within the context window,
    prioritizing sentence boundaries.
    """
    # 1. Split by sentence endings (. ! ? followed by space)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        # If adding the next sentence exceeds limit, push current chunk
        if len(current_chunk) + len(sentence) < max_chars:
            current_chunk = (current_chunk + " " + sentence).strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            
            # If the single sentence is huge (bigger than max_chars), hard split it by commas
            if len(sentence) >= max_chars:
                sub_parts = re.split(r'(?<=[,;])\s+', sentence)
                temp_sub = ""
                for part in sub_parts:
                    if len(temp_sub) + len(part) < max_chars:
                        temp_sub = (temp_sub + " " + part).strip()
                    else:
                        if temp_sub: chunks.append(temp_sub)
                        temp_sub = part
                current_chunk = temp_sub
            else:
                current_chunk = sentence

    if current_chunk:
        chunks.append(current_chunk)

    return [c for c in chunks if c.strip()]

def init_tts_engine():
    """Initializes Supertonic with GPU checks."""
    print("Initializing TTS Engine...")

    providers = ort.get_available_providers()
    
    if 'CUDAExecutionProvider' in providers:
        print(f"🚀 CUDA Detected. Running on GPU ({providers[0]})")
    else:
        print(f"⚠️  CUDA NOT Detected. Running on CPU (This will be slower). Available: {providers}")

    # Initialize
    return TTS(auto_download=True)

# --- Main Logic ---

def process_folder(input_dir, output_dir, voice_name):
    # 1. Setup
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 2. Find text files
    files = sorted([f for f in os.listdir(input_path) if f.lower().endswith('.txt')])
    
    if not files:
        print(f"❌ No .txt files found in {input_dir}")
        return

    print(f"Found {len(files)} chapters. Using Voice: {voice_name}")
    print(f"Output Directory: {output_path.resolve()}\n")

    # 3. Initialize Engine
    tts = init_tts_engine()
    voice_style = tts.get_voice_style(voice_name=voice_name)
    supported_chars = tts.model.text_processor.supported_character_set

    # 4. Process Loop
    # We use tqdm for a nice progress bar
    total_start = time.time()
    
    with tqdm(total=len(files), unit="file", desc="Generating Audiobook") as pbar:
        for filename in files:
            file_path = os.path.join(input_path, filename)
            out_filename = os.path.splitext(filename)[0] + ".wav"
            out_file_path = os.path.join(output_path, out_filename)

            # Update progress bar description
            pbar.set_postfix(file=filename[:20])

            try:
                # Read Text
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read().strip()

                if not text:
                    pbar.update(1)
                    continue

                # Chunking
                chunks = get_smart_chunks(text)
                
                audio_segments = []
                
                # Process chunks (silently, unless error)
                for chunk in chunks:
                    clean_chunk = sanitize_text(chunk, supported_chars)
                    if not clean_chunk: continue
                    
                    # Synthesize
                    wav, _ = tts.synthesize(clean_chunk, voice_style=voice_style)
                    audio_segments.append(wav)

                if audio_segments:
                    # Concatenate all chunks for this chapter
                    # Supertonic outputs (1, N), we concat along axis 1
                    final_wav = np.concatenate(audio_segments, axis=1)
                    
                    # Save
                    tts.save_audio(final_wav, out_file_path)

            except Exception as e:
                tqdm.write(f"\n❌ Error processing {filename}: {e}")
            
            pbar.update(1)

    total_time = time.time() - total_start
    print(f"\n✨ Done! Processed {len(files)} files in {total_time:.2f}s.")

# --- CLI Entry Point ---

if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Generate an audiobook from a folder of text files using Supertonic TTS.")
    
    parser.add_argument("input_folder", help="Path to the folder containing .txt files")
    parser.add_argument("--output", "-o", help="Path to output folder (default: input_folder_audio)")
    parser.add_argument("--voice", "-v", default=DEFAULT_VOICE, help="Voice ID (e.g., M1, M2, F1, F2... Default: M3)")
    parser.add_argument("--list-voices", action="store_true", help="List available voices and exit")

    args = parser.parse_args()

    if args.list_voices:
        print("Available Voices: M1, M2, M3, M4, M5, F1, F2, F3, F4, F5")
        sys.exit(0)

    # Determine Output Folder
    if args.output:
        out_dir = args.output
    else:
        out_dir = f"{args.input_folder}_audio"

    if not os.path.exists(args.input_folder):
        print(f"Error: Input folder '{args.input_folder}' does not exist.")
        sys.exit(1)

    process_folder(args.input_folder, out_dir, args.voice)