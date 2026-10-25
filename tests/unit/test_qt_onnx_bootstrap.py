import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_bootstrap_loads_qt_and_onnx_in_fresh_process():
    script = textwrap.dedent("""
        import os
        import sys
        from qt.app import prepare_qt_runtime

        prepare_qt_runtime()
        if os.name == "nt":
            assert "onnxruntime" in sys.modules

        from qt.qt_compat import QtCore, QtWidgets
        import onnxruntime

        print(QtCore.qVersion(), QtWidgets.__name__, onnxruntime.__version__)
        print(onnxruntime.get_available_providers())
    """)
    env = dict(os.environ, CADENCE_QT_API="pyqt6")
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CPUExecutionProvider" in result.stdout
