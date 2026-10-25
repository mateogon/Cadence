"""Entry points must enable MPS fallback before a dependency can import Torch."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("entrypoint", [
    "main.py", "qt/app.py", "adapters/kokoro_backend.py",
    "adapters/generate_audiobook_supertonic.py", "system/whisperx_align_cli.py",
    "system/whisperx_align_worker.py", "system/whisperx_runtime.py",
    "scripts/collect_alignment_mismatches.py", "scripts/benchmark_kokoro.py",
])
def test_mps_fallback_precedes_dependency_imports(entrypoint):
    probe = '''
import builtins, os, runpy, sys
os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
class DependencyReached(BaseException):
    pass
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in {"torch", "numpy", "onnxruntime", "whisperx", "supertonic"}:
        assert os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1", name
        raise DependencyReached
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
try:
    runpy.run_path(sys.argv[2], run_name="bootstrap_probe")
except DependencyReached:
    pass
assert os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK") == "1"
'''
    subprocess.run([sys.executable, "-c", probe, str(ROOT), str(ROOT / entrypoint)], check=True)
