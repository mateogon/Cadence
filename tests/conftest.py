import os

from qt.app import prepare_qt_runtime

# Keep Qt tests headless and deterministic across local runs/CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Match application startup before pytest-qt imports its Qt bindings.
prepare_qt_runtime()
