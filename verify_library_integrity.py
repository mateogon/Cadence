import argparse
import json
import re
import statistics
from pathlib import Path


def robust_zscores(values):
    if not values:
        return []
    median = statistics.median(values)
    abs_devs = [abs(v - median) for v in values]
    mad = statistics.median(abs_devs)
    if mad == 0:
        scale = max(abs(median) * 0.1, 1.0)
        return [abs(v - median) / scale for v in values]
    return [0.6745 * abs(v - median) / mad for v in values]


def build_chapter_rows(book_dir):
    content_dir = book_dir / "content"
    audio_dir = book_dir / "audio"

    chapter_name_re = re.compile(r"^ch_\d{3}$")

    txt_stems = {
        p.stem for p in content_dir.glob("ch_*.txt") if chapter_name_re.match(p.stem)
    }
    wav_stems = {
        p.stem for p in audio_dir.glob("ch_*.wav") if chapter_name_re.match(p.stem)
    }
    # Exclude ch_XXX.whisperx_report.json and any non-chapter JSON files.
    json_stems = {
        p.stem
        for p in content_dir.glob("ch_*.json")
        if chapter_name_re.match(p.stem)
    }
    stems = sorted(txt_stems | wav_stems | json_stems)

    rows = []
    for stem in stems:
        txt = content_dir / f"{stem}.txt"
        wav = audio_dir / f"{stem}.wav"
        jsn = content_dir / f"{stem}.json"
        row = {
            "book": book_dir.name,
            "chapter": stem,
            "txt_exists": txt.exists(),
            "wav_exists": wav.exists(),
            "json_exists": jsn.exists(),
            "txt_bytes": txt.stat().st_size if txt.exists() else 0,
            "wav_bytes": wav.stat().st_size if wav.exists() else 0,
            "json_bytes": jsn.stat().st_size if jsn.exists() else 0,
            "issues": [],
        }
        rows.append(row)
    return rows


def add_issue(row, issue):
    if issue not in row["issues"]:
        row["issues"].append(issue)


def analyze_rows(rows, z_threshold, min_txt_for_ratio):
    ratio_rows = [
        r
        for r in rows
        if (
            r["txt_bytes"] >= min_txt_for_ratio
            and r["wav_bytes"] > 0
            and r["json_bytes"] > 0
        )
    ]

    r_audio_txt = [r["wav_bytes"] / r["txt_bytes"] for r in ratio_rows]
    r_json_txt = [r["json_bytes"] / r["txt_bytes"] for r in ratio_rows]
    r_json_audio = [r["json_bytes"] / r["wav_bytes"] for r in ratio_rows]

    z1 = robust_zscores(r_audio_txt)
    z2 = robust_zscores(r_json_txt)
    z3 = robust_zscores(r_json_audio)

    for r in rows:
        if not r["txt_exists"]:
            add_issue(r, "missing_txt")
        if not r["wav_exists"]:
            add_issue(r, "missing_wav")
        if not r["json_exists"]:
            add_issue(r, "missing_json")
        if r["txt_exists"] and r["txt_bytes"] < 80:
            add_issue(r, "txt_too_small")
        if r["wav_exists"] and r["wav_bytes"] < 5000:
            add_issue(r, "wav_too_small")
        if r["json_exists"] and r["json_bytes"] < 100:
            add_issue(r, "json_too_small")

    for i, r in enumerate(ratio_rows):
        if z1[i] > z_threshold:
            add_issue(r, "audio_txt_ratio_outlier")
        if z2[i] > z_threshold:
            add_issue(r, "json_txt_ratio_outlier")
        if z3[i] > z_threshold:
            add_issue(r, "json_audio_ratio_outlier")

    return {
        "ratio_medians": {
            "audio_per_txt": statistics.median(r_audio_txt) if r_audio_txt else None,
            "json_per_txt": statistics.median(r_json_txt) if r_json_txt else None,
            "json_per_audio": statistics.median(r_json_audio) if r_json_audio else None,
        },
        "complete_triplets": len(ratio_rows),
        "total_rows": len(rows),
    }


def run_scan(library_dir, z_threshold, min_txt_for_ratio):
    books = [p for p in library_dir.iterdir() if p.is_dir()]
    all_rows = []
    per_book = {}

    for book in books:
        rows = build_chapter_rows(book)
        stats = analyze_rows(rows, z_threshold, min_txt_for_ratio)
        flagged = [r for r in rows if r["issues"]]
        per_book[book.name] = {
            "stats": stats,
            "flagged_count": len(flagged),
            "rows": rows,
        }
        all_rows.extend(rows)

    global_stats = analyze_rows(all_rows, z_threshold, min_txt_for_ratio) if all_rows else {}
    global_flagged = [r for r in all_rows if r["issues"]]

    return {
        "library": str(library_dir),
        "z_threshold": z_threshold,
        "min_txt_for_ratio": min_txt_for_ratio,
        "book_count": len(books),
        "global_stats": global_stats,
        "global_flagged_count": len(global_flagged),
        "books": per_book,
    }


def print_report(report):
    print(f"Library: {report['library']}")
    print(f"Books: {report['book_count']}")
    print(f"Flagged chapters: {report['global_flagged_count']}")
    gs = report.get("global_stats", {})
    med = gs.get("ratio_medians", {})
    if med:
        print("Median ratios:")
        print(f"  audio/txt:  {med.get('audio_per_txt')}")
        print(f"  json/txt:   {med.get('json_per_txt')}")
        print(f"  json/audio: {med.get('json_per_audio')}")
    print("")

    for book, payload in sorted(report["books"].items()):
        flagged = [r for r in payload["rows"] if r["issues"]]
        if not flagged:
            continue
        print(f"{book}  ({len(flagged)} flagged)")
        for r in flagged:
            print(
                f"  {r['chapter']}: "
                f"txt={r['txt_bytes']} wav={r['wav_bytes']} json={r['json_bytes']} "
                f"issues={','.join(r['issues'])}"
            )
        print("")


def main():
    parser = argparse.ArgumentParser(
        description="Scan library artifacts and flag suspicious/incomplete chapters."
    )
    parser.add_argument(
        "--library",
        default="library",
        help="Path to library root (default: library)",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=4.0,
        help="Robust z-score threshold for ratio outliers (default: 4.0)",
    )
    parser.add_argument(
        "--min-txt-for-ratio",
        type=int,
        default=300,
        help="Ignore txt shorter than this (bytes) for ratio outlier checks (default: 300)",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional path to write full machine-readable report JSON",
    )
    args = parser.parse_args()

    library_dir = Path(args.library)
    if not library_dir.exists():
        raise SystemExit(f"Library path not found: {library_dir}")

    report = run_scan(library_dir, args.z_threshold, args.min_txt_for_ratio)
    print_report(report)

    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Wrote JSON report: {out}")


if __name__ == "__main__":
    main()
