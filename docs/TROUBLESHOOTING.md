# Troubleshooting

## Calibre Not Found
Symptom:
- Import fails before extraction with a Calibre/`ebook-convert` error.

Fix:
- Install Calibre.
- Set `CADENCE_CALIBRE_PATH` to `ebook-convert` executable path, or add it to `PATH`.

## FFmpeg Not Found
Symptom:
- Playback speed conversion falls back to original audio.

Fix:
- Install FFmpeg and ensure `ffmpeg` is available in `PATH`.

## WhisperX Startup/Alignment Problems
Symptom:
- Alignment is slow/failing or falls back repeatedly.

Fix:
- Verify `CADENCE_WHISPERX_PYTHON` points to an environment with WhisperX installed.
- Tune:
  - `CADENCE_WHISPERX_MODEL`
  - `CADENCE_WHISPERX_BATCH_SIZE`
  - `CADENCE_WHISPERX_COMPUTE_TYPE`
  - `CADENCE_WHISPERX_DEVICE`

## Qt Runtime Issues
Symptom:
- App fails to launch or plugin load errors appear.

Fix:
- Use project venv.
- Ensure only one Qt binding path is active.
- Set `CADENCE_QT_API=pyqt6` for consistency with default setup.

## Web Reader: Kokoro Is Not Available
Symptom:
- The import dialog shows the Kokoro card as not installed.

Fix:
- Start the reader with both extras: `uv run --extra kokoro --extra web main.py --web`.
  A `uv run` without `--extra kokoro` removes the Kokoro packages.

## Web Reader: Window Does Not Open
Symptom:
- `--web` prints that pywebview is missing.

Fix:
- Add the web extra: `uv run --extra web main.py --web`.

## Test Runtime
Symptom:
- UI tests fail in headless environments.

Fix:
- Set `QT_QPA_PLATFORM=offscreen` (Linux CI) or `minimal` (Windows CI).

