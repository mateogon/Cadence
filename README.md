![Cadence](assets/branding/cadence-badge.svg)

# Cadence
Cadence is an immersive reading pipeline: **book file -> chapter text -> audiobook audio -> word-level synced reader data**.

## Overview
- Imports EPUB/MOBI/AZW3 files (MOBI/AZW3 are converted to EPUB via Calibre) and extracts ordered chapter text.
- Synthesizes chapter audio with [Supertonic 3](https://pypi.org/project/supertonic/1.3.1/) across 31 languages, or optional Kokoro.
- Uses Kokoro native English word timestamps when available; otherwise aligns with WhisperX.
- Plays back in a synced reader/player UI.
- Uses a streaming chapter pipeline so reading can start before full import finishes.

## Pipeline
1. Source normalization: MOBI/AZW3 -> EPUB (Calibre, when needed)
2. EPUB extraction (Calibre) -> `library/<book>/content/ch_XXX.txt`
3. Per chapter: TTS synthesis (Supertonic or Kokoro) -> `library/<book>/audio/ch_XXX.wav`
4. Per chapter: Alignment (Kokoro native timestamps or WhisperX) -> `library/<book>/content/ch_XXX.json`
5. Player can read chapters as soon as each chapter has audio + alignment.

## Import Behavior
- Cadence now runs **chapter-by-chapter interleaved processing**:
  - If a chapter already has `.wav`, Cadence skips synthesis and aligns it.
  - If `.wav` is missing, Cadence synthesizes first, then aligns.
  - If `.wav` and `.json` both exist, Cadence skips that chapter.
- This makes resume robust after interruptions and enables immediate reading while import is still running.
- Import reports success only when every chapter has non-empty audio and alignment. Failed chapters remain available for resume and the reader shows the import as incomplete.
- Library cards update live with ready counts (`Audio x/y`, `Alignment x/y`) during import.
- EPUB `dc:language` is saved in `metadata.json` and passed to Supertonic. Regional tags such as `es-CL` use their base code; missing or unsupported codes use `na`.
- New books store `tts_backend` and `tts_model`. Resume uses the book's stored backend, voice and model even if the current settings change.
- Older books without TTS identity keep their existing audio. For missing chapters, Cadence warns that the historical model is unknown, uses the configured Supertonic model once, and stores that continuation configuration for later resumes. This does not establish which model produced older WAV files. Select the known older model before continuing if needed.

## Read While Importing
Cadence processes books one chapter at a time, not as one long batch.

- As soon as a chapter finishes synthesis + alignment, it is immediately readable.
- You can open the reader and start from available chapters while the rest of the book continues importing.
- If import is interrupted, re-import resumes from existing chapter outputs instead of starting over.

## UI Preview
![Library While Importing](docs/media/library-importing.png)
![RSVP View](docs/media/rsvp.gif)
![Context View](docs/media/context.gif)

## Requirements
- Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Apple Silicon macOS, Windows 10/11 x64, or Linux x64.
- [Calibre](https://calibre-ebook.com/download) for importing books.
- FFmpeg in `PATH` for playback speed control and WhisperX.
- An NVIDIA GPU is optional on Windows/Linux. The default install uses CPU wheels.

## Install
### macOS (Apple Silicon)
1. Install FFmpeg with Homebrew:
   ```bash
   brew install ffmpeg
   ```
2. Install the [Calibre app](https://calibre-ebook.com/download_osx) in `/Applications`.
3. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) if needed.
4. Install Cadence from the repository root:
   ```bash
   uv sync --locked
   ```
5. Start Cadence:
   ```bash
   uv run main.py
   ```

### Windows
1. Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Install [Calibre](https://calibre-ebook.com/download_windows) at its default location, or set `CADENCE_CALIBRE_PATH`.
3. Install FFmpeg and add its directory to `PATH`.
4. Install Cadence from the repository root:
   ```powershell
   uv sync --locked
   ```
5. Start Cadence:
   ```powershell
   uv run main.py
   ```

### Linux
1. Install Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
2. Install Calibre, FFmpeg, and the Qt system libraries for your distribution. On Ubuntu:
   ```bash
   sudo apt-get install calibre ffmpeg libegl1 libgl1 libpulse0 libxkbcommon-x11-0 libxcb-cursor0
   ```
3. Install Cadence from the repository root:
   ```bash
   uv sync --locked
   ```
4. Start Cadence:
   ```bash
   uv run main.py
   ```

### Runtime profiles
`uv sync --locked` creates `.venv` with CPU ONNX Runtime and matching Torch/Torchaudio 2.6.0.
It also installs the development tools. Existing `venv` directories are kept.

For NVIDIA GPUs on Windows/Linux, install and run the GPU profile:
```bash
uv sync --locked --no-group cpu --extra gpu
uv run --no-group cpu --extra gpu main.py
```
This selects ONNX Runtime GPU 1.24.1 and the official CUDA 12.4 Torch/Torchaudio wheels.
The machine also needs compatible NVIDIA drivers and ONNX Runtime's [CUDA/cuDNN runtime libraries](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#requirements).
Use the same profile flags for each `uv run`; a plain `uv run` restores the default CPU profile.
The `cpu` group and `gpu` extra conflict, so uv rejects a request for both.
The GPU extra is for Windows/Linux; use the default profile on macOS.

### Optional Kokoro backend
1. Install the optional backend:
   ```bash
   uv sync --locked --extra kokoro
   ```
2. Start with the same extra enabled:
   ```bash
   uv run --extra kokoro main.py
   ```
3. In runtime settings, set `CADENCE_TTS_BACKEND` to `kokoro`. Leave
   `CADENCE_KOKORO_DEVICE` at `auto` to select CUDA, then MPS, then CPU.
4. Select `auto` in the existing voice selector to use a voice for the book's
   language, or choose a compatible Kokoro voice explicitly.

The optional install pins Kokoro 0.9.4, `preshed==3.0.9`, and the English spaCy
model. The preshed pin avoids the English tokenizer failure seen on macOS.
Keep `--extra kokoro` on each `uv run`; plain `uv run` removes the optional packages.
On Windows/Linux with NVIDIA, combine it with `--no-group cpu --extra gpu`.
First synthesis downloads `hexgrad/Kokoro-82M` and the selected voice.

Kokoro supports English, Spanish, French, Hindi, Italian, Portuguese, Japanese,
and Mandarin voices. Japanese and Mandarin need additional upstream language
packages; the supplied extra includes English and eSpeak-based tokenization.
For Japanese, start with `uv run --extra kokoro --with 'misaki[ja]' main.py`;
use `misaki[zh]` for Mandarin. These optional language paths are not covered by CI.
An unsupported book language or incompatible explicit voice stops the import
with an error. Existing Supertonic voice selections map to Kokoro's language
default for a new book. New English books default to `af_heart` (US/general English) or `bf_emma` (UK).
Other languages retain catalog order. Resume always keeps the book's saved backend and voice.

Cadence packs complete sentences into paragraph blocks of about 450 characters.
It preserves common abbreviations and decimals when finding sentence boundaries.
A sentence longer than 450 characters remains whole; Kokoro handles its internal
splits. This avoids added mid-sentence pauses from arbitrary word wrapping and
inference overhead from synthesizing every short sentence separately. Blank lines
preserve paragraph boundaries. Kokoro's native English
word times accumulate the duration of every audio fragment before the next
fragment starts. Missing or invalid times trigger WhisperX for the whole chapter,
with a log entry. Non-English synthesis currently uses that fallback.

MPS enables PyTorch's CPU fallback for unsupported operators before loading
Torch. `CADENCE_KOKORO_DEVICE=cpu` forces CPU; an unavailable explicit accelerator
falls back to CPU with a log message. `CADENCE_TTS_SPEED` applies to both backends;
`CADENCE_TTS_MODEL`, `CADENCE_TTS_STEPS`, and `CADENCE_TTS_MAX_CHARS` configure
Supertonic only. Kokoro's model identity is saved with each book.

The lockfile uses version-specific [uv metadata overrides](https://docs.astral.sh/uv/concepts/resolution/#dependency-metadata)
for Supertonic 1.3.1 and faster-whisper 1.1.0. Each package requests the CPU `onnxruntime`
distribution upstream, although both ONNX distributions expose the same API. The overrides
remove only that requirement. Cadence's selected profile supplies exactly one runtime.
Use uv for installation; plain pip does not apply these overrides.

Supertonic uses CPU by default on macOS. Measurements on an Apple M3 Pro used a
71-word Spanish chapter (M3 voice, 8 steps, speed 1.05, seed 42; 26.54 seconds of audio).
CPU synthesis took
7.33–8.38 seconds over three runs (median 7.58). CoreML took 36.00 seconds on its
first synthesis; its second had not finished after 140 seconds and was stopped.
Model loading took 0.74 seconds for CPU and 10.66 seconds for CoreML.
These measurements apply to this chapter and machine. To try CoreML when available,
set `CADENCE_USE_COREML=1` before starting Cadence; `CADENCE_FORCE_CPU=1` takes priority.

WhisperX uses CPU with `int8` when CUDA is unavailable. Faster-whisper has no MPS backend.
Cadence verifies the bundled VAD checkpoint hash and temporarily permits its known metadata classes during loading. Torch keeps `weights_only` loading enabled; no local wrapper is needed. External WhisperX environments must provide the pinned compatible dependencies and Torch 2.6 or newer.

Calibre lookup uses `CADENCE_CALIBRE_PATH`, then `PATH`, the macOS app path, and the Windows default. An invalid explicit override fails instead of silently selecting another installation. Alignment uses `CADENCE_WHISPERX_PYTHON` first, then the running interpreter (`sys.executable`), `.venv`, and `venv`.
To keep a separate WhisperX environment, set its interpreter before starting Cadence:
```powershell
$env:CADENCE_WHISPERX_PYTHON="C:\path\to\venv_whisperx\Scripts\python.exe"
```
```bash
export CADENCE_WHISPERX_PYTHON="/path/to/venv_whisperx/bin/python"
```

## Run
```bash
uv run main.py
```

## Configuration
Cadence uses `cadence_settings.json` (managed from the UI settings cog next to **Import Book**).

- Settings are persisted automatically when you click **Apply**.
- Settings are applied immediately to the current app process.
- `CADENCE_*` environment variables are still usable for one-off CLI/script runs.

Useful keys:
- `CADENCE_EXTRACT_WORKERS`
- `CADENCE_SYNTH_WORKERS`
- `CADENCE_TTS_MAX_CHARS`
- `CADENCE_TTS_BACKEND`: `supertonic` (default) or `kokoro`.
- `CADENCE_KOKORO_DEVICE`: `auto` (default), `cpu`, `cuda`, or `mps`.
- `CADENCE_TTS_MODEL`: `supertonic-3` by default; `supertonic-2` and `supertonic` remain available.
- `CADENCE_TTS_SPEED`: `0.7`–`2.0`, default `1.05`.
- `CADENCE_TTS_STEPS`: integer `1`–`100`, default `8`.
- `CADENCE_FORCE_CPU`
- `CADENCE_CUDA_ONLY`
- `CADENCE_WHISPERX_MODEL`
- `CADENCE_WHISPERX_BATCH_SIZE`
- `CADENCE_WHISPERX_COMPUTE_TYPE`
- `CADENCE_WHISPERX_DEVICE`
- `CADENCE_WHISPERX_PYTHON`
- `CADENCE_CALIBRE_PATH`

The runtime settings dialog validates the TTS speed and steps before applying them. Supertonic's package handles text chunking through `max_chunk_length`; `CADENCE_TTS_MAX_CHARS` controls that value. A single sentence beyond the package's 100,000-character input limit is not supported.

WhisperX detects each chapter's language for alignment. Its diagnostic `ch_XXX.whisperx_report.json` records the detected language; the reader's alignment JSON format is unchanged.

## Project Docs
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
