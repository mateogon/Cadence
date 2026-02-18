import argparse
import csv
import threading
import time
from pathlib import Path

import numpy as np

from generate_audiobook_supertonic import (
    DEFAULT_VOICE,
    get_smart_chunks,
    init_tts_engine,
    sanitize_text,
)


def parse_workers(value):
    out = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        out.append(max(1, int(item)))
    if not out:
        raise ValueError("No workers provided.")
    return sorted(set(out))


def synthesize_serial(chunks, voice, repeats):
    tts = init_tts_engine()
    voice_style = tts.get_voice_style(voice_name=voice)
    supported_chars = tts.model.text_processor.supported_character_set

    best = None
    for _ in range(repeats):
        start = time.perf_counter()
        wavs = []
        for chunk in chunks:
            clean = sanitize_text(chunk, supported_chars)
            if not clean:
                continue
            wav, _ = tts.synthesize(clean, voice_style=voice_style, lang="en")
            wavs.append(wav)
        _ = np.concatenate(wavs, axis=1) if wavs else None
        elapsed = time.perf_counter() - start
        if best is None or elapsed < best:
            best = elapsed
    return best


def synthesize_parallel(chunks, voice, workers, repeats):
    import concurrent.futures

    thread_local = threading.local()

    def get_thread_state():
        if not hasattr(thread_local, "state"):
            tts = init_tts_engine()
            voice_style = tts.get_voice_style(voice_name=voice)
            supported_chars = tts.model.text_processor.supported_character_set
            thread_local.state = (tts, voice_style, supported_chars)
        return thread_local.state

    def task(item):
        idx, chunk = item
        tts, voice_style, supported_chars = get_thread_state()
        clean = sanitize_text(chunk, supported_chars)
        if not clean:
            return idx, None
        wav, _ = tts.synthesize(clean, voice_style=voice_style, lang="en")
        return idx, wav

    best = None
    for _ in range(repeats):
        start = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            items = list(enumerate(chunks))
            results = list(ex.map(task, items))
        results.sort(key=lambda x: x[0])
        wavs = [wav for _, wav in results if wav is not None]
        _ = np.concatenate(wavs, axis=1) if wavs else None
        elapsed = time.perf_counter() - start
        if best is None or elapsed < best:
            best = elapsed
    return best


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark chunk-level parallelization on one text file."
    )
    parser.add_argument("input_txt", help="Path to source chapter .txt")
    parser.add_argument("--voice", "-v", default=DEFAULT_VOICE)
    parser.add_argument("--max-chars", type=int, default=1600)
    parser.add_argument("--workers", default="1,2,3,4")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--output-csv", default="benchmark_single_file_chunks.csv")
    args = parser.parse_args()

    input_path = Path(args.input_txt)
    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Input file is empty: {input_path}")

    chunks = get_smart_chunks(text, max_chars=args.max_chars)
    workers = parse_workers(args.workers)

    print(
        f"Benchmarking {input_path.name}: chunks={len(chunks)}, chars={len(text)}, "
        f"workers={workers}, repeats={args.repeats}"
    )

    rows = []
    for w in workers:
        if w == 1:
            seconds = synthesize_serial(chunks, args.voice, args.repeats)
        else:
            seconds = synthesize_parallel(chunks, args.voice, w, args.repeats)
        chunks_per_sec = len(chunks) / seconds if seconds > 0 else 0.0
        chars_per_sec = len(text) / seconds if seconds > 0 else 0.0
        rows.append(
            {
                "workers": w,
                "seconds_best_of_repeats": seconds,
                "chunks": len(chunks),
                "chars": len(text),
                "chunks_per_sec": chunks_per_sec,
                "chars_per_sec": chars_per_sec,
            }
        )
        print(
            f"workers={w} best_sec={seconds:.2f} chunks/sec={chunks_per_sec:.2f} chars/sec={chars_per_sec:.1f}"
        )

    out_csv = Path(args.output_csv)
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "workers",
                "seconds_best_of_repeats",
                "chunks",
                "chars",
                "chunks_per_sec",
                "chars_per_sec",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote: {out_csv.resolve()}")


if __name__ == "__main__":
    main()
