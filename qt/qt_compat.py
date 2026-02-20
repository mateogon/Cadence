"""
Qt compatibility layer:
- Prefer PySide6
- Fallback to PyQt6
"""

QT_API = None
_requested = ""
try:
    import os

    _requested = os.getenv("CADENCE_QT_API", "auto").strip().lower()
except Exception:
    _requested = "auto"

if _requested in {"pyqt6", "pyqt"}:
    from PyQt6 import QtCore, QtWidgets, QtGui, QtMultimedia  # type: ignore

    Signal = QtCore.pyqtSignal
    Slot = QtCore.pyqtSlot
    QT_API = "PyQt6"
elif _requested in {"pyside6", "pyside"}:
    from PySide6 import QtCore, QtWidgets, QtGui, QtMultimedia  # type: ignore

    Signal = QtCore.Signal
    Slot = QtCore.Slot
    QT_API = "PySide6"
else:
    # auto: try PyQt6 first on Windows to avoid PySide DLL conflicts.
    try:
        from PyQt6 import QtCore, QtWidgets, QtGui, QtMultimedia  # type: ignore

        Signal = QtCore.pyqtSignal
        Slot = QtCore.pyqtSlot
        QT_API = "PyQt6"
    except Exception:  # pragma: no cover
        from PySide6 import QtCore, QtWidgets, QtGui, QtMultimedia  # type: ignore

        Signal = QtCore.Signal
        Slot = QtCore.Slot
        QT_API = "PySide6"

if QT_API is None:  # pragma: no cover
    from PyQt6 import QtCore, QtWidgets, QtGui, QtMultimedia  # type: ignore

    Signal = QtCore.pyqtSignal
    Slot = QtCore.pyqtSlot
    QT_API = "PyQt6"


def user_role():
    # Enum location differs between bindings/versions.
    try:
        return QtCore.Qt.ItemDataRole.UserRole
    except Exception:
        return QtCore.Qt.UserRole
