import argparse
import csv
from pathlib import Path

import numpy as np

from generate_audiobook_supertonic import (
    DEFAULT_VOICE,
    get_smart_chunks,
    init_tts_engine,
    sanitize_text,
)


APOSTROPHE_CASES = [
    ("contraction_dont", "Contraction (don't)", "I don{a}t know why this word sounds strange."),
    ("contraction_wont", "Contraction (won't)", "This won{a}t happen every time."),
    ("contraction_im", "Contraction (I'm)", "I{a}m sure this can be fixed."),
    ("contraction_theyre", "Contraction (they're)", "They{a}re ready for the next test."),
    ("contraction_ive", "Contraction (I've)", "I{a}ve seen this issue before."),
    ("contraction_id", "Contraction (I'd)", "I{a}d rather test this first."),
    ("contraction_ill", "Contraction (I'll)", "I{a}ll run another pass."),
    ("possessive_singular", "Possessive singular", "Sarah{a}s notebook is on the desk."),
    ("possessive_plural", "Possessive plural", "The students{a} lounge is full."),
    ("leading_apostrophe", "Leading apostrophe", "{a}tis better to verify than assume."),
    ("decade_elision", "Decade elision", "The {a}90s had different software habits."),
    ("o_reilly_name", "Name with apostrophe", "O{a}Reilly published many technical books."),
    ("rock_n_roll", "Apostrophe in phrase", "Rock {a}n{a} roll changed modern music."),
    ("letters_ps_qs", "Plural letters with apostrophe", "Mind your p{a}s and q{a}s in emails."),
]

DASH_CASES = [
    ("dash_em", "Em dash in clause", "Card magicians\u2014especially experts\u2014exploit this."),
    ("dash_en", "En dash in clause", "Card magicians\u2013especially experts\u2013exploit this."),
    ("dash_hyphen", "Hyphen in clause", "Card magicians-especially experts-exploit this."),
    ("dash_comma", "Comma control case", "Card magicians, especially experts, exploit this."),
]

APOSTROPHE_VARIANTS = [
    ("ascii", "'"),
    ("curly", "\u2019"),
    ("none", ""),
]

LONG_CONTEXT_CASES = [
    (
        "long_magic_excerpt",
        "Long context excerpt with dash + contraction",
        (
            "Here is a technique that card magicians\u2014at least the best of them\u2014exploit with amazing results. "
            "A good card magician knows many tricks that depend on luck\u2014they don{a}t always work, or even often work. "
            "There are some effects\u2014they can hardly be called tricks\u2014that might work only once in a thousand times. "
            "You start by telling the audience you are going to perform a trick, and then glide from one attempt to another. "
            "In the course of a whole performance, you will be very unlucky indeed if you always have to rely on your final safety net."
        ),
    ),
    (
        "long_boundary_dont_middle",
        "Long context with target near chunk boundary",
        (
            ("This setup sentence exists to build context and length for testing. " * 14)
            + "In this exact moment, they don{a}t expect the fallback path to trigger. "
            + ("After that, the paragraph continues with neutral content for stability. " * 10)
        ),
    ),
]


def slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in value)


def build_apostrophe_twister_cases(repeats=8):
    twister_templates = [
        (
            "twister_contractions_dense",
            "Tongue twister: dense contractions",
            (
                "Don{a}t you think I{a}m sure they{a}re right when we{a}re told it{a}s fine, "
                "but I{a}d say we{a}ll test again because won{a}t, can{a}t, and shouldn{a}t "
                "sometimes shift in long context."
            ),
        ),
        (
            "twister_possessive_dense",
            "Tongue twister: possessives and elisions",
            (
                "Sarah{a}s editor said the students{a} notes from the {a}90s and O{a}Reilly{a}s "
                "draft weren{a}t wrong, and rock {a}n{a} roll wasn{a}t gone."
            ),
        ),
    ]

    for case_id, case_description, sentence in twister_templates:
        long_template = " ".join([sentence] * repeats)
        yield case_id, case_description, long_template


def build_cases(include_long=False, include_short=True, twister_repeats=8):
    if include_short:
        for case_id, case_description, template in APOSTROPHE_CASES:
            for variant_name, apostrophe in APOSTROPHE_VARIANTS:
                text = template.format(a=apostrophe)
                yield {
                    "sample_id": f"{case_id}_{variant_name}",
                    "test_category": "apostrophe",
                    "test_description": f"{case_description} ({variant_name} apostrophe)",
                    "original_text": text,
                }

        for case_id, case_description, text in DASH_CASES:
            yield {
                "sample_id": case_id,
                "test_category": "dash",
                "test_description": case_description,
                "original_text": text,
            }

    if include_long:
        for case_id, case_description, template in LONG_CONTEXT_CASES:
            for variant_name, apostrophe in APOSTROPHE_VARIANTS:
                text = template.format(a=apostrophe)
                yield {
                    "sample_id": f"{case_id}_{variant_name}",
                    "test_category": "long_context",
                    "test_description": f"{case_description} ({variant_name} apostrophe)",
                    "original_text": text,
                }

        for case_id, case_description, template in build_apostrophe_twister_cases(repeats=twister_repeats):
            for variant_name, apostrophe in APOSTROPHE_VARIANTS:
                text = template.format(a=apostrophe)
                yield {
                    "sample_id": f"{case_id}_{variant_name}",
                    "test_category": "long_context",
                    "test_description": f"{case_description} ({variant_name} apostrophe)",
                    "original_text": text,
                }


