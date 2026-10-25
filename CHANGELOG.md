# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
- Locked uv installation with mutually exclusive CPU/GPU ONNX profiles and full Ubuntu, Windows, and Apple Silicon macOS CI.
- Opt-in CoreML synthesis; CPU remains the Mac default after same-chapter measurements.
- Supertonic model, speed and inference-step controls in runtime settings.
- EPUB language and TTS backend/model metadata, with consistent resume and explicit legacy continuation behavior.
- Detected WhisperX language in chapter alignment diagnostics.
- Initial changelog tracking.

### Changed
- Pin Supertonic 1.3.1 and use Supertonic 3 by default (31 languages plus the `na` fallback).
- Use package text validation and chunking for both desktop synthesis and the standalone adapter CLI.

### Fixed
- Read OPF title, author, and language across XML namespaces without discarding leaf elements.
- Report import success only when every chapter has audio and alignment; preserve incomplete outputs for resume.
- Discover Calibre on macOS and prefer the running Python environment for alignment.
- Match Torch/Torchaudio versions and load the verified WhisperX VAD checkpoint with scoped safe globals.
- Load ONNX Runtime before Qt on Windows to avoid the bundled MSVC runtime conflict exposed by native backend tests.
- Replace the removed Supertonic voices API with `voice_style_names` and stop forcing English for every book.
- Preserve the ONNX provider patch that the 1.3.1 loader still reads, with regression coverage for provider selection.

