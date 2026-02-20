import ctypes
import importlib.util
import os
import sys
from pathlib import Path


def try_load(path: Path):
    try:
        ctypes.WinDLL(str(path))
        return True, ""
    except OSError as exc:
        return False, str(exc)


def main():
    print("python:", sys.executable)
    print("sys.prefix:", sys.prefix)
    print("CONDA_PREFIX:", os.environ.get("CONDA_PREFIX"))
    print("CONDA_DEFAULT_ENV:", os.environ.get("CONDA_DEFAULT_ENV"))

    spec = importlib.util.find_spec("PySide6")
    if not spec or not spec.submodule_search_locations:
        print("PySide6 spec not found")
        return 1
    pyside_dir = Path(list(spec.submodule_search_locations)[0]).resolve()
    print("PySide6 dir:", pyside_dir)
    print("Exists:", pyside_dir.exists())

    targets = [
        pyside_dir / "Qt6Core.dll",
        pyside_dir / "Qt6Gui.dll",
        pyside_dir / "Qt6Widgets.dll",
        pyside_dir / "QtWidgets.pyd",
    ]
    for t in targets:
        ok, msg = try_load(t)
        print(f"load {t.name}: {'OK' if ok else 'FAIL'}")
        if msg:
            print(" ", msg)

    try:
        import PySide6

        print("PySide6 import: OK", PySide6.__version__)
    except Exception as exc:
        print("PySide6 import: FAIL", exc)

    try:
        from PySide6 import QtCore

        print("QtCore import: OK", QtCore.qVersion())
    except Exception as exc:
        print("QtCore import: FAIL", exc)

    try:
        from PySide6 import QtWidgets

        print("QtWidgets import: OK")
    except Exception as exc:
        print("QtWidgets import: FAIL", exc)

    print("--- PyQt6 check ---")
    try:
        import PyQt6

        print("PyQt6 import: OK", getattr(PyQt6, "__file__", ""))
    except Exception as exc:
        print("PyQt6 import: FAIL", exc)

    try:
        from PyQt6 import QtCore as QtCore6

        print("PyQt6 QtCore import: OK", QtCore6.QT_VERSION_STR)
    except Exception as exc:
        print("PyQt6 QtCore import: FAIL", exc)

    try:
        from PyQt6 import QtWidgets as QtWidgets6

        print("PyQt6 QtWidgets import: OK", QtWidgets6.__name__)
    except Exception as exc:
        print("PyQt6 QtWidgets import: FAIL", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
