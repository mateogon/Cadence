import bisect
import json
import os
import shutil
import subprocess
import time
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font, messagebox

import numpy as np
import pygame
import soundfile as sf
import librosa

SETTINGS_FILE = "player_settings.json"
DEFAULT_SETTINGS = {
    "settings_version": 6,
    "chain_size": 5,
    "font_size": 150,
    "font_family": "Arial",
    "gap_threshold": 0.3,
    "sync_offset": 0,
    "playback_speed": 1.0,
    "bg_color": "#121212",
    "text_color": "#E0E0E0",
    "focus_color": "#FFD700",
    "secondary_text_color": "#555555",
    "font_scale_center": 1.25,
    "font_scale_side": 1.00,
    "slot_step": 1.20,
    "slot_padding": 0.06,
    "fit_mode": "shrink",
    "reading_view_mode": "rsvp",
    "context_force_center": True,
}

BASE_SETTINGS_SCHEMA = [
    {
        "key": "reading_view_mode",
        "label": "Reading View",
        "type": "choice",
        "values": ["rsvp", "context"],
        "group": "Display",
    },
    {
        "key": "font_size",
        "label": "Font Size",
        "type": "float",
        "min": 30.0,
        "max": 260.0,
        "step": 2.0,
        "group": "Display",
    },
    {
        "key": "context_force_center",
        "label": "Center Current Line (Context)",
        "type": "bool",
        "group": "Display",
        "help": "Only for Context view. Keep the currently spoken line centered.",
    },
    {
        "key": "font_family",
        "label": "Font Family",
        "type": "choice",
        "group": "Display",
    },
    {"key": "bg_color", "label": "Background Color", "type": "color", "group": "Display"},
    {"key": "text_color", "label": "Text Color", "type": "color", "group": "Display"},
    {"key": "focus_color", "label": "Focus Word Color", "type": "color", "group": "Display"},
    {
        "key": "secondary_text_color",
        "label": "Secondary Text Color",
        "type": "color",
        "group": "Display",
    },
    {
        "key": "sync_offset",
        "label": "Sync Offset (s)",
        "type": "float",
        "min": -3.0,
        "max": 3.0,
        "step": 0.05,
        "group": "Timing",
    },
    {
        "key": "gap_threshold",
        "label": "Pause Gap Threshold (s)",
        "type": "float",
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
        "group": "Timing",
        "help": "Minimum silent gap between words to render as a visible pause. Lower = more pauses.",
    },
    {
        "key": "playback_speed",
        "label": "Playback Speed",
        "type": "float",
        "min": 0.50,
        "max": 2.00,
        "step": 0.05,
        "group": "Playback",
    },
]

PREVIEW_SECONDS = 60.0
PREVIEW_PAD_SECONDS = 4.0
PREVIEW_SPEED_MIN = 0.80
PREVIEW_SPEED_MAX = 1.25
SPEED_CACHE_VERSION = "v3_ffmpeg"


