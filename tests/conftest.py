import os

# Keep Qt tests headless and deterministic across local runs/CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
