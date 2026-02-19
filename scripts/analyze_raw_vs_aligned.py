#!/usr/bin/env python3
"""
Analyze differences between raw WhisperX JSON and final aligned JSON.

Expected chapter files:
- content/ch_XXX_raw.json   (raw WhisperX words/timings)
- content/ch_XXX.json       (post-alignment output used by reader)

Outputs:
- raw_vs_aligned_report.json
- raw_vs_aligned_summary.csv
- raw_vs_aligned_cases.jsonl
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

NORMALIZE_MAP = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "—": "-",
    "–": "-",
}


def normalize_clean(text: str) -> str:
    out = (text or "").lower()
    for k, v in NORMALIZE_MAP.items():
        out = out.replace(k, v)
    out = re.sub(r"[^\w]", "", out)
    return out


def load_word_json(path: Path) -> List[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        w = str(item.get("word", ""))
        s = item.get("start")
        e = item.get("end")
        if s is None or e is None:
            continue
        try:
            out.append({"word": w, "start": float(s), "end": float(e), "clean": normalize_clean(w)})
        except Exception:
            continue
    return out


def cleaned_tokens(words: List[dict]) -> List[dict]:
    return [w for w in words if w["clean"]]


def chapter_pairs(book_dir: Path) -> List[Tuple[str, Path, Path]]:
    content = book_dir / "content"
    if not content.exists():
        return []
    pairs = []
    for aligned in sorted(content.glob("ch_*.json")):
        stem = aligned.stem
        if not re.match(r"^ch_\d{3}$", stem):
            continue
        raw = content / f"{stem}_raw.json"
        if raw.exists():
            pairs.append((stem, raw, aligned))
    return pairs


def txt_word_count_from_file(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return 0
    return len(re.findall(r"[A-Za-z0-9']+", text))


def analyze_pair(stem: str, raw_words: List[dict], aligned_words: List[dict], case_limit: int):
    raw_clean = cleaned_tokens(raw_words)
    aligned_clean = cleaned_tokens(aligned_words)

    raw_seq = [w["clean"] for w in raw_clean]
    aligned_seq = [w["clean"] for w in aligned_clean]

    m = difflib.SequenceMatcher(None, raw_seq, aligned_seq)
    opcodes = m.get_opcodes()

    equal_tokens = 0
    replace_ops = 0
    insert_ops = 0
    delete_ops = 0
    changed_tokens = 0
    time_shift_samples = []
    cases = []
    one_to_one_replacements = Counter()

    for tag, i1, i2, j1, j2 in opcodes:
        raw_count = max(0, i2 - i1)
        aligned_count = max(0, j2 - j1)
        if tag == "equal":
            equal_tokens += raw_count
            for k in range(raw_count):
                rw = raw_clean[i1 + k]
                aw = aligned_clean[j1 + k]
                time_shift_samples.append(abs(rw["start"] - aw["start"]))
            continue

        changed_tokens += max(raw_count, aligned_count)
        if tag == "replace":
            replace_ops += 1
            if raw_count == 1 and aligned_count == 1:
                one_to_one_replacements[(raw_seq[i1], aligned_seq[j1])] += 1
        elif tag == "insert":
            insert_ops += 1
        elif tag == "delete":
            delete_ops += 1

        if len(cases) < case_limit:
            cases.append(
                {
                    "chapter": stem,
                    "tag": tag,
                    "raw_tokens": [w["word"] for w in raw_clean[i1:i2]],
                    "aligned_tokens": [w["word"] for w in aligned_clean[j1:j2]],
                    "raw_clean": raw_seq[i1:i2],
                    "aligned_clean": aligned_seq[j1:j2],
                }
            )

    total_base = max(len(raw_seq), 1)
    mismatch_ratio = changed_tokens / total_base
    avg_start_shift = (sum(time_shift_samples) / len(time_shift_samples)) if time_shift_samples else 0.0

    summary = {
        "chapter": stem,
        "raw_tokens_clean": len(raw_seq),
        "aligned_tokens_clean": len(aligned_seq),
        "equal_tokens": equal_tokens,
        "changed_tokens": changed_tokens,
        "mismatch_ratio": round(mismatch_ratio, 6),
        "replace_ops": replace_ops,
        "insert_ops": insert_ops,
        "delete_ops": delete_ops,
        "avg_start_shift_on_equal": round(avg_start_shift, 6),
        "one_to_one_replacements_top": [
            {"raw": k[0], "aligned": k[1], "count": v}
            for k, v in one_to_one_replacements.most_common(8)
        ],
    }
    return summary, cases, one_to_one_replacements


def write_outputs(out_dir: Path, report: dict, rows: List[dict], cases: List[dict]):
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw_vs_aligned_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    with (out_dir / "raw_vs_aligned_summary.csv").open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "book",
            "chapter",
            "txt_words",
            "raw_tokens_clean",
            "aligned_tokens_clean",
            "aligned_vs_txt_token_ratio",
            "equal_tokens",
            "changed_tokens",
            "mismatch_ratio",
            "replace_ops",
            "insert_ops",
            "delete_ops",
            "avg_start_shift_on_equal",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fieldnames})

    with (out_dir / "raw_vs_aligned_cases.jsonl").open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Analyze raw WhisperX JSON vs aligned JSON deltas.")
    parser.add_argument("--library", default="library", help="Library root path")
    parser.add_argument("--book", default="", help="Optional substring filter for book folder name")
    parser.add_argument("--max-chapters", type=int, default=0, help="Limit chapters analyzed (0=all)")
    parser.add_argument("--case-limit", type=int, default=12, help="Mismatch cases to keep per chapter")
    parser.add_argument("--out-dir", default="alignment_delta_output", help="Output directory")
    parser.add_argument(
        "--content-only",
        action="store_true",
        help="Skip very short chapters and focus on likely content chapters",
    )
    parser.add_argument(
        "--min-content-words",
        type=int,
        default=300,
        help="Minimum TXT words to include when --content-only is enabled",
    )
    args = parser.parse_args()

    lib = Path(args.library)
    if not lib.exists():
        raise SystemExit(f"Library path not found: {lib}")

    books = [d for d in sorted(lib.iterdir()) if d.is_dir()]
    if args.book:
        books = [b for b in books if args.book.lower() in b.name.lower()]

    rows = []
    cases_all = []
    replacements_all = Counter()
    skipped_short = 0

    for book_dir in books:
        pairs = chapter_pairs(book_dir)
        if args.max_chapters > 0:
            pairs = pairs[: args.max_chapters]
        for stem, raw_path, aligned_path in pairs:
            txt_path = book_dir / "content" / f"{stem}.txt"
            txt_word_count = txt_word_count_from_file(txt_path)
            if args.content_only and txt_word_count < args.min_content_words:
                skipped_short += 1
                continue

            raw_words = load_word_json(raw_path)
            aligned_words = load_word_json(aligned_path)
            summary, cases, repl = analyze_pair(
                stem=stem,
                raw_words=raw_words,
                aligned_words=aligned_words,
                case_limit=args.case_limit,
            )
            summary["book"] = book_dir.name
            summary["txt_words"] = txt_word_count
            # Sanity metric: aligned content should mirror source text tokenization.
            # We approximate by comparing cleaned aligned token count vs txt word count.
            summary["aligned_vs_txt_token_ratio"] = round(
                (summary["aligned_tokens_clean"] / max(txt_word_count, 1)), 6
            )
            rows.append(summary)
            for c in cases:
                c["book"] = book_dir.name
                c["raw_path"] = str(raw_path)
                c["aligned_path"] = str(aligned_path)
                c["mismatch_ratio"] = summary["mismatch_ratio"]
                cases_all.append(c)
            replacements_all.update(repl)

    rows_sorted = sorted(rows, key=lambda r: r["mismatch_ratio"], reverse=True)
    avg_mismatch = (sum(r["mismatch_ratio"] for r in rows) / len(rows)) if rows else 0.0
    report = {
        "library": str(lib.resolve()),
        "chapters_analyzed": len(rows),
        "chapters_skipped_short": skipped_short,
        "avg_mismatch_ratio": avg_mismatch,
        "top_chapters": rows_sorted[:20],
        "top_replacements_global": [
            {"raw": k[0], "aligned": k[1], "count": v}
            for k, v in replacements_all.most_common(30)
        ],
        "filters": {
            "content_only": bool(args.content_only),
            "min_content_words": int(args.min_content_words),
        },
    }

    out_dir = Path(args.out_dir)
    write_outputs(out_dir, report, rows, cases_all)

    print(f"Analyzed chapters: {len(rows)}")
    print(f"Skipped short chapters: {skipped_short}")
    print(f"Average mismatch ratio (raw -> aligned): {avg_mismatch:.4f}")
    print(f"Wrote: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
