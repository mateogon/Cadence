import argparse
import json
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from system.book_manager import BookManager
from ui.app import App


def percentile(values, p):
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    k = (len(values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return float(values[f])
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return float(d0 + d1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Benchmark Cadence player resize responsiveness."
    )
    parser.add_argument("--book-index", type=int, default=0, help="Index from library list.")
    parser.add_argument("--cycles", type=int, default=3, help="Resize cycles.")
    parser.add_argument("--min-width", type=int, default=980, help="Minimum window width.")
    parser.add_argument("--max-width", type=int, default=1500, help="Maximum window width.")
    parser.add_argument("--height", type=int, default=860, help="Window height during test.")
    parser.add_argument("--steps", type=int, default=16, help="Width steps per half cycle.")
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Optional path to write full metrics JSON (omit for console-only).",
    )
    return parser.parse_args()


def build_width_sequence(min_w, max_w, steps):
    steps = max(2, steps)
    if max_w <= min_w:
        max_w = min_w + 200
    delta = (max_w - min_w) / float(steps - 1)
    up = [int(round(min_w + i * delta)) for i in range(steps)]
    down = list(reversed(up))
    return up, down


def main():
    args = parse_args()
    books = BookManager.get_books()
    if not books:
        raise SystemExit("No books in library. Import at least one book first.")
    if args.book_index < 0 or args.book_index >= len(books):
        raise SystemExit(
            f"book-index out of range. got={args.book_index}, available=0..{len(books)-1}"
        )

    book = books[args.book_index]
    up, down = build_width_sequence(args.min_width, args.max_width, args.steps)

    app = App(debug=False)
    app.geometry(f"{args.min_width}x{args.height}")
    app.update_idletasks()
    app.show_player(book)
    app.update_idletasks()

    # Ensure we benchmark the expensive mode you are tuning.
    if app.player_view.core is not None:
        app.player_view.core.update_settings(
            {"reading_view_mode": "context", "context_force_center": True}
        )

    metrics = {
        "book_title": book.get("title", ""),
        "book_path": book.get("path", ""),
        "cycles": args.cycles,
        "min_width": args.min_width,
        "max_width": args.max_width,
        "height": args.height,
        "steps_per_half_cycle": args.steps,
        "configure_events": 0,
        "samples_ms": [],
    }

    def on_configure(_event):
        metrics["configure_events"] += 1

    app.player_view.bind("<Configure>", on_configure, add="+")

    def run_benchmark():
        t0 = time.perf_counter()
        samples = []
        for _ in range(args.cycles):
            for width in up:
                s = time.perf_counter()
                app.geometry(f"{width}x{args.height}")
                app.update_idletasks()
                app.update()
                samples.append((time.perf_counter() - s) * 1000.0)
            for width in down:
                s = time.perf_counter()
                app.geometry(f"{width}x{args.height}")
                app.update_idletasks()
                app.update()
                samples.append((time.perf_counter() - s) * 1000.0)
        total_s = time.perf_counter() - t0

        sorted_samples = sorted(samples)
        metrics["samples_ms"] = samples
        metrics["summary"] = {
            "count": len(samples),
            "total_seconds": total_s,
            "mean_ms": statistics.fmean(samples) if samples else 0.0,
            "median_ms": statistics.median(samples) if samples else 0.0,
            "p90_ms": percentile(sorted_samples, 90),
            "p95_ms": percentile(sorted_samples, 95),
            "max_ms": max(samples) if samples else 0.0,
        }

        if args.output_json and args.output_json.strip():
            out_path = Path(args.output_json)
            out_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
            print(f"Wrote metrics: {out_path.resolve()}")
        print(json.dumps(metrics["summary"], indent=2))
        app.destroy()

    app.after(500, run_benchmark)
    app.mainloop()


if __name__ == "__main__":
    main()
