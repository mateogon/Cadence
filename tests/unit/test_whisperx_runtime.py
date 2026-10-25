import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest
import torch
import whisperx
from whisperx.vads import pyannote as vad

from system import whisperx_runtime


def test_verified_vad_load_has_scoped_globals(monkeypatch):
    before = set(torch.serialization.get_safe_globals())
    original_torch_load = torch.load
    calls = []
    vad_model = object()

    def load_vad(device, model_fp):
        assert str(device) == "cpu"
        # Exercise the real restricted unpickler, not just the context manager.
        checkpoint = torch.load(model_fp, map_location="cpu", weights_only=True)
        assert "state_dict" in checkpoint
        assert len(set(torch.serialization.get_safe_globals())) > len(before)
        calls.append("vad")
        return vad_model

    def load_model(model_name, device, **kwargs):
        assert set(torch.serialization.get_safe_globals()) == before
        assert kwargs == {"compute_type": "int8", "vad_model": vad_model}
        calls.append("asr")
        return "loaded"

    monkeypatch.setattr(vad, "load_vad_model", load_vad)
    monkeypatch.setattr(whisperx, "load_model", load_model)
    assert whisperx_runtime.load_whisperx_model("small", "cpu", "int8") == "loaded"
    assert calls == ["vad", "asr"]
    assert set(torch.serialization.get_safe_globals()) == before
    assert torch.load is original_torch_load


def test_vad_hash_mismatch_fails_before_loading(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "pytorch_model.bin").write_bytes(b"changed checkpoint")
    monkeypatch.setattr(whisperx, "__file__", str(tmp_path / "__init__.py"))
    load_vad = Mock()
    monkeypatch.setattr(vad, "load_vad_model", load_vad)
    with pytest.raises(RuntimeError, match="SHA256"):
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")
    load_vad.assert_not_called()


def test_unknown_vad_global_fails_before_loading(monkeypatch):
    monkeypatch.setattr(torch.serialization, "get_unsafe_globals_in_checkpoint", lambda path: ["unknown.UntrustedType"])
    load_vad = Mock()
    monkeypatch.setattr(vad, "load_vad_model", load_vad)
    before = set(torch.serialization.get_safe_globals())
    with pytest.raises(RuntimeError, match="unknown.UntrustedType"):
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")
    load_vad.assert_not_called()
    assert set(torch.serialization.get_safe_globals()) == before


def test_vad_failure_restores_safe_globals(monkeypatch):
    before = set(torch.serialization.get_safe_globals())
    monkeypatch.setattr(vad, "load_vad_model", Mock(side_effect=RuntimeError("load failed")))
    with pytest.raises(RuntimeError, match="load failed"):
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")
    assert set(torch.serialization.get_safe_globals()) == before


@pytest.mark.parametrize("value", ["1", "yes", "TRUE"])
def test_weights_only_override_is_rejected(monkeypatch, value):
    monkeypatch.setenv("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", value)
    with pytest.raises(RuntimeError, match="TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"):
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")


def test_old_torch_in_external_environment_is_rejected(monkeypatch):
    monkeypatch.setattr(torch, "__version__", "2.5.1")
    with pytest.raises(RuntimeError, match="Torch 2.6"):
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")


def test_vad_scope_preserves_existing_permissions(monkeypatch):
    from torch.torch_version import TorchVersion

    monkeypatch.setattr(vad, "load_vad_model", Mock(return_value=object()))
    monkeypatch.setattr(whisperx, "load_model", Mock(return_value="loaded"))
    with torch.serialization.safe_globals([TorchVersion]):
        before = set(torch.serialization.get_safe_globals())
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")
        assert set(torch.serialization.get_safe_globals()) == before


@pytest.mark.parametrize("version", ["3.3.2", "4.0.0", "4.0.1", "4.0.3", "4.0.7", "4.1.0"])
def test_unreviewed_pyannote_version_is_rejected(monkeypatch, version):
    monkeypatch.setattr(whisperx_runtime, "version", lambda package: version)
    load_vad = Mock()
    monkeypatch.setattr(vad, "load_vad_model", load_vad)
    with pytest.raises(RuntimeError, match=r"pyannote.audio==4\.0\.2"):
        whisperx_runtime.load_whisperx_model("small", "cpu", "int8")
    load_vad.assert_not_called()


def test_runtime_enables_mps_fallback_before_importing_torch():
    script = """
import builtins
import os
import sys

os.environ.pop("PYTORCH_ENABLE_MPS_FALLBACK", None)
original = builtins.__import__
observed = []
def watched(name, *args, **kwargs):
    if name == "torch" and "torch" not in sys.modules:
        observed.append(os.environ.get("PYTORCH_ENABLE_MPS_FALLBACK"))
    return original(name, *args, **kwargs)
builtins.__import__ = watched
from system import whisperx_runtime
assert observed and observed[0] == "1", observed
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