def synthesize_via_pipeline(tts, voice_style, supported_chars, text):
    chunks = get_smart_chunks(text)
    audio_segments = []
    clean_chunks = []

    for chunk in chunks:
        clean_chunk = sanitize_text(chunk, supported_chars)
        if not clean_chunk:
            continue
        wav, _ = tts.synthesize(clean_chunk, voice_style=voice_style, lang="en")
        audio_segments.append(wav)
        clean_chunks.append(clean_chunk)

    if not audio_segments:
        return None, clean_chunks
    return np.concatenate(audio_segments, axis=1), clean_chunks


def main():
    parser = argparse.ArgumentParser(
        description="Generate Supertonic pronunciation matrix WAVs for apostrophe and dash variants."
    )
    parser.add_argument("--output", "-o", default="supertonic_pronunciation_test_output")
    parser.add_argument("--voice", "-v", default=DEFAULT_VOICE)
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Use raw test text directly instead of sanitize_text().",
    )
    parser.add_argument(
        "--include-long",
        action="store_true",
        help="Include long-context stress tests (better proxy for chapter behavior).",
    )
    parser.add_argument(
        "--use-chunking",
        action="store_true",
        help="Use get_smart_chunks pipeline for synthesis (matches chapter generation flow).",
    )
    parser.add_argument(
        "--long-only",
        action="store_true",
        help="Generate only long-context tests (skip short apostrophe/dash matrix).",
    )
    parser.add_argument(
        "--twister-repeats",
        type=int,
        default=8,
        help="How many times each apostrophe tongue-twister sentence is repeated.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    table_path = output_dir / "test_matrix.md"

    print("Initializing TTS...")
    tts = init_tts_engine()
    voice_style = tts.get_voice_style(voice_name=args.voice)
    supported_chars = tts.model.text_processor.supported_character_set

    include_short = not args.long_only
    include_long = args.include_long or args.long_only

    rows = []
    for index, case in enumerate(
        build_cases(
            include_long=include_long,
            include_short=include_short,
            twister_repeats=args.twister_repeats,
        ),
        start=1,
    ):
        sample_id = case["sample_id"]
        original_text = case["original_text"]
        chunk_count = 1

        if args.use_chunking:
            wav, clean_chunks = synthesize_via_pipeline(tts, voice_style, supported_chars, original_text)
            if wav is None:
                print(f"Skipping empty sample after cleanup: {sample_id}")
                continue
            synthesis_text = " || ".join(clean_chunks)
            chunk_count = len(clean_chunks)
        else:
            synthesis_text = original_text if args.raw else sanitize_text(original_text, supported_chars)
            if not synthesis_text:
                print(f"Skipping empty sample after cleanup: {sample_id}")
                continue
            wav, _ = tts.synthesize(synthesis_text, voice_style=voice_style, lang="en")

        out_name = f"{index:03d}_{slugify(sample_id)}.wav"
        out_path = output_dir / out_name
        tts.save_audio(wav, str(out_path))
        print(f"Saved {out_name}")

        rows.append(
            {
                "index": index,
                "sample_id": sample_id,
                "output_wav": out_name,
                "test_category": case["test_category"],
                "test_description": case["test_description"],
                "original_text": original_text,
                "synthesis_text": synthesis_text,
                "chunk_count": chunk_count,
            }
        )

    with manifest_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "index",
                "output_wav",
                "sample_id",
                "test_category",
                "test_description",
                "original_text",
                "synthesis_text",
                "chunk_count",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    with table_path.open("w", encoding="utf-8") as f:
        f.write("# Supertonic Pronunciation Test Matrix\n\n")
        f.write("| # | File | Category | Test | Chunks | Phrase |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in rows:
            phrase = row["original_text"].replace("|", "\\|")
            f.write(
                f"| {row['index']} | `{row['output_wav']}` | {row['test_category']} | {row['test_description']} | {row['chunk_count']} | {phrase} |\n"
            )

    print(f"\nDone. Generated {len(rows)} files in: {output_dir.resolve()}")
    print(f"Manifest: {manifest_path.resolve()}")
    print(f"Table: {table_path.resolve()}")


if __name__ == "__main__":
    main()
