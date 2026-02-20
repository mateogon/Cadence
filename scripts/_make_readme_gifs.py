from pathlib import Path
from PIL import Image

media = Path(r"C:\Users\mateo\Desktop\AudioBookForge\docs\media")


def build(prefix: str, durations_s, speedup: float = 1.7):
    frames = [media / f"{prefix}_{i}.png" for i in range(1, 10)]
    imgs = [Image.open(p).convert("P", palette=Image.ADAPTIVE) for p in frames]
    if len(durations_s) < len(imgs):
        raise ValueError(f"{prefix}: need {len(imgs)} durations, got {len(durations_s)}")
    out = media / f"{prefix}.gif"
    durations_ms = []
    for d in durations_s[: len(imgs)]:
        ms = int(round((float(d) * 1000.0) / max(1.0, float(speedup))))
        durations_ms.append(max(40, ms))
    imgs[0].save(
        out,
        save_all=True,
        append_images=imgs[1:],
        duration=durations_ms,
        loop=0,
        optimize=True,
    )
    print(f"{out} durations_ms={durations_ms}")


# RSVP words (non-space): evolution by natural selection is that it depends crucially
rsvp_durations = [
    4.676 - 4.075,  # evolution
    5.076 - 4.956,  # by
    5.537 - 5.097,  # natural
    6.078 - 5.597,  # selection
    6.618 - 6.558,  # is
    6.758 - 6.658,  # that
    6.838 - 6.798,  # it
    7.279 - 6.898,  # depends
    7.960 - 7.419,  # crucially
]

# Context first 9 non-space words from provided snippet:
# curious feature of evolution by natural selection is that
context_durations = [
    3.805 - 3.655,  # curious
    3.955 - 3.805,  # feature
    4.035 - 3.995,  # of
    4.676 - 4.075,  # evolution
    5.076 - 4.956,  # by
    5.537 - 5.097,  # natural
    6.078 - 5.597,  # selection
    6.618 - 6.558,  # is
    6.758 - 6.658,  # that
]

build("rsvp", rsvp_durations, speedup=1.7)
build("context", context_durations, speedup=1.7)
