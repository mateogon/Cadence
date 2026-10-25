import os
import sys
import re
import argparse
import time
import numpy as np
from pathlib import Path
from unicodedata import normalize
from tqdm import tqdm  # pip install tqdm

# Reduce ONNX Runtime warning spam by default; override with CADENCE_ORT_LOG_LEVEL.
os.environ.setdefault("ORT_LOG_SEVERITY_LEVEL", os.getenv("CADENCE_ORT_LOG_LEVEL", "3"))
os.environ.setdefault("ORT_LOG_VERBOSITY_LEVEL", "0")

import onnxruntime as ort

# Try to import supertonic; handle error if not found
try:
    from supertonic import TTS
    from supertonic.config import AVAILABLE_LANGUAGES, MAX_TEXT_LENGTH
    from supertonic.utils import chunk_text
except ImportError:
    print("Error: 'supertonic' library not found. Please ensure it is installed.")
    sys.exit(1)

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from system.runtime_settings import resolve_tts_settings

# --- Configuration ---
DEFAULT_VOICE = "M3"  # A solid default voice
DEFAULT_ONNX_PROVIDER_ORDER = [
    "CUDAExecutionProvider",
    "CPUExecutionProvider",
]

UNICODE_PUNCT_TRANSLATIONS = str.maketrans({
    "\u2018": "'",   # left single quote
    "\u2019": "'",   # right single quote / curly apostrophe
    "\u201B": "'",   # single high-reversed-9 quotation mark
    "\u2032": "'",   # prime
    "\u02BC": "'",   # modifier letter apostrophe
    "\u2010": "-",   # hyphen
    "\u2011": "-",   # non-breaking hyphen
    "\u2012": "-",   # figure dash
    "\u2013": "-",   # en dash
    "\u2014": ", ",  # em dash -> comma pause
    "\u2015": ", ",  # horizontal bar -> comma pause
    "\u2212": "-",   # minus sign
    "\u2026": "...", # ellipsis
    "\u00A0": " ",   # no-break space
})

# --- CUDA Setup (Windows Specific) ---
# Optional: add system CUDA DLL path. Disabled by default to avoid conflicts with
# PyTorch bundled CUDA/cuDNN DLLs (can trigger WinError 127 on torch import).
USE_SYSTEM_CUDA_DLL_PATH = os.getenv("CADENCE_ADD_SYSTEM_CUDA_DLL_PATH", "").strip() == "1"
if USE_SYSTEM_CUDA_DLL_PATH:
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

def sanitize_text(text, text_processor):
    """Normalize punctuation and remove characters rejected by the model."""
    normalized = normalize("NFKC", text.translate(UNICODE_PUNCT_TRANSLATIONS))
    _, unsupported = text_processor.validate_text(normalized)
    unsupported = set(unsupported)

    # Preserve words when the model cannot represent in-word apostrophes.
    if "'" in unsupported:
        normalized = re.sub(r"(?<=\w)'(?=\w)", "", normalized)

    output = []
    for ch in normalized:
        if ch not in unsupported:
            output.append(ch)
        elif ch != "'":
            output.append(" ")
    return re.sub(r"\s+", " ", "".join(output)).strip()


def synthesize_text(tts, text, voice_style, max_chars=1600, lang="na", model=None):
    """Use the same synthesis settings for the application and standalone CLI."""
    settings = resolve_tts_settings(model=model)
    clean_text = sanitize_text(text, tts.model.text_processor)
    if not clean_text:
        return None
    language = str(lang or "na").strip().lower().replace("_", "-").split("-")[0]
    if language not in AVAILABLE_LANGUAGES:
        language = "na"
    # Keep long chapters under the package's per-call text limit.
    batches = chunk_text(clean_text, MAX_TEXT_LENGTH) if len(clean_text) > MAX_TEXT_LENGTH else [clean_text]
    audio = []
    for batch in batches:
        wav, _ = tts.synthesize(
            batch,
            voice_style=voice_style,
            lang=language,
            max_chunk_length=max_chars,
            speed=settings["speed"],
            total_steps=settings["steps"],
        )
        audio.append(wav)
    return audio[0] if len(audio) == 1 else np.concatenate(audio, axis=1)


