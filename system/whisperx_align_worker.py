import argparse
import json
import sys
import time
from pathlib import Path

import torch
import whisperx

# Ensure local package imports work even when launched as a direct script path.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from system.book_manager import BookManager


def atomic_write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
            raise RuntimeError(f"Temporary JSON write failed: {tmp_path}")
        tmp_path.replace(path)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(description="Persistent WhisperX alignment worker.")
    parser.add_argument("--whisper-model", default="small")
    parser.add_argument("--whisper-batch-size", type=int, default=24)
    parser.add_argument("--whisper-compute-type", default="float16")
    parser.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    args = parser.parse_args()

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device

    compute_type = args.whisper_compute_type
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"

    model = whisperx.load_model(
        args.whisper_model,
        device,
        compute_type=compute_type,
    )
    # Lazy-init align model once language is known from first transcript.
    align_models = {}

    emit(
        {
            "event": "ready",
            "device": device,
            "whisper_model": args.whisper_model,
            "whisper_batch_size": args.whisper_batch_size,
            "requested_compute_type": args.whisper_compute_type,
            "resolved_compute_type": compute_type,
        }
    )

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as exc:
            emit({"event": "error", "error": f"invalid_json: {exc}"})
            continue

        cmd = req.get("cmd")
        if cmd == "shutdown":
            emit({"event": "bye"})
            return 0
        if cmd != "align":
            emit({"event": "error", "error": f"unknown_cmd: {cmd}"})
            continue

        wav_path = Path(str(req.get("wav", "")))
        txt_path = Path(str(req.get("txt", "")))
        out_json = Path(str(req.get("out_json", "")))
        report_json = Path(str(req.get("report_json", "")))
        raw_json = Path(str(req.get("raw_json", "")))

        if not wav_path.exists():
            emit({"event": "error", "error": f"missing_wav: {wav_path}"})
            continue
        if not txt_path.exists():
            emit({"event": "error", "error": f"missing_txt: {txt_path}"})
            continue

        try:
            text = txt_path.read_text(encoding="utf-8")
            t0 = time.perf_counter()
            audio = whisperx.load_audio(str(wav_path))
            result = model.transcribe(audio, batch_size=args.whisper_batch_size)

            language_code = result["language"]
            if language_code not in align_models:
                model_a, alignment_meta = whisperx.load_align_model(
                    language_code=language_code, device=device
                )
                align_models[language_code] = (model_a, alignment_meta)
            else:
                model_a, alignment_meta = align_models[language_code]

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

            atomic_write_json(raw_json, asr_words)
            final_word_list = BookManager.align_timestamps(text, asr_words)
            atomic_write_json(out_json, final_word_list)
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
            atomic_write_json(report_json, report)

            emit(
                {
                    "event": "aligned",
                    "wav": str(wav_path),
                    "out_json": str(out_json),
                    "report_json": str(report_json),
                    "timing_seconds": report["timing_seconds"],
                    "device": device,
                }
            )
        except Exception as exc:
            emit({"event": "error", "error": str(exc), "wav": str(wav_path)})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
