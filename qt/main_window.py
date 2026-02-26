from __future__ import annotations

import bisect
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from qt.qt_compat import QtCore, QtGui, QtMultimedia, QtWidgets, Signal, Slot

from system.book_manager import BookManager
from system.runtime_settings import DEFAULTS, apply_settings_to_environ, load_settings, save_settings
from qt.styles import (
    STYLE_PROFILES,
    build_qss,
    color_swatch_style,
    horizontal_divider_style,
    player_panel_style,
    player_seek_style,
    player_text_style,
    player_text_viewport_style,
    player_view_stack_style,
    transparent_bg_style,
    vertical_divider_style,
)

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
        ready_last = int(self.book.get("last_chapter", 0) or 0)
        resume_last = int(self.book.get("resume_chapter", 0) or 0)
        incomplete = bool(self.book.get("is_incomplete", False))

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        title = HoverMarqueeLabel(self.book.get("title", "Unknown"))
        title.setObjectName("BookTitle")
        outer.addWidget(title)

        if resume_last > 0:
            meta_text = (
                f"Read Ch {resume_last}/{total}  •  Ready Ch {ready_last}/{total}  •  "
                f"Voice: {self.book.get('voice', '?')}"
            )
        else:
            meta_text = f"Ready Ch {ready_last}/{total}  •  Voice: {self.book.get('voice', '?')}"
        meta = QtWidgets.QLabel(meta_text)
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


class HoverMarqueeLabel(QtWidgets.QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self._scroll_offset = 0.0
        self._hovering = False
        self._anim_group = None
        # Horizontal "Ignored" prevents long text from forcing parent/card width.
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setMinimumHeight(24)
        self.setMaximumHeight(24)
        self.setWordWrap(False)

    def setText(self, text: str):
        super().setText(text)
        self._reset_animation()
        self.update()

    def enterEvent(self, event):
        self._hovering = True
        self._start_animation_if_needed()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovering = False
        self._reset_animation()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        self._reset_animation()
        super().resizeEvent(event)

    def _overflow_px(self) -> int:
        avail = max(0, self.contentsRect().width() - 2)
        text_w = self.fontMetrics().horizontalAdvance(self.text() or "")
        return max(0, text_w - avail)

    def _reset_animation(self):
        if self._anim_group is not None:
            try:
                self._anim_group.stop()
            except Exception:
                pass
        self._anim_group = None
        self._scroll_offset = 0.0
        self.update()

    def _start_animation_if_needed(self):
        if not self._hovering:
            return
        overflow = self._overflow_px()
        if overflow <= 0:
            return
        if self._anim_group is not None:
            return
        group = QtCore.QSequentialAnimationGroup(self)
        group.addPause(250)

        # Constant-speed marquee (no ease-in acceleration).
        px_per_sec = 95.0
        fwd_ms = max(600, int((overflow / px_per_sec) * 1000.0))
        fwd = QtCore.QVariantAnimation(self)
        fwd.setStartValue(0.0)
        fwd.setEndValue(float(overflow))
        fwd.setDuration(fwd_ms)
        fwd.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        fwd.valueChanged.connect(self._on_anim_value)
        group.addAnimation(fwd)

        group.addPause(300)

        back_ms = max(500, int((overflow / (px_per_sec * 1.15)) * 1000.0))
        back = QtCore.QVariantAnimation(self)
        back.setStartValue(float(overflow))
        back.setEndValue(0.0)
        back.setDuration(back_ms)
        back.setEasingCurve(QtCore.QEasingCurve.Type.Linear)
        back.valueChanged.connect(self._on_anim_value)
        group.addAnimation(back)
        group.setLoopCount(-1)
        self._anim_group = group
        group.start()

    def _on_anim_value(self, value):
        self._scroll_offset = float(value)
        self.update()

    def paintEvent(self, _event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing, True)
        painter.setPen(self.palette().color(QtGui.QPalette.ColorRole.WindowText))
        r = self.contentsRect().adjusted(1, 0, -1, 0)
        text = self.text() or ""

        if self._hovering and self._overflow_px() > 0:
            painter.setClipRect(r)
            x = r.x() - int(round(self._scroll_offset))
            y = r.y()
            painter.drawText(
                QtCore.QRect(x, y, max(r.width() + int(self._scroll_offset) + 20, r.width()), r.height()),
                QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter,
                text,
            )
            return

        elided = self.fontMetrics().elidedText(text, QtCore.Qt.TextElideMode.ElideRight, r.width())
        painter.drawText(r, QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, elided)

    def minimumSizeHint(self):
        h = max(24, self.fontMetrics().height() + 8)
        return QtCore.QSize(0, h)

    def sizeHint(self):
        h = max(24, self.fontMetrics().height() + 8)
        # Keep width flexible so container decides; avoid full-text width pressure.
        return QtCore.QSize(10, h)


class RuntimeSettingsDialog(QtWidgets.QDialog):
    profile_preview = Signal(str)

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
        scroll.setObjectName("RuntimeSettingsScroll")
        scroll.setWidgetResizable(True)
        wrap = QtWidgets.QWidget()
        wrap.setObjectName("RuntimeSettingsWrap")
        form_layout = QtWidgets.QVBoxLayout(wrap)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(8)

        settings = load_settings()
        select_options = {
            "CADENCE_STYLE_PROFILE": sorted(STYLE_PROFILES.keys()),
            "CADENCE_FORCE_CPU": ["0", "1"],
            "CADENCE_USE_TENSORRT": ["0", "1"],
            "CADENCE_CUDA_ONLY": ["1", "0"],
            "CADENCE_SUPPRESS_ORT_WARNINGS": ["1", "0"],
            "CADENCE_ADD_SYSTEM_CUDA_DLL_PATH": ["0", "1"],
            "CADENCE_WHISPERX_MODEL": [
                "small",
                "base",
                "medium",
                "tiny",
                "large-v3",
                "large-v2",
            ],
            "CADENCE_WHISPERX_COMPUTE_TYPE": [
                "float16",
                "int8",
                "int8_float16",
                "float32",
            ],
            "CADENCE_WHISPERX_DEVICE": ["auto", "cuda", "cpu"],
        }
        editable_combo_options = {
            "CADENCE_EXTRACT_WORKERS": ["1", "2", "4", "6", "8"],
            "CADENCE_SYNTH_WORKERS": ["1", "2", "3", "4"],
            "CADENCE_TTS_MAX_CHARS": ["500", "800", "1000", "1200", "1600", "2000"],
            "CADENCE_ORT_LOG_LEVEL": ["0", "1", "2", "3", "4"],
            "CADENCE_WHISPERX_BATCH_SIZE": ["4", "8", "16", "24", "32"],
        }

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

            if key in select_options:
                entry = QtWidgets.QComboBox()
                entry.addItems(select_options[key])
                current = str(settings.get(key, DEFAULTS.get(key, ""))).strip()
                if key == "CADENCE_STYLE_PROFILE":
                    current = current.lower()
                if current not in select_options[key]:
                    current = str(DEFAULTS.get(key, "")).strip()
                entry.setCurrentText(current)
                if key == "CADENCE_STYLE_PROFILE":
                    entry.currentTextChanged.connect(self._on_profile_changed)
            elif key in editable_combo_options:
                entry = QtWidgets.QComboBox()
                entry.setEditable(True)
                entry.addItems(editable_combo_options[key])
                current = str(settings.get(key, DEFAULTS.get(key, ""))).strip()
                entry.setCurrentText(current)
            else:
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
            value = str(self._defaults.get(key, ""))
            if isinstance(w, QtWidgets.QComboBox):
                w.setCurrentText(value)
            elif isinstance(w, QtWidgets.QLineEdit):
                w.setText(value)

    def _apply(self):
        updated = {}
        for k, w in self._vars.items():
            if isinstance(w, QtWidgets.QComboBox):
                updated[k] = w.currentText().strip()
            elif isinstance(w, QtWidgets.QLineEdit):
                updated[k] = w.text().strip()
            else:
                updated[k] = ""
        save_settings(updated)
        apply_settings_to_environ(updated, override=True)
        self.accept()

    def _on_profile_changed(self, value: str):
        profile = (value or "").strip().lower() or "cadence"
        if profile not in STYLE_PROFILES:
            profile = "cadence"
        self.profile_preview.emit(profile)


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
    "book_positions": {},
    "book_positions_ms": {},
}


