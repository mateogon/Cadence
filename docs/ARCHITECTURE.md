# Cadence Architecture

## Flow Overview
1. Source normalization (`.epub/.mobi/.azw3` -> `.epub`)
2. Text extraction to chapter files (`content/ch_XXX.txt`)
3. Chapter synthesis (`audio/ch_XXX.wav`)
4. Word alignment (`content/ch_XXX.json`)
5. Reader playback and chapter navigation in Qt UI

## Main Components
- `qt/main_window.py`
  - Library UI, player UI, runtime settings dialogs.
- `system/book_manager.py`
  - Import orchestration, chapter extraction/synthesis/alignment flow.
- `adapters/tts_factory.py`
  - Lazily selects the backend from the saved book identity or the new-book setting.
- `adapters/supertonic_backend.py` + `adapters/kokoro_backend.py`
  - Synthesis, voice/device selection, and atomic audio writes. Kokoro returns
    `SynthesisResult` with audio and optional chapter-relative word timestamps.
  - BookManager remaps native words onto the original text and writes the same
    alignment JSON used by the reader. Missing native times use WhisperX.
  - A saved WAV without JSON resumes through WhisperX without resynthesis.
- `system/whisperx_align_worker.py` + `system/whisperx_align_cli.py`
  - Persistent worker and fallback single-run alignment paths.
- `system/runtime_settings.py`
  - Runtime settings defaults and environment application.

## Data Model (Library Book Folder)
- `library/<book>/metadata.json`
- `library/<book>/source/*.epub` (+ optional original source format)
- `library/<book>/content/ch_XXX.txt`
- `library/<book>/content/ch_XXX.json`
- `library/<book>/audio/ch_XXX.wav`

## Runtime Settings
- Persisted in `cadence_settings.json`
- Player view preferences persisted in `player_settings.json`

