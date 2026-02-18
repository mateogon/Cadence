# Cadence
Cadence is an immersive reading pipeline: **EPUB -> chapter text -> audiobook audio -> word-level synced reader data**.

It is built for people who want to read and listen at the same time, with a local-first workflow and clear chapter-level artifacts.

## What It Does
- Imports EPUB files and extracts ordered chapter text.
- Synthesizes chapter audio with Supertonic TTS.
- Aligns audio to text with WhisperX for word timestamps.
- Plays back in a synced reader/player UI.

## Pipeline
1. EPUB extraction (Calibre) -> `library/<book>/content/ch_XXX.txt`
2. TTS synthesis (Supertonic) -> `library/<book>/audio/ch_XXX.wav`
3. Alignment (WhisperX) -> `library/<book>/content/ch_XXX.json`
4. Player reads audio + timestamps for RSVP/immersive reading.

## Media (Placeholders)
![Library View Placeholder](docs/media/library-view.png)
![Player View Placeholder](docs/media/player-view.png)
![Import To Playback GIF Placeholder](docs/media/import-to-playback.gif)

## Requirements
- Windows 10/11 (current scripts and paths are Windows-oriented)
- Python 3.12
- Calibre (`ebook-convert.exe`) installed at:
  - `C:\Program Files\Calibre2\ebook-convert.exe`
- NVIDIA GPU recommended for faster TTS/ASR

## Install
### 1) Main App Environment
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2) Optional: Dedicated WhisperX GPU Environment
If you hit dependency conflicts between Supertonic and WhisperX, use a split env:
```powershell
.\scripts\setup_whisperx_gpu_env.ps1
```

Then point Cadence to that Python:
```powershell
$env:AUDIOBOOKFORGE_WHISPERX_PYTHON="C:\Users\mateo\Desktop\AudioBookForge\venv_whisperx\Scripts\python.exe"
```

## Run
```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

Debug mode:
```powershell
python main.py --debug
```

## Configuration
Cadence loads `.env` automatically at startup.

Useful keys:
- `AUDIOBOOKFORGE_SYNTH_WORKERS`
- `AUDIOBOOKFORGE_TTS_MAX_CHARS`
- `AUDIOBOOKFORGE_FORCE_CPU`
- `AUDIOBOOKFORGE_CUDA_ONLY`
- `AUDIOBOOKFORGE_WHISPERX_MODEL`
- `AUDIOBOOKFORGE_WHISPERX_BATCH_SIZE`
- `AUDIOBOOKFORGE_WHISPERX_COMPUTE_TYPE`
- `AUDIOBOOKFORGE_WHISPERX_DEVICE`
- `AUDIOBOOKFORGE_WHISPERX_PYTHON`

## Benchmarks
Repository includes benchmark helpers:
- `scripts/benchmark_supertonic_single_file_chunks.py`
- `scripts/benchmark_text_length_sweep.ps1`
- `scripts/benchmark_e2e_single_chapter.py`

## Project Status
Actively iterating. Current focus areas:
- pronunciation cleanup and punctuation normalization
- TTS throughput tuning
- WhisperX stability/configuration
