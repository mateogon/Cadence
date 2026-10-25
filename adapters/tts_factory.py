"""Construct the selected synthesizer without importing optional backends at startup."""

KOKORO_MODEL = "hexgrad/Kokoro-82M"


def create_backend(name, model=None):
    if name == "supertonic":
        from adapters.supertonic_backend import SupertonicBackend

        return SupertonicBackend(model=model)
    if name == "kokoro":
        from adapters.kokoro_backend import KokoroBackend

        return KokoroBackend(model=model or KOKORO_MODEL)
    raise ValueError(f"Unsupported TTS backend: {name}")
