# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project follows Semantic Versioning.

## [Unreleased]

### Added
- Supertonic model, speed and inference-step controls in runtime settings.
- EPUB language and TTS backend/model metadata, with consistent resume and explicit legacy continuation behavior.
- Detected WhisperX language in chapter alignment diagnostics.
- Initial changelog tracking.

### Changed
- Pin Supertonic 1.3.1 and use Supertonic 3 by default (31 languages plus the `na` fallback).
- Use package text validation and chunking for both desktop synthesis and the standalone adapter CLI.

### Fixed
- Replace the removed Supertonic voices API with `voice_style_names` and stop forcing English for every book.
- Preserve the ONNX provider patch that the 1.3.1 loader still reads, with regression coverage for provider selection.

