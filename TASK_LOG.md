# Cadence Task Log

Status key:
- `[ ]` not started
- `[-]` in progress
- `[x]` done

## Phase 0: Baseline
- `[x]` Commit resume-position fix from Library `Read` flow.
  - Commit: `cda5b61`

## Phase 1: Release and CI Consistency
- `[x]` Align release artifact name with PyInstaller output.
  - Update `.github/workflows/release.yml` artifact/upload paths to `dist/Cadence.exe` (or rename build output intentionally).
  - Verify release workflow paths are consistent end-to-end.
- `[x]` Align Python version across docs and release workflow.
  - Pick one target version (recommend `3.12`) and update:
    - `.github/workflows/release.yml`
    - `README.md`
    - any scripts/docs that still reference a different version.
- `[x]` Add a Windows CI test job.
  - Add `windows-latest` matrix/job in `.github/workflows/tests.yml`.
  - Run at least unit + service + minimal UI smoke on Windows.

## Phase 2: Config and Environment Hardening
- `[x]` Make Calibre path configurable (no hardcoded single path).
  - Add setting/env key (e.g. `CADENCE_CALIBRE_PATH`) with fallback auto-discovery.
  - Surface helpful error message in UI when missing.
- `[x]` Unify default settings in one source of truth.
  - Remove mismatches between `system/runtime_settings.py` and `BookManager` helper defaults.
  - Ensure UI dropdown defaults map exactly to runtime defaults.
- `[x]` Add tests for config resolution and fallback behavior.
  - Missing/invalid Calibre path.
  - Default-resolution consistency assertions.

## Phase 3: Pipeline Refactor and Reliability
- `[x]` Split `BookManager.import_book` orchestration into focused components.
  - Extract modules/functions for:
    - source normalization/conversion
    - book target/source artifact persistence
    - text extraction
    - synthesis + alignment streaming phase
    - metadata finalization
- `[-]` Replace broad silent exceptions with structured error handling.
  - Keep app resilient, but always log actionable context.
  - Avoid `except Exception: pass` unless explicitly justified.
- `[x]` Add cancellation/timeout reliability tests.
  - [x] WhisperX startup timeout fallback.
  - [x] per-chapter alignment timeout.
  - [x] cancellation mid-synthesis.
  - [x] cancellation mid-alignment.

## Phase 4: Metadata and Library UX
- `[x]` Extract richer metadata from EPUB/OPF.
  - author, canonical title, cover reference.
  - preserve normalized fallback values if extraction fails.
- `[x]` Improve library search and filtering.
  - [x] search by title + author + voice.
  - [x] optional quick filters: incomplete/complete.
- `[x]` Expose real reading progress in library cards.
  - [x] keep import progress and reading progress as separate fields.
  - [x] avoid overloading `last_chapter` semantics.

## Phase 5: Engineering Quality Gates
- `[x]` Add lint/type tooling.
  - [x] `ruff` baseline with repo config.
  - [x] optional type checker (`mypy`) with pragmatic scope.
- `[x]` Add pre-commit hooks for fast local quality checks.
- `[x]` Update CI to run lint + tests together.

## Phase 6: Documentation and Contributor Ops
- `[x]` Add contributor docs.
  - `CONTRIBUTING.md` with setup, test commands, CI expectations.
- `[x]` Add changelog discipline.
  - `CHANGELOG.md` with release notes template.
- `[x]` Expand docs beyond README.
  - architecture overview (pipeline + data model).
  - troubleshooting page (Calibre/ffmpeg/WhisperX/Qt runtime issues).

## Execution Order (Sprint Plan)
1. Phase 1 (release/CI correctness)
2. Phase 2 (config hardening)
3. Phase 3 (refactor/reliability)
4. Phase 4 (metadata + UX)
5. Phase 5 (quality gates)
6. Phase 6 (docs/process)

## Working Notes
- Keep each phase in separate PR-sized changes.
- Do not mix refactor-only changes with behavior changes unless needed.
- Add tests alongside each behavior change before moving to the next phase.
