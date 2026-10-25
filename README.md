![Cadence](assets/branding/cadence-badge.svg)

# Cadence
Cadence is an immersive reading pipeline: **book file -> chapter text -> audiobook audio -> word-level synced reader data**.

## Overview
- Imports EPUB/MOBI/AZW3 files (MOBI/AZW3 are converted to EPUB via Calibre) and extracts ordered chapter text.
- Synthesizes chapter audio with [Supertonic 3](https://pypi.org/project/supertonic/1.3.1/) across 31 languages.
- Aligns audio to text with WhisperX for word timestamps.
- Plays back in a synced reader/player UI.
- Uses a streaming chapter pipeline so reading can start before full import finishes.

## Pipeline
1. Source normalization: MOBI/AZW3 -> EPUB (Calibre, when needed)
2. EPUB extraction (Calibre) -> `library/<book>/content/ch_XXX.txt`
3. Per chapter: TTS synthesis (Supertonic) -> `library/<book>/audio/ch_XXX.wav`
4. Per chapter: Alignment (WhisperX) -> `library/<book>/content/ch_XXX.json`
5. Player can read chapters as soon as each chapter has audio + alignment.

## Import Behavior
- Cadence now runs **chapter-by-chapter interleaved processing**:
  - If a chapter already has `.wav`, Cadence skips synthesis and aligns it.
  - If `.wav` is missing, Cadence synthesizes first, then aligns.
  - If `.wav` and `.json` both exist, Cadence skips that chapter.
- This makes resume robust after interruptions and enables immediate reading while import is still running.
- Library cards update live with ready counts (`Audio x/y`, `Alignment x/y`) during import.
- EPUB `dc:language` is saved in `metadata.json` and passed to Supertonic. Regional tags such as `es-CL` use their base code; missing or unsupported codes use `na`.
- New books store `tts_backend` and `tts_model`. Resume uses the book's stored voice and model even if the current settings change.
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
- Windows 10/11
- Python 3.12
- Calibre (`ebook-convert.exe`) installed at:
  - `C:\Program Files\Calibre2\ebook-convert.exe`
- FFmpeg (`ffmpeg.exe`) available in `PATH` (required for Qt player speed control)
- NVIDIA GPU recommended for faster TTS/ASR

## Install
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Install one runtime profile (fresh venv recommended):

GPU profile (default):
```powershell
pip install -r requirements-gpu.txt
```

CPU profile:
```powershell
pip install -r requirements-cpu.txt
```

Backward-compatible default (`requirements.txt`) points to GPU profile.
Do not install both CPU and GPU ONNX Runtime packages in the same environment.

If you use a separate WhisperX venv, point Cadence to it:
```powershell
$env:CADENCE_WHISPERX_PYTHON="C:\Users\mateo\Desktop\Cadence\venv_whisperx\Scripts\python.exe"
```

## Run
```powershell
.\venv\Scripts\Activate.ps1
python main.py
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
