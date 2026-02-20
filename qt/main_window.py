from __future__ import annotations

import bisect
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from qt.qt_compat import QtCore, QtGui, QtMultimedia, QtWidgets, Signal, Slot

from system.book_manager import BookManager
from system.runtime_settings import DEFAULTS, apply_settings_to_environ, load_settings, save_settings
from qt.styles import QSS

try:
    import pygame
except Exception:
    pygame = None

try:
    import soundfile as sf
except Exception:
    sf = None


class ImportSignals(QtCore.QObject):
    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(bool)


class ImportWorker(QtCore.QRunnable):
    def __init__(self, epub_path: str, voice: str):
        super().__init__()
        self.epub_path = epub_path
        self.voice = voice
        self.signals = ImportSignals()
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    @Slot()
    def run(self):
        def progress(pct, msg):
            self.signals.progress.emit(float(pct), str(msg))

        def log(msg):
            self.signals.log.emit(str(msg))

        ok = BookManager.import_book(
            self.epub_path,
            self.voice,
            progress,
            log_callback=log,
            cancel_check=self._cancel_event.is_set,
        )
        self.signals.done.emit(bool(ok))


class BookCard(QtWidgets.QFrame):
    read_requested = Signal(dict)
    continue_requested = Signal(dict)

    def __init__(self, book: dict):
        super().__init__()
        self.book = book
        self.setObjectName("BookCard")
        self._build_ui()

    def _build_ui(self):
        expected = int(self.book.get("content_chapters", 0) or 0)
        audio = int(self.book.get("audio_chapters_ready", 0) or 0)
        align = int(self.book.get("aligned_chapters_ready", 0) or 0)
        total = int(self.book.get("total_chapters", expected) or expected)
        last = int(self.book.get("last_chapter", 0) or 0)
        incomplete = bool(self.book.get("is_incomplete", False))

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        title = QtWidgets.QLabel(self.book.get("title", "Unknown"))
        title.setObjectName("BookTitle")
        title.setWordWrap(True)
        outer.addWidget(title)

        meta = QtWidgets.QLabel(f"Ch {last}/{total}  •  Voice: {self.book.get('voice', '?')}")
        meta.setObjectName("BookMeta")
        outer.addWidget(meta)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        if incomplete:
            status = QtWidgets.QLabel(
                f"Incomplete  •  Audio {audio}/{expected}  •  Alignment {align}/{expected}  •  Available chapters readable"
            )
            status.setObjectName("BookStatusIncomplete")
        else:
            status = QtWidgets.QLabel(
                f"Complete  •  Audio {audio}/{expected}  •  Alignment {align}/{expected}"
            )
            status.setObjectName("BookStatusComplete")
        status.setWordWrap(True)
        row.addWidget(status, 1)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(8)

        if incomplete:
            btn_continue = QtWidgets.QPushButton("Continue Import")
            btn_continue.setObjectName("ContinueButton")
            btn_continue.setEnabled(bool(self.book.get("stored_epub_exists", False)))
            btn_continue.clicked.connect(lambda: self.continue_requested.emit(self.book))
            actions.addWidget(btn_continue)

        btn_read = QtWidgets.QPushButton("Read")
        btn_read.setObjectName("ReadButton")
        btn_read.clicked.connect(lambda: self.read_requested.emit(self.book))
        actions.addWidget(btn_read)

        row.addLayout(actions, 0)
        outer.addLayout(row)


class RuntimeSettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Runtime Settings")
        self.resize(760, 620)
        self._vars = {}
        self._defaults = dict(DEFAULTS)
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        hdr = QtWidgets.QLabel("Cadence Runtime Settings")
        hdr.setObjectName("MainTitle")
        layout.addWidget(hdr)

        sub = QtWidgets.QLabel("Saved in cadence_settings.json and applied immediately.")
        sub.setObjectName("BookMeta")
        layout.addWidget(sub)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        wrap = QtWidgets.QWidget()
        form_layout = QtWidgets.QVBoxLayout(wrap)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        settings = load_settings()
        for key in DEFAULTS:
            row = QtWidgets.QFrame()
            row.setObjectName("BookCard")
            row_layout = QtWidgets.QGridLayout(row)
            row_layout.setContentsMargins(10, 8, 10, 8)
            row_layout.setHorizontalSpacing(10)
            row_layout.setVerticalSpacing(4)

            title = QtWidgets.QLabel(key.replace("CADENCE_", "").replace("_", " ").title())
            title.setObjectName("SectionLabel")
            row_layout.addWidget(title, 0, 0, 1, 1)

            entry = QtWidgets.QLineEdit(str(settings.get(key, DEFAULTS.get(key, ""))))
            row_layout.addWidget(entry, 0, 1, 1, 1)

            raw = QtWidgets.QLabel(key)
            raw.setObjectName("BookMeta")
            row_layout.addWidget(raw, 1, 0, 1, 2)

            self._vars[key] = entry
            form_layout.addWidget(row)

        form_layout.addStretch(1)
        scroll.setWidget(wrap)
        layout.addWidget(scroll, 1)

        actions = QtWidgets.QHBoxLayout()
        actions.addStretch(1)
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        actions.addWidget(btn_cancel)
        btn_reset = QtWidgets.QPushButton("Reset")
        btn_reset.clicked.connect(self._reset_defaults)
        actions.addWidget(btn_reset)
        btn_apply = QtWidgets.QPushButton("Apply")
        btn_apply.setObjectName("ImportButton")
        btn_apply.clicked.connect(self._apply)
        actions.addWidget(btn_apply)
        layout.addLayout(actions)

    def _reset_defaults(self):
        for key, w in self._vars.items():
            w.setText(str(self._defaults.get(key, "")))

    def _apply(self):
        updated = {k: w.text().strip() for k, w in self._vars.items()}
        save_settings(updated)
        apply_settings_to_environ(updated, override=True)
        self.accept()


PLAYER_SETTINGS_FILE = Path("player_settings.json")
PLAYER_DEFAULTS = {
    "reading_view_mode": "context",
    "context_force_center": True,
    "font_family": "Arial",
    "font_size": 150.0,
    "bg_color": "#121212",
    "text_color": "#E0E0E0",
    "focus_color": "#FFD700",
    "context_highlight_style": "underline",
    "playback_speed": 1.0,
    "sync_offset": 0.0,
}


class PlayerSettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Player Settings")
        self.resize(640, 560)
        self._settings = dict(settings)
        self._slider_specs = {}
        self._color_swatches = {}
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        hdr = QtWidgets.QLabel("Player Settings")
        hdr.setObjectName("MainTitle")
        layout.addWidget(hdr)

        card = QtWidgets.QFrame()
        card.setObjectName("BookCard")
        grid = QtWidgets.QGridLayout(card)
        grid.setContentsMargins(12, 12, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        row = 0

        grid.addWidget(QtWidgets.QLabel("Reading View"), row, 0)
        self.reading_view = QtWidgets.QComboBox()
        self.reading_view.addItems(["Context", "RSVP"])
        grid.addWidget(self.reading_view, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Center Current Line (Context)"), row, 0)
        self.center_context = QtWidgets.QCheckBox("Enabled")
        grid.addWidget(self.center_context, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Font Family"), row, 0)
        self.font_family = QtWidgets.QComboBox()
        try:
            families = sorted(QtGui.QFontDatabase.families())
        except Exception:
            try:
                families = sorted(QtGui.QFontDatabase().families())
            except Exception:
                families = ["Arial", "Segoe UI", "Consolas"]
        self.font_family.addItems(families)
        grid.addWidget(self.font_family, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Context Highlight"), row, 0)
        self.context_highlight_style = QtWidgets.QComboBox()
        self.context_highlight_style.addItems(["underline", "word", "block"])
        grid.addWidget(self.context_highlight_style, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Font Size"), row, 0)
        self.font_size, self.font_size_value = self._build_slider_with_clamps(
            min_value=30.0, max_value=260.0, step=2.0, decimals=0
        )
        grid.addWidget(self.font_size, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Playback Speed"), row, 0)
        self.playback_speed, self.playback_speed_value = self._build_slider_with_clamps(
            min_value=0.50, max_value=4.00, step=0.05, decimals=2
        )
        grid.addWidget(self.playback_speed, row, 1)
        row += 1

        grid.addWidget(QtWidgets.QLabel("Sync Offset (s)"), row, 0)
        self.sync_offset, self.sync_offset_value = self._build_slider_with_clamps(
            min_value=-3.0, max_value=3.0, step=0.05, decimals=2
        )
        grid.addWidget(self.sync_offset, row, 1)
        row += 1

        self.bg_color = QtWidgets.QLineEdit()
        self.text_color = QtWidgets.QLineEdit()
        self.focus_color = QtWidgets.QLineEdit()

        for label, edit in [
            ("Background Color", self.bg_color),
            ("Text Color", self.text_color),
            ("Focus Color", self.focus_color),
        ]:
            grid.addWidget(QtWidgets.QLabel(label), row, 0)
            r = QtWidgets.QHBoxLayout()
            r.setContentsMargins(0, 0, 0, 0)
            r.setSpacing(8)
            r.addWidget(edit, 1)
            swatch = QtWidgets.QLabel("")
            swatch.setFixedSize(28, 20)
            swatch.setStyleSheet("border: 1px solid #3f4a5a; border-radius: 5px; background: #000000;")
            r.addWidget(swatch, 0)
            self._color_swatches[edit] = swatch
            pick = QtWidgets.QPushButton("Pick")
            pick.clicked.connect(lambda _=False, e=edit: self._pick_color(e))
            r.addWidget(pick, 0)
            wrap = QtWidgets.QWidget()
            wrap.setStyleSheet("background: transparent;")
            wrap.setLayout(r)
            grid.addWidget(wrap, row, 1)
            row += 1

        layout.addWidget(card, 1)

        actions = QtWidgets.QHBoxLayout()
        actions.addStretch(1)
        cancel = QtWidgets.QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        reset = QtWidgets.QPushButton("Reset")
        reset.clicked.connect(self._reset_defaults)
        actions.addWidget(reset)
        apply_btn = QtWidgets.QPushButton("Apply")
        apply_btn.setObjectName("ImportButton")
        apply_btn.clicked.connect(self.accept)
        actions.addWidget(apply_btn)
        layout.addLayout(actions)

    def _pick_color(self, target: QtWidgets.QLineEdit):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(target.text().strip() or "#ffffff"), self)
        if c.isValid():
            target.setText(c.name().upper())
            self._update_color_preview(target)

    def _update_color_preview(self, edit: QtWidgets.QLineEdit):
        swatch = self._color_swatches.get(edit)
        if swatch is None:
            return
        raw = (edit.text() or "").strip()
        color = QtGui.QColor(raw)
        if not color.isValid():
            color = QtGui.QColor("#000000")
        swatch.setStyleSheet(
            f"border: 1px solid #3f4a5a; border-radius: 5px; background: {color.name().upper()};"
        )

    def _build_slider_with_clamps(self, min_value: float, max_value: float, step: float, decimals: int):
        container = QtWidgets.QWidget()
        container.setStyleSheet("background: transparent;")
        v = QtWidgets.QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        top = QtWidgets.QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        min_lbl = QtWidgets.QLabel(f"{min_value:.{decimals}f}")
        min_lbl.setObjectName("BookMeta")
        max_lbl = QtWidgets.QLabel(f"{max_value:.{decimals}f}")
        max_lbl.setObjectName("BookMeta")
        value_lbl = QtWidgets.QLabel("")
        value_lbl.setObjectName("SectionLabel")
        top.addWidget(min_lbl, 0)
        top.addStretch(1)
        top.addWidget(value_lbl, 0)
        top.addStretch(1)
        top.addWidget(max_lbl, 0)
        v.addLayout(top)

        slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        steps = max(1, int(round((max_value - min_value) / step)))
        slider.setRange(0, steps)
        slider.setSingleStep(1)
        slider.setPageStep(max(1, int(steps / 10)))
        slider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        v.addWidget(slider)

        self._slider_specs[slider] = {
            "min_value": float(min_value),
            "max_value": float(max_value),
            "step": float(step),
            "decimals": decimals,
            "value_label": value_lbl,
        }
        slider.valueChanged.connect(lambda _v, s=slider: self._refresh_slider_label(s))
        return container, value_lbl

    def _refresh_slider_label(self, slider):
        spec = self._slider_specs.get(slider)
        if not spec:
            return
        min_value = spec["min_value"]
        step = spec["step"]
        decimals = spec["decimals"]
        value = float(min_value) + float(slider.value()) * float(step)
        spec["value_label"].setText(f"{value:.{decimals}f}")

    def _set_slider_float(self, container, value: float):
        slider = container.findChild(QtWidgets.QSlider)
        if slider is None:
            return
        spec = self._slider_specs.get(slider)
        if not spec:
            return
        min_value = float(spec["min_value"])
        max_value = float(spec["max_value"])
        step = float(spec["step"])
        clamped = max(min_value, min(max_value, float(value)))
        raw = int(round((clamped - min_value) / step))
        slider.setValue(max(slider.minimum(), min(slider.maximum(), raw)))
        self._refresh_slider_label(slider)

    def _get_slider_float(self, container):
        slider = container.findChild(QtWidgets.QSlider)
        if slider is None:
            return 0.0
        spec = self._slider_specs.get(slider)
        if not spec:
            return 0.0
        min_value = float(spec["min_value"])
        step = float(spec["step"])
        max_value = float(spec["max_value"])
        value = min_value + float(slider.value()) * step
        return max(min_value, min(max_value, value))

    def _load_values(self):
        s = self._settings
        mode = str(s.get("reading_view_mode", "context")).strip().lower()
        self.reading_view.setCurrentText("RSVP" if mode == "rsvp" else "Context")
        self.center_context.setChecked(bool(s.get("context_force_center", True)))
        self.font_family.setCurrentText(str(s.get("font_family", "Arial")))
        self.context_highlight_style.setCurrentText(
            str(s.get("context_highlight_style", "underline")).strip().lower() or "underline"
        )
        self._set_slider_float(self.font_size, float(s.get("font_size", 150.0)))
        self._set_slider_float(self.playback_speed, float(s.get("playback_speed", 1.0)))
        self._set_slider_float(self.sync_offset, float(s.get("sync_offset", 0.0)))
        self.bg_color.setText(str(s.get("bg_color", "#121212")))
        self.text_color.setText(str(s.get("text_color", "#E0E0E0")))
        self.focus_color.setText(str(s.get("focus_color", "#FFD700")))
        self._update_color_preview(self.bg_color)
        self._update_color_preview(self.text_color)
        self._update_color_preview(self.focus_color)

    def _reset_defaults(self):
        self._settings = dict(PLAYER_DEFAULTS)
        self._load_values()

    def values(self):
        return {
            "reading_view_mode": self.reading_view.currentText().strip().lower() or "context",
            "context_force_center": bool(self.center_context.isChecked()),
            "font_family": self.font_family.currentText().strip() or "Arial",
            "context_highlight_style": self.context_highlight_style.currentText().strip().lower() or "underline",
            "font_size": float(self._get_slider_float(self.font_size)),
            "playback_speed": float(self._get_slider_float(self.playback_speed)),
            "sync_offset": float(self._get_slider_float(self.sync_offset)),
            "bg_color": self.bg_color.text().strip() or "#121212",
            "text_color": self.text_color.text().strip() or "#E0E0E0",
            "focus_color": self.focus_color.text().strip() or "#FFD700",
        }


class RSVPWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.word = ""
        self.bg_color = QtGui.QColor("#1f232a")
        self.text_color = QtGui.QColor("#e6ebf2")
        self.focus_color = QtGui.QColor("#ffd700")
        self.font_family = "Arial"
        self.font_size = 150.0

    def set_words(self, focus: str, secondary: str = ""):
        self.word = focus or ""
        _ = secondary
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self.bg_color)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
        center = self.rect().center()

        px = max(28, int(float(self.font_size) * 0.52))
        focus_font = QtGui.QFont(self.font_family, px, QtGui.QFont.Weight.Bold)
        painter.setFont(focus_font)
        painter.setPen(self.focus_color)
        focus_text = self.word or "—"
        fm = QtGui.QFontMetrics(focus_font)
        w = fm.horizontalAdvance(focus_text)
        h = fm.height()
        painter.drawText(
            int(center.x() - w / 2),
            int(center.y() + h / 4),
            focus_text,
        )


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.setWindowTitle("Cadence")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1180, 760)
        self.setStyleSheet(QSS)
        self.thread_pool = QtCore.QThreadPool.globalInstance()
        self._last_live_refresh = 0.0
        self._import_running = False
        self._import_cancel_requested = False
        self._active_import_worker = None
        self._active_book = None
        self._player_chapters = []
        self._player_timed_entries = []
        self._player_time_starts = []
        self._player_current_index = -1
        self._player_duration_ms = 0
        self._player_seek_dragging = False
        self._player_seek_was_playing = False
        self._player_scrub_target_ms = 0
        self._player_source_audio = None
        self._player_playback_audio = None
        self._player_playback_speed = 1.0
        self._audio_backend = "pygame" if pygame is not None else "qt"
        self._qt_media_available = False
        self.media_audio = None
        self.media_player = None
        self._pygame_ready = False
        self._pygame_pos_offset_ms = 0
        self._pygame_last_pos_ms = 0
        self._qt_last_pos_ms = 0
        self._player_settings = self._load_player_settings()
        self._suspend_player_settings_save = False
        self._player_title_full = "No book open"
        self._drag_active = False
        self._drag_offset = QtCore.QPoint(0, 0)
        self._title_drag_widgets = set()
        self._resize_active = False
        self._resize_edges = QtCore.Qt.Edge(0)
        self._resize_start_geom = QtCore.QRect()
        self._resize_start_global = QtCore.QPoint(0, 0)
        self._resize_border_px = 6
        self._library_sidebar_width = 320
        self._player_sidebar_width = 280
        self._player_sidebar_collapsed_width = 32
        self._player_chapters_collapsed = False

        self._build_ui()
        self._apply_player_settings()
        self._init_media_player()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.refresh_library()

    def eventFilter(self, obj, event):
        if self._handle_window_resize_event(obj, event):
            return True

        if obj in self._title_drag_widgets:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    if self.isMaximized():
                        return True
                    self._drag_active = True
                    self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseMove:
                if self._drag_active and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._drag_active = False
                    return True
            elif event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._toggle_max_restore()
                    return True
        if event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()
            if key == QtCore.Qt.Key.Key_Space:
                if self.view_stack.currentWidget() is self.player_page:
                    # Keep Space as global play/pause on player page,
                    # regardless of focused child widget.
                    self._toggle_play_pause()
                    return True
        return super().eventFilter(obj, event)

    def _shell_global_rect(self) -> QtCore.QRect:
        if not hasattr(self, "window_shell") or self.window_shell is None:
            return self.frameGeometry()
        top_left = self.window_shell.mapToGlobal(QtCore.QPoint(0, 0))
        return QtCore.QRect(top_left, self.window_shell.size())

    def _resize_edges_for_global_pos(self, global_pos: QtCore.QPoint) -> QtCore.Qt.Edge:
        if self.isMaximized():
            return QtCore.Qt.Edge(0)
        rect = self._shell_global_rect()
        if rect.isNull():
            return QtCore.Qt.Edge(0)
        pad = int(self._resize_border_px)
        left = rect.left() <= global_pos.x() <= rect.left() + pad
        right = rect.right() - pad <= global_pos.x() <= rect.right()
        top = rect.top() <= global_pos.y() <= rect.top() + pad
        bottom = rect.bottom() - pad <= global_pos.y() <= rect.bottom()
        edges = QtCore.Qt.Edge(0)
        if left:
            edges |= QtCore.Qt.Edge.LeftEdge
        if right:
            edges |= QtCore.Qt.Edge.RightEdge
        if top:
            edges |= QtCore.Qt.Edge.TopEdge
        if bottom:
            edges |= QtCore.Qt.Edge.BottomEdge
        return edges

    def _cursor_for_edges(self, edges: QtCore.Qt.Edge):
        has_left = bool(edges & QtCore.Qt.Edge.LeftEdge)
        has_right = bool(edges & QtCore.Qt.Edge.RightEdge)
        has_top = bool(edges & QtCore.Qt.Edge.TopEdge)
        has_bottom = bool(edges & QtCore.Qt.Edge.BottomEdge)
        if (has_left and has_top) or (has_right and has_bottom):
            return QtCore.Qt.CursorShape.SizeFDiagCursor
        if (has_right and has_top) or (has_left and has_bottom):
            return QtCore.Qt.CursorShape.SizeBDiagCursor
        if has_left or has_right:
            return QtCore.Qt.CursorShape.SizeHorCursor
        if has_top or has_bottom:
            return QtCore.Qt.CursorShape.SizeVerCursor
        return None

    def _apply_resize_from_drag(self, global_pos: QtCore.QPoint):
        dx = int(global_pos.x() - self._resize_start_global.x())
        dy = int(global_pos.y() - self._resize_start_global.y())
        g = QtCore.QRect(self._resize_start_geom)
        min_w = max(640, int(self.minimumWidth() or 0))
        min_h = max(420, int(self.minimumHeight() or 0))

        if self._resize_edges & QtCore.Qt.Edge.LeftEdge:
            new_left = g.left() + dx
            if g.right() - new_left + 1 < min_w:
                new_left = g.right() - min_w + 1
            g.setLeft(new_left)
        if self._resize_edges & QtCore.Qt.Edge.RightEdge:
            new_right = g.right() + dx
            if new_right - g.left() + 1 < min_w:
                new_right = g.left() + min_w - 1
            g.setRight(new_right)
        if self._resize_edges & QtCore.Qt.Edge.TopEdge:
            new_top = g.top() + dy
            if g.bottom() - new_top + 1 < min_h:
                new_top = g.bottom() - min_h + 1
            g.setTop(new_top)
        if self._resize_edges & QtCore.Qt.Edge.BottomEdge:
            new_bottom = g.bottom() + dy
            if new_bottom - g.top() + 1 < min_h:
                new_bottom = g.top() + min_h - 1
            g.setBottom(new_bottom)
        self.setGeometry(g)

    def _handle_window_resize_event(self, obj, event) -> bool:
        et = event.type()
        if et not in (
            QtCore.QEvent.Type.MouseMove,
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.MouseButtonRelease,
            QtCore.QEvent.Type.Leave,
        ):
            return False
        if self.isMaximized():
            return False
        if not isinstance(obj, QtWidgets.QWidget):
            return False
        if not (obj is self or self.isAncestorOf(obj)):
            return False

        if et == QtCore.QEvent.Type.Leave:
            if not self._resize_active:
                self.unsetCursor()
            return False

        global_pos = event.globalPosition().toPoint()
        if et == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() != QtCore.Qt.MouseButton.LeftButton:
                return False
            edges = self._resize_edges_for_global_pos(global_pos)
            if edges == QtCore.Qt.Edge(0):
                return False
            self._resize_active = True
            self._resize_edges = edges
            self._resize_start_geom = self.geometry()
            self._resize_start_global = global_pos
            return True

        if et == QtCore.QEvent.Type.MouseMove:
            if self._resize_active and (event.buttons() & QtCore.Qt.MouseButton.LeftButton):
                self._apply_resize_from_drag(global_pos)
                return True
            if not self._drag_active:
                edges = self._resize_edges_for_global_pos(global_pos)
                cursor = self._cursor_for_edges(edges)
                if cursor is None:
                    self.unsetCursor()
                else:
                    self.setCursor(cursor)
            return False

        if et == QtCore.QEvent.Type.MouseButtonRelease:
            if event.button() == QtCore.Qt.MouseButton.LeftButton and self._resize_active:
                self._resize_active = False
                self._resize_edges = QtCore.Qt.Edge(0)
                return True
        return False

    def _init_media_player(self):
        self.media_audio = None
        self.media_player = None
        # Prefer pygame backend when available to avoid QtMultimedia plugin noise
        # on environments without full multimedia backends.
        if pygame is not None:
            self._qt_media_available = False
            self._player_timer = QtCore.QTimer(self)
            self._player_timer.setInterval(50)
            self._player_timer.timeout.connect(self._poll_player)
            self._player_timer.start()
            return
        try:
            self.media_audio = QtMultimedia.QAudioOutput(self)
            self.media_player = QtMultimedia.QMediaPlayer(self)
            self.media_player.setAudioOutput(self.media_audio)
            self.media_player.positionChanged.connect(self._on_media_position)
            self.media_player.durationChanged.connect(self._on_media_duration)
            self.media_player.playbackStateChanged.connect(self._on_media_state)
            try:
                self.media_player.errorOccurred.connect(self._on_media_error)
            except Exception:
                pass
            self._qt_media_available = True
        except Exception:
            self._qt_media_available = False

        self._player_timer = QtCore.QTimer(self)
        self._player_timer.setInterval(50)
        self._player_timer.timeout.connect(self._poll_player)
        self._player_timer.start()

    def _build_ui(self):
        root = QtWidgets.QWidget()
        root.setObjectName("RootWindow")
        self.setCentralWidget(root)
        root_layout = QtWidgets.QVBoxLayout(root)
        self._normal_root_margins = (34, 4, 34, 66)
        root_layout.setContentsMargins(*self._normal_root_margins)
        root_layout.setSpacing(0)
        self._root_layout = root_layout

        shell = QtWidgets.QFrame()
        shell.setObjectName("WindowShell")
        self.window_shell = shell
        shell_layout = QtWidgets.QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        root_layout.addWidget(shell, 1)

        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(76)
        shadow.setOffset(0, 14)
        shadow.setColor(QtGui.QColor(0, 0, 0, 98))
        shell.setGraphicsEffect(shadow)
        self._window_shadow = shadow

        title_bar = QtWidgets.QFrame()
        title_bar.setObjectName("WindowTitleBar")
        title_bar.setFixedHeight(36)
        t = QtWidgets.QHBoxLayout(title_bar)
        t.setContentsMargins(10, 0, 0, 0)
        t.setSpacing(0)

        title_label = QtWidgets.QLabel("Cadence")
        title_label.setObjectName("WindowTitleLabel")
        t.addWidget(title_label, 0)
        t.addStretch(1)

        self.title_min_btn = QtWidgets.QPushButton("—")
        self.title_min_btn.setObjectName("TitleBarButton")
        self.title_min_btn.setFlat(True)
        self.title_min_btn.clicked.connect(self.showMinimized)
        t.addWidget(self.title_min_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        self.title_max_btn = QtWidgets.QPushButton("□")
        self.title_max_btn.setObjectName("TitleBarMaxButton")
        self.title_max_btn.setFlat(True)
        self.title_max_btn.clicked.connect(self._toggle_max_restore)
        t.addWidget(self.title_max_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        self.title_close_btn = QtWidgets.QPushButton("×")
        self.title_close_btn.setObjectName("TitleBarCloseButton")
        self.title_close_btn.setFlat(True)
        self.title_close_btn.clicked.connect(self.close)
        t.addWidget(self.title_close_btn, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        shell_layout.addWidget(title_bar, 0)
        self._title_drag_widgets = {title_bar, title_label}
        title_bar.installEventFilter(self)
        title_label.installEventFilter(self)

        self.view_stack = QtWidgets.QStackedWidget()
        self.view_stack.setObjectName("MainViewStack")
        shell_layout.addWidget(self.view_stack, 1)

        self.library_page = self._build_library_page()
        self.player_page = self._build_player_page()
        self.view_stack.addWidget(self.library_page)
        self.view_stack.addWidget(self.player_page)

        bottom_cap = QtWidgets.QFrame()
        bottom_cap.setObjectName("BottomCornerCap")
        bottom_cap.setFixedHeight(12)
        self.bottom_corner_cap = bottom_cap
        self.bottom_cap_divider = QtWidgets.QFrame(bottom_cap)
        self.bottom_cap_divider.setObjectName("BottomCapDivider")
        self.bottom_cap_divider.setFixedWidth(1)
        shell_layout.addWidget(bottom_cap, 0)

        footer_div = QtWidgets.QFrame()
        footer_div.setFixedHeight(1)
        footer_div.setStyleSheet("background:#3f4a5a;")
        self.import_footer_div = footer_div
        shell_layout.addWidget(footer_div, 0)

        footer = QtWidgets.QFrame()
        footer.setObjectName("Footer")
        self.import_footer = footer
        f = QtWidgets.QVBoxLayout(footer)
        f.setContentsMargins(12, 8, 12, 8)
        f.setSpacing(6)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        f.addWidget(self.progress)
        self.status = QtWidgets.QLabel("Ready")
        f.addWidget(self.status)
        shell_layout.addWidget(footer, 0)
        self._set_import_footer_visible(False)
        self._layout_bottom_cap_divider()
        self._sync_window_chrome()

    def _toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self.title_max_btn.setText("□")
        else:
            self.showMaximized()
            self.title_max_btn.setText("❐")
        self._sync_window_chrome()

    def _sync_window_chrome(self):
        if not hasattr(self, "_root_layout"):
            return
        if self.isMaximized():
            self._root_layout.setContentsMargins(0, 0, 0, 0)
            if hasattr(self, "_window_shadow"):
                self._window_shadow.setEnabled(False)
        else:
            self._root_layout.setContentsMargins(*self._normal_root_margins)
            if hasattr(self, "_window_shadow"):
                self._window_shadow.setEnabled(True)

    def resizeEvent(self, event):
        self._sync_window_chrome()
        self._layout_bottom_cap_divider()
        self._refresh_player_title_elide()
        super().resizeEvent(event)

    def _set_import_footer_visible(self, show_footer: bool):
        self.import_footer_div.setVisible(show_footer)
        self.import_footer.setVisible(show_footer)
        if hasattr(self, "bottom_corner_cap"):
            self.bottom_corner_cap.setVisible(not show_footer)
        self._layout_bottom_cap_divider()

    def _layout_bottom_cap_divider(self):
        if not hasattr(self, "bottom_corner_cap") or not hasattr(self, "bottom_cap_divider"):
            return
        if not self.bottom_corner_cap.isVisible():
            self.bottom_cap_divider.setVisible(False)
            return
        if hasattr(self, "view_stack") and self.view_stack.currentWidget() is self.player_page:
            x = int(self.player_left_sidebar.width()) if hasattr(self, "player_left_sidebar") else int(self._player_sidebar_width)
        else:
            x = int(self._library_sidebar_width)
        h = max(1, int(self.bottom_corner_cap.height()))
        self.bottom_cap_divider.setGeometry(x, 0, 1, h)
        self.bottom_cap_divider.setVisible(True)

    def _set_player_chapters_panel_collapsed(self, collapsed: bool):
        self._player_chapters_collapsed = bool(collapsed)
        if hasattr(self, "player_left_sidebar"):
            self.player_left_sidebar.setFixedWidth(
                int(self._player_sidebar_collapsed_width if self._player_chapters_collapsed else self._player_sidebar_width)
            )
            self.player_left_sidebar.setVisible(True)
        if hasattr(self, "player_left_layout"):
            if self._player_chapters_collapsed:
                self.player_left_layout.setContentsMargins(2, 12, 0, 4)
                self.player_left_layout.setSpacing(2)
            else:
                self.player_left_layout.setContentsMargins(12, 12, 12, 12)
                self.player_left_layout.setSpacing(8)
        if hasattr(self, "player_chapter_header_layout"):
            self.player_chapter_header_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        if hasattr(self, "player_chapter_panel"):
            self.player_chapter_panel.setVisible(not self._player_chapters_collapsed)
        if hasattr(self, "player_chapter_label"):
            self.player_chapter_label.setVisible(not self._player_chapters_collapsed)
        if hasattr(self, "player_content_divider"):
            self.player_content_divider.setVisible(True)
        if hasattr(self, "player_chapters_toggle_btn"):
            self.player_chapters_toggle_btn.setText("▸" if self._player_chapters_collapsed else "◂")
        self._layout_bottom_cap_divider()

    def _toggle_player_chapters_panel(self):
        self._set_player_chapters_panel_collapsed(not self._player_chapters_collapsed)

    def _build_library_page(self):
        body = QtWidgets.QWidget()
        body.setObjectName("LibraryPageRoot")
        body_layout = QtWidgets.QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar = QtWidgets.QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(320)
        side = QtWidgets.QVBoxLayout(sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(10)

        controls_card = QtWidgets.QFrame()
        controls_card.setObjectName("ControlsCard")
        controls_layout = QtWidgets.QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(8)

        import_row = QtWidgets.QHBoxLayout()
        self.import_btn = QtWidgets.QPushButton("Import EPUB")
        self.import_btn.setObjectName("ImportButton")
        self.import_btn.clicked.connect(self._on_import_button_clicked)
        import_row.addWidget(self.import_btn, 1)
        self.settings_btn = QtWidgets.QPushButton("⚙")
        self.settings_btn.clicked.connect(self.open_runtime_settings)
        import_row.addWidget(self.settings_btn, 0)
        controls_layout.addLayout(import_row)

        voice_lbl = QtWidgets.QLabel("Voice")
        voice_lbl.setObjectName("SectionLabel")
        controls_layout.addWidget(voice_lbl)

        self.voice_combo = QtWidgets.QComboBox()
        self.voice_combo.addItems(["M3", "M1", "F1", "F3"])
        self.voice_combo.setCurrentText("M3")
        controls_layout.addWidget(self.voice_combo)

        side.addWidget(controls_card, 0)

        log_card = QtWidgets.QFrame()
        log_card.setObjectName("LogCard")
        log_layout = QtWidgets.QVBoxLayout(log_card)
        log_layout.setContentsMargins(12, 12, 12, 12)
        log_layout.setSpacing(8)

        log_lbl = QtWidgets.QLabel("Process Log")
        log_lbl.setObjectName("SectionLabel")
        log_layout.addWidget(log_lbl)

        self.log_box = QtWidgets.QPlainTextEdit()
        self.log_box.setReadOnly(True)
        log_layout.addWidget(self.log_box, 1)
        side.addWidget(log_card, 1)

        divider = QtWidgets.QFrame()
        divider.setStyleSheet("background:#3f4a5a; max-width:1px; min-width:1px;")

        main = QtWidgets.QFrame()
        main.setObjectName("MainArea")
        m = QtWidgets.QVBoxLayout(main)
        m.setContentsMargins(16, 16, 16, 16)
        m.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        library_lbl = QtWidgets.QLabel("My Library")
        library_lbl.setObjectName("MainTitle")
        header.addWidget(library_lbl)
        header.addStretch(1)
        self.open_library_btn = QtWidgets.QPushButton("Open Folder")
        self.open_library_btn.clicked.connect(self.open_library_folder)
        header.addWidget(self.open_library_btn)
        self.refresh_btn = QtWidgets.QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_library)
        header.addWidget(self.refresh_btn)
        m.addLayout(header)

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search book title...")
        self.search.textChanged.connect(self.refresh_library)
        m.addWidget(self.search)

        self.list_shell = QtWidgets.QFrame()
        self.list_shell.setObjectName("ListShell")
        list_shell_layout = QtWidgets.QVBoxLayout(self.list_shell)
        list_shell_layout.setContentsMargins(8, 8, 8, 8)
        list_shell_layout.setSpacing(0)

        self.books_scroll = QtWidgets.QScrollArea()
        self.books_scroll.setWidgetResizable(True)
        self.books_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.books_scroll_content = QtWidgets.QWidget()
        self.books_scroll_content.setObjectName("BooksScrollContent")
        self.books_layout = QtWidgets.QVBoxLayout(self.books_scroll_content)
        self.books_layout.setContentsMargins(4, 4, 4, 4)
        self.books_layout.setSpacing(8)
        self.books_layout.addStretch(1)
        self.books_scroll.setWidget(self.books_scroll_content)
        list_shell_layout.addWidget(self.books_scroll)

        m.addWidget(self.list_shell, 1)

        body_layout.addWidget(sidebar, 0)
        body_layout.addWidget(divider, 0)
        body_layout.addWidget(main, 1)
        return body

    def _build_player_page(self):
        page = QtWidgets.QWidget()
        page.setObjectName("PlayerPageRoot")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top = QtWidgets.QFrame()
        top.setObjectName("MainArea")
        top_layout = QtWidgets.QHBoxLayout(top)
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_layout.setSpacing(8)

        self.player_back_btn = QtWidgets.QPushButton("◀ Library")
        self.player_back_btn.clicked.connect(self.show_library_page)
        top_layout.addWidget(self.player_back_btn, 0)

        self.player_title = QtWidgets.QLabel("No book open")
        self.player_title.setObjectName("MainTitle")
        self.player_title.setWordWrap(False)
        self.player_title.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self.player_title.setMinimumWidth(0)
        top_layout.addWidget(self.player_title, 1)

        self.player_settings_btn = QtWidgets.QPushButton("⚙ Settings")
        self.player_settings_btn.clicked.connect(self.open_player_settings)
        top_layout.addWidget(self.player_settings_btn, 0)

        layout.addWidget(top, 0)

        pbar_row = QtWidgets.QFrame()
        pbar_row.setObjectName("MainArea")
        pbar_layout = QtWidgets.QVBoxLayout(pbar_row)
        pbar_layout.setContentsMargins(12, 8, 12, 8)
        pbar_layout.setSpacing(6)

        self.player_seek = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.player_seek.setRange(0, 1000)
        self.player_seek.setValue(0)
        self.player_seek.sliderPressed.connect(self._on_seek_start)
        self.player_seek.sliderReleased.connect(self._on_seek_release)
        self.player_seek.valueChanged.connect(self._on_seek_changed)
        pbar_layout.addWidget(self.player_seek)
        # Keep internal naming for existing progress update code.
        self.player_progress = self.player_seek

        controls_row = QtWidgets.QHBoxLayout()
        controls_row.setSpacing(8)
        self.player_chapter_meta = QtWidgets.QLabel("Chapter -/-")
        self.player_chapter_meta.setObjectName("BookMeta")
        controls_row.addWidget(self.player_chapter_meta, 0)
        controls_row.addStretch(1)

        self.player_prev_btn = QtWidgets.QPushButton("◀ Chapter")
        self.player_prev_btn.clicked.connect(lambda: self._jump_chapter(-1))
        controls_row.addWidget(self.player_prev_btn, 0)

        self.player_play_btn = QtWidgets.QPushButton("Play")
        self.player_play_btn.setObjectName("ReadButton")
        self.player_play_btn.clicked.connect(self._toggle_play_pause)
        controls_row.addWidget(self.player_play_btn, 0)

        self.player_next_btn = QtWidgets.QPushButton("Chapter ▶")
        self.player_next_btn.clicked.connect(lambda: self._jump_chapter(1))
        controls_row.addWidget(self.player_next_btn, 0)
        controls_row.addStretch(1)

        self.player_time_meta = QtWidgets.QLabel("00:00 / 00:00")
        self.player_time_meta.setObjectName("BookMeta")
        controls_row.addWidget(self.player_time_meta, 0)

        pbar_layout.addLayout(controls_row)

        layout.addWidget(pbar_row, 0)

        d2 = QtWidgets.QFrame()
        d2.setFixedHeight(1)
        d2.setStyleSheet("background:#3f4a5a;")
        layout.addWidget(d2, 0)

        content = QtWidgets.QWidget()
        content.setObjectName("PlayerContentRoot")
        c = QtWidgets.QHBoxLayout(content)
        c.setContentsMargins(0, 0, 0, 0)
        c.setSpacing(0)

        left = QtWidgets.QFrame()
        left.setObjectName("Sidebar")
        left.setFixedWidth(int(self._player_sidebar_width))
        self.player_left_sidebar = left
        l = QtWidgets.QVBoxLayout(left)
        l.setContentsMargins(12, 12, 12, 12)
        l.setSpacing(8)
        self.player_left_layout = l

        chapter_hdr = QtWidgets.QHBoxLayout()
        chapter_hdr.setContentsMargins(0, 0, 0, 0)
        chapter_hdr.setSpacing(6)
        self.player_chapter_header_layout = chapter_hdr
        self.player_chapter_label = QtWidgets.QLabel("Chapters")
        self.player_chapter_label.setObjectName("SectionLabel")
        chapter_hdr.addWidget(self.player_chapter_label, 1)
        self.player_chapters_toggle_btn = QtWidgets.QPushButton("◂")
        self.player_chapters_toggle_btn.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.player_chapters_toggle_btn.setFixedWidth(28)
        self.player_chapters_toggle_btn.clicked.connect(self._toggle_player_chapters_panel)
        chapter_hdr.addWidget(self.player_chapters_toggle_btn, 0)
        l.addLayout(chapter_hdr)

        self.player_chapter_panel = QtWidgets.QFrame()
        self.player_chapter_panel.setObjectName("PlayerPanel")
        lp = QtWidgets.QVBoxLayout(self.player_chapter_panel)
        lp.setContentsMargins(8, 8, 8, 8)
        lp.setSpacing(0)
        self.player_chapter_list = QtWidgets.QListWidget()
        self.player_chapter_list.currentRowChanged.connect(self._on_player_chapter_selected)
        lp.addWidget(self.player_chapter_list, 1)
        l.addWidget(self.player_chapter_panel, 1)

        vdiv = QtWidgets.QFrame()
        vdiv.setStyleSheet("background:#3f4a5a; max-width:1px; min-width:1px;")
        self.player_content_divider = vdiv

        right = QtWidgets.QFrame()
        right.setObjectName("MainArea")
        r = QtWidgets.QVBoxLayout(right)
        r.setContentsMargins(12, 12, 12, 12)
        r.setSpacing(8)

        self.player_reader_panel = QtWidgets.QFrame()
        self.player_reader_panel.setObjectName("PlayerPanel")
        rp = QtWidgets.QVBoxLayout(self.player_reader_panel)
        rp.setContentsMargins(8, 8, 8, 8)
        rp.setSpacing(0)
        self.player_view_stack = QtWidgets.QStackedWidget()
        self.player_text = QtWidgets.QTextEdit()
        self.player_text.setReadOnly(True)
        self.player_text.setAcceptRichText(False)
        self.player_text.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.player_text.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
            | QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.player_view_stack.addWidget(self.player_text)
        self.player_rsvp = RSVPWidget()
        self.player_view_stack.addWidget(self.player_rsvp)
        rp.addWidget(self.player_view_stack, 1)
        r.addWidget(self.player_reader_panel, 1)

        c.addWidget(left, 0)
        c.addWidget(vdiv, 0)
        c.addWidget(right, 1)
        layout.addWidget(content, 1)
        self._set_player_chapters_panel_collapsed(False)

        return page

    def log(self, message: str):
        self.log_box.appendPlainText(message)
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_status(self, pct: float, msg: str):
        self.progress.setValue(max(0, min(1000, int(pct * 1000))))
        self.status.setText(msg)
        show_footer = bool(self._import_running)
        self._set_import_footer_visible(show_footer)
        now = time.monotonic()
        if now - self._last_live_refresh >= 1.0:
            self._last_live_refresh = now
            self.refresh_library()
            self._update_player_chapter_availability()

    def _clear_book_cards(self):
        while self.books_layout.count() > 0:
            item = self.books_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def refresh_library(self):
        books = BookManager.get_books()
        q = self.search.text().strip().lower()
        if q:
            books = [b for b in books if q in b.get("title", "").lower()]
        books.sort(key=lambda b: (not b.get("is_incomplete", False), b.get("title", "").lower()))

        self._clear_book_cards()

        if not books:
            lbl = QtWidgets.QLabel("No matching books." if q else "No books found. Import an EPUB to start.")
            lbl.setObjectName("BookMeta")
            self.books_layout.addWidget(lbl)
            self.books_layout.addStretch(1)
            return

        for book in books:
            card = BookCard(book)
            card.read_requested.connect(self.open_player_page)
            card.continue_requested.connect(self.continue_import_book)
            self.books_layout.addWidget(card)
        self.books_layout.addStretch(1)

    def show_library_page(self):
        self._pause_all_audio()
        self.player_play_btn.setText("Play")
        self.view_stack.setCurrentWidget(self.library_page)
        self._layout_bottom_cap_divider()
        self.refresh_library()

    def open_player_page(self, book: dict):
        self._active_book = dict(book)
        self._set_player_title(book.get("title", "Book"))
        self.player_progress.setValue(0)
        self.player_seek.setValue(0)
        self.player_time_meta.setText("00:00 / 00:00")
        self._player_current_index = -1
        self.player_chapter_list.clear()
        self._player_chapters = []

        cdir = Path(book.get("path", "")) / "content"
        txt_files = sorted(cdir.glob("ch_*.txt"))
        for txt in txt_files:
            stem = txt.stem
            label = stem.replace("ch_", "Chapter ")
            item = QtWidgets.QListWidgetItem(label)
            item.setData(32, stem)
            self.player_chapter_list.addItem(item)
            self._player_chapters.append(stem)

        self._update_player_chapter_availability()

        if txt_files:
            target_row = 0
            last = int(book.get("last_chapter", 1) or 1)
            if 1 <= last <= len(txt_files):
                target_row = last - 1
            self.player_chapter_list.setCurrentRow(target_row)
            self.player_chapter_meta.setText(f"Chapter {target_row + 1}/{len(txt_files)}")
        else:
            self.player_chapter_meta.setText("Chapter -/-")
            self.player_text.setPlainText("No chapter text found for this book.")

        self.view_stack.setCurrentWidget(self.player_page)
        self._layout_bottom_cap_divider()
        QtCore.QTimer.singleShot(0, self._refresh_player_title_elide)
        QtCore.QTimer.singleShot(25, self._refresh_player_title_elide)

    def _set_player_title(self, title: str):
        self._player_title_full = str(title or "Book")
        self.player_title.setToolTip(self._player_title_full)
        self._refresh_player_title_elide()

    def _refresh_player_title_elide(self):
        if not hasattr(self, "player_title") or self.player_title is None:
            return
        full = getattr(self, "_player_title_full", "") or "No book open"
        avail = max(0, int(self.player_title.width()) - 6)
        if avail <= 0:
            self.player_title.setText(full)
            return
        elided = self.player_title.fontMetrics().elidedText(
            full,
            QtCore.Qt.TextElideMode.ElideRight,
            avail,
        )
        self.player_title.setText(elided)

    def _on_player_chapter_selected(self, row: int):
        if row < 0 or not self._active_book:
            return
        self._pause_all_audio()
        self._pygame_pos_offset_ms = 0
        self._pygame_last_pos_ms = 0
        item = self.player_chapter_list.item(row)
        if item is None:
            return
        stem = item.data(32)
        book_path = Path(self._active_book.get("path", ""))
        txt = book_path / "content" / f"{stem}.txt"
        wav = book_path / "audio" / f"{stem}.wav"
        jsn = book_path / "content" / f"{stem}.json"

        total = max(1, self.player_chapter_list.count())
        self.player_chapter_meta.setText(f"Chapter {row + 1}/{total}")
        try:
            self._load_chapter_text_and_timing(txt, jsn)
        except Exception as exc:
            self.player_text.setPlainText(f"Failed to load chapter text:\n{exc}")
            self._player_timed_entries = []
            self._player_time_starts = []

        if wav.exists() and wav.stat().st_size > 0:
            self._player_source_audio = wav
            self._player_playback_speed = max(0.5, min(4.0, float(self._player_settings.get("playback_speed", 1.0))))
            self._player_playback_audio = self._resolve_playback_audio(
                self._player_source_audio, self._player_playback_speed
            )
            self._player_duration_ms = self._probe_audio_duration_ms(wav)
            if self.media_player is not None:
                self.media_player.setSource(QtCore.QUrl.fromLocalFile(str(wav.resolve())))
            self._audio_backend = "pygame" if self._ensure_pygame_audio() else "qt"
            if self._audio_backend == "qt" and not self._qt_media_available:
                self._audio_backend = "pygame"
            self.player_play_btn.setEnabled(True)
            self.player_seek.setEnabled(True)
            self._update_time_labels(0, self._player_duration_ms)
        else:
            self._player_source_audio = None
            self._player_playback_audio = None
            if self.media_player is not None:
                self.media_player.setSource(QtCore.QUrl())
            self._audio_backend = "qt"
            self.player_play_btn.setEnabled(False)
            self.player_seek.setEnabled(False)
            self.player_play_btn.setText("Play")
            self.player_progress.setValue(0)
            self.player_seek.setValue(0)
            self.player_time_meta.setText("00:00 / 00:00")

    def _update_player_chapter_availability(self):
        if not self._active_book:
            return
        book_path = Path(self._active_book.get("path", ""))
        if not book_path.exists():
            return
        for i in range(self.player_chapter_list.count()):
            item = self.player_chapter_list.item(i)
            if item is None:
                continue
            stem = item.data(32)
            if not stem:
                continue
            wav = book_path / "audio" / f"{stem}.wav"
            jsn = book_path / "content" / f"{stem}.json"
            has_audio = wav.exists() and wav.stat().st_size > 0
            has_align = jsn.exists() and jsn.stat().st_size > 0
            chapter_num = stem.replace("ch_", "Chapter ")
            item.setText(chapter_num)
            if has_audio and has_align:
                item.setForeground(QtGui.QBrush(QtGui.QColor("#e6ebf2")))
                item.setBackground(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))
            elif has_audio and not has_align:
                item.setForeground(QtGui.QBrush(QtGui.QColor("#f0d27a")))
                item.setBackground(QtGui.QBrush(QtGui.QColor("#4a3f22")))
            else:
                item.setForeground(QtGui.QBrush(QtGui.QColor("#f3b0b0")))
                item.setBackground(QtGui.QBrush(QtGui.QColor("#4a2a2a")))

    def _load_chapter_text_and_timing(self, txt_path: Path, json_path: Path):
        raw_text = txt_path.read_text(encoding="utf-8")
        if not json_path.exists() or json_path.stat().st_size <= 0:
            self.player_text.setPlainText(raw_text)
            self._player_timed_entries = []
            self._player_time_starts = []
            return

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            self.player_text.setPlainText(raw_text)
            self._player_timed_entries = []
            self._player_time_starts = []
            return

        parts = []
        timed = []
        cursor = 0
        for token in data:
            w = str(token.get("word", ""))
            if not w:
                continue
            start_c = cursor
            parts.append(w)
            cursor += len(w)
            end_c = cursor
            start_t = float(token.get("start", 0.0))
            end_t = float(token.get("end", start_t))
            if w.strip():
                timed.append(
                    {
                        "char_start": start_c,
                        "char_end": end_c,
                        "start_t": start_t,
                        "end_t": end_t,
                        "word": w,
                    }
                )

        final_text = "".join(parts) if parts else raw_text
        self.player_text.setPlainText(final_text)
        self._player_timed_entries = timed
        self._player_time_starts = [e["start_t"] for e in timed]
        self._player_current_index = -1
        self._set_context_highlight(-1)
        self.player_rsvp.set_words("", "")

    def _toggle_play_pause(self):
        if self._audio_backend == "pygame":
            if pygame is None:
                return
            if pygame.mixer.music.get_busy():
                self._pause_pygame()
            else:
                value = int(self.player_seek.value())
                target = int((float(value) / 1000.0) * float(max(1, self._player_duration_ms)))
                self._play_pygame_from(target)
        else:
            if self.media_player is None:
                return
            state = self.media_player.playbackState()
            if state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
                self.media_player.pause()
            else:
                self.media_player.play()

    def _jump_chapter(self, offset: int):
        row = self.player_chapter_list.currentRow()
        if row < 0:
            return
        target = row + int(offset)
        if 0 <= target < self.player_chapter_list.count():
            self.player_chapter_list.setCurrentRow(target)

    def _on_seek_start(self):
        self._player_scrub_target_ms = int(max(0, self._pygame_current_pos_ms()))
        if self._audio_backend == "pygame":
            self._player_seek_was_playing = bool(
                pygame is not None and self._pygame_ready and pygame.mixer.music.get_busy()
            )
        else:
            self._player_seek_was_playing = bool(
                self.media_player is not None
                and self.media_player.playbackState() == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState
            )
        self._player_seek_dragging = True

    def _on_seek_release(self):
        if self._player_duration_ms > 0:
            value = int(self.player_seek.value())
            target = int((float(value) / 1000.0) * float(self._player_duration_ms))
            target = max(0, min(self._player_duration_ms, target))
            if self._player_scrub_target_ms > 0:
                target = int(max(0, min(self._player_duration_ms, self._player_scrub_target_ms)))
            if self._audio_backend == "pygame":
                if self._player_seek_was_playing:
                    self._play_pygame_from(target)
                else:
                    self._pygame_pos_offset_ms = target
                    self._pygame_last_pos_ms = target
                    self.player_play_btn.setText("Play")
                    slider_value = int((float(target) / float(max(1, self._player_duration_ms))) * 1000.0)
                    self.player_progress.setValue(slider_value)
                    self.player_seek.setValue(slider_value)
                    self._update_time_labels(target, self._player_duration_ms)
                    self._update_word_highlight(
                        float(target) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0))
                    )
            else:
                if self.media_player is not None:
                    self.media_player.setPosition(target)
                    if self._player_seek_was_playing:
                        self.media_player.play()
                    else:
                        self.media_player.pause()
                    slider_value = int((float(target) / float(max(1, self._player_duration_ms))) * 1000.0)
                    self.player_progress.setValue(slider_value)
                    self.player_seek.setValue(slider_value)
                    self._update_time_labels(target, self._player_duration_ms)
                    self._update_word_highlight(
                        float(target) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0))
                    )
        self._player_seek_dragging = False
        self._player_seek_was_playing = False
        self._player_scrub_target_ms = 0

    def _on_seek_changed(self, value: int):
        if self._player_duration_ms <= 0:
            return
        target = int((float(value) / 1000.0) * float(self._player_duration_ms))
        target = max(0, min(self._player_duration_ms, target))
        if self._player_seek_dragging:
            # While dragging, scrub UI only. Final audio seek happens on release.
            self._player_scrub_target_ms = target
            self._update_time_labels(target, self._player_duration_ms)
            self._update_word_highlight(
                float(target) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0))
            )
            return
        if self.sender() is self.player_seek:
            return

    def _on_media_state(self, state):
        if self._audio_backend != "qt":
            return
        if state == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState:
            self.player_play_btn.setText("Pause")
        else:
            self.player_play_btn.setText("Play")

    def _on_media_duration(self, duration_ms: int):
        if self._audio_backend != "qt":
            return
        if self.media_player is None:
            return
        self._player_duration_ms = int(max(0, duration_ms))
        self._update_time_labels(self.media_player.position(), self._player_duration_ms)

    def _on_media_position(self, pos_ms: int):
        if self._audio_backend != "qt":
            return
        pos_ms = int(max(0, pos_ms))
        self._qt_last_pos_ms = pos_ms
        duration = int(max(1, self._player_duration_ms))
        ratio = max(0.0, min(1.0, float(pos_ms) / float(duration))) if duration > 0 else 0.0
        value = int(ratio * 1000.0)
        self.player_progress.setValue(value)
        if not self._player_seek_dragging:
            self.player_seek.setValue(value)
        self._update_time_labels(pos_ms, self._player_duration_ms)
        self._update_word_highlight(float(pos_ms) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0)))

    def _update_time_labels(self, pos_ms: int, dur_ms: int):
        self.player_time_meta.setText(
            f"{self._format_ms(pos_ms)} / {self._format_ms(max(0, dur_ms))}"
        )

    def _format_ms(self, ms: int):
        total_s = max(0, int(ms / 1000))
        m, s = divmod(total_s, 60)
        return f"{m:02d}:{s:02d}"

    def _probe_audio_duration_ms(self, wav_path: Path):
        if sf is None:
            return 0
        try:
            info = sf.info(str(wav_path))
            if info.samplerate > 0 and info.frames > 0:
                return int((float(info.frames) / float(info.samplerate)) * 1000.0)
        except Exception:
            return 0
        return 0

    def _atempo_filter(self, speed: float):
        speed = max(0.5, min(4.0, float(speed)))
        parts = []
        remaining = speed
        while remaining > 2.0:
            parts.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            parts.append("atempo=0.5")
            remaining /= 0.5
        parts.append(f"atempo={remaining:.4f}")
        return ",".join(parts)

    def _resolve_playback_audio(self, source_wav: Path, speed: float):
        speed = max(0.5, min(4.0, float(speed)))
        if abs(speed - 1.0) < 1e-6:
            return source_wav

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.log("ffmpeg not found, playback speed uses original audio.")
            return source_wav

        cache_dir = source_wav.parent / ".cadence_speed_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        speed_tag = f"{speed:.2f}".replace(".", "_")
        out_path = cache_dir / f"{source_wav.stem}.speed_{speed_tag}.wav"
        # Keep cache bounded: remove other speed variants for this same chapter.
        for old in cache_dir.glob(f"{source_wav.stem}.speed_*.wav"):
            if old == out_path:
                continue
            try:
                old.unlink()
            except Exception:
                pass
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path

        filter_chain = self._atempo_filter(speed)
        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_wav),
            "-vn",
            "-filter:a",
            filter_chain,
            str(out_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                self._trim_speed_cache(cache_dir, max_bytes=512 * 1024 * 1024)
                return out_path
            if proc.stderr:
                self.log(f"ffmpeg speed convert failed: {proc.stderr.strip()[:240]}")
        except Exception as exc:
            self.log(f"ffmpeg speed convert error: {exc}")
        return source_wav

    def _trim_speed_cache(self, cache_dir: Path, max_bytes: int):
        try:
            files = [p for p in cache_dir.glob("*.wav") if p.is_file()]
            total = sum(p.stat().st_size for p in files)
            if total <= max_bytes:
                return
            files.sort(key=lambda p: p.stat().st_mtime)
            for p in files:
                if total <= max_bytes:
                    break
                # Never delete currently active playback file.
                if self._player_playback_audio is not None and p == self._player_playback_audio:
                    continue
                try:
                    size = p.stat().st_size
                    p.unlink()
                    total -= size
                except Exception:
                    pass
        except Exception:
            pass

    def _ensure_pygame_audio(self):
        if pygame is None:
            return False
        if self._pygame_ready:
            return True
        try:
            pygame.mixer.init()
            self._pygame_ready = True
            return True
        except Exception:
            return False

    def _play_pygame_from(self, target_ms: int):
        if not self._ensure_pygame_audio() or self._player_source_audio is None:
            return
        target_ms = max(0, int(target_ms))
        speed = float(max(0.5, min(4.0, self._player_playback_speed or 1.0)))
        audio_path = self._player_playback_audio or self._player_source_audio
        path = str(audio_path.resolve())
        try:
            pygame.mixer.music.load(path)
            try:
                pygame_target_s = max(0.0, float(target_ms) / 1000.0 / speed)
                pygame.mixer.music.play(0, pygame_target_s)
            except TypeError:
                pygame.mixer.music.play()
            self._pygame_pos_offset_ms = target_ms
            self._pygame_last_pos_ms = target_ms
            self.player_play_btn.setText("Pause")
        except Exception as exc:
            self.log(f"pygame playback error: {exc}")

    def _pause_pygame(self):
        if pygame is None or not self._pygame_ready:
            return
        current = self._pygame_current_pos_ms()
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self._pygame_pos_offset_ms = current
        self._pygame_last_pos_ms = current
        self.player_play_btn.setText("Play")

    def _pygame_current_pos_ms(self):
        if pygame is None or not self._pygame_ready:
            return int(self._pygame_last_pos_ms)
        pos = pygame.mixer.music.get_pos()
        if pos < 0:
            return int(self._pygame_last_pos_ms)
        speed = float(max(0.5, min(4.0, self._player_playback_speed or 1.0)))
        current = int(self._pygame_pos_offset_ms + float(pos) * speed)
        self._pygame_last_pos_ms = current
        return current

    def _pause_all_audio(self):
        if self.media_player is not None:
            try:
                self.media_player.pause()
            except Exception:
                pass
        if pygame is not None and self._pygame_ready:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

    def _on_media_error(self, error, error_string=""):
        if self._audio_backend == "qt":
            self.log(f"Qt audio error: {error_string or str(error)}")
            if self._ensure_pygame_audio():
                self._audio_backend = "pygame"
                self.log("Falling back to pygame audio backend.")

    def _poll_player(self):
        if self._audio_backend != "pygame":
            return
        if self._player_duration_ms <= 0:
            return

        if pygame is None or not self._pygame_ready:
            return

        if self._player_seek_dragging:
            # While user scrubs, keep UI pinned to scrub position and ignore playback position.
            target = int(max(0, min(self._player_duration_ms, self._player_scrub_target_ms)))
            ratio = max(0.0, min(1.0, float(target) / float(max(1, self._player_duration_ms))))
            value = int(ratio * 1000.0)
            self.player_progress.setValue(value)
            self._update_time_labels(target, self._player_duration_ms)
            self._update_word_highlight(
                float(target) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0))
            )
            return

        busy = pygame.mixer.music.get_busy()
        pos_ms = self._pygame_current_pos_ms()
        pos_ms = max(0, min(self._player_duration_ms, pos_ms))

        ratio = max(0.0, min(1.0, float(pos_ms) / float(max(1, self._player_duration_ms))))
        value = int(ratio * 1000.0)
        self.player_progress.setValue(value)
        if not self._player_seek_dragging:
            self.player_seek.setValue(value)
        self._update_time_labels(pos_ms, self._player_duration_ms)
        self._update_word_highlight(float(pos_ms) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0)))

        if not busy:
            self.player_play_btn.setText("Play")

    def _update_word_highlight(self, t_s: float):
        if not self._player_timed_entries:
            return
        idx = bisect.bisect_right(self._player_time_starts, t_s) - 1
        if idx < 0:
            idx = 0
        if idx >= len(self._player_timed_entries):
            idx = len(self._player_timed_entries) - 1
        if idx == self._player_current_index:
            return
        self._player_current_index = idx
        self._set_context_highlight(idx)

        current = self._player_timed_entries[idx]["word"].strip()
        self.player_rsvp.set_words(current)

    def _set_context_highlight(self, idx: int):
        self.player_text.setExtraSelections([])
        if idx < 0 or idx >= len(self._player_timed_entries):
            return
        entry = self._player_timed_entries[idx]
        cursor = self.player_text.textCursor()
        cursor.setPosition(int(entry["char_start"]))
        cursor.setPosition(int(entry["char_end"]), QtGui.QTextCursor.MoveMode.KeepAnchor)

        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.cursor = cursor
        focus = QtGui.QColor(str(self._player_settings.get("focus_color", "#FFD700")))
        style = str(self._player_settings.get("context_highlight_style", "underline")).strip().lower()
        if style == "block":
            selection.format.setBackground(QtGui.QBrush(focus))
            selection.format.setForeground(QtGui.QBrush(self._pick_contrast_text_color(focus)))
            selection.format.setFontUnderline(False)
        elif style == "word":
            selection.format.setForeground(QtGui.QBrush(focus))
            selection.format.setFontUnderline(False)
        else:
            selection.format.setForeground(QtGui.QBrush(focus))
            selection.format.setFontUnderline(True)
        self.player_text.setExtraSelections([selection])

        if bool(self._player_settings.get("context_force_center", True)):
            rect = self.player_text.cursorRect(cursor)
            viewport_h = self.player_text.viewport().height()
            vbar = self.player_text.verticalScrollBar()
            target = vbar.value() + rect.center().y() - int(viewport_h / 2)
            vbar.setValue(max(vbar.minimum(), min(vbar.maximum(), target)))

    def _load_player_settings(self):
        data = dict(PLAYER_DEFAULTS)
        try:
            if PLAYER_SETTINGS_FILE.exists():
                loaded = json.loads(PLAYER_SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data.update(loaded)
        except Exception:
            pass
        return data

    def _pick_contrast_text_color(self, bg: QtGui.QColor):
        r = int(bg.red())
        g = int(bg.green())
        b = int(bg.blue())
        # Perceived luminance; choose dark text for bright backgrounds and vice versa.
        luminance = (0.299 * r) + (0.587 * g) + (0.114 * b)
        return QtGui.QColor("#111111") if luminance >= 150 else QtGui.QColor("#f5f7fa")

    def _save_player_settings(self):
        try:
            PLAYER_SETTINGS_FILE.write_text(
                json.dumps(self._player_settings, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            self.log(f"Failed to save player settings: {exc}")

    def _apply_player_settings(self):
        s = self._player_settings
        bg = str(s.get("bg_color", "#121212"))
        text = str(s.get("text_color", "#E0E0E0"))
        focus = str(s.get("focus_color", "#FFD700"))
        family = str(s.get("font_family", "Arial"))
        size = int(max(12, float(s.get("font_size", 150.0)) * 0.24))
        speed = float(s.get("playback_speed", 1.0))

        self.player_reader_panel.setStyleSheet(
            f"QFrame#PlayerPanel {{ background: {bg}; border: 1px solid #3f4a5a; border-radius: 12px; }}"
        )
        self.player_view_stack.setStyleSheet(
            f"QStackedWidget {{ background: {bg}; border: none; border-radius: 10px; }}"
        )
        self.player_text.setStyleSheet(
            f"QTextEdit {{ background: {bg}; color: {text}; border: none; padding: 10px; border-radius: 10px; selection-background-color: #4e6488; selection-color: #ffffff; }}"
        )
        self.player_text.viewport().setStyleSheet(f"background: {bg}; border-radius: 10px;")
        self.player_text.setViewportMargins(0, 0, 0, 0)
        text_font = QtGui.QFont(family, max(12, size))
        self.player_text.setFont(text_font)
        self.player_text.document().setDefaultFont(text_font)
        self.player_seek.setStyleSheet(
            "QSlider::groove:horizontal {"
            "height: 8px; background: #242a33; border: 1px solid #3f4a5a; border-radius: 5px; }"
            "QSlider::sub-page:horizontal {"
            "background: #2CC985; border: 1px solid #2CC985; border-radius: 5px; }"
            "QSlider::add-page:horizontal {"
            "background: #242a33; border: 1px solid #3f4a5a; border-radius: 5px; }"
            "QSlider::handle:horizontal {"
            "background: #d7dde8; border: 1px solid #7a8799; width: 16px; margin: -5px 0; border-radius: 8px; }"
            "QSlider::handle:horizontal:hover { background: #ffffff; }"
        )

        self.player_rsvp.bg_color = QtGui.QColor(bg)
        self.player_rsvp.text_color = QtGui.QColor(text)
        self.player_rsvp.focus_color = QtGui.QColor(focus)
        self.player_rsvp.font_family = family
        self.player_rsvp.font_size = float(s.get("font_size", 150.0))
        self.player_rsvp.update()

        mode = str(s.get("reading_view_mode", "context")).strip().lower()
        if mode == "rsvp":
            self.player_view_stack.setCurrentWidget(self.player_rsvp)
        else:
            self.player_view_stack.setCurrentWidget(self.player_text)

        media_player = getattr(self, "media_player", None)
        if media_player is not None:
            try:
                media_player.setPlaybackRate(max(0.5, min(4.0, speed)))
            except Exception:
                pass

        new_speed = max(0.5, min(4.0, speed))
        if abs(new_speed - float(self._player_playback_speed or 1.0)) > 1e-6:
            current_pos = 0
            was_playing = False
            if self._audio_backend == "pygame" and pygame is not None and self._pygame_ready:
                current_pos = self._pygame_current_pos_ms()
                was_playing = bool(pygame.mixer.music.get_busy())
            elif self._audio_backend == "qt" and media_player is not None:
                current_pos = int(media_player.position())
                try:
                    was_playing = (
                        media_player.playbackState()
                        == QtMultimedia.QMediaPlayer.PlaybackState.PlayingState
                    )
                except Exception:
                    was_playing = False

            self._player_playback_speed = new_speed
            if self._player_source_audio is not None:
                self._player_playback_audio = self._resolve_playback_audio(
                    self._player_source_audio, self._player_playback_speed
                )
            if self._audio_backend == "pygame" and was_playing:
                self._play_pygame_from(current_pos)

    def open_player_settings(self):
        dlg = PlayerSettingsDialog(self._player_settings, self)
        if dlg.exec():
            self._player_settings.update(dlg.values())
            self._save_player_settings()
            self._apply_player_settings()
            self.log("Saved player settings.")

    def import_epub(self):
        if self._import_running:
            QtWidgets.QMessageBox.information(
                self,
                "Import Running",
                "An import is already running. Please wait for it to finish.",
            )
            return

        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select EPUB", "", "EPUB files (*.epub)"
        )
        if not path:
            return

        self._start_import(path, self.voice_combo.currentText())

    def _set_import_button_mode(self, importing: bool):
        self.import_btn.setText("Cancel Import" if importing else "Import EPUB")
        self.import_btn.setObjectName("ContinueButton" if importing else "ImportButton")
        # Re-polish so objectName style change is applied immediately.
        self.import_btn.style().unpolish(self.import_btn)
        self.import_btn.style().polish(self.import_btn)
        self.import_btn.update()

    def _on_import_button_clicked(self):
        if self._import_running:
            self.cancel_import()
        else:
            self.import_epub()

    def continue_import_book(self, book: dict):
        if self._import_running:
            QtWidgets.QMessageBox.information(
                self,
                "Import Running",
                "An import is already running. Please wait for it to finish.",
            )
            return
        stored_epub = (book.get("stored_epub_path") or "").strip()
        if not stored_epub:
            QtWidgets.QMessageBox.warning(
                self,
                "Stored EPUB Missing",
                "No stored EPUB was found for this book.",
            )
            return
        voice = book.get("voice", self.voice_combo.currentText() or "M3")
        self.log(f"--- Continuing Import: {book.get('title', 'Unknown')} ---")
        self._start_import(stored_epub, voice)

    def _start_import(self, epub_path: str, voice: str):
        self._import_running = True
        self._import_cancel_requested = False
        self._set_import_footer_visible(True)
        self._set_import_button_mode(True)
        self.refresh_btn.setEnabled(False)
        self.open_library_btn.setEnabled(False)
        self.log(f"--- Starting Import: {epub_path} ---")
        self.set_status(0.0, "Starting import...")

        worker = ImportWorker(epub_path, voice)
        self._active_import_worker = worker
        worker.signals.log.connect(self.log)
        worker.signals.progress.connect(self.set_status)
        worker.signals.done.connect(self._on_import_done)
        self.thread_pool.start(worker)

    def _on_import_done(self, ok: bool):
        self._import_running = False
        self._active_import_worker = None
        self._set_import_button_mode(False)
        self.import_btn.setEnabled(True)
        self.refresh_btn.setEnabled(True)
        self.open_library_btn.setEnabled(True)
        if self._import_cancel_requested:
            self.set_status(0.0, "Import canceled")
            self.log("--- Import Canceled ---")
            self._import_cancel_requested = False
        else:
            self.set_status(0.0, "Ready" if ok else "Import failed")
            self.log("--- Import Finished ---" if ok else "--- Import Failed ---")
        self.refresh_library()
        self._set_import_footer_visible(False)

    def cancel_import(self):
        if not self._import_running:
            return
        self._import_cancel_requested = True
        self.import_btn.setText("Canceling...")
        self.import_btn.setEnabled(False)
        self.status.setText("Cancel requested...")
        worker = self._active_import_worker
        if worker is not None:
            worker.cancel()

    def open_library_folder(self):
        library_path = Path("library").resolve()
        library_path.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(library_path)))

    def open_runtime_settings(self):
        dlg = RuntimeSettingsDialog(self)
        if dlg.exec():
            self.log("Saved runtime settings to cadence_settings.json.")
            self.log(
                "Note: running imports use new values immediately; existing loaded models may need restart."
            )
