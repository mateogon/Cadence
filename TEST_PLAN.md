# Cadence Test Plan

## Goals
- Catch regressions early while iterating quickly with LLM-assisted development.
- Keep feedback fast for daily changes, with deeper checks available when needed.
- Cover the full pipeline: settings -> extraction -> TTS -> alignment -> reader UI.

## Test Layers

### 1) Unit Tests (fast, always run)
Focus on pure logic and deterministic behavior.

- `system/runtime_settings.py`
  - Defaults when file is missing
  - Valid file overrides defaults
  - Malformed JSON handled safely
  - Save/load roundtrip
  - `apply_settings_to_environ` with override on/off
- `system/book_manager.py` helpers
  - `tokenize_for_alignment` normalization behavior
  - `align_timestamps` on matching and mismatching token streams
  - Apostrophes and punctuation edge cases
- Environment parsing helpers
  - Worker/max-char parsing and fallback behavior
  - WhisperX python/device/model option resolution

### 2) Service Tests (mocked external dependencies)
Validate pipeline orchestration without GPU/Calibre/WhisperX execution.

- Mock `subprocess.run` for Calibre and WhisperX CLI calls
- Mock `SupertonicBackend` synth/save methods
- Validate:
  - Step order and transitions (extract -> synth -> align)
  - Progress callback range and message shape
  - Skip behavior for existing WAV/JSON outputs
  - Metadata status transitions and persistence
  - Error handling/logging paths

### 3) Integration Tests (filesystem-level)
Run on temp directories with small fixtures and local I/O.

- Build tiny fake book structures with 1-3 chapters
- Simulate generated outputs where needed
- Verify final structure and metadata consistency
- Ensure reader-required artifacts exist and are valid

### 4) UI Behavior Tests (lightweight)
Focus on behavior contracts, not visual snapshots.

- Library search filters titles correctly
- Runtime settings dialog load/apply/reset behavior
- Settings persist to `cadence_settings.json`
- Global bottom import footer updates while switching views

### 5) GPU Smoke Tests (manual/scheduled)
Minimal real end-to-end checks on GPU machines.

- One small chapter synth + align run
- Confirm timestamps output and no runtime exceptions
- Capture effective device/provider and timing summary

### 6) Regression Corpus (text/punctuation)
Maintain a small fixture corpus for known failure patterns.

- Apostrophe variants (`don't`, `don’t`, `dont`, possessives)
- Dash variants (`—`, `–`, `-`, comma replacements)
- Long paragraph chunking edge cases
- Previously observed mispronunciation/alignment failures

## Tooling
- `pytest`
- `pytest-mock` (or `unittest.mock`)
- `tmp_path`, `monkeypatch`
- Optional: `ruff` for lint gate

## Suggested Test Layout
- `tests/unit/`
- `tests/service/`
- `tests/integration/`
- `tests/ui/`
- `tests/gpu_smoke/`
- `tests/fixtures/`

## CI Strategy

### Required (fast)
- Lint
- Unit + service tests (no GPU)
- Syntax/import check

### Optional (scheduled or manual)
- GPU smoke tests
- Longer integration matrix

## Rollout Order
1. Unit tests for runtime settings + alignment helpers
2. Service tests for `BookManager.import_book` with mocks
3. One integration test covering metadata + artifact flow
4. Regression text corpus assertions
5. GPU smoke script/tests for periodic validation
