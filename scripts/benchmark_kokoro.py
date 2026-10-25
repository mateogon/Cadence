"""Benchmark production Kokoro on a fixed Alice excerpt and cached model assets."""

import os

# Set these before Torch or Hugging Face can be imported through another module.
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "scripts" / "fixtures" / "alice-chapter-1-first20.txt"
# The fixture contains the first 20 production speech_blocks of this source chapter.
ORIGINAL_CHAPTER_SHA256 = "f20fc70c2502de4b05a42faaec52014369360b23835c998558cf04120b195e6b"
VOICE = "af_heart"
SPEED = 1.05


def run_benchmark():
    sys.path.insert(0, str(ROOT))
    import torch

    from adapters.kokoro_backend import SAMPLE_RATE, KokoroBackend

    # Normalize checkout line endings so Windows measures and hashes the same input.
    source = FIXTURE.read_text(encoding="utf-8").encode("utf-8")
    text = source.decode("utf-8").strip()
    blocks = text.split("\n\n")
    if len(blocks) != 20:
        raise ValueError("The benchmark fixture must contain exactly 20 speech blocks.")
    os.environ["CADENCE_TTS_SPEED"] = str(SPEED)
    backend = KokoroBackend(device="mps")
    model = backend.ensure_model()
    actual_device = str(model.device)
    if actual_device.split(":")[0] != "mps":
        raise RuntimeError(f"The MPS benchmark requires MPS; model is on {actual_device}.")

    print("Model loaded; warming up once with the first input block.", flush=True)
    backend.synthesize(blocks[0], VOICE, lang="en-US")
    torch.mps.synchronize()
    started = time.perf_counter()
    result = backend.synthesize(text, VOICE, lang="en-US")
    torch.mps.synchronize()
    elapsed = time.perf_counter() - started
    audio_seconds = len(result.audio) / SAMPLE_RATE
    if audio_seconds <= 0 or elapsed <= 0:
        raise RuntimeError("Kokoro produced no measurable audio or synthesis time.")
    return {
        "python": platform.python_version(),
        "versions": {name: importlib.metadata.version(name) for name in (
            "torch", "torchaudio", "kokoro", "whisperx", "numpy", "misaki",
        )},
        "torch_runtime_version": torch.__version__,
        "actual_device": actual_device,
        "mps_fallback": os.environ["PYTORCH_ENABLE_MPS_FALLBACK"],
        "model": backend.model,
        "voice": VOICE,
        "speed": SPEED,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "original_chapter_sha256": ORIGINAL_CHAPTER_SHA256,
        "input_blocks": len(blocks),
        "input_words": len(text.split()),
        "warmup_calls": 1,
        "warmup_text_sha256": hashlib.sha256(blocks[0].encode()).hexdigest(),
        "audio_seconds": audio_seconds,
        "synthesis_seconds": elapsed,
        "rtf": elapsed / audio_seconds,
        "realtime_speedup": audio_seconds / elapsed,
        "native_words": len(result.word_timestamps or []),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save the JSON result to this path.")
    args = parser.parse_args()
    result = run_benchmark()
    output = json.dumps(result, indent=2) + "\n"
    print(output, end="", flush=True)
    print(f"RTF (time/audio): {result['rtf']:.4f}; speed (audio/time): {result['realtime_speedup']:.2f}x")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")


if __name__ == "__main__":
    main()
