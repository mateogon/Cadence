import builtins
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark_kokoro.py"


@pytest.fixture
def benchmark(monkeypatch):
    monkeypatch.setenv("PYTORCH_ENABLE_MPS_FALLBACK", "0")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("CADENCE_TTS_SPEED", "1.2")
    spec = importlib.util.spec_from_file_location("benchmark_kokoro", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_help_works_from_unrelated_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"], cwd=tmp_path,
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


def test_benchmark_times_only_production_synthesis(benchmark, monkeypatch, tmp_path):
    events = []
    calls = []

    class Backend:
        model = "hexgrad/Kokoro-82M"

        def __init__(self, device):
            assert device == "mps"

        def ensure_model(self):
            events.append("load")
            return SimpleNamespace(device="mps:0")

        def synthesize(self, text, voice, lang):
            events.append("synthesize")
            calls.append((text, voice, lang))
            return SimpleNamespace(audio=range(72000), word_timestamps=[{"word": "Alice"}])

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        __version__="2.6.0", mps=SimpleNamespace(synchronize=lambda: events.append("sync")),
    ))
    monkeypatch.setitem(sys.modules, "adapters.kokoro_backend", SimpleNamespace(
        KokoroBackend=Backend, SAMPLE_RATE=24000,
    ))
    monkeypatch.setattr(benchmark.importlib.metadata, "version", lambda name: "test-version")
    times = iter([10.0, 30.0])

    def now():
        events.append("time")
        return next(times)

    monkeypatch.setattr(benchmark.time, "perf_counter", now)
    monkeypatch.chdir(tmp_path)
    original_import = builtins.__import__

    def checked(name, *args, **kwargs):
        if name == "torch":
            assert os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] == "1"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked)
    result = benchmark.run_benchmark()
    assert events == ["load", "synthesize", "sync", "time", "synthesize", "sync", "time"]
    assert calls[0][0] == calls[1][0].split("\n\n")[0]
    assert calls[0][1:] == calls[1][1:] == ("af_heart", "en-US")
    assert result["actual_device"] == "mps:0"
    assert result["audio_seconds"] == 3.0
    assert result["synthesis_seconds"] == 20.0
    assert result["rtf"] == pytest.approx(20 / 3)
    assert result["realtime_speedup"] == 0.15
    assert result["input_blocks"] == 20
    assert result["speed"] == 1.05
    assert len(result["source_sha256"]) == 64


def test_fixed_fixture_preserves_exact_twenty_production_blocks(benchmark):
    from adapters.kokoro_backend import speech_blocks

    text = benchmark.FIXTURE.read_text(encoding="utf-8").strip()
    assert len(text.split("\n\n")) == 20
    assert speech_blocks(text).splitlines() == text.split("\n\n")
