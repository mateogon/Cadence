import argparse
import json
import time
from pathlib import Path

import torch
import whisperx

from system.book_manager import BookManager


def main():
    parser = argparse.ArgumentParser(
        description="WhisperX-only benchmark/alignment from existing WAV and TXT."
    )
    parser.add_argument("input_wav")
    parser.add_argument("input_txt")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-batch-size", type=int, default=24)
    parser.add_argument("--whisper-compute-type", default="float16")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    parser.add_argument("--output-json", default="benchmark_e2e_single.json")
    parser.add_argument("--report-json", default="benchmark_e2e_whisper_report.json")
    args = parser.parse_args()

    wav_path = Path(args.input_wav)
    txt_path = Path(args.input_txt)
    if not wav_path.exists():
        raise FileNotFoundError(f"Missing WAV: {wav_path}")
    if not txt_path.exists():
        raise FileNotFoundError(f"Missing TXT: {txt_path}")
    text = txt_path.read_text(encoding="utf-8")

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device
    compute_type = args.whisper_compute_type
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"
        print("CPU detected: overriding compute_type float16 -> int8 for compatibility.")

    t0 = time.perf_counter()
    model = whisperx.load_model(
        args.whisper_model,
        device,
        compute_type=compute_type,
    )
    audio = whisperx.load_audio(str(wav_path))
    result = model.transcribe(audio, batch_size=args.whisper_batch_size)
    model_a, alignment_meta = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    aligned = whisperx.align(
        result["segments"],
        model_a,
        alignment_meta,
        audio,
        device,
        return_char_alignments=False,
    )
    t1 = time.perf_counter()

    asr_words = []
    for segment in aligned["segments"]:
        for word in segment.get("words", []):
            if "start" in word:
                asr_words.append(
                    {
                        "word": word["word"],
                        "start": word["start"],
                        "end": word["end"],
                    }
                )

    final_word_list = BookManager.align_timestamps(text, asr_words)
    out_json = Path(args.output_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(final_word_list, indent=2), encoding="utf-8")
    t2 = time.perf_counter()

    report = {
        "device": device,
        "whisper_model": args.whisper_model,
        "whisper_batch_size": args.whisper_batch_size,
        "whisper_compute_type": args.whisper_compute_type,
        "resolved_compute_type": compute_type,
        "timing_seconds": {
            "whisperx_transcribe_and_align": t1 - t0,
            "robust_text_alignment_and_save": t2 - t1,
            "total": t2 - t0,
        },
        "counts": {
            "asr_words": len(asr_words),
            "final_words": len(final_word_list),
        },
    }
    report_path = Path(args.report_json)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
