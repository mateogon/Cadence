"""Load WhisperX's bundled VAD with the restricted Torch unpickler."""

from collections import defaultdict
import hashlib
from importlib.metadata import version
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import torch
from torch.torch_version import TorchVersion
import whisperx

# WhisperX 3.8.6 bundles the same VAD checkpoint verified for 3.3.1.
VAD_SHA256 = "0b5b3216d60a2d32fc086b47ea8c67589aaeb26b7e07fcbe620d6d0b83e209ea"


def load_whisperx_model(model_name, device, compute_type):
    if TorchVersion(torch.__version__) < "2.6":
        raise RuntimeError("WhisperX alignment requires Torch 2.6 or later for weights_only loading.")
    if os.getenv("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", "").lower() in ("1", "y", "yes", "true"):
        raise RuntimeError("Remove TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD to keep checkpoint loading restricted.")

    # Later pyannote releases force weights_only=False inside their model loader.
    if version("pyannote.audio") != "4.0.2":
        raise RuntimeError("WhisperX alignment requires pyannote.audio==4.0.2 for restricted VAD loading.")

    from whisperx.vads import pyannote as vad

    checkpoint = Path(whisperx.__file__).parent / "assets" / "pytorch_model.bin"
    if hashlib.sha256(checkpoint.read_bytes()).hexdigest() != VAD_SHA256:
        raise RuntimeError(f"WhisperX VAD checkpoint SHA256 does not match the trusted model: {checkpoint}")

    from omegaconf.base import ContainerMetadata, Metadata
    from omegaconf.listconfig import ListConfig
    from omegaconf.nodes import AnyNode
    from pyannote.audio.core.model import Introspection
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    allowed = [
        defaultdict, dict, int, list, Any, ContainerMetadata, Metadata,
        ListConfig, AnyNode, Introspection, Problem, Resolution, Specifications, TorchVersion,
    ]
    names = {f"{item.__module__}.{item.__qualname__}" for item in allowed}
    unexpected = set(torch.serialization.get_unsafe_globals_in_checkpoint(checkpoint)) - names
    if unexpected:
        raise RuntimeError(f"WhisperX VAD checkpoint has unreviewed globals: {sorted(unexpected)}")

    # Only this verified VAD checkpoint needs the legacy metadata classes.
    existing = set(torch.serialization.get_safe_globals())
    with torch.serialization.safe_globals([item for item in allowed if item not in existing]):
        vad_model = vad.load_vad_model(torch.device(device), model_fp=str(checkpoint))
    return whisperx.load_model(
        model_name, device, compute_type=compute_type, vad_model=vad_model,
    )
