# Technical notes

Details behind the short descriptions in the [README](../README.md): import and resume
rules, the TTS backends, the alignment stack and the dependency lock.

## Import and resume

Cadence processes a book chapter by chapter:

- If a chapter already has `.wav`, Cadence skips synthesis and aligns it.
- If `.wav` is missing, Cadence synthesizes first, then aligns.
- If `.wav` and `.json` both exist, Cadence skips that chapter.

This makes resume robust after interruptions and lets you read while the import runs.

- Import reports success only when every chapter has non-empty audio and alignment. Failed
  chapters remain available for resume, and the reader shows the import as incomplete.
- Library cards update live with ready counts during import.
- EPUB `dc:language` is saved in `metadata.json` and passed to Supertonic. Regional tags
  such as `es-CL` use their base code; missing or unsupported codes use `na`.
- New books store `tts_backend` and `tts_model`. Resume uses the book's stored backend,
  voice and model even if the current settings change.
- Older books without TTS identity keep their existing audio. For missing chapters,
  Cadence warns that the historical model is unknown, uses the configured Supertonic model
  once, and stores that continuation configuration for later resumes. This does not
  establish which model produced older WAV files. Select the known older model before
  continuing if needed.

## Kokoro

The optional install pins Kokoro 0.9.4, `preshed==3.0.9`, and the English spaCy model.
The preshed pin avoids the English tokenizer failure seen on macOS. Keep `--extra kokoro`
on each `uv run`; plain `uv run` removes the optional packages. On Windows/Linux with
NVIDIA, combine it with `--no-group cpu --extra gpu`. First synthesis downloads
`hexgrad/Kokoro-82M` and the selected voice.

Kokoro supports English, Spanish, French, Hindi, Italian, Portuguese, Japanese, and
Mandarin voices. Japanese and Mandarin need additional upstream language packages; the
supplied extra includes English and eSpeak-based tokenization. For Japanese, start with
`uv run --extra kokoro --with 'misaki[ja]' main.py`; use `misaki[zh]` for Mandarin. These
optional language paths are not covered by CI.

An unsupported book language or incompatible explicit voice stops the import with an
error. Existing Supertonic voice selections map to Kokoro's language default for a new
book. New English books default to `af_heart` (US/general English) or `bf_emma` (UK).
Other languages retain catalog order. Resume always keeps the book's saved backend and
voice.

Cadence packs complete sentences into paragraph blocks of about 450 characters. It
preserves common abbreviations and decimals when finding sentence boundaries. A sentence
longer than 450 characters remains whole; Kokoro handles its internal splits. This avoids
added mid-sentence pauses from arbitrary word wrapping and inference overhead from
synthesizing every short sentence separately. Blank lines preserve paragraph boundaries.

Kokoro's native English word times accumulate the duration of every audio fragment before
the next fragment starts. Missing or invalid times trigger WhisperX for the whole chapter,
with a log entry. Non-English synthesis currently uses that fallback.

MPS enables PyTorch's CPU fallback for unsupported operators before loading Torch.
`CADENCE_KOKORO_DEVICE=cpu` forces CPU; an unavailable explicit accelerator falls back to
CPU with a log message. `CADENCE_TTS_SPEED` applies to both backends; `CADENCE_TTS_MODEL`,
`CADENCE_TTS_STEPS`, and `CADENCE_TTS_MAX_CHARS` configure Supertonic only. Kokoro's model
identity is saved with each book.

## Supertonic on macOS

Supertonic uses CPU by default on macOS. Measurements on an Apple M3 Pro used a 71-word
Spanish chapter (M3 voice, 8 steps, speed 1.05, seed 42; 26.54 seconds of audio). CPU
synthesis took 7.33–8.38 seconds over three runs (median 7.58). CoreML took 36.00 seconds
on its first synthesis; its second had not finished after 140 seconds and was stopped.
Model loading took 0.74 seconds for CPU and 10.66 seconds for CoreML. These measurements
apply to this chapter and machine. To try CoreML when available, set `CADENCE_USE_COREML=1`
before starting Cadence; `CADENCE_FORCE_CPU=1` takes priority.

