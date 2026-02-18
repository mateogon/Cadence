import argparse
import json
from pathlib import Path

import numpy as np

from generate_audiobook_supertonic import (
    DEFAULT_VOICE,
    get_smart_chunks,
    init_tts_engine,
    sanitize_text,
)


def synthesize_chunked(tts, voice_style, supported_chars, text):
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
        description="Generate a standalone Supertonic WAV from a single .txt file."
    )
    parser.add_argument("input_txt", help="Path to source .txt file")
    parser.add_argument("--output", "-o", required=True, help="Path to output .wav file")
    parser.add_argument("--voice", "-v", default=DEFAULT_VOICE, help="Voice ID (default: M3)")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Bypass sanitize_text (single-pass synthesis).",
    )
    parser.add_argument(
        "--no-chunking",
        action="store_true",
        help="Disable chunking and synthesize the full text in one pass.",
    )
    parser.add_argument(
        "--dump-chunks",
        action="store_true",
        help="Write a sidecar JSON with original/clean chunks for debugging.",
    )
    args = parser.parse_args()

    input_path = Path(args.input_txt)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    text = input_path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Input file is empty: {input_path}")

    print("Initializing TTS...")
    tts = init_tts_engine()
    voice_style = tts.get_voice_style(voice_name=args.voice)
    supported_chars = tts.model.text_processor.supported_character_set

    chunk_report = []
    if args.no_chunking:
        synthesis_text = text if args.raw else sanitize_text(text, supported_chars)
        if not synthesis_text:
            raise RuntimeError("Text became empty after cleanup.")
        wav, _ = tts.synthesize(synthesis_text, voice_style=voice_style, lang="en")
        chunk_report.append({"original": text, "clean": synthesis_text})
    else:
        if args.raw:
            chunks = get_smart_chunks(text)
            audio_segments = []
            for chunk in chunks:
                if not chunk.strip():
                    continue
                wav_chunk, _ = tts.synthesize(chunk, voice_style=voice_style, lang="en")
                audio_segments.append(wav_chunk)
                chunk_report.append({"original": chunk, "clean": chunk})
            if not audio_segments:
                raise RuntimeError("No chunks available for synthesis.")
            wav = np.concatenate(audio_segments, axis=1)
        else:
            wav, clean_chunks = synthesize_chunked(tts, voice_style, supported_chars, text)
            if wav is None:
                raise RuntimeError("Text became empty after chunk cleanup.")
            original_chunks = get_smart_chunks(text)
            for i, clean in enumerate(clean_chunks):
                original = original_chunks[i] if i < len(original_chunks) else ""
                chunk_report.append({"original": original, "clean": clean})

    tts.save_audio(wav, str(output_path))
    print(f"Saved WAV: {output_path.resolve()}")
    print(f"Chunks used: {len(chunk_report)}")

    if args.dump_chunks:
        sidecar = output_path.with_suffix(output_path.suffix + ".chunks.json")
        sidecar.write_text(json.dumps(chunk_report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Chunk report: {sidecar.resolve()}")


if __name__ == "__main__":
    main()
