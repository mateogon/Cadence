# Cadence Test Plan

## Scope
This plan covers the current app stack:
- Desktop UI on `PyQt6`
- Core pipeline in `system/book_manager.py` (extract -> synth -> align)
- TTS adapter (`adapters/supertonic_backend.py`)
- WhisperX worker/CLI scripts
- Runtime settings persistence and environment mapping

## Goals
- Catch functional regressions quickly during normal development.
- Keep default checks fast enough to run before every push.
- Validate the highest-risk production path: import a book and read while import is still running.

## Test Pyramid

### 1) Unit Tests (fast, deterministic)
Target pure logic and edge-case behavior.

- `system/runtime_settings.py`
  - default settings when file is missing
  - malformed JSON fallback behavior
  - save/load round-trip
  - environment apply behavior with and without override
- `system/book_manager.py` helpers
  - token normalization for alignment
  - timestamp alignment for matching/mismatched token streams
  - punctuation/apostrophe normalization edge cases
  - worker/model/batch/compute option parsing from env
- `adapters/generate_audiobook_supertonic.py`
  - `sanitize_text` for unicode punctuation and unsupported chars
  - `get_smart_chunks` boundaries for long/short paragraphs

### 2) Service Tests (mocked dependencies)
Validate orchestration without requiring Calibre, Supertonic, WhisperX, GPU, or ffmpeg.

- Mock process calls used by extraction/alignment paths.
- Mock `SupertonicBackend` synth/save behavior.
- Assert:
  - chapter-by-chapter interleaving behavior
  - skip/resume behavior when `.wav` / `.json` already exist
  - metadata state transitions and persistence
  - progress callback shape and monotonicity
  - error paths produce clear log messages and non-corrupt state

### 3) Integration Tests (filesystem-level)
Run against temporary directories and small fixtures.

- Build 1-3 chapter test books with synthetic artifacts.
- Verify expected output tree:
  - `library/<book>/content/ch_XXX.txt`
  - `library/<book>/audio/ch_XXX.wav`
  - `library/<book>/content/ch_XXX.json`
- Validate metadata consistency (ready counts, status fields, resumability).
- Verify import restart does not duplicate work or break prior artifacts.

### 4) UI Tests (PyQt6 behavior)
Headless behavior tests with `pytest-qt` and `QT_QPA_PLATFORM=offscreen`.

- App startup smoke:
  - `qt.app.main()` bootstraps under `PyQt6`
  - main window opens/closes cleanly
- Library view:
  - search/filter behavior
  - selecting a book/chapter updates UI state
- Settings:
  - load/apply/reset persists to `cadence_settings.json`
  - setting changes propagate to runtime env mapping
- Import footer/progress:
  - progress text updates and remains visible while switching views
- Audio backend behavior:
  - if pygame unavailable, QT backend fallback remains stable

### 5) Manual GPU/External Smoke (scheduled or pre-release)
Real dependency checks on a Windows machine with Calibre + ffmpeg + CUDA.

- Import a small EPUB end-to-end.
- Confirm:
  - Supertonic provider selection logs expected device/provider
  - WhisperX alignment outputs valid chapter JSON
  - reading works while later chapters still process
  - speed change path works when ffmpeg is present

## Tooling
- `pytest`
- `pytest-qt` (for PyQt6 UI behavior)
- `pytest-mock` or `unittest.mock`
- `tmp_path`, `monkeypatch`, `capsys`
- Optional lint gate: `ruff`

## Proposed Test Layout
- `tests/unit/test_runtime_settings.py`
- `tests/unit/test_book_manager_helpers.py`
- `tests/unit/test_supertonic_text_processing.py`
- `tests/service/test_import_orchestration.py`
- `tests/integration/test_library_artifact_flow.py`
- `tests/ui/test_app_startup_pyqt6.py`
- `tests/ui/test_settings_dialog.py`
- `tests/ui/test_library_search_and_selection.py`
- `tests/fixtures/`

## Execution Cadence

### Pre-commit / pre-push (required)
- Unit tests
- Service tests
- Basic UI smoke (`tests/ui/test_app_startup_pyqt6.py`)

### CI on every PR (required)
- Unit + service + integration (mocked/external-free)
- PyQt6 headless UI suite
- Syntax/import check

### Scheduled or release-candidate (required before release)
- Manual GPU/external smoke pass on Windows

## Environment Notes
- Set `QT_QPA_PLATFORM=offscreen` for headless UI runs.
- Keep CI tests independent of local GPU/Calibre/ffmpeg availability.
- Use mocks for WhisperX/Supertonic process-heavy paths in default CI.

## Initial Rollout Order
1. Land unit coverage for settings and text/alignment helpers.
2. Add service tests for import orchestration and resume/skip semantics.
3. Add one integration test for chapter artifact flow and metadata.
4. Add PyQt6 startup + settings dialog behavior tests.
5. Add scheduled manual GPU smoke checklist to release routine.
