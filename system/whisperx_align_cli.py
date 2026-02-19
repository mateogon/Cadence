import argparse
import json
import sys
import time
from pathlib import Path


def collect_words(aligned_result):
    words = []
    for segment in aligned_result.get("segments", []):
        for word in segment.get("words", []):
            text = (word.get("word") or "").strip()
            if not text:
                continue
            start = word.get("start")
            end = word.get("end")
            if start is None or end is None:
                continue
            words.append({"word": text, "start": float(start), "end": float(end)})
    return words


def resolve_device(device_arg, torch_module):
    device = (device_arg or "auto").strip().lower()
    if device == "auto":
        return "cuda" if torch_module.cuda.is_available() else "cpu"
    return device


def main():
    parser = argparse.ArgumentParser(description="Run WhisperX align for one chapter.")
    parser.add_argument("input_wav", type=Path)
    parser.add_argument("source_txt", type=Path)
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-batch-size", type=int, default=16)
    parser.add_argument("--whisper-compute-type", default="float16")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    args = parser.parse_args()

    try:
        import torch
        import whisperx
    except Exception as exc:
        print(f"Failed to import whisperx/torch: {exc}", file=sys.stderr)
        return 2

    if not args.input_wav.exists():
        print(f"Missing wav file: {args.input_wav}", file=sys.stderr)
        return 2
    if not args.source_txt.exists():
        print(f"Missing source txt file: {args.source_txt}", file=sys.stderr)
        return 2

    device = resolve_device(args.device, torch)
    report = {
        "input_wav": str(args.input_wav),
        "source_txt": str(args.source_txt),
        "device": device,
        "whisper_model": args.whisper_model,
        "whisper_batch_size": int(args.whisper_batch_size),
        "whisper_compute_type": args.whisper_compute_type,
        "timing_seconds": {},
    }

    from system.book_manager import BookManager

    t0 = time.perf_counter()
    model = whisperx.load_model(
        args.whisper_model,
        device=device,
        compute_type=args.whisper_compute_type,
        language="en",
    )
    audio = whisperx.load_audio(str(args.input_wav))
    asr_result = model.transcribe(audio, batch_size=int(args.whisper_batch_size))

    align_model, align_metadata = whisperx.load_align_model(
        language_code=asr_result["language"],
        device=device,
    )
    aligned = whisperx.align(
        asr_result["segments"],
        align_model,
        align_metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    t1 = time.perf_counter()

    raw_words = collect_words(aligned)
    source_text = args.source_txt.read_text(encoding="utf-8", errors="replace")
    final_words = BookManager.align_timestamps(source_text, raw_words)
    args.output_json.write_text(
        json.dumps(final_words, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    t2 = time.perf_counter()
    report["counts"] = {
        "asr_words": len(raw_words),
        "final_words": len(final_words),
    }
    report["timing_seconds"] = {
        "whisperx_transcribe_and_align": t1 - t0,
        "robust_text_alignment_and_save": t2 - t1,
        "total": t2 - t0,
    }
    args.report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