def init_tts_engine(model=None):
    """Initializes Supertonic with GPU checks."""
    print("Initializing TTS Engine...")

    # Default to error-only ORT logs unless user explicitly asks for warnings/info.
    # 0=verbose,1=info,2=warning,3=error,4=fatal
    log_level = int(os.getenv("CADENCE_ORT_LOG_LEVEL", "3"))
    os.environ["ORT_LOG_SEVERITY_LEVEL"] = str(log_level)
    try:
        ort.set_default_logger_severity(log_level)
    except Exception:
        pass

    providers = ort.get_available_providers()
    print(f"ONNX available providers: {providers}")

    # The 1.3.1 loader reads this module constant when creating ONNX sessions.
    force_cpu = os.getenv("CADENCE_FORCE_CPU", "").strip() == "1"
    use_tensorrt = os.getenv("CADENCE_USE_TENSORRT", "").strip() == "1"
    cuda_only = os.getenv("CADENCE_CUDA_ONLY", "").strip() == "1"

    if force_cpu:
        requested = ["CPUExecutionProvider"]
    elif cuda_only and "CUDAExecutionProvider" in providers:
        # Strict CUDA mode can reduce CPU fallback/copy overhead, but may fail if
        # the model requires unsupported ops on CUDA.
        requested = ["CUDAExecutionProvider"]
    else:
        preferred = list(DEFAULT_ONNX_PROVIDER_ORDER)
        if use_tensorrt:
            preferred = ["TensorrtExecutionProvider"] + preferred
        requested = [p for p in preferred if p in providers]
        if not requested:
            requested = ["CPUExecutionProvider"]

    try:
        import supertonic.loader as st_loader

        st_loader.DEFAULT_ONNX_PROVIDERS = requested
        print(f"Supertonic requested providers: {requested}")
    except Exception as e:
        print(f"⚠️  Could not patch Supertonic providers: {e}")

    tts = TTS(model=resolve_tts_settings(model=model)["model"], auto_download=True)

    # Report real providers actually bound to the model sessions.
    try:
        sessions = [
            tts.model.dp_ort,
            tts.model.text_enc_ort,
            tts.model.vector_est_ort,
            tts.model.vocoder_ort,
        ]
        active = sorted({tuple(s.get_providers()) for s in sessions})
        print(f"Supertonic active providers per session: {active}")
    except Exception as e:
        print(f"⚠️  Could not read active providers: {e}")

    return tts

# --- Main Logic ---

def process_folder(input_dir, output_dir, voice_name, lang="na", model=None):
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
    tts = init_tts_engine(model=model)
    voice_style = tts.get_voice_style(voice_name)

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

                wav = synthesize_text(tts, text, voice_style, max_chars=800, lang=lang, model=model)
                if wav is not None:
                    tts.save_audio(wav, out_file_path)

            except Exception as e:
                tqdm.write(f"\n❌ Error processing {filename}: {e}")

            pbar.update(1)

    total_time = time.time() - total_start
    print(f"\n✨ Done! Processed {len(files)} files in {total_time:.2f}s.")

# --- CLI Entry Point ---

def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate an audiobook from text files using Supertonic TTS.")
    parser.add_argument("input_folder", nargs="?", help="Folder containing .txt files")
    parser.add_argument("--output", "-o", help="Output folder (default: input_folder_audio)")
    parser.add_argument("--voice", "-v", default=DEFAULT_VOICE, help="Voice ID (default: M3)")
    parser.add_argument("--lang", default="na", help="Book language code (default: na)")
    parser.add_argument("--model", help="Supertonic model (default: CADENCE_TTS_MODEL or supertonic-3)")
    parser.add_argument("--list-voices", action="store_true", help="List available voices and exit")
    args = parser.parse_args(argv)

    if args.list_voices:
        tts = init_tts_engine(model=args.model)
        print(f"Available Voices: {', '.join(tts.voice_style_names)}")
        return
    if not args.input_folder:
        parser.error("input_folder is required unless --list-voices is used")
    if not os.path.isdir(args.input_folder):
        parser.error(f"Input folder '{args.input_folder}' does not exist.")
    out_dir = args.output or f"{args.input_folder}_audio"
    process_folder(args.input_folder, out_dir, args.voice, lang=args.lang, model=args.model)


if __name__ == "__main__":
    main()