class PlayerCore:
    def __init__(self, parent, book_path, on_exit, on_state_change=None, debug=False):
        self.parent = parent
        self.root = parent.winfo_toplevel()
        self.book_path = Path(book_path)
        self.content_dir = self.book_path / "content"
        self.metadata_path = self.book_path / "metadata.json"
        self.on_exit = on_exit
        self.on_state_change = on_state_change
        self.debug = debug

        self.meta = {}
        self.current_chapter = 1
        self.words = []
        self.chapter_raw_words = []
        self.start_times = []
        self.is_playing = False
        self.running = False
        self._after_id = None
        self.start_offset = 0.0
        self.settings = self.load_settings()
        self._bound_handlers = {}
        self._mounted_widgets = []

        self._font_cache = {}
        self.main_font = font.Font(family="Arial", size=-180, weight="bold")
        self.side_font = font.Font(family="Arial", size=-120, weight="normal")
        self.bg_col = self.settings.get("bg_color", DEFAULT_SETTINGS["bg_color"])
        self.fg_col = self.settings.get("text_color", DEFAULT_SETTINGS["text_color"])
        self.center_col = self.settings.get("focus_color", DEFAULT_SETTINGS["focus_color"])
        self.dim_col = self.settings.get(
            "secondary_text_color", DEFAULT_SETTINGS["secondary_text_color"]
        )

        self.canvas = None
        self.context_text = None
        self.context_entries = []
        self.context_timed_entries = []
        self.context_time_starts = []
        self.last_context_index = -1
        self._last_context_render_sig = None
        self._last_context_scroll_at = 0.0
        self.context_padding_lines = 12
        self.lbl_info = None
        self.last_render_index = -1
        self.duration = 0.0
        self._last_state_emit = 0.0
        self._state_emit_interval_s = 0.25
        self._chapter_duration_cache = {}
        self._speed_audio_cache = {}
        self.current_audio_path = None
        self._speed_job_token = 0
        self._speed_processing = False
        self._speed_status_text = ""
        self._seek_clip_cache = {}
        self._ui_resizing = False
        self._needs_render_after_resize = False
        self._context_hidden_for_resize = False

    def debug_log(self, message):
        if self.debug:
            print(f"[DEBUG][PlayerCore] {message}")

    def mount(self):
        self.load_metadata()
        self.current_chapter = self.meta.get("last_chapter", 1) or 1
        self.running = True
        self.last_render_index = -1
        self.apply_theme()

        self.canvas = tk.Canvas(self.parent, bg=self.bg_col, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.context_text = tk.Text(
            self.parent,
            bg=self.bg_col,
            fg=self.fg_col,
            insertbackground=self.fg_col,
            wrap="word",
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=28,
            pady=24,
            font=(self.settings.get("font_family", DEFAULT_SETTINGS["font_family"]), 20),
        )
        self.context_text.configure(state="disabled")
        self.context_text.tag_configure("current_word", foreground=self.center_col, underline=True)
        self.context_text.pack_forget()
        self.apply_view_mode_visibility()

        info = "Space: Play | Left/Right: Seek | Up/Down: Chapter | Esc: Back"
        self.lbl_info = tk.Label(
            self.parent, text=info, bg=self.bg_col, fg=self.dim_col, font=("Consolas", 10)
        )
        self.lbl_info.pack(side=tk.BOTTOM, fill=tk.X, pady=8)
        self._mounted_widgets = [self.canvas, self.context_text, self.lbl_info]

        self.ensure_mixer()
        self.bind_keys()

        if self.load_chapter(self.current_chapter):
            start_time = float(self.meta.get("last_timestamp", 0.0))
            if start_time > 0:
                self.start_offset = start_time
                self.draw_message(f"Resumed Ch {self.current_chapter}: {int(start_time)}s")
                self.set_index_from_time(start_time)
            else:
                self.start_offset = 0.0
                self.draw_message(f"Chapter {self.current_chapter}")
        else:
            self.draw_message("Unable to load chapter")

        self.update_state(force=True)
        self.update_loop()

    def unmount(self):
        self.running = False
        self.save_progress()
        self.stop_audio()
        self.unbind_keys()
        if self._after_id:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        for widget in self._mounted_widgets:
            try:
                widget.destroy()
            except Exception:
                pass
        self._mounted_widgets = []
        self.canvas = None
        self.lbl_info = None

    def ensure_mixer(self):
        if pygame.mixer.get_init():
            return
        try:
            pygame.mixer.init()
        except Exception as exc:
            messagebox.showerror("Audio Error", str(exc))

    def bind_keys(self):
        bindings = {
            "<space>": self.toggle_play,
            "<Right>": lambda _e: self.seek(5),
            "<Left>": lambda _e: self.seek(-5),
            "<Up>": lambda _e: self.change_chapter(1),
            "<Down>": lambda _e: self.change_chapter(-1),
            "<Prior>": lambda _e: self.change_font(10),
            "<Next>": lambda _e: self.change_font(-10),
            "<Escape>": self.exit_to_library,
        }
        for seq, handler in bindings.items():
            self.root.bind(seq, handler)
            self._bound_handlers[seq] = handler

    def unbind_keys(self):
        for seq in self._bound_handlers:
            self.root.unbind(seq)
        self._bound_handlers = {}

    def load_metadata(self):
        with open(self.metadata_path, "r", encoding="utf-8") as file:
            self.meta = json.load(file)

    def load_chapter(self, chapter_num):
        wav_file = self.get_source_audio_path(chapter_num)
        json_file = self.content_dir / f"ch_{chapter_num:03d}.json"
        if not wav_file.exists() or not json_file.exists():
            return False
        try:
            speed = float(self.settings.get("playback_speed", 1.0))
            playable_wav = self.get_playable_audio(chapter_num, wav_file, speed)
            pygame.mixer.music.load(str(playable_wav))
            self.current_audio_path = playable_wav
            with open(json_file, "r", encoding="utf-8") as file:
                self.chapter_raw_words = json.load(file)
            self.words = self.inject_gaps(self.chapter_raw_words)
            self.start_times = [word.get("start", 0.0) for word in self.words]
            self.build_context_text_data()
            self.start_offset = 0.0
            self.is_playing = False
            self.last_render_index = -1
            self.last_context_index = -1
            self._last_context_render_sig = None
            self.apply_view_mode_visibility()
            self.duration = self.get_chapter_duration(chapter_num, wav_file)
            self.update_state(force=True)
            return True
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load chapter: {exc}")
            return False

    def update_state(self, force=False):
        if not self.on_state_change:
            return
        now = time.monotonic()
        if not force and (now - self._last_state_emit) < self._state_emit_interval_s:
            return
        self._last_state_emit = now
        total = self.meta.get("total_chapters", self.meta.get("chapters", 0))
        position = max(0.0, min(self.get_current_time(), self.duration if self.duration > 0 else self.get_current_time()))
        self.on_state_change(
            {
                "title": self.meta.get("title", "Book"),
                "chapter": self.current_chapter,
                "total_chapters": total,
                "position_s": position,
                "duration_s": self.duration,
                "is_playing": self.is_playing,
                "settings": self.get_settings(),
                "speed_processing": self._speed_processing,
                "speed_status_text": self._speed_status_text,
            }
        )

    def change_chapter(self, offset):
        new_chapter = self.current_chapter + offset
        if new_chapter < 1:
            return
        previous = self.current_chapter
        self.current_chapter = new_chapter
        if self.load_chapter(new_chapter):
            self.draw_message(f"Chapter {self.current_chapter}")
            pygame.mixer.music.play()
            self.is_playing = True
            self.update_state(force=True)
            self.save_progress()
        else:
            self.current_chapter = previous

    def save_progress(self):
        if not self.meta:
            return
        self.meta["last_chapter"] = self.current_chapter
        self.meta["last_timestamp"] = self.get_current_time()
        self.atomic_json_write(self.metadata_path, self.meta, indent=2)

    def stop_audio(self):
        if not pygame.mixer.get_init():
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.is_playing = False
        self.update_state(force=True)

    def exit_to_library(self, event=None):
        self.save_progress()
        if callable(self.on_exit):
            self.on_exit()

    def inject_gaps(self, data):
        if not data:
            return []
        output = []
        threshold = self.settings.get("gap_threshold", 0.3)
        for index, item in enumerate(data):
            output.append(item)
            if index >= len(data) - 1:
                continue
            gap = data[index + 1]["start"] - item["end"]
            if gap > threshold:
                output.append(
                    {
                        "word": "",
                        "start": item["end"],
                        "end": data[index + 1]["start"],
                        "is_gap": True,
                    }
                )
        return output

    def render(self, center_idx):
        if self.get_view_mode() == "context":
            current = self.get_current_time() + self.settings["sync_offset"]
            self.render_context(current)
            return
        if not self.canvas or not self.words:
            return
        if center_idx == self.last_render_index:
            return
        self.last_render_index = center_idx
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        center_x, center_y = width // 2, height // 2
        center_max_width = int(width * 0.92)

        center_size_px = int(self.settings["font_size"] * self.settings["font_scale_center"])
        self.main_font.configure(
            family=self.settings.get("font_family", DEFAULT_SETTINGS["font_family"]),
            size=-center_size_px,
            weight="bold",
        )

        word = self.words[center_idx].get("word", "")
        text = self.ellipsize(word, self.main_font, center_max_width)
        self.canvas.create_text(
            center_x,
            center_y,
            text=text,
            font=self.main_font,
            fill=self.center_col,
        )

    def render_context(self, current_time):
        if not self.context_text or not self.context_timed_entries:
            return
        now = time.monotonic()
        render_sig = (
            int(self.context_text.winfo_width()),
            int(self.context_text.winfo_height()),
            bool(self.settings.get("context_force_center", True)),
        )
        idx = self.find_context_index_at_time(current_time)
        if idx < 0:
            return
        entry = self.context_timed_entries[idx]
        start_char = int(entry["char_start"])
        end_char = int(entry["char_end"])
        if end_char <= start_char:
            return

        # If only viewport/layout changed, avoid expensive retagging and just recenter.
        if idx == self.last_context_index:
            if render_sig == self._last_context_render_sig:
                return
            self._last_context_render_sig = render_sig
            if now - self._last_context_scroll_at >= 0.08:
                self.scroll_context_to_word(start_char)
                self._last_context_scroll_at = now
            return

        self.last_context_index = idx
        self._last_context_render_sig = render_sig
        start_idx = f"1.0+{start_char}c"
        end_idx = f"1.0+{end_char}c"
        self.context_text.tag_remove("current_word", "1.0", tk.END)
        self.context_text.tag_add("current_word", start_idx, end_idx)
        self.scroll_context_to_word(start_char)
        self._last_context_scroll_at = now

    def scroll_context_to_word(self, char_index):
        if not self.context_text:
            return
        target = f"1.0+{int(char_index)}c"
        force_center = bool(self.settings.get("context_force_center", True))
        if not force_center:
            self.context_text.see(target)
            return

        self.context_text.see(target)
        self.context_text.update_idletasks()

        try:
            line_info = self.context_text.dlineinfo(target)
            if line_info is None:
                return
            y_px = float(line_info[1])
            h_px = max(1.0, float(line_info[3]))
            widget_h = max(1.0, float(self.context_text.winfo_height()))
            desired_y = (widget_h - h_px) / 2.0
            delta_px = y_px - desired_y
            # Deadband prevents small oscillation/flicker near center.
            deadband = max(2.0, h_px * 0.35)
            if abs(delta_px) <= deadband:
                return
            units = int(round(delta_px / h_px))
            if units == 0:
                units = 1 if delta_px > 0 else -1
            self.context_text.yview_scroll(units, "units")
        except Exception:
            self.context_text.see(target)

    def find_context_index_at_time(self, t):
        if not self.context_timed_entries:
            return -1
        idx = bisect.bisect_right(self.context_time_starts, t) - 1
        if idx < 0:
            return 0
        if idx >= len(self.context_timed_entries):
            return len(self.context_timed_entries) - 1
        end_t = float(self.context_timed_entries[idx].get("end_t", 0.0))
        if t <= end_t:
            return idx
        if idx + 1 < len(self.context_timed_entries):
            return idx + 1
        return idx

    def build_context_text_data(self):
        self.context_entries = []
        self.context_timed_entries = []
        self.context_time_starts = []
        if not self.context_text:
            return

        parts = []
        top_pad = "\n" * int(self.context_padding_lines)
        bottom_pad = "\n" * int(self.context_padding_lines)
        parts.append(top_pad)
        cursor = len(top_pad)
        for raw in self.chapter_raw_words:
            token = str(raw.get("word", ""))
            if not token:
                continue
            char_start = cursor
            parts.append(token)
            cursor += len(token)
            char_end = cursor
            entry = {
                "char_start": char_start,
                "char_end": char_end,
                "start_t": float(raw.get("start", 0.0)),
                "end_t": float(raw.get("end", 0.0)),
                "token": token,
            }
            self.context_entries.append(entry)
            if token.strip():
                self.context_timed_entries.append(entry)
                self.context_time_starts.append(entry["start_t"])

        parts.append(bottom_pad)
        text = "".join(parts)
        self.context_text.configure(state="normal")
        self.context_text.delete("1.0", tk.END)
        self.context_text.insert("1.0", text)
        self.context_text.tag_remove("current_word", "1.0", tk.END)
        self.context_text.configure(state="disabled")
        self.last_context_index = -1
        self._last_context_render_sig = None
        self._last_context_scroll_at = 0.0

    def ellipsize(self, text, tk_font, max_width):
        if tk_font.measure(text) <= max_width:
            return text
        if max_width <= tk_font.measure("..."):
            return "..."
        remaining = text
        while remaining and tk_font.measure(remaining + "...") > max_width:
            remaining = remaining[:-1]
        return f"{remaining}..." if remaining else "..."

    def update_loop(self):
        if not self.running:
            return
        if self._ui_resizing:
            self._needs_render_after_resize = True
            self.update_state()
            self._after_id = self.root.after(40, self.update_loop)
            return
        if self.is_playing and self.words:
            current = self.get_current_time() + self.settings["sync_offset"]
            idx = self.find_index_at_time(current)
            if idx != -1:
                self.render(idx)
            if pygame.mixer.music.get_pos() == -1 and self.duration > 0:
                self.is_playing = False
        self.update_state()
        self._after_id = self.root.after(24, self.update_loop)

    def set_ui_resizing(self, resizing):
        new_state = bool(resizing)
        if self._ui_resizing == new_state:
            return
        self._ui_resizing = new_state
        if self._ui_resizing:
            # Context view (tk.Text) can be expensive to re-wrap while resizing.
            # Temporarily hide it and restore when resizing settles.
            if (
                self.get_view_mode() == "context"
                and self.context_text
                and self.context_text.winfo_manager()
            ):
                try:
                    self.context_text.pack_forget()
                    self._context_hidden_for_resize = True
                except Exception:
                    self._context_hidden_for_resize = False
        if not self._ui_resizing and self._needs_render_after_resize:
            if self._context_hidden_for_resize:
                self._context_hidden_for_resize = False
                self.apply_view_mode_visibility()
            self._needs_render_after_resize = False
            try:
                idx = self.find_index_at_time(self.get_current_time() + self.settings["sync_offset"])
                if idx != -1:
                    self.render(idx)
            except Exception:
                pass

    def get_current_time(self):
        speed = max(0.5, float(self.settings.get("playback_speed", 1.0)))
        if self.is_playing:
            elapsed_playback_s = pygame.mixer.music.get_pos() / 1000.0
            elapsed_source_s = max(0.0, elapsed_playback_s * speed)
            return elapsed_source_s + self.start_offset
        return self.start_offset

    def toggle_play(self, event=None):
        if self._speed_processing:
            return
        if self.is_playing:
            self.start_offset = self.get_current_time()
            pygame.mixer.music.pause()
            self.is_playing = False
            self.update_state(force=True)
            return
        # Resume by seeking from source time instead of unpause; this avoids
        # double-counting elapsed time against start_offset after pauses.
        self.play_from_source_time(self.start_offset)
        self.is_playing = True
        self.update_state(force=True)

    def seek(self, amount):
        if self._speed_processing:
            return
        max_t = self.duration if self.duration > 0 else self.get_current_time() + amount
        target = max(0.0, min(self.get_current_time() + amount, max_t))
        self.start_offset = target
        self.play_from_source_time(target)
        if not self.is_playing:
            pygame.mixer.music.pause()
        idx = self.find_index_at_time(target + self.settings["sync_offset"])
        if idx != -1:
            self.render(idx)
        self.update_state(force=True)

    def find_index_at_time(self, t):
        if not self.words:
            return -1
        idx = bisect.bisect_right(self.start_times, t) - 1
        if idx < 0:
            return -1
        if t <= self.words[idx].get("end", 0.0):
            return idx
        return -1

    def set_index_from_time(self, t):
        idx = self.find_index_at_time(t)
        if idx != -1:
            self.render(idx)

    def change_font(self, amount):
        self.settings["font_size"] = max(10, self.settings["font_size"] + amount)
        idx = self.find_index_at_time(self.get_current_time() + self.settings["sync_offset"])
        if idx != -1:
            self.render(idx)
        self.update_state(force=True)

    def draw_message(self, message):
        if not self.canvas:
            return
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        family = self.settings.get("font_family", DEFAULT_SETTINGS["font_family"])
        self.canvas.create_text(
            width // 2,
            height // 2,
            text=message,
            fill=self.fg_col,
            font=(family, 30),
        )

    def get_settings(self):
        return dict(self.settings)

    def get_settings_schema(self):
        schema = []
        font_choices = self.get_font_family_choices()
        for spec in BASE_SETTINGS_SCHEMA:
            item = dict(spec)
            if item.get("key") == "font_family":
                item["values"] = font_choices
            schema.append(item)
        return schema

    def save_settings(self):
        self.atomic_json_write(Path(SETTINGS_FILE), self.settings, indent=2)

    def update_settings(self, patch):
        if not patch:
            return
        pre_change_time = self.get_current_time()
        was_playing = self.is_playing
        previous = dict(self.settings)
        for key, value in patch.items():
            if key == "font_size":
                self.settings[key] = float(self.clamp(value, 30.0, 260.0))
            elif key == "font_family":
                self.settings[key] = str(value).strip() or DEFAULT_SETTINGS["font_family"]
            elif key == "sync_offset":
                self.settings[key] = float(self.clamp(value, -3.0, 3.0))
            elif key == "gap_threshold":
                self.settings[key] = float(self.clamp(value, 0.0, 1.5))
            elif key == "playback_speed":
                self.settings[key] = float(self.clamp(value, 0.50, 2.00))
            elif key == "reading_view_mode":
                normalized = str(value).strip().lower()
                self.settings[key] = "context" if normalized == "context" else "rsvp"
            elif key == "context_force_center":
                self.settings[key] = bool(value)
            elif key in {"bg_color", "text_color", "focus_color", "secondary_text_color"}:
                self.settings[key] = str(value)

        speed_changed = previous.get("playback_speed") != self.settings.get("playback_speed")
        gap_changed = previous.get("gap_threshold") != self.settings.get("gap_threshold")
        context_layout_changed = any(
            previous.get(k) != self.settings.get(k)
            for k in ("context_force_center", "font_size", "font_family", "reading_view_mode")
        )
        display_changed = any(
            previous.get(k) != self.settings.get(k)
            for k in (
                "font_family",
                "bg_color",
                "text_color",
                "focus_color",
                "secondary_text_color",
                "reading_view_mode",
                "context_force_center",
            )
        )

        self.apply_theme()
        self.apply_view_mode_visibility()
        if gap_changed:
            self.words = self.inject_gaps(self.chapter_raw_words)
            self.start_times = [word.get("start", 0.0) for word in self.words]
            self.last_render_index = -1
            self.last_context_index = -1
            self._last_context_render_sig = None
        if context_layout_changed:
            self.last_context_index = -1
            self._last_context_render_sig = None
        if speed_changed and self.current_chapter > 0:
            self.stop_audio()
            self.start_offset = pre_change_time
            self.request_speed_reload(
                target_speed=float(self.settings["playback_speed"]),
                source_time=pre_change_time,
                was_playing=was_playing,
            )

        idx = self.find_index_at_time(self.get_current_time() + self.settings["sync_offset"])
        if idx != -1:
            self.render(idx)
        elif display_changed:
            self.draw_message(f"Chapter {self.current_chapter}")
        self.update_state(force=True)

    def clamp(self, value, minimum, maximum):
        try:
            numeric = float(value)
        except Exception:
            numeric = minimum
        return max(minimum, min(maximum, numeric))

    def apply_theme(self):
        self.bg_col = self.settings.get("bg_color", DEFAULT_SETTINGS["bg_color"])
        self.fg_col = self.settings.get("text_color", DEFAULT_SETTINGS["text_color"])
        self.center_col = self.settings.get("focus_color", DEFAULT_SETTINGS["focus_color"])
        self.dim_col = self.settings.get(
            "secondary_text_color", DEFAULT_SETTINGS["secondary_text_color"]
        )
        if self.canvas:
            self.canvas.configure(bg=self.bg_col)
        if self.lbl_info:
            self.lbl_info.configure(bg=self.bg_col, fg=self.dim_col)
        if self.context_text:
            family = self.settings.get("font_family", DEFAULT_SETTINGS["font_family"])
            context_size = max(12, int(float(self.settings.get("font_size", 150)) * 0.20))
            self.context_text.configure(
                bg=self.bg_col,
                fg=self.fg_col,
                insertbackground=self.fg_col,
                font=(family, context_size),
            )
            self.context_text.tag_configure(
                "current_word", foreground=self.center_col, underline=True
            )

    def get_view_mode(self):
        mode = str(self.settings.get("reading_view_mode", "rsvp")).strip().lower()
        return "context" if mode == "context" else "rsvp"

    def apply_view_mode_visibility(self):
        mode = self.get_view_mode()
        if not self.canvas or not self.context_text:
            return
        if mode == "context":
            if self.canvas.winfo_manager():
                self.canvas.pack_forget()
            if not self.context_text.winfo_manager():
                self.context_text.pack(fill=tk.BOTH, expand=True)
        else:
            if self.context_text.winfo_manager():
                self.context_text.pack_forget()
            if not self.canvas.winfo_manager():
                self.canvas.pack(fill=tk.BOTH, expand=True)

    def to_playback_seconds(self, source_seconds, speed=None):
        if speed is None:
            speed = float(self.settings.get("playback_speed", 1.0))
        speed = max(0.5, float(speed))
        return max(0.0, float(source_seconds) / speed)

    def play_from_source_time(self, source_time, speed=None):
        if speed is None:
            speed = float(self.settings.get("playback_speed", 1.0))
        playback_time = self.to_playback_seconds(source_time, speed)
        try:
            pygame.mixer.music.play(start=playback_time)
            return
        except pygame.error as exc:
            if "Position not implemented" not in str(exc):
                raise
            self.debug_log("pygame start-position unsupported; using cached seek clip fallback.")
        if not self.current_audio_path:
            pygame.mixer.music.play()
            self.start_offset = 0.0
            return
        seek_clip = self.get_seek_clip_path(
            chapter=self.current_chapter,
            speed=speed,
            playback_time=playback_time,
            audio_path=Path(self.current_audio_path),
        )
        pygame.mixer.music.load(str(seek_clip))
        pygame.mixer.music.play()
        self.start_offset = max(0.0, float(source_time))

    def get_seek_clip_path(self, chapter, speed, playback_time, audio_path):
        seek_second = round(max(0.0, playback_time), 1)
        key = (SPEED_CACHE_VERSION, chapter, f"{speed:.2f}", str(audio_path), seek_second)
        cached = self._seek_clip_cache.get(key)
        if cached and Path(cached).exists():
            return Path(cached)
        cache_dir = self.book_path / "cache" / f"seek_audio_{SPEED_CACHE_VERSION}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        output = cache_dir / f"ch_{chapter:03d}@{speed:.2f}@{int(seek_second*10):06d}.wav"
        if not output.exists():
            data, sample_rate = sf.read(str(audio_path), always_2d=True, dtype="float32")
            start_frame = int(seek_second * sample_rate)
            start_frame = min(start_frame, max(0, data.shape[0] - 1))
            clipped = data[start_frame:]
            sf.write(str(output), clipped, sample_rate)
        self._seek_clip_cache[key] = str(output)
        return output

    def get_source_audio_path(self, chapter_num):
        return self.book_path / "audio" / f"ch_{chapter_num:03d}.wav"

    def get_playable_audio(self, chapter_num, wav_file, speed):
        if abs(speed - 1.0) < 1e-6:
            return wav_file
        key = (SPEED_CACHE_VERSION, "full", chapter_num, f"{speed:.2f}")
        cached = self._speed_audio_cache.get(key)
        if cached and Path(cached).exists():
            return Path(cached)

        output = self.get_full_speed_audio_path(chapter_num, speed)
        if not output.exists():
            self.render_speed_audio(wav_file, output, speed)
        self._speed_audio_cache[key] = str(output)
        return output

    def get_full_speed_audio_path(self, chapter_num, speed):
        cache_dir = self.book_path / "cache" / f"speed_audio_{SPEED_CACHE_VERSION}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"ch_{chapter_num:03d}@{speed:.2f}.wav"

    def get_preview_speed_audio_path(self, chapter_num, speed, start_second):
        cache_dir = self.book_path / "cache" / f"speed_audio_preview_{SPEED_CACHE_VERSION}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        start_tag = int(max(0, start_second))
        return cache_dir / f"ch_{chapter_num:03d}@{speed:.2f}@{start_tag:06d}.wav"

    def render_speed_audio(self, input_path, output_path, speed):
        if self.render_speed_audio_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            speed=speed,
        ):
            return
        data, sample_rate = sf.read(str(input_path), always_2d=True, dtype="float32")
        output_audio = self.time_stretch_audio_data(data, speed)
        sf.write(str(output_path), output_audio, sample_rate)

    def render_speed_audio_segment(self, input_path, output_path, speed, start_s, duration_s):
        if self.render_speed_audio_ffmpeg(
            input_path=input_path,
            output_path=output_path,
            speed=speed,
            start_s=start_s,
            duration_s=duration_s,
        ):
            return
        info = sf.info(str(input_path))
        sample_rate = info.samplerate
        padded_start_s = max(0.0, start_s - PREVIEW_PAD_SECONDS)
        padded_stop_s = max(0.0, start_s + duration_s + PREVIEW_PAD_SECONDS)
        start_frame = int(padded_start_s * sample_rate)
        stop_frame = int(padded_stop_s * sample_rate)
        stop_frame = min(stop_frame, info.frames)
        data, _ = sf.read(
            str(input_path),
            start=start_frame,
            stop=stop_frame,
            always_2d=True,
            dtype="float32",
        )
        output_audio = self.time_stretch_audio_data(data, speed)
        trim_start = int(((start_s - padded_start_s) / max(0.5, speed)) * sample_rate)
        trim_end = trim_start + int((duration_s / max(0.5, speed)) * sample_rate)
        trim_end = min(trim_end, output_audio.shape[0])
        output_audio = output_audio[max(0, trim_start):max(0, trim_end)]
        sf.write(str(output_path), output_audio, sample_rate)

    def render_speed_audio_ffmpeg(self, input_path, output_path, speed, start_s=None, duration_s=None):
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            return False
        speed = float(speed)
        if speed <= 0:
            return False
        cmd = [ffmpeg_path, "-y"]
        if start_s is not None:
            cmd.extend(["-ss", f"{max(0.0, float(start_s)):.3f}"])
        if duration_s is not None:
            cmd.extend(["-t", f"{max(0.01, float(duration_s)):.3f}"])
        cmd.extend(["-i", str(input_path)])
        cmd.extend(["-vn", "-af", f"atempo={speed:.6f}", "-acodec", "pcm_s16le", str(output_path)])
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0 and Path(output_path).exists():
                return True
            self.debug_log(f"ffmpeg speed render failed: {result.stderr.strip()}")
            return False
        except Exception as exc:
            self.debug_log(f"ffmpeg execution error: {exc}")
            return False

    def time_stretch_audio_data(self, data, speed):
        if data.size == 0:
            return data
        stretched_channels = []
        for channel in range(data.shape[1]):
            channel_audio = data[:, channel]
            stretched = self.stretch_channel_high_quality(channel_audio, speed)
            stretched_channels.append(stretched.astype(np.float32))
        min_len = min(len(channel_audio) for channel_audio in stretched_channels)
        return np.stack(
            [channel_audio[:min_len] for channel_audio in stretched_channels], axis=1
        )

    def stretch_channel_high_quality(self, channel_audio, speed):
        if channel_audio.size == 0:
            return channel_audio.astype(np.float32)
        if abs(speed - 1.0) < 1e-6:
            return channel_audio.astype(np.float32)
        n_fft = 4096
        hop_length = 1024
        win_length = 4096
        stft = librosa.stft(
            channel_audio,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=win_length,
            window="hann",
            center=True,
        )
        stretched_stft = librosa.phase_vocoder(stft, rate=speed, hop_length=hop_length)
        target_length = max(1, int(len(channel_audio) / speed))
        return librosa.istft(
            stretched_stft,
            hop_length=hop_length,
            win_length=win_length,
            length=target_length,
        ).astype(np.float32)

    def get_chapter_duration(self, chapter_num, wav_file):
        key = (chapter_num, "source")
        if key not in self._chapter_duration_cache:
            self._chapter_duration_cache[key] = pygame.mixer.Sound(str(wav_file)).get_length()
        return float(self._chapter_duration_cache[key])

    def reload_current_chapter_for_speed(self):
        chapter = self.current_chapter
        if chapter < 1:
            return
        was_playing = self.is_playing
        source_time = self.get_current_time()
        if not self.load_chapter(chapter):
            return
        self.start_offset = max(0.0, min(source_time, self.duration))
        self.set_index_from_time(self.start_offset + self.settings["sync_offset"])
        if was_playing:
            self.play_from_source_time(self.start_offset)
            self.is_playing = True

    def request_speed_reload(self, target_speed, source_time, was_playing):
        chapter = self.current_chapter
        source_wav = self.get_source_audio_path(chapter)
        if not source_wav.exists():
            return
        self._speed_job_token += 1
        token = self._speed_job_token
        if PREVIEW_SPEED_MIN <= target_speed <= PREVIEW_SPEED_MAX:
            self.set_speed_processing(True, "Preparing quick preview...")
        else:
            self.set_speed_processing(True, "Rendering full chapter (high quality)...")

        full_path = self.get_full_speed_audio_path(chapter, target_speed)
        if full_path.exists():
            self.apply_prepared_speed_audio(
                token=token,
                chapter=chapter,
                target_speed=target_speed,
                playable_path=full_path,
                source_time=source_time,
                was_playing=was_playing,
                final_stage=True,
                use_current_time=False,
            )
            return

        def worker():
            try:
                if PREVIEW_SPEED_MIN <= target_speed <= PREVIEW_SPEED_MAX:
                    preview_start = max(0.0, source_time)
                    preview_duration = PREVIEW_SECONDS
                    preview_path = self.get_preview_speed_audio_path(
                        chapter, target_speed, preview_start
                    )
                    if not preview_path.exists():
                        self.render_speed_audio_segment(
                            source_wav,
                            preview_path,
                            target_speed,
                            start_s=preview_start,
                            duration_s=preview_duration,
                        )
                    self.root.after(
                        0,
                        lambda: self.apply_prepared_speed_audio(
                            token=token,
                            chapter=chapter,
                            target_speed=target_speed,
                            playable_path=preview_path,
                            source_time=preview_start,
                            was_playing=was_playing,
                            final_stage=False,
                            use_current_time=False,
                        ),
                    )
                    self.root.after(
                        0, lambda: self.set_speed_processing(True, "Finishing full chapter...")
                    )
                else:
                    self.root.after(
                        0,
                        lambda: self.set_speed_processing(
                            True, "Finishing full chapter (high quality)..."
                        ),
                    )

                playable = self.get_playable_audio(chapter, source_wav, target_speed)
            except Exception as exc:
                self.debug_log(f"Speed render failed: {exc}")
                self.root.after(0, self.finish_speed_processing)
                return
            self.root.after(
                0,
                lambda: self.apply_prepared_speed_audio(
                    token=token,
                    chapter=chapter,
                    target_speed=target_speed,
                    playable_path=playable,
                    source_time=source_time,
                    was_playing=was_playing,
                    final_stage=True,
                    use_current_time=True,
                ),
            )

        threading.Thread(target=worker, daemon=True).start()

    def finish_speed_processing(self):
        self._speed_processing = False
        self._speed_status_text = ""
        self.update_state(force=True)

    def set_speed_processing(self, processing, status_text=""):
        self._speed_processing = processing
        self._speed_status_text = status_text
        self.update_state(force=True)

    def apply_prepared_speed_audio(
        self,
        token,
        chapter,
        target_speed,
        playable_path,
        source_time,
        was_playing,
        final_stage,
        use_current_time,
    ):
        if not self.running:
            self.finish_speed_processing()
            return
        if token != self._speed_job_token:
            self.finish_speed_processing()
            return
        if chapter != self.current_chapter:
            self.finish_speed_processing()
            return
        if abs(float(self.settings.get("playback_speed", 1.0)) - float(target_speed)) > 1e-6:
            self.finish_speed_processing()
            return

        try:
            pygame.mixer.music.load(str(playable_path))
        except Exception as exc:
            self.debug_log(f"Failed loading prepared speed audio: {exc}")
            self.finish_speed_processing()
            return

        self.current_audio_path = playable_path
        target_source_time = self.get_current_time() if use_current_time else float(source_time)
        self.start_offset = max(
            0.0,
            min(
                float(target_source_time),
                self.duration if self.duration > 0 else float(target_source_time),
            ),
        )
        self.last_render_index = -1
        idx = self.find_index_at_time(self.start_offset + self.settings["sync_offset"])
        if idx != -1:
            self.render(idx)

        if was_playing:
            self.play_from_source_time(self.start_offset, target_speed)
            self.is_playing = True
        else:
            self.is_playing = False
        if final_stage:
            self.finish_speed_processing()
        self.update_state(force=True)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
                    loaded = json.load(file)
                settings = {**DEFAULT_SETTINGS, **loaded}
                if "dark_mode" in loaded and not any(
                    k in loaded for k in ("bg_color", "text_color", "focus_color")
                ):
                    if bool(loaded.get("dark_mode", True)):
                        settings.update(
                            {
                                "bg_color": "#121212",
                                "text_color": "#E0E0E0",
                                "focus_color": "#FFD700",
                                "secondary_text_color": "#555555",
                            }
                        )
                    else:
                        settings.update(
                            {
                                "bg_color": "#F5F5F5",
                                "text_color": "#121212",
                                "focus_color": "#C28A00",
                                "secondary_text_color": "#666666",
                            }
                        )
                return settings
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)

    def reset_settings_defaults(self):
        self.settings = dict(DEFAULT_SETTINGS)
        self.apply_theme()
        self.apply_view_mode_visibility()

    def get_font_family_choices(self):
        preferred = [
            "Arial",
            "Consolas",
            "Georgia",
            "Times New Roman",
            "Calibri",
            "Verdana",
            "Trebuchet MS",
            "Tahoma",
            "Segoe UI",
            "Courier New",
        ]
        try:
            available = set(font.families())
        except Exception:
            return preferred
        ordered = [f for f in preferred if f in available]
        extras = sorted([f for f in available if f not in ordered])[:25]
        return ordered + extras if ordered else preferred

    def get_font(self, family, size, weight="normal"):
        key = (family, size, weight)
        cached = self._font_cache.get(key)
        if cached is None:
            cached = font.Font(family=family, size=size, weight=weight)
            self._font_cache[key] = cached
        return cached

    def atomic_json_write(self, path, payload, indent=None):
        target = Path(path)
        tmp_path = target.with_suffix(target.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=indent)
        os.replace(tmp_path, target)
