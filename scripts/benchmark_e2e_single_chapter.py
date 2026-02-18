import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from adapters.supertonic_backend import SupertonicBackend
from system.book_manager import BookManager


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end single chapter benchmark: Supertonic synthesis + WhisperX alignment."
    )
    parser.add_argument("input_txt", help="Path to chapter .txt")
    parser.add_argument("--voice", "-v", default="M3")
    parser.add_argument("--tts-max-chars", type=int, default=800)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-batch-size", type=int, default=16)
    parser.add_argument("--whisper-compute-type", default="int8")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--output-wav", default="benchmark_e2e_single.wav")
    parser.add_argument("--output-json", default="benchmark_e2e_single.json")
    parser.add_argument("--report-json", default="benchmark_e2e_report.json")
    args = parser.parse_args()

    input_path = Path(args.input_txt)
    if not input_path.exists():
        raise FileNotFoundError(f"Input .txt not found: {input_path}")
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Input .txt is empty: {input_path}")

    # Step 1: TTS synthesis
    t0 = time.perf_counter()
    backend = SupertonicBackend()
    wav = backend.synthesize(text, args.voice, max_chars=args.tts_max_chars)
    if wav is None:
        raise RuntimeError("Synthesis produced no audio.")
    output_wav = Path(args.output_wav)
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    backend.save_audio(wav, output_wav)
    t1 = time.perf_counter()

    # Step 2/3 in isolated subprocess: WhisperX + robust alignment.
    whisper_report = Path(args.report_json).with_name(
        Path(args.report_json).stem + "_whisper.json"
    )
    whisper_cmd = [
        sys.executable,
        str(Path(__file__).with_name("benchmark_whisperx_align_only.py")),
        str(output_wav),
        str(input_path),
        "--whisper-model",
        args.whisper_model,
        "--whisper-batch-size",
        str(args.whisper_batch_size),
        "--whisper-compute-type",
        args.whisper_compute_type,
        "--device",
        args.device,
        "--output-json",
        args.output_json,
        "--report-json",
        str(whisper_report),
    ]
    proc = subprocess.run(whisper_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(
            "WhisperX subprocess failed.\n"
            f"Command: {' '.join(whisper_cmd)}\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
    t3 = time.perf_counter()

    whisper_data = {}
    if whisper_report.exists():
        whisper_data = json.loads(whisper_report.read_text(encoding="utf-8"))

    report = {
        "input_txt": str(input_path),
        "output_wav": str(output_wav),
        "output_json": str(args.output_json),
        "tts_max_chars": args.tts_max_chars,
        "whisper_model": args.whisper_model,
        "whisper_batch_size": args.whisper_batch_size,
        "whisper_compute_type": args.whisper_compute_type,
        "device": whisper_data.get("device", args.device),
        "timing_seconds": {
            "tts_synthesis_and_save": t1 - t0,
            "whisperx_pipeline_subprocess": t3 - t1,
            "total": t3 - t0,
        },
        "counts": {"input_chars": len(text), **whisper_data.get("counts", {})},
        "whisper_timing_seconds": whisper_data.get("timing_seconds", {}),
    }
    report_json = Path(args.report_json)
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
