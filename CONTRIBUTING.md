# Contributing to Cadence

## Prerequisites
- Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Apple Silicon macOS, Windows x64, or Linux x64 for runtime validation.
- Calibre (`ebook-convert`) and FFmpeg for end-to-end local testing.

## Local Setup
```bash
uv sync --locked
```
This creates `.venv` and installs the CPU runtime plus lint, type-check, and test tools.
For the Windows/Linux GPU profile, add `--no-group cpu --extra gpu` to `uv sync` and `uv run`.
See [runtime profiles](README.md#runtime-profiles) for CUDA prerequisites and metadata overrides.
Keep dependency changes in `pyproject.toml` and regenerate `uv.lock` with `uv lock`.

## Run the App
```bash
uv run main.py
```

## Test and Lint
```bash
uv run ruff check .
uv run mypy --config-file mypy.ini system/runtime_settings.py
uv run pytest -q tests/unit tests/service tests/integration tests/ui
```
CI runs the base and optional Kokoro profiles on Ubuntu, Windows, and macOS.
To test Kokoro locally, add `--extra kokoro` to each `uv sync` and `uv run`.
The base profile checks that Cadence starts without Kokoro. The optional profile
checks the real English tokenizer without downloading the TTS model.

Optional real E2E test:
```powershell
$env:CADENCE_RUN_E2E="1"
$env:CADENCE_E2E_BOOK="C:\path\to\book.epub"
uv run pytest -q tests/e2e/test_full_pipeline_real.py -m e2e
```

## Commit Guidelines
- Keep commits small and behavior-focused.
- Add or update tests for behavior changes.
- Avoid combining large refactors with product changes in one commit.

## Pull Request Checklist
- Lint passes.
- Relevant test suite passes.
- User-visible behavior changes are documented in README or docs.
- Breaking config/runtime changes are called out in PR description.

