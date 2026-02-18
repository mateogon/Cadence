import argparse
import csv
import threading
import time
from pathlib import Path

from adapters.supertonic_backend import SupertonicBackend


def parse_workers(value):
    workers = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        workers.append(max(1, int(item)))
    if not workers:
        raise ValueError("No worker counts provided.")
    return sorted(set(workers))


def select_files(input_dir, glob_pattern, files_csv, max_files):
    if files_csv:
        names = [n.strip() for n in files_csv.split(",") if n.strip()]
        return [input_dir / n for n in names]
    files = sorted(input_dir.glob(glob_pattern))
    if max_files and max_files > 0:
        files = files[:max_files]
    return files


def run_single_worker(text_items, voice, max_chars, warmup, include_init):
    backend = SupertonicBackend()
    if not include_init:
        backend.ensure_model()
    if warmup:
        backend.synthesize("Warmup line. Don't panic.", voice, max_chars=max_chars)

    start = time.perf_counter()
    for _, text in text_items:
        backend.synthesize(text, voice, max_chars=max_chars)
    return time.perf_counter() - start


def run_multi_worker(text_items, voice, max_chars, workers, warmup, include_init):
    import concurrent.futures

    thread_local = threading.local()

    def get_backend():
        if not hasattr(thread_local, "backend"):
            backend = SupertonicBackend()
            if not include_init:
                backend.ensure_model()
            thread_local.backend = backend
        return thread_local.backend

    def warmup_task(_):
        backend = get_backend()
        backend.synthesize("Warmup line. Don't panic.", voice, max_chars=max_chars)
        return True

    def synth_task(item):
        _, text = item
        backend = get_backend()
        backend.synthesize(text, voice, max_chars=max_chars)
        return True

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        if warmup:
            list(executor.map(warmup_task, range(workers)))

        start = time.perf_counter()
        list(executor.map(synth_task, text_items))
        return time.perf_counter() - start


def benchmark(text_items, voice, max_chars, workers, repeats, warmup, include_init):
    rows = []
    total_chars = sum(len(text) for _, text in text_items)
    chapter_count = len(text_items)

    for w in workers:
        for run in range(1, repeats + 1):
            if w == 1:
                seconds = run_single_worker(
                    text_items=text_items,
                    voice=voice,
                    max_chars=max_chars,
                    warmup=warmup,
                    include_init=include_init,
                )
            else:
                seconds = run_multi_worker(
                    text_items=text_items,
                    voice=voice,
                    max_chars=max_chars,
                    workers=w,
                    warmup=warmup,
                    include_init=include_init,
                )

            chapters_per_min = (chapter_count / seconds) * 60.0 if seconds > 0 else 0.0
            chars_per_sec = (total_chars / seconds) if seconds > 0 else 0.0

            rows.append(
                {
                    "workers": w,
                    "run": run,
                    "seconds": seconds,
                    "chapters_per_min": chapters_per_min,
                    "chars_per_sec": chars_per_sec,
                    "chapters": chapter_count,
                    "chars": total_chars,
                }
            )
            print(
                f"[workers={w}] run={run} sec={seconds:.2f} "
                f"chap/min={chapters_per_min:.2f} chars/sec={chars_per_sec:.1f}"
            )
    return rows


def write_reports(rows, output_csv, output_md):
    with output_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "workers",
                "run",
                "seconds",
                "chapters_per_min",
                "chars_per_sec",
                "chapters",
                "chars",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    by_worker = {}
    for row in rows:
        by_worker.setdefault(row["workers"], []).append(row)

    summary = []
    for w, items in sorted(by_worker.items()):
        avg_seconds = sum(r["seconds"] for r in items) / len(items)
        avg_cpm = sum(r["chapters_per_min"] for r in items) / len(items)
        avg_cps = sum(r["chars_per_sec"] for r in items) / len(items)
        summary.append((w, avg_seconds, avg_cpm, avg_cps))

    with output_md.open("w", encoding="utf-8") as f:
        f.write("# Supertonic Worker Benchmark\n\n")
        f.write("| Workers | Avg Seconds | Avg Chapters/Min | Avg Chars/Sec |\n")
        f.write("|---|---:|---:|---:|\n")
        for w, avg_seconds, avg_cpm, avg_cps in summary:
            f.write(f"| {w} | {avg_seconds:.2f} | {avg_cpm:.2f} | {avg_cps:.1f} |\n")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark Supertonic synthesis throughput across worker counts."
    )
    parser.add_argument("input_dir", help="Directory with chapter .txt files")
    parser.add_argument("--voice", "-v", default="M3")
    parser.add_argument("--workers", default="1,2,3,4")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--max-chars", type=int, default=1600)
    parser.add_argument("--glob", default="ch_*.txt")
    parser.add_argument(
        "--files",
        default="",
        help="Comma-separated chapter files (overrides --glob/--max-files)",
    )
    parser.add_argument("--max-files", type=int, default=8)
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument(
        "--include-init",
        action="store_true",
        help="Include model initialization time inside each run timing.",
    )
    parser.add_argument("--output-csv", default="benchmark_supertonic_workers.csv")
    parser.add_argument("--output-md", default="benchmark_supertonic_workers.md")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        raise FileNotFoundError(f"Input dir not found: {input_dir}")

    selected = select_files(
        input_dir=input_dir,
        glob_pattern=args.glob,
        files_csv=args.files,
        max_files=args.max_files,
    )
    selected = [p for p in selected if p.exists()]
    if not selected:
        raise RuntimeError("No input .txt files selected.")

    text_items = []
    for p in selected:
        text = p.read_text(encoding="utf-8").strip()
        if text:
            text_items.append((p.name, text))
    if not text_items:
        raise RuntimeError("Selected files are empty.")

    workers = parse_workers(args.workers)
    warmup = not args.no_warmup
    total_chars = sum(len(text) for _, text in text_items)
    print(
        f"Benchmarking {len(text_items)} chapters ({total_chars} chars) "
        f"with workers={workers}, repeats={args.repeats}, max_chars={args.max_chars}"
    )

    rows = benchmark(
        text_items=text_items,
        voice=args.voice,
        max_chars=args.max_chars,
        workers=workers,
        repeats=args.repeats,
        warmup=warmup,
        include_init=args.include_init,
    )

    output_csv = Path(args.output_csv)
    output_md = Path(args.output_md)
    write_reports(rows, output_csv, output_md)
    print(f"\nWrote: {output_csv.resolve()}")
    print(f"Wrote: {output_md.resolve()}")


if __name__ == "__main__":
    main()
