try:
    print("Importing supertonic...")
    import supertonic
    print(f"Supertonic version: {supertonic.__version__}")
except Exception as e:
    print(f"Supertonic import failed: {e}")

try:
    print("Importing whisperx...")
    import whisperx
    print("WhisperX imported successfully")
except Exception as e:
    print(f"WhisperX import failed: {e}")

try:
    import numpy
    print(f"Numpy version: {numpy.__version__}")
except Exception as e:
    print(f"Numpy import failed: {e}")
