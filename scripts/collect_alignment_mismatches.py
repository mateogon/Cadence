#!/usr/bin/env python3
"""
Collect alignment mismatch metrics and test snippets from audiobook chapters.

Outputs:
- JSON report with per-chapter metrics and mismatch spans
- CSV summary
- JSONL mismatch cases
- Text snippets directory (ready to synthesize as mini test chapters)
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import torch
import whisperx


NORMALIZE_MAP = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "—": "-",
    "–": "-",
}


@dataclass
class Token:
    text: str
    clean: str
    idx: int


def normalize_clean(text: str) -> str:
    out = text.lower()
    for k, v in NORMALIZE_MAP.items():
        out = out.replace(k, v)
    out = re.sub(r"[^\w]", "", out)
    return out


def tokenize_for_match(text: str) -> List[Token]:
    splits = re.split(r"(\s+)", text)
    tokens: List[Token] = []
    for i, s in enumerate(splits):
        if s == "":
            continue
        tokens.append(Token(text=s, clean=normalize_clean(s), idx=i))
    return tokens


def extract_raw_words(aligned: dict) -> List[dict]:
    words = []
    for segment in aligned.get("segments", []):
        for word in segment.get("words", []):
            if "start" in word and "end" in word and word.get("word", "").strip():
                words.append(
                    {
                        "word": str(word["word"]),
                        "start": float(word["start"]),
                        "end": float(word["end"]),
                    }
                )
    return words


def chapter_stem_paths(book_dir: Path) -> List[Tuple[str, Path, Path]]:
    content_dir = book_dir / "content"
    audio_dir = book_dir / "audio"
    out = []
    for txt in sorted(content_dir.glob("ch_*.txt")):
        stem = txt.stem
        if not re.match(r"^ch_\d{3}$", stem):
            continue
        wav = audio_dir / f"{stem}.wav"
        if wav.exists() and wav.stat().st_size > 0:
            out.append((stem, txt, wav))
    return out


def load_raw_words_from_file(raw_json_path: Path) -> Optional[List[dict]]:
    if not raw_json_path.exists():
        return None
    try:
        data = json.loads(raw_json_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return None
    if not isinstance(data, list):
        return None
    words = []
    for item in data:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word", "")).strip()
        start = item.get("start")
        end = item.get("end")
        if not word or start is None or end is None:
            continue
        try:
            words.append({"word": word, "start": float(start), "end": float(end)})
        except Exception:
            continue
    return words


def pick_text_window(tokens: List[Token], left: int, right: int, pad: int) -> str:
    start = max(0, left - pad)
    end = min(len(tokens), right + pad)
    return "".join(t.text for t in tokens[start:end]).strip()


def compute_mismatch_cases(
    txt_tokens: List[Token],
    raw_words: List[dict],
    context_pad: int,
) -> Tuple[dict, List[dict]]:
    txt_match = [t.clean for t in txt_tokens if t.clean]
    txt_map = [i for i, t in enumerate(txt_tokens) if t.clean]
    raw_match = [normalize_clean(w["word"]) for w in raw_words]

    matcher = difflib.SequenceMatcher(None, txt_match, raw_match)
    opcodes = matcher.get_opcodes()

    equal = 0
    replace = 0
    delete = 0
    insert = 0
    mismatched_tokens = 0
    cases = []

    for tag, i1, i2, j1, j2 in opcodes:
        txt_count = max(0, i2 - i1)
        raw_count = max(0, j2 - j1)
        if tag == "equal":
            equal += txt_count
            continue

        mismatched_tokens += txt_count
        if tag == "replace":
            replace += 1
        elif tag == "delete":
            delete += 1
        elif tag == "insert":
            insert += 1

        txt_left = txt_map[i1] if i1 < len(txt_map) else (txt_map[-1] if txt_map else 0)
        txt_right = (
            txt_map[i2 - 1] + 1
            if (i2 - 1) >= 0 and (i2 - 1) < len(txt_map)
            else min(len(txt_tokens), txt_left + 1)
        )
        snippet = pick_text_window(txt_tokens, txt_left, txt_right, context_pad)

        cases.append(
            {
                "tag": tag,
                "txt_range": [i1, i2],
                "raw_range": [j1, j2],
                "txt_tokens_clean": txt_match[i1:i2],
                "raw_tokens_clean": raw_match[j1:j2],
                "raw_words": [w["word"] for w in raw_words[j1:j2]],
                "snippet": snippet,
                "counts": {"txt": txt_count, "raw": raw_count},
            }
        )

    total_txt_tokens = len(txt_match)
    mismatch_ratio = (mismatched_tokens / total_txt_tokens) if total_txt_tokens else 0.0
    summary = {
        "txt_tokens": total_txt_tokens,
        "raw_tokens": len(raw_match),
        "equal_tokens": equal,
        "mismatch_tokens": mismatched_tokens,
        "mismatch_ratio": mismatch_ratio,
        "opcode_counts": {
            "replace": replace,
            "delete": delete,
            "insert": insert,
        },
    }
    return summary, cases


def resolve_device(device_arg: str) -> str:
    if device_arg == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device_arg


def build_chapter_list(library_dir: Path, book_filter: str, max_chapters: int) -> List[dict]:
    chapters = []
    for book_dir in sorted([d for d in library_dir.iterdir() if d.is_dir()]):
        if book_filter and book_filter.lower() not in book_dir.name.lower():
            continue
        for stem, txt, wav in chapter_stem_paths(book_dir):
            chapters.append(
                {
                    "book": book_dir.name,
                    "book_dir": book_dir,
                    "stem": stem,
                    "txt": txt,
                    "wav": wav,
                }
            )
    if max_chapters > 0:
        chapters = chapters[:max_chapters]
    return chapters


def save_outputs(out_dir: Path, report: dict, rows: List[dict], cases: List[dict], write_snippets: bool):
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "alignment_mismatch_report.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    with (out_dir / "alignment_mismatch_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "book",
                "chapter",
                "source",
                "txt_tokens",
                "raw_tokens",
                "equal_tokens",
                "mismatch_tokens",
                "mismatch_ratio",
                "replace_ops",
                "delete_ops",
                "insert_ops",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    with (out_dir / "alignment_mismatch_cases.jsonl").open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    if write_snippets:
        snippets_dir = out_dir / "snippets"
        snippets_dir.mkdir(parents=True, exist_ok=True)
        for i, c in enumerate(cases, 1):
            snippet = c.get("snippet", "").strip()
            if not snippet:
                continue
            filename = f"{i:04d}_{c['book']}_{c['chapter']}_{c['tag']}.txt"
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", filename)
            (snippets_dir / safe_name).write_text(snippet + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Collect WhisperX alignment mismatch dataset.")
    parser.add_argument("--library", default="library", help="Library root path")
    parser.add_argument("--book", default="", help="Optional substring filter for book name")
    parser.add_argument("--max-chapters", type=int, default=0, help="Limit chapters scanned (0 = all)")
    parser.add_argument("--out-dir", default="alignment_mismatch_output", help="Output directory")
    parser.add_argument("--context-pad", type=int, default=12, help="Token padding around mismatch snippets")
    parser.add_argument("--whisper-model", default="base")
    parser.add_argument("--whisper-batch-size", type=int, default=16)
    parser.add_argument("--whisper-compute-type", default="float16")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    parser.add_argument(
        "--prefer-raw-json",
        action="store_true",
        help="Use existing ch_XXX.whisperx_raw.json when available (skip WhisperX for those chapters)",
    )
    parser.add_argument(
        "--write-snippets",
        action="store_true",
        help="Write mismatch snippets as .txt files for mini test audiobook generation",
    )
    args = parser.parse_args()

    library_dir = Path(args.library)
    if not library_dir.exists():
        raise SystemExit(f"Library path not found: {library_dir}")

    chapters = build_chapter_list(library_dir, args.book, args.max_chapters)
    if not chapters:
        raise SystemExit("No chapters found matching filters.")

    device = resolve_device(args.device)
    compute_type = args.whisper_compute_type
    if device == "cpu" and compute_type == "float16":
        compute_type = "int8"

    model = None

    align_models: Dict[str, tuple] = {}
    rows = []
    cases_all = []

    for idx, ch in enumerate(chapters, 1):
        print(f"[{idx}/{len(chapters)}] {ch['book']} {ch['stem']}")
        text = ch["txt"].read_text(encoding="utf-8", errors="ignore")
        txt_tokens = tokenize_for_match(text)

        raw_path_new = ch["txt"].parent / f"{ch['stem']}_raw.json"
        raw_path_legacy = ch["txt"].parent / f"{ch['stem']}.whisperx_raw.json"
        raw_words = None
        source = "whisperx"
        if args.prefer_raw_json:
            raw_words = load_raw_words_from_file(raw_path_new)
            if raw_words is None:
                raw_words = load_raw_words_from_file(raw_path_legacy)
            if raw_words is not None:
                source = "raw_json"

        if raw_words is None:
            if model is None:
                print(
                    f"Loading WhisperX model={args.whisper_model} device={device} "
                    f"compute_type={compute_type} ..."
                )
                model = whisperx.load_model(
                    args.whisper_model,
                    device=device,
                    compute_type=compute_type,
                )
            audio = whisperx.load_audio(str(ch["wav"]))
            result = model.transcribe(audio, batch_size=args.whisper_batch_size)
            lang = result.get("language", "en")
            if lang not in align_models:
                align_models[lang] = whisperx.load_align_model(language_code=lang, device=device)
            model_a, align_meta = align_models[lang]
            aligned = whisperx.align(
                result["segments"],
                model_a,
                align_meta,
                audio,
                device,
                return_char_alignments=False,
            )
            raw_words = extract_raw_words(aligned)

        summary, cases = compute_mismatch_cases(txt_tokens, raw_words, args.context_pad)

        row = {
            "book": ch["book"],
            "chapter": ch["stem"],
            "txt_tokens": summary["txt_tokens"],
            "raw_tokens": summary["raw_tokens"],
            "equal_tokens": summary["equal_tokens"],
            "mismatch_tokens": summary["mismatch_tokens"],
            "mismatch_ratio": round(summary["mismatch_ratio"], 6),
            "replace_ops": summary["opcode_counts"]["replace"],
            "delete_ops": summary["opcode_counts"]["delete"],
            "insert_ops": summary["opcode_counts"]["insert"],
            "source": source,
        }
        rows.append(row)

        for c in cases:
            c["book"] = ch["book"]
            c["chapter"] = ch["stem"]
            c["txt_path"] = str(ch["txt"])
            c["wav_path"] = str(ch["wav"])
            c["mismatch_ratio"] = row["mismatch_ratio"]
            cases_all.append(c)

    avg_mismatch_ratio = (
        sum(r["mismatch_ratio"] for r in rows) / len(rows) if rows else 0.0
    )
    top = sorted(rows, key=lambda r: r["mismatch_ratio"], reverse=True)[:10]
    report = {
        "library": str(library_dir.resolve()),
        "chapters_scanned": len(rows),
        "avg_mismatch_ratio": avg_mismatch_ratio,
        "top_mismatch_chapters": top,
        "settings": {
            "whisper_model": args.whisper_model,
            "whisper_batch_size": args.whisper_batch_size,
            "requested_compute_type": args.whisper_compute_type,
            "resolved_compute_type": compute_type,
            "device": device,
            "context_pad": args.context_pad,
            "prefer_raw_json": bool(args.prefer_raw_json),
        },
        "rows": rows,
    }

    out_dir = Path(args.out_dir)
    save_outputs(out_dir, report, rows, cases_all, args.write_snippets)
    print(f"Wrote outputs to: {out_dir.resolve()}")
    print(f"Avg mismatch ratio: {avg_mismatch_ratio:.4f}")


if __name__ == "__main__":
    main()
