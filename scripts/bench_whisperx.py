import argparse
import time
import wave
from pathlib import Path

import torch
import whisperx


def wav_duration(path):
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-dir", required=True)
    parser.add_argument("--num-files", type=int, default=3)
    parser.add_argument("--model", default="small")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    audio_dir = Path(args.audio_dir)
    files = sorted(audio_dir.glob("ch_*.wav"))[: args.num_files]
    if not files:
        raise SystemExit(f"No wav files found in: {audio_dir}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(
        f"device={device} model={args.model} compute_type={args.compute_type} "
        f"batch_size={args.batch_size} files={len(files)}"
    )

    t_model = time.time()
    model = whisperx.load_model(args.model, device, compute_type=args.compute_type)
    model_load_s = time.time() - t_model
    print(f"model_load_s={model_load_s:.3f}")

    total_audio_s = 0.0
    total_proc_s = 0.0
    for wav in files:
        audio_s = wav_duration(wav)
        t0 = time.time()
        audio = whisperx.load_audio(str(wav))
        _ = model.transcribe(audio, batch_size=args.batch_size)
        proc_s = time.time() - t0
        total_audio_s += audio_s
        total_proc_s += proc_s
        rtf = proc_s / audio_s if audio_s > 0 else 0.0
        x_rt = audio_s / proc_s if proc_s > 0 else 0.0
        print(
            f"{wav.name}: audio_s={audio_s:.2f} proc_s={proc_s:.2f} "
            f"rtf={rtf:.3f} x_realtime={x_rt:.2f}"
        )

    overall_rtf = total_proc_s / total_audio_s if total_audio_s > 0 else 0.0
    overall_x_rt = total_audio_s / total_proc_s if total_proc_s > 0 else 0.0
    print("---")
    print(f"total_audio_s={total_audio_s:.2f} total_proc_s={total_proc_s:.2f}")
    print(f"overall_rtf={overall_rtf:.3f} overall_x_realtime={overall_x_rt:.2f}")


if __name__ == "__main__":
    main()