Supertonic's package handles text chunking through `max_chunk_length`;
`CADENCE_TTS_MAX_CHARS` controls that value. A single sentence beyond the package's
100,000-character input limit is not supported.

## WhisperX alignment

WhisperX 3.8.6 uses CPU with `int8` when CUDA is unavailable. Faster-whisper has no MPS
backend. WhisperX detects each chapter's language for alignment. Its diagnostic
`ch_XXX.whisperx_report.json` records the detected language; the reader's alignment JSON
format is unchanged.

Cadence verifies the bundled VAD checkpoint hash and temporarily permits its known metadata
classes during loading. Torch keeps `weights_only` loading enabled; no local wrapper is
needed. External WhisperX environments must provide the locked compatible stack, including
pyannote.audio 4.0.2. Other pyannote versions are rejected before VAD loading: later
releases force unrestricted checkpoint loading internally.

The stack pins NumPy 2.2.6 and pyannote.audio 4.0.2. On a Mac with Homebrew FFmpeg 8,
TorchCodec 0.7 can warn that its FFmpeg 4–7 libraries cannot load. Cadence does not use
that decoder: WhisperX decodes with the FFmpeg CLI and passes waveform tensors to
pyannote's supported in-memory path. The normal import requires no FFmpeg downgrade or
Hugging Face token. TorchCodec's direct file decoding is not supported by this FFmpeg 8
setup.

Alignment uses `CADENCE_WHISPERX_PYTHON` first, then the running interpreter
(`sys.executable`), `.venv`, and `venv`. To keep a separate WhisperX environment, set its
interpreter before starting Cadence:

```powershell
$env:CADENCE_WHISPERX_PYTHON="C:\path\to\venv_whisperx\Scripts\python.exe"
```

```bash
export CADENCE_WHISPERX_PYTHON="/path/to/venv_whisperx/bin/python"
```

## Calibre lookup

Calibre lookup uses `CADENCE_CALIBRE_PATH`, then `PATH`, the macOS app path, and the
Windows default. An invalid explicit override fails instead of silently selecting another
installation.

## Runtime profiles and the lock

`uv sync --locked` creates `.venv` with CPU ONNX Runtime and matching Torch/Torchaudio
2.8.0 and Torchvision 0.23.0. It also installs the development tools. Existing `venv`
directories are kept.

The GPU profile (`--no-group cpu --extra gpu`) selects ONNX Runtime GPU 1.24.1 and the
official CUDA 12.8 Torch/Torchaudio/Torchvision wheels. The machine also needs compatible
NVIDIA drivers and ONNX Runtime's
[CUDA/cuDNN runtime libraries](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html#requirements).
Use the same profile flags for each `uv run`; a plain `uv run` restores the default CPU
profile. The `cpu` group and `gpu` extra conflict, so uv rejects a request for both. The
GPU extra is for Windows/Linux; use the default profile on macOS.

The lockfile uses version-specific
[uv metadata overrides](https://docs.astral.sh/uv/concepts/resolution/#dependency-metadata)
for Supertonic 1.3.1 and faster-whisper 1.2.1. Each package requests the CPU `onnxruntime`
distribution upstream, although both ONNX distributions expose the same API. The overrides
remove only that requirement. Cadence's selected profile supplies exactly one runtime. Use
uv for installation; plain pip does not apply these overrides.

## Web reader

The web reader (`--web`) runs the files in `webui/static/` in a pywebview window
(WKWebView on macOS, WebView2 on Windows). A local server in `webui/server.py` serves the
page and the library's audio:

- It listens on 127.0.0.1 only, on a random port.
- Media URLs carry a per-session token and support HTTP Range requests.
- It serves only files inside the library folder.

The word highlight follows `audio.currentTime` on every animation frame. On an Apple M3
Pro, the measured lag between the audio position and the highlighted word was a median of
11.7 ms, p95 16.4 ms and a maximum of 19.5 ms.

Reading positions use the Qt reader's keys in `player_settings.json` (`book_positions` and
`book_positions_ms`), so both readers resume at the same place. Settings that only the web
reader has live under the `web_reader` key. Import uses the same `BookManager.import_book`
pipeline as the Qt app, with the engine and model chosen in the dialog. Voice samples and
cached covers are stored in `library/.samples/`.