class PlayerSettingsDialog(QtWidgets.QDialog):
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Player Settings")
        self.resize(640, 560)
        self._settings = dict(settings)
        self._style_profile = str(getattr(parent, "_style_profile", "cadence")).strip().lower() or "cadence"
        if self._style_profile not in STYLE_PROFILES:
            self._style_profile = "cadence"
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
        card.setObjectName("PlayerSettingsCard")
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
            swatch.setStyleSheet(color_swatch_style("#000000", border=self._swatch_border_color()))
            r.addWidget(swatch, 0)
            self._color_swatches[edit] = swatch
            pick = QtWidgets.QPushButton("Pick")
            pick.clicked.connect(lambda _=False, e=edit: self._pick_color(e))
            r.addWidget(pick, 0)
            edit.textChanged.connect(lambda _t, e=edit: self._update_color_preview(e))
            wrap = QtWidgets.QWidget()
            wrap.setStyleSheet(transparent_bg_style())
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
        default_hex = self._default_for_color_edit(target)
        original = self._normalized_hex(target.text(), default_hex)
        initial = QtGui.QColor(original)
        dlg = QtWidgets.QColorDialog(initial, self)
        dlg.setOption(QtWidgets.QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setOption(QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel, False)

        def on_live(color: QtGui.QColor):
            if not color.isValid():
                return
            self._set_edit_color(target, color)

        dlg.currentColorChanged.connect(on_live)
        if dlg.exec():
            c = dlg.currentColor()
            if c.isValid():
                self._set_edit_color(target, c)
        else:
            target.setText(original)
            self._update_color_preview(target)

    def _update_color_preview(self, edit: QtWidgets.QLineEdit):
        swatch = self._color_swatches.get(edit)
        if swatch is None:
            return
        raw = (edit.text() or "").strip()
        color = QtGui.QColor(raw)
        if not color.isValid():
            color = QtGui.QColor("#000000")
        self._update_color_preview_from_color(edit, color)

    def _swatch_border_color(self) -> str:
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        return str(profile.get("border_panel", "#3f4a5a"))

    def _default_for_color_edit(self, edit: QtWidgets.QLineEdit) -> str:
        if edit is self.bg_color:
            return "#121212"
        if edit is self.text_color:
            return "#E0E0E0"
        if edit is self.focus_color:
            return "#FFD700"
        return "#000000"

    def _set_edit_color(self, edit: QtWidgets.QLineEdit, color: QtGui.QColor):
        if not color.isValid():
            return
        hex_color = color.name(QtGui.QColor.NameFormat.HexRgb).upper()
        prev = edit.blockSignals(True)
        edit.setText(hex_color)
        edit.blockSignals(prev)
        self._update_color_preview_from_color(edit, color)

    def _update_color_preview_from_color(self, edit: QtWidgets.QLineEdit, color: QtGui.QColor):
        swatch = self._color_swatches.get(edit)
        if swatch is None:
            return
        c = color if color.isValid() else QtGui.QColor("#000000")
        swatch.setStyleSheet(
            color_swatch_style(c.name(QtGui.QColor.NameFormat.HexRgb).upper(), border=self._swatch_border_color())
        )

    def _normalized_hex(self, raw: str, default_hex: str) -> str:
        c = QtGui.QColor((raw or "").strip())
        if not c.isValid():
            c = QtGui.QColor(default_hex)
        if not c.isValid():
            c = QtGui.QColor("#000000")
        return c.name(QtGui.QColor.NameFormat.HexRgb).upper()

    def _build_slider_with_clamps(self, min_value: float, max_value: float, step: float, decimals: int):
        container = QtWidgets.QWidget()
        container.setStyleSheet(transparent_bg_style())
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
        self.bg_color.setText(self._normalized_hex(str(s.get("bg_color", "#121212")), "#121212"))
        self.text_color.setText(self._normalized_hex(str(s.get("text_color", "#E0E0E0")), "#E0E0E0"))
        self.focus_color.setText(self._normalized_hex(str(s.get("focus_color", "#FFD700")), "#FFD700"))
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
            "bg_color": self._normalized_hex(self.bg_color.text(), "#121212"),
            "text_color": self._normalized_hex(self.text_color.text(), "#E0E0E0"),
            "focus_color": self._normalized_hex(self.focus_color.text(), "#FFD700"),
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
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)

    def set_words(self, focus: str, secondary: str = ""):
        self.word = focus or ""
        _ = secondary
        self.update()

    def paintEvent(self, event):
        _ = event
        painter = QtGui.QPainter(self)
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


class CadenceMarkWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 42)
        self._logo_path = Path("assets/branding/cadence-logo.svg")
        self._pixmap = QtGui.QPixmap()
        self._load_logo()

    def set_theme_colors(self, accent: str, muted: str):
        _ = accent
        _ = muted
        self._load_logo()
        self.update()

    def _load_logo(self):
        if not self._logo_path.exists():
            self._pixmap = QtGui.QPixmap()
            return
        pix = QtGui.QPixmap(str(self._logo_path))
        if pix.isNull():
            pix = QtGui.QIcon(str(self._logo_path)).pixmap(42, 42)
        self._pixmap = pix

    def paintEvent(self, _event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        if self._pixmap.isNull():
            return
        target = self.rect().adjusted(1, 1, -1, -1)
        scaled = self._pixmap.scaled(
            target.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        x = target.x() + (target.width() - scaled.width()) // 2
        y = target.y() + (target.height() - scaled.height()) // 2
        p.drawPixmap(x, y, scaled)


class CadenceHeaderWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CadenceHeader")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 2)
        layout.setSpacing(10)

        self.mark = CadenceMarkWidget(self)
        layout.addWidget(self.mark, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.title = QtWidgets.QLabel("Cadence")
        self.title.setObjectName("CadenceHeaderTitle")
        self.subtitle = QtWidgets.QLabel("Immersive reading")
        self.subtitle.setObjectName("CadenceHeaderSubtitle")
        right.addWidget(self.title, 0)
        right.addWidget(self.subtitle, 0)
        layout.addLayout(right, 1)

    def set_theme(self, profile: dict):
        accent = str(profile.get("accent", "#2CC985"))
        text_main = str(profile.get("text_main", "#e6ebf2"))
        text_muted = str(profile.get("text_muted", "#aeb7c3"))
        self.mark.set_theme_colors(accent, text_muted)
        self.title.setStyleSheet(f"color: {text_main}; font-size: 22px; font-weight: 700;")
        self.subtitle.setStyleSheet(f"color: {text_muted}; font-size: 12px; font-weight: 600;")


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, debug: bool = False):
        super().__init__()
        self.debug = debug
        self.setWindowTitle("Cadence")
        logo_ico_path = Path("assets/branding/cadence-logo.ico")
        logo_svg_path = Path("assets/branding/cadence-logo.svg")
        if logo_ico_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(logo_ico_path)))
        elif logo_svg_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(logo_svg_path)))
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1180, 760)
        runtime = load_settings()
        self._style_profile = str(runtime.get("CADENCE_STYLE_PROFILE", "cadence")).strip().lower() or "cadence"
        if self._style_profile not in STYLE_PROFILES:
            self._style_profile = "cadence"
        self.setStyleSheet(build_qss(self._style_profile))
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
        self._player_active_stem = ""
        self._last_resume_save_t = 0.0
        self._last_resume_saved_pos_ms = -1
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
        self._player_sidebar_width_anim = None
        self._player_view_fade_anim = None
        self._button_shadow_effects = {}
        self._button_shadow_values = {}
        self._button_shadow_animations = {}

        self._build_ui()
        self._apply_profile_card_shadows()
        self._apply_profile_button_depths()
        self._apply_profile_header_theme()
        self._apply_player_settings()
        self._init_media_player()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.refresh_library()

    def eventFilter(self, obj, event):
        if self._handle_window_resize_event(obj, event):
            return True

        title_drag_widgets = getattr(self, "_title_drag_widgets", set())
        if obj in title_drag_widgets:
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
        if self._handle_button_depth_event(obj, event):
            return False
        return super().eventFilter(obj, event)

    def _handle_button_depth_event(self, obj, event) -> bool:
        if not isinstance(obj, QtWidgets.QPushButton):
            return False
        if obj not in self._button_shadow_effects:
            return False
        et = event.type()
        if et == QtCore.QEvent.Type.Enter:
            self._animate_button_shadow_state(obj, "hover")
        elif et == QtCore.QEvent.Type.Leave:
            self._animate_button_shadow_state(obj, "rest")
        elif et == QtCore.QEvent.Type.MouseButtonPress:
            if getattr(event, "button", lambda: None)() == QtCore.Qt.MouseButton.LeftButton:
                self._animate_button_shadow_state(obj, "pressed")
        elif et == QtCore.QEvent.Type.MouseButtonRelease:
            self._animate_button_shadow_state(obj, "hover" if obj.underMouse() else "rest")
        return False

    def _button_shadow_state_values(self, state: str) -> tuple[float, float, int]:
        # blur, y_offset, alpha
        if state == "hover":
            return (20.0, 1.0, 86)
        if state == "pressed":
            return (8.0, 0.0, 52)
        return (14.0, 2.0, 68)

    def _register_button_depth(self, button: QtWidgets.QPushButton):
        if button is None:
            return
        name = button.objectName() or ""
        if name in {"TitleBarButton", "TitleBarMaxButton", "TitleBarCloseButton"}:
            return
        if button in self._button_shadow_effects:
            return
        button.installEventFilter(self)
        effect = QtWidgets.QGraphicsDropShadowEffect(button)
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        c = QtGui.QColor(str(profile.get("shadow_color", "#000000")))
        blur, off_y, alpha = self._button_shadow_state_values("rest")
        c.setAlpha(alpha)
        effect.setColor(c)
        effect.setBlurRadius(blur)
        effect.setOffset(0.0, off_y)
        button.setGraphicsEffect(effect)
        self._button_shadow_effects[button] = effect
        self._button_shadow_values[button] = (blur, off_y, alpha)
        try:
            button.destroyed.connect(lambda *_args, b=button: self._cleanup_button_depth(b))
        except Exception:
            pass

    def _cleanup_button_depth(self, button: QtWidgets.QPushButton):
        self._button_shadow_effects.pop(button, None)
        self._button_shadow_values.pop(button, None)
        anim = self._button_shadow_animations.pop(button, None)
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass

    def _animate_button_shadow_state(self, button: QtWidgets.QPushButton, state: str):
        effect = self._button_shadow_effects.get(button)
        if effect is None:
            return
        start_blur, start_off, start_alpha = self._button_shadow_values.get(button, self._button_shadow_state_values("rest"))
        end_blur, end_off, end_alpha = self._button_shadow_state_values(state)
        anim = self._button_shadow_animations.get(button)
        if anim is not None:
            anim.stop()
        anim = QtCore.QVariantAnimation(button)
        if state == "pressed":
            anim.setDuration(90)
            anim.setEasingCurve(QtCore.QEasingCurve.Type.OutQuad)
        elif state == "hover":
            anim.setDuration(160)
            anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        else:
            anim.setDuration(140)
            anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        base_color = QtGui.QColor(str(profile.get("shadow_color", "#000000")))

        def on_value(v):
            t = float(v)
            blur = start_blur + (end_blur - start_blur) * t
            off = start_off + (end_off - start_off) * t
            alpha = int(round(start_alpha + (end_alpha - start_alpha) * t))
            color = QtGui.QColor(base_color)
            color.setAlpha(max(0, min(255, alpha)))
            try:
                effect.setColor(color)
                effect.setBlurRadius(blur)
                effect.setOffset(0.0, off)
            except RuntimeError:
                self._cleanup_button_depth(button)
                try:
                    anim.stop()
                except Exception:
                    pass

        def on_done():
            self._button_shadow_values[button] = (end_blur, end_off, end_alpha)

        anim.valueChanged.connect(on_value)
        anim.finished.connect(on_done)
        self._button_shadow_animations[button] = anim
        anim.start()

    def _apply_profile_button_depths(self):
        for button in self.findChildren(QtWidgets.QPushButton):
            self._register_button_depth(button)
        # Refresh existing effects with current profile shadow color.
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        stale = []
        for button, effect in list(self._button_shadow_effects.items()):
            if button is None:
                stale.append(button)
                continue
            blur, off_y, alpha = self._button_shadow_values.get(button, self._button_shadow_state_values("rest"))
            color = QtGui.QColor(str(profile.get("shadow_color", "#000000")))
            color.setAlpha(alpha)
            try:
                effect.setColor(color)
                effect.setBlurRadius(blur)
                effect.setOffset(0.0, off_y)
            except RuntimeError:
                stale.append(button)
        for button in stale:
            self._cleanup_button_depth(button)

    def _fade_switch_player_view(self, target_widget: QtWidgets.QWidget):
        if not hasattr(self, "player_view_stack") or self.player_view_stack is None:
            return
        current = self.player_view_stack.currentWidget()
        if current is target_widget:
            return
        # Do a hard switch to avoid making the whole stack transparent.
        # Fading the full stack can expose the desktop through our translucent shell.
        if self._player_view_fade_anim is not None:
            try:
                self._player_view_fade_anim.stop()
            except Exception:
                pass
            self._player_view_fade_anim = None
        effect = self.player_view_stack.graphicsEffect()
        if isinstance(effect, QtWidgets.QGraphicsOpacityEffect):
            try:
                effect.setOpacity(1.0)
            except Exception:
                pass
            self.player_view_stack.setGraphicsEffect(None)
        self.player_view_stack.setCurrentWidget(target_widget)
        self.player_view_stack.update()

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
        t.setSpacing(8)

        logo_label = QtWidgets.QLabel("")
        logo_label.setObjectName("WindowLogo")
        logo_label.setFixedSize(23, 23)
        logo_path = Path("assets/branding/cadence-logo.svg")
        if logo_path.exists():
            pix = QtGui.QPixmap(str(logo_path))
            if pix.isNull():
                pix = QtGui.QIcon(str(logo_path)).pixmap(21, 21)
            if not pix.isNull():
                logo_label.setPixmap(
                    pix.scaled(
                        21,
                        21,
                        QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                        QtCore.Qt.TransformationMode.SmoothTransformation,
                    )
                )
        t.addWidget(logo_label, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

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
        self._title_drag_widgets = {title_bar, title_label, logo_label}
        title_bar.installEventFilter(self)
        title_label.installEventFilter(self)
        logo_label.installEventFilter(self)

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
        self._apply_profile_divider_styles()
        self._apply_profile_header_theme()
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
        divider_widget = None
        if hasattr(self, "view_stack") and self.view_stack.currentWidget() is self.player_page:
            divider_widget = getattr(self, "player_content_divider", None)
        else:
            divider_widget = getattr(self, "library_content_divider", None)

        if divider_widget is not None and divider_widget.isVisible():
            divider_global = divider_widget.mapToGlobal(QtCore.QPoint(0, 0))
            local = self.bottom_corner_cap.mapFromGlobal(divider_global)
            x = int(local.x())
        else:
            if hasattr(self, "view_stack") and self.view_stack.currentWidget() is self.player_page:
                x = int(self.player_left_sidebar.width()) if hasattr(self, "player_left_sidebar") else int(self._player_sidebar_width)
            else:
                x = int(self._library_sidebar_width)
        h = max(1, int(self.bottom_corner_cap.height()))
        self.bottom_cap_divider.setGeometry(x, 0, 1, h)
        self.bottom_cap_divider.setVisible(True)

    def _apply_profile_divider_styles(self):
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        color = str(profile.get("border_panel", "#3f4a5a"))
        v_style = vertical_divider_style(color)
        h_style = horizontal_divider_style(color)
        for attr_name in ("library_content_divider", "player_content_divider", "bottom_cap_divider"):
            widget = getattr(self, attr_name, None)
            if widget is not None:
                widget.setStyleSheet(v_style)
        for attr_name in ("import_footer_div", "player_top_divider"):
            widget = getattr(self, attr_name, None)
            if widget is not None:
                widget.setStyleSheet(h_style)

    def _apply_profile_header_theme(self):
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        if hasattr(self, "library_header") and self.library_header is not None:
            self.library_header.set_theme(profile)

    def _apply_shadow_effect(
        self,
        widget: QtWidgets.QWidget | None,
        *,
        color: str,
        alpha: int,
        blur: int,
        off_x: int,
        off_y: int,
    ):
        if widget is None:
            return
        effect = QtWidgets.QGraphicsDropShadowEffect(widget)
        qcolor = QtGui.QColor(color)
        qcolor.setAlpha(max(0, min(255, int(alpha))))
        effect.setColor(qcolor)
        effect.setBlurRadius(float(max(0, blur)))
        effect.setOffset(float(off_x), float(off_y))
        widget.setGraphicsEffect(effect)

    def _apply_profile_card_shadows(self):
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        color = str(profile.get("shadow_color", "#000000"))
        alpha = int(profile.get("shadow_alpha", 78))
        blur = int(profile.get("shadow_blur", 24))
        off_x = int(profile.get("shadow_offset_x", 0))
        off_y = int(profile.get("shadow_offset_y", 3))

        for attr_name in (
            "controls_card",
            "log_card",
            "list_shell",
            "player_chapter_panel",
            "player_reader_panel",
        ):
            self._apply_shadow_effect(
                getattr(self, attr_name, None),
                color=color,
                alpha=alpha,
                blur=blur,
                off_x=off_x,
                off_y=off_y,
            )

    def _animate_player_sidebar_width(self, target_width: int, duration_ms: int = 180):
        if not hasattr(self, "player_left_sidebar") or self.player_left_sidebar is None:
            return
        target = int(target_width)
        current = int(self.player_left_sidebar.width() or target)
        if current == target:
            self.player_left_sidebar.setFixedWidth(target)
            return
        if self._player_sidebar_width_anim is not None:
            try:
                self._player_sidebar_width_anim.stop()
            except Exception:
                pass
        anim = QtCore.QVariantAnimation(self.player_left_sidebar)
        anim.setStartValue(current)
        anim.setEndValue(target)
        anim.setDuration(max(80, int(duration_ms)))
        anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)

        def on_value(v):
            w = max(1, int(float(v)))
            self.player_left_sidebar.setFixedWidth(w)
            self._layout_bottom_cap_divider()

        def on_done():
            self.player_left_sidebar.setFixedWidth(target)
            self._layout_bottom_cap_divider()

        anim.valueChanged.connect(on_value)
        anim.finished.connect(on_done)
        self._player_sidebar_width_anim = anim
        anim.start()

    def _set_player_chapters_panel_collapsed(self, collapsed: bool, animate: bool = True):
        self._player_chapters_collapsed = bool(collapsed)
        if hasattr(self, "player_left_sidebar"):
            target_w = int(self._player_sidebar_collapsed_width if self._player_chapters_collapsed else self._player_sidebar_width)
            if animate:
                self._animate_player_sidebar_width(target_w, duration_ms=180)
            else:
                self.player_left_sidebar.setFixedWidth(target_w)
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
        self._set_player_chapters_panel_collapsed(not self._player_chapters_collapsed, animate=True)

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

        self.library_header = CadenceHeaderWidget()
        side.addWidget(self.library_header, 0)

        controls_card = QtWidgets.QFrame()
        controls_card.setObjectName("ControlsCard")
        self.controls_card = controls_card
        controls_layout = QtWidgets.QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(12, 12, 12, 12)
        controls_layout.setSpacing(8)

        import_row = QtWidgets.QHBoxLayout()
        self.import_btn = QtWidgets.QPushButton("Import Book")
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
        self.log_card = log_card
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
        self.library_content_divider = divider

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
        self.search.setPlaceholderText("Search title, author, or voice...")
        self.search.textChanged.connect(self.refresh_library)
        m.addWidget(self.search)

        filter_row = QtWidgets.QHBoxLayout()
        filter_lbl = QtWidgets.QLabel("Filter")
        filter_lbl.setObjectName("SectionLabel")
        filter_row.addWidget(filter_lbl, 0)
        self.library_filter = QtWidgets.QComboBox()
        self.library_filter.addItems(["All", "Incomplete", "Complete"])
        self.library_filter.currentTextChanged.connect(self.refresh_library)
        filter_row.addWidget(self.library_filter, 0)
        filter_row.addStretch(1)
        m.addLayout(filter_row)

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
        self.player_top_divider = d2
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
        self.player_text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
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
        self._set_player_chapters_panel_collapsed(False, animate=False)
        self._apply_profile_divider_styles()

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
        positions = self._player_settings.get("book_positions", {})
        if isinstance(positions, dict):
            for book in books:
                key = self._book_resume_key(book)
                if not key:
                    continue
                try:
                    resume_chapter = int(positions.get(key, 0) or 0)
                except Exception:
                    resume_chapter = 0
                if resume_chapter > 0:
                    book["resume_chapter"] = resume_chapter
        q = self.search.text().strip().lower()
        if q:
            books = [
                b
                for b in books
                if q in str(b.get("title", "")).lower()
                or q in str(b.get("author", "")).lower()
                or q in str(b.get("voice", "")).lower()
            ]
        selected_filter = self.library_filter.currentText().strip().lower()
        if selected_filter == "incomplete":
            books = [b for b in books if bool(b.get("is_incomplete", False))]
        elif selected_filter == "complete":
            books = [b for b in books if not bool(b.get("is_incomplete", False))]
        books.sort(key=lambda b: (not b.get("is_incomplete", False), b.get("title", "").lower()))

        self._clear_book_cards()

        if not books:
            lbl = QtWidgets.QLabel("No matching books." if q else "No books found. Import a book to start.")
            lbl.setObjectName("BookMeta")
            self.books_layout.addWidget(lbl)
            self.books_layout.addStretch(1)
            return

        for book in books:
            card = BookCard(book)
            card.read_requested.connect(self.open_player_page)
            card.continue_requested.connect(self.continue_import_book)
            profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
            self._apply_shadow_effect(
                card,
                color=str(profile.get("shadow_color", "#000000")),
                alpha=int(profile.get("shadow_alpha", 78)),
                blur=max(8, int(profile.get("shadow_blur", 24) * 0.65)),
                off_x=int(profile.get("shadow_offset_x", 0)),
                off_y=max(1, int(profile.get("shadow_offset_y", 3))),
            )
            self.books_layout.addWidget(card)
        self.books_layout.addStretch(1)
        self._apply_profile_button_depths()

    def show_library_page(self):
        self._pause_all_audio()
        self.player_play_btn.setText("Play")
        self.view_stack.setCurrentWidget(self.library_page)
        self._layout_bottom_cap_divider()
        self.refresh_library()

    def open_player_page(self, book: dict):
        self._persist_current_chapter_position(force=True)
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
            target_row = self._resolve_resume_row(book, len(txt_files))
            self.player_chapter_list.setCurrentRow(target_row)
            self.player_chapter_meta.setText(f"Chapter {target_row + 1}/{len(txt_files)}")
        else:
            self.player_chapter_meta.setText("Chapter -/-")
            self.player_text.setPlainText("No chapter text found for this book.")

        self.view_stack.setCurrentWidget(self.player_page)
        self._layout_bottom_cap_divider()
        QtCore.QTimer.singleShot(0, self._refresh_player_title_elide)
        QtCore.QTimer.singleShot(25, self._refresh_player_title_elide)

    def _book_resume_key(self, book: dict):
        raw = str((book or {}).get("path", "")).strip()
        if not raw:
            return ""
        try:
            return str(Path(raw).resolve())
        except Exception:
            return raw

    def _resolve_resume_row(self, book: dict, chapter_count: int):
        if chapter_count <= 0:
            return 0

        settings_chapter = 0
        key = self._book_resume_key(book)
        positions = self._player_settings.get("book_positions", {})
        if isinstance(positions, dict) and key:
            try:
                settings_chapter = int(positions.get(key, 0) or 0)
            except Exception:
                settings_chapter = 0

        metadata_chapter = 0
        try:
            metadata_chapter = int((book or {}).get("last_chapter", 0) or 0)
        except Exception:
            metadata_chapter = 0

        chosen = settings_chapter if settings_chapter > 0 else metadata_chapter
        if 1 <= chosen <= chapter_count:
            return chosen - 1
        return 0

    def _save_book_resume_chapter(self, chapter_num: int):
        if not self._active_book:
            return
        key = self._book_resume_key(self._active_book)
        if not key:
            return
        chapter_num = int(max(1, chapter_num))
        positions = self._player_settings.get("book_positions")
        if not isinstance(positions, dict):
            positions = {}
        if int(positions.get(key, 0) or 0) == chapter_num:
            return
        positions[key] = chapter_num
        self._player_settings["book_positions"] = positions
        self._save_player_settings()

    def _get_book_resume_position_ms(self, book: dict, stem: str):
        key = self._book_resume_key(book)
        if not key or not stem:
            return 0
        positions = self._player_settings.get("book_positions_ms", {})
        if not isinstance(positions, dict):
            return 0
        chapter_positions = positions.get(key, {})
        if not isinstance(chapter_positions, dict):
            return 0
        try:
            value = int(chapter_positions.get(stem, 0) or 0)
        except Exception:
            return 0
        return max(0, value)

    def _save_book_resume_position_ms(self, stem: str, pos_ms: int, force: bool = False):
        if not self._active_book or not stem:
            return
        key = self._book_resume_key(self._active_book)
        if not key:
            return
        pos_ms = int(max(0, pos_ms))
        now = time.monotonic()
        if not force and self._last_resume_saved_pos_ms >= 0:
            if abs(pos_ms - self._last_resume_saved_pos_ms) < 1000 and (now - self._last_resume_save_t) < 1.0:
                return

        positions = self._player_settings.get("book_positions_ms")
        if not isinstance(positions, dict):
            positions = {}
        chapter_positions = positions.get(key)
        if not isinstance(chapter_positions, dict):
            chapter_positions = {}
        if not force and int(chapter_positions.get(stem, 0) or 0) == pos_ms:
            return
        chapter_positions[stem] = pos_ms
        positions[key] = chapter_positions
        self._player_settings["book_positions_ms"] = positions
        self._last_resume_save_t = now
        self._last_resume_saved_pos_ms = pos_ms
        self._save_player_settings()

    def _current_playback_pos_ms(self):
        if self._audio_backend == "pygame":
            return int(max(0, self._pygame_current_pos_ms()))
        if self.media_player is not None:
            try:
                return int(max(0, self.media_player.position()))
            except Exception:
                pass
        return int(max(0, self._qt_last_pos_ms))

    def _persist_current_chapter_position(self, force: bool = False):
        stem = str(getattr(self, "_player_active_stem", "") or "").strip()
        if not stem:
            return
        pos_ms = self._current_playback_pos_ms()
        self._save_book_resume_position_ms(stem, pos_ms, force=force)

    def _restore_chapter_position(self, stem: str):
        if not stem:
            return
        target = self._get_book_resume_position_ms(self._active_book, stem)
        if target <= 0:
            return
        target = int(max(0, min(max(1, self._player_duration_ms), target)))
        if self._audio_backend == "pygame":
            self._pygame_pos_offset_ms = target
            self._pygame_last_pos_ms = target
        elif self.media_player is not None:
            try:
                self.media_player.setPosition(target)
            except Exception:
                pass
            self._qt_last_pos_ms = target
        slider_value = int((float(target) / float(max(1, self._player_duration_ms))) * 1000.0)
        self.player_progress.setValue(slider_value)
        self.player_seek.setValue(slider_value)
        self._update_time_labels(target, self._player_duration_ms)
        self._update_word_highlight(float(target) / 1000.0 + float(self._player_settings.get("sync_offset", 0.0)))

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
        self._persist_current_chapter_position(force=True)
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
        self._save_book_resume_chapter(row + 1)
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
            self._player_active_stem = str(stem)
            self._restore_chapter_position(self._player_active_stem)
        else:
            self._player_active_stem = str(stem)
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
        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        ready_fg = QtGui.QColor(str(profile.get("text_main", "#e6ebf2")))
        bg_shell = QtGui.QColor(str(profile.get("bg_shell", "#242a33")))
        light_theme = bg_shell.isValid() and (
            (0.299 * bg_shell.red()) + (0.587 * bg_shell.green()) + (0.114 * bg_shell.blue()) >= 145
        )
        if light_theme:
            warn_fg = QtGui.QColor("#7a5a00")
            warn_bg = QtGui.QColor("#fff0c2")
            err_fg = QtGui.QColor("#8b1f1f")
            err_bg = QtGui.QColor("#ffdada")
        else:
            warn_fg = QtGui.QColor("#f0d27a")
            warn_bg = QtGui.QColor("#4a3f22")
            err_fg = QtGui.QColor("#f3b0b0")
            err_bg = QtGui.QColor("#4a2a2a")
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
                item.setForeground(QtGui.QBrush(ready_fg))
                item.setBackground(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))
            elif has_audio and not has_align:
                item.setForeground(QtGui.QBrush(warn_fg))
                item.setBackground(QtGui.QBrush(warn_bg))
            else:
                item.setForeground(QtGui.QBrush(err_fg))
                item.setBackground(QtGui.QBrush(err_bg))

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
        self._persist_current_chapter_position(force=True)

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
        self._persist_current_chapter_position(force=False)

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
        self._persist_current_chapter_position(force=True)

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
        self._persist_current_chapter_position(force=True)
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
        self._persist_current_chapter_position(force=False)

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
        positions = data.get("book_positions")
        if not isinstance(positions, dict):
            data["book_positions"] = {}
        else:
            normalized = {}
            for key, value in positions.items():
                try:
                    chapter_num = int(value)
                except Exception:
                    continue
                if chapter_num < 1:
                    continue
                normalized[str(key)] = chapter_num
            data["book_positions"] = normalized
        pos_ms = data.get("book_positions_ms")
        if not isinstance(pos_ms, dict):
            data["book_positions_ms"] = {}
        else:
            normalized_ms = {}
            for key, value in pos_ms.items():
                if not isinstance(value, dict):
                    continue
                row = {}
                for stem, ms in value.items():
                    try:
                        v = int(ms)
                    except Exception:
                        continue
                    if v < 0:
                        continue
                    row[str(stem)] = v
                if row:
                    normalized_ms[str(key)] = row
            data["book_positions_ms"] = normalized_ms
        return data

    def _normalized_hex(self, raw: str, default_hex: str) -> str:
        c = QtGui.QColor((raw or "").strip())
        if not c.isValid():
            c = QtGui.QColor(default_hex)
        if not c.isValid():
            c = QtGui.QColor("#000000")
        return c.name(QtGui.QColor.NameFormat.HexRgb).upper()

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
        bg = self._normalized_hex(str(s.get("bg_color", "#121212")), "#121212")
        text = self._normalized_hex(str(s.get("text_color", "#E0E0E0")), "#E0E0E0")
        focus = self._normalized_hex(str(s.get("focus_color", "#FFD700")), "#FFD700")
        self._player_settings["bg_color"] = bg
        self._player_settings["text_color"] = text
        self._player_settings["focus_color"] = focus
        family = str(s.get("font_family", "Arial"))
        size = int(max(12, float(s.get("font_size", 150.0)) * 0.24))
        speed = float(s.get("playback_speed", 1.0))

        profile = STYLE_PROFILES.get(self._style_profile, STYLE_PROFILES["cadence"])
        border = str(profile.get("border_panel", "#3f4a5a"))
        thumb = str(profile.get("scroll_thumb", "#4a5668"))
        thumb_hover = str(profile.get("scroll_thumb_hover", "#5a6880"))
        self.player_reader_panel.setStyleSheet(player_panel_style(bg))
        self.player_view_stack.setStyleSheet(player_view_stack_style(bg))
        self.player_text.setStyleSheet(
            player_text_style(bg, text, border=border, thumb=thumb, thumb_hover=thumb_hover)
        )
        self.player_text.viewport().setStyleSheet(player_text_viewport_style(bg))
        self.player_text.setViewportMargins(0, 0, 0, 0)
        self.player_text.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        # Some Qt builds ignore QTextEdit background from stylesheet in this composition.
        # Force Base/Window palette colors so context background always follows player settings.
        bg_q = QtGui.QColor(bg)
        text_q = QtGui.QColor(text)
        text_pal = self.player_text.palette()
        text_pal.setColor(QtGui.QPalette.ColorRole.Base, bg_q)
        text_pal.setColor(QtGui.QPalette.ColorRole.Text, text_q)
        text_pal.setColor(QtGui.QPalette.ColorRole.Window, bg_q)
        text_pal.setColor(QtGui.QPalette.ColorRole.WindowText, text_q)
        self.player_text.setPalette(text_pal)
        self.player_text.setAutoFillBackground(True)

        vp = self.player_text.viewport()
        vp_pal = vp.palette()
        vp_pal.setColor(QtGui.QPalette.ColorRole.Window, bg_q)
        vp_pal.setColor(QtGui.QPalette.ColorRole.Base, bg_q)
        vp.setPalette(vp_pal)
        vp.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        vp.setAutoFillBackground(True)

        stack_pal = self.player_view_stack.palette()
        stack_pal.setColor(QtGui.QPalette.ColorRole.Window, bg_q)
        self.player_view_stack.setPalette(stack_pal)
        self.player_view_stack.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.player_view_stack.setAutoFillBackground(True)

        text_font = QtGui.QFont(family, max(12, size))
        self.player_text.setFont(text_font)
        self.player_text.document().setDefaultFont(text_font)
        self.player_rsvp.bg_color = QtGui.QColor(bg)
        self.player_rsvp.text_color = QtGui.QColor(text)
        self.player_rsvp.focus_color = QtGui.QColor(focus)
        self.player_rsvp.font_family = family
        self.player_rsvp.font_size = float(s.get("font_size", 150.0))
        self.player_rsvp.update()

        seek_shell = str(profile.get("bg_shell", "#242a33"))
        seek_line = str(profile.get("border_panel", "#3f4a5a"))
        seek_accent = str(profile.get("accent", "#2CC985"))
        self.player_seek.setStyleSheet(
            player_seek_style(shell_bg=seek_shell, border=seek_line, accent=seek_accent)
        )

        mode = str(s.get("reading_view_mode", "context")).strip().lower()
        if mode == "rsvp":
            self._fade_switch_player_view(self.player_rsvp)
        else:
            self._fade_switch_player_view(self.player_text)

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
        self._apply_profile_button_depths()
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
            self,
            "Select Book File",
            "",
            "Book files (*.epub *.mobi *.azw3);;EPUB files (*.epub);;MOBI files (*.mobi);;AZW3 files (*.azw3)",
        )
        if not path:
            return

        self._start_import(path, self.voice_combo.currentText())

    def _set_import_button_mode(self, importing: bool):
        self.import_btn.setText("Cancel Import" if importing else "Import Book")
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
                "Stored Source Missing",
                "No stored source file was found for this book.",
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

    def _apply_style_profile(self, requested: str):
        profile = str(requested or "").strip().lower() or "cadence"
        if profile not in STYLE_PROFILES:
            profile = "cadence"
        if profile == self._style_profile:
            return
        self._style_profile = profile
        self.setStyleSheet(build_qss(self._style_profile))
        self._apply_profile_divider_styles()
        self._apply_profile_card_shadows()
        self._apply_profile_button_depths()
        self._apply_profile_header_theme()
        self._apply_player_settings()

    def open_runtime_settings(self):
        prev_profile = self._style_profile
        dlg = RuntimeSettingsDialog(self)
        self._apply_profile_button_depths()
        dlg.profile_preview.connect(self._apply_style_profile)
        if dlg.exec():
            requested = str(os.environ.get("CADENCE_STYLE_PROFILE", "cadence")).strip().lower() or "cadence"
            self._apply_style_profile(requested)
            self.log("Saved runtime settings to cadence_settings.json.")
            self.log(
                "Note: running imports use new values immediately; existing loaded models may need restart."
            )
        else:
            self._apply_style_profile(prev_profile)
