import argparse
import importlib.util
import os
import sys
import ctypes

from system.runtime_settings import apply_settings_to_environ, load_settings


def build_parser():
    parser = argparse.ArgumentParser(description="Cadence (Qt)")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging in Qt app.",
    )
    return parser


def prepare_qt_runtime():
    # Prevent loading Qt plugins/DLLs from conda/system locations.
    for key in (
        "QT_PLUGIN_PATH",
        "QML2_IMPORT_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
    ):
        os.environ.pop(key, None)

    if os.name != "nt":
        return

    # Ensure selected Qt backend wheel DLL directory is preferred.
    try:
        from pathlib import Path

        # Remove known conda/anaconda DLL dirs from PATH to avoid ABI conflicts.
        raw_path = os.environ.get("PATH", "")
        parts = [p for p in raw_path.split(os.pathsep) if p]
        cleaned = []
        for p in parts:
            low = p.lower()
            if "anaconda" in low or "\\conda" in low or "/conda" in low:
                continue
            cleaned.append(p)
        # Also clear active conda env markers.
        for key in list(os.environ.keys()):
            if key.startswith("CONDA"):
                os.environ.pop(key, None)

        req = os.getenv("CADENCE_QT_API", "auto").strip().lower()
        if req in {"", "auto"}:
            req = "pyqt6"  # windows default for now

        pyside_dir = None
        pyqt_dir = None
        pyqt_qt_bin = None

        pyside_spec = importlib.util.find_spec("PySide6")
        if pyside_spec and pyside_spec.submodule_search_locations:
            pyside_dir = Path(list(pyside_spec.submodule_search_locations)[0]).resolve()
        pyqt_spec = importlib.util.find_spec("PyQt6")
        if pyqt_spec and pyqt_spec.submodule_search_locations:
            pyqt_dir = Path(list(pyqt_spec.submodule_search_locations)[0]).resolve()
            candidate_bin = pyqt_dir / "Qt6" / "bin"
            if candidate_bin.exists():
                pyqt_qt_bin = candidate_bin.resolve()

        # Build a deterministic PATH with venv + PySide6 first.
        preferred = []
        venv_scripts = Path(sys.prefix) / "Scripts"
        if venv_scripts.exists():
            preferred.append(str(venv_scripts))

        if req in {"pyqt6", "pyqt"}:
            if pyqt_dir and pyqt_dir.exists():
                preferred.append(str(pyqt_dir))
                if pyqt_qt_bin:
                    preferred.append(str(pyqt_qt_bin))
                    os.add_dll_directory(str(pyqt_qt_bin))
                os.add_dll_directory(str(pyqt_dir))
                # PyQt plugin paths
                plugins = pyqt_dir / "Qt6" / "plugins"
                platforms = plugins / "platforms"
                if plugins.exists():
                    os.environ["QT_PLUGIN_PATH"] = str(plugins)
                if platforms.exists():
                    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)
        else:
            if pyside_dir and pyside_dir.exists():
                preferred.append(str(pyside_dir))
                plugins = pyside_dir / "plugins"
                platforms = plugins / "platforms"
                os.environ["QT_PLUGIN_PATH"] = str(plugins)
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)
                os.add_dll_directory(str(pyside_dir))
                shiboken_dir = pyside_dir.parent / "shiboken6"
                if shiboken_dir.exists():
                    os.add_dll_directory(str(shiboken_dir))

        merged = preferred + cleaned
        # Deduplicate while preserving order.
        dedup = []
        seen = set()
        for p in merged:
            key = p.lower()
            if key in seen:
                continue
            seen.add(key)
            dedup.append(p)
        os.environ["PATH"] = os.pathsep.join(dedup)
        if os.getenv("CADENCE_QT_DEBUG", "0").strip() == "1":
            print(f"[qt] sys.prefix={sys.prefix}", file=sys.stderr)
            print(f"[qt] requested_api={req}", file=sys.stderr)
            print(f"[qt] pyside_dir={pyside_dir}", file=sys.stderr)
            print(f"[qt] pyqt_dir={pyqt_dir}", file=sys.stderr)
            print(f"[qt] pyqt_qt_bin={pyqt_qt_bin}", file=sys.stderr)
            print(f"[qt] QT_PLUGIN_PATH={os.environ.get('QT_PLUGIN_PATH')}", file=sys.stderr)
            print(
                f"[qt] QT_QPA_PLATFORM_PLUGIN_PATH={os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH')}",
                file=sys.stderr,
            )
    except Exception as exc:
        if os.getenv("CADENCE_QT_DEBUG", "0").strip() == "1":
            print(f"[qt] prepare_qt_runtime error: {exc}", file=sys.stderr)


def main(argv=None):
    apply_settings_to_environ(load_settings())
    prepare_qt_runtime()
    from pathlib import Path
    from qt.qt_compat import QtWidgets, QtGui, QT_API
    from qt.main_window import MainWindow

    args = build_parser().parse_args(argv)

    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Cadence.App")
        except Exception:
            pass

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Cadence")
    app.setOrganizationName("Cadence")
    icon_ico = Path("assets/branding/cadence-logo.ico")
    icon_svg = Path("assets/branding/cadence-logo.svg")
    if icon_ico.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_ico)))
    elif icon_svg.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_svg)))
    if args.debug:
        print(f"[qt] backend={QT_API}", file=sys.stderr)

    window = MainWindow(debug=args.debug)
    window.show()

    return app.exec()
