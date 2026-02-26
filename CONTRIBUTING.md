# Contributing to Cadence

## Prerequisites
- Python 3.12
- Windows 10/11 for full runtime validation
- Calibre (`ebook-convert`) and FFmpeg for end-to-end local testing

## Local Setup
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install -r requirements-gpu.txt
```

For CPU-only development:
```powershell
pip install -r requirements-cpu.txt
```

## Run the App
```powershell
python main.py
```

## Test and Lint
```powershell
python -m ruff check .
python -m pytest -q tests/unit tests/service tests/integration tests/ui
```

Optional real E2E test:
```powershell
$env:CADENCE_RUN_E2E="1"
$env:CADENCE_E2E_BOOK="C:\path\to\book.epub"
python -m pytest -q tests/e2e/test_full_pipeline_real.py -m e2e
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

