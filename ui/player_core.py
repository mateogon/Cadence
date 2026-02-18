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
    "settings_version": 5,
    "chain_size": 5,
    "font_size": 150,
    "dark_mode": True,
    "gap_threshold": 0.3,
    "sync_offset": 0,
    "playback_speed": 1.0,
    "font_scale_center": 1.25,
    "font_scale_side": 1.00,
    "slot_step": 1.20,
    "slot_padding": 0.06,
    "fit_mode": "shrink",
}

SETTINGS_SCHEMA = [
    {
        "key": "font_size",
        "label": "Font Size",
        "type": "float",
        "min": 60.0,
        "max": 260.0,
        "step": 2.0,
        "group": "Display",
    },
    {
        "key": "dark_mode",
        "label": "Dark Mode",
        "type": "bool",
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
        "label": "Gap Threshold (s)",
        "type": "float",
        "min": 0.0,
        "max": 1.5,
        "step": 0.05,
        "group": "Timing",
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
        self.bg_col = "#121212" if self.settings["dark_mode"] else "#F5F5F5"
        self.fg_col = "#E0E0E0" if self.settings["dark_mode"] else "#121212"
        self.center_col = "#FFD700"
        self.dim_col = "#555555"

        self.canvas = None
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

        info = "Space: Play | Left/Right: Seek | Up/Down: Chapter | Esc: Back"
        self.lbl_info = tk.Label(
            self.parent, text=info, bg=self.bg_col, fg=self.dim_col, font=("Consolas", 10)
        )
        self.lbl_info.pack(side=tk.BOTTOM, fill=tk.X, pady=8)
        self._mounted_widgets = [self.canvas, self.lbl_info]

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
            messagebox.showinfo("End of Book", "No more chapters.")
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
            self.start_offset = 0.0
            self.is_playing = False
            self.last_render_index = -1
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
        self.main_font.configure(size=-center_size_px, weight="bold")

        word = self.words[center_idx].get("word", "")
        text = self.ellipsize(word, self.main_font, center_max_width)
        self.canvas.create_text(
            center_x,
            center_y,
            text=text,
            font=self.main_font,
            fill=self.center_col,
        )

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
        if self.is_playing and self.words:
            current = self.get_current_time() + self.settings["sync_offset"]
            idx = self.find_index_at_time(current)
            if idx != -1:
                self.render(idx)
            if pygame.mixer.music.get_pos() == -1 and self.duration > 0:
                self.is_playing = False
        self.update_state()
        self._after_id = self.root.after(16, self.update_loop)

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
        if pygame.mixer.music.get_pos() == -1:
            self.play_from_source_time(self.start_offset)
        else:
            pygame.mixer.music.unpause()
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
        self.canvas.create_text(width // 2, height // 2, text=message, fill=self.fg_col, font=("Arial", 30))

    def get_settings(self):
        return dict(self.settings)

    def get_settings_schema(self):
        return list(SETTINGS_SCHEMA)

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
                self.settings[key] = float(self.clamp(value, 60.0, 260.0))
            elif key == "sync_offset":
                self.settings[key] = float(self.clamp(value, -3.0, 3.0))
            elif key == "gap_threshold":
                self.settings[key] = float(self.clamp(value, 0.0, 1.5))
            elif key == "dark_mode":
                self.settings[key] = bool(value)
            elif key == "playback_speed":
                self.settings[key] = float(self.clamp(value, 0.50, 2.00))

        speed_changed = previous.get("playback_speed") != self.settings.get("playback_speed")
        gap_changed = previous.get("gap_threshold") != self.settings.get("gap_threshold")
        dark_changed = previous.get("dark_mode") != self.settings.get("dark_mode")

        self.apply_theme()
        if gap_changed:
            self.words = self.inject_gaps(self.chapter_raw_words)
            self.start_times = [word.get("start", 0.0) for word in self.words]
            self.last_render_index = -1
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
        elif dark_changed:
            self.draw_message(f"Chapter {self.current_chapter}")
        self.update_state(force=True)

    def clamp(self, value, minimum, maximum):
        try:
            numeric = float(value)
        except Exception:
            numeric = minimum
        return max(minimum, min(maximum, numeric))

    def apply_theme(self):
        self.bg_col = "#121212" if self.settings["dark_mode"] else "#F5F5F5"
        self.fg_col = "#E0E0E0" if self.settings["dark_mode"] else "#121212"
        self.center_col = "#FFD700"
        self.dim_col = "#555555" if self.settings["dark_mode"] else "#666666"
        if self.canvas:
            self.canvas.configure(bg=self.bg_col)
        if self.lbl_info:
            self.lbl_info.configure(bg=self.bg_col, fg=self.dim_col)

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
                if loaded.get("settings_version") != DEFAULT_SETTINGS["settings_version"]:
                    return dict(DEFAULT_SETTINGS)
                return {**DEFAULT_SETTINGS, **loaded}
            except Exception:
                pass
        return dict(DEFAULT_SETTINGS)

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
