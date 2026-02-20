import importlib
import sys
import types

import qt.app as app_mod


def test_qt_compat_uses_pyqt6_when_requested(monkeypatch):
    monkeypatch.setenv("CADENCE_QT_API", "pyqt6")

    import qt.qt_compat as qt_compat

    qt_compat = importlib.reload(qt_compat)
    assert qt_compat.QT_API == "PyQt6"


def test_app_main_bootstrap_flow_with_stubs(monkeypatch):
    calls = {
        "loaded": False,
        "applied": False,
        "show": False,
        "debug": None,
    }

    class _DummyApp:
        def __init__(self, argv):
            self.argv = argv

        def setApplicationName(self, _name):
            return None

        def setOrganizationName(self, _name):
            return None

        def setWindowIcon(self, _icon):
            return None

        def exec(self):
            return 0

    class _DummyQIcon:
        def __init__(self, _path):
            pass

    fake_qt_compat = types.ModuleType("qt.qt_compat")
    fake_qt_compat.QT_API = "PyQt6"
    fake_qt_compat.QtWidgets = types.SimpleNamespace(QApplication=_DummyApp)
    fake_qt_compat.QtGui = types.SimpleNamespace(QIcon=_DummyQIcon)

    class _DummyMainWindow:
        def __init__(self, debug=False):
            calls["debug"] = bool(debug)

        def show(self):
            calls["show"] = True

    fake_main_window = types.ModuleType("qt.main_window")
    fake_main_window.MainWindow = _DummyMainWindow

    monkeypatch.setitem(sys.modules, "qt.qt_compat", fake_qt_compat)
    monkeypatch.setitem(sys.modules, "qt.main_window", fake_main_window)

    def _fake_load_settings():
        calls["loaded"] = True
        return {"CADENCE_FORCE_CPU": "0"}

    def _fake_apply_settings(settings):
        calls["applied"] = settings == {"CADENCE_FORCE_CPU": "0"}

    monkeypatch.setattr(app_mod, "load_settings", _fake_load_settings)
    monkeypatch.setattr(app_mod, "apply_settings_to_environ", _fake_apply_settings)
    monkeypatch.setattr(app_mod, "prepare_qt_runtime", lambda: None)

    rc = app_mod.main(["--debug"])

    assert rc == 0
    assert calls["loaded"] is True
    assert calls["applied"] is True
    assert calls["show"] is True
    assert calls["debug"] is True
