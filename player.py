import sys
# DPI Awareness before any Tk/ctk objects
if sys.platform.startswith("win"):
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2) # 2 = per-monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

import os
import json
import tkinter as tk
from tkinter import messagebox, font
import pygame
from pathlib import Path

# --- Configuration ---
SETTINGS_FILE = "player_settings.json"
DEFAULT_SETTINGS = {
    "settings_version": 4,
    "chain_size": 5,
    "font_size": 150,
    "dark_mode": True,
    "gap_threshold": 0.3,
    "sync_offset": 0,
    "font_scale_center": 1.25,
    "font_scale_side": 1.00,
    "slot_step": 1.20,
    "slot_padding": 0.06,
    "fit_mode": "shrink"
}

class FlowReader:
    def __init__(self, root, book_path):
        self.root = root
        self.book_path = Path(book_path)
        self.content_dir = self.book_path / "content"
        self.metadata_path = self.book_path / "metadata.json"
        
        # Load Metadata
        with open(self.metadata_path, 'r') as f:
            self.meta = json.load(f)
            
        self.current_chapter = self.meta.get("last_chapter", 1)
        self.words = []
        self.is_playing = False
        self.settings = self.load_settings()
        self.running = True
        self._after_id = None
        
        # --- UI Setup ---
        self.root.title(f"Reading: {self.meta.get('title', 'Book')}")
        self.root.geometry("1100x600")
        self.bg_col = "#121212" if self.settings["dark_mode"] else "#F5F5F5"
        self.fg_col = "#E0E0E0" if self.settings["dark_mode"] else "#121212"
        self.center_col = "#FFD700" 
        self.dim_col = "#555555"
        
        self.root.configure(bg=self.bg_col)
        self._font_cache = {}
        
        # Persistent fonts (negative size = pixels)
        self.main_font = font.Font(family="Arial", size=-180, weight="bold")
        self.side_font = font.Font(family="Arial", size=-120, weight="normal")

        self.canvas = tk.Canvas(root, bg=self.bg_col, highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        info = "Space: Play | Left/Right: Seek | Up/Down: Chapter | [ ]: Chain"
        self.lbl_info = tk.Label(root, text=info, bg=self.bg_col, fg=self.dim_col, font=("Consolas", 10))
        self.lbl_info.pack(side=tk.BOTTOM, fill=tk.X, pady=8)

        # Init Audio
        try: pygame.mixer.init()
        except Exception as e: messagebox.showerror("Audio Error", str(e))

        # Bindings
        self.root.bind("<space>", self.toggle_play)
        self.root.bind("<Right>", lambda e: self.seek(5))
        self.root.bind("<Left>", lambda e: self.seek(-5))
        self.root.bind("]", lambda e: self.change_chain(2))
        self.root.bind("[", lambda e: self.change_chain(-2))
        self.root.bind("<Up>", lambda e: self.change_chapter(1))
        self.root.bind("<Down>", lambda e: self.change_chapter(-1))
        self.root.bind("<Prior>", lambda e: self.change_font(10))   # PageUp
        self.root.bind("<Next>",  lambda e: self.change_font(-10))  # PageDown
        self.root.bind("<Escape>", lambda e: self.on_close())
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Load Content
        self.load_chapter(self.current_chapter)
        
        # Resume Time
        start_time = self.meta.get("last_timestamp", 0.0)
        if start_time > 0:
            self.start_offset = start_time
            self.draw_message(f"Resumed Ch {self.current_chapter}: {int(start_time)}s")
            self.set_index_from_time(start_time)
        else:
            self.start_offset = 0
            self.draw_message(f"Chapter {self.current_chapter}")

        self.update_loop()
        print(f"DEBUG: FlowReader initialized. Font Size: {self.settings['font_size']}")

    def load_chapter(self, chapter_num):
        # Format: ch_001.wav is in 'audio', ch_001.json is in 'content'
        audio_dir = self.book_path / "audio"
        wav_file = audio_dir / f"ch_{chapter_num:03d}.wav"
        json_file = self.content_dir / f"ch_{chapter_num:03d}.json"
        
        if not wav_file.exists():
            messagebox.showinfo("End of Book", "No more chapters.")
            return False

        try:
            pygame.mixer.music.load(str(wav_file))
            with open(json_file, 'r', encoding='utf-8') as f:
                self.words = self.inject_gaps(json.load(f))
            self.start_offset = 0
            self.is_playing = False
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load chapter: {e}")
            return False

    def change_chapter(self, offset):
        new_ch = self.current_chapter + offset
        if new_ch < 1: return
        
        if self.load_chapter(new_ch):
            self.current_chapter = new_ch
            self.draw_message(f"Chapter {self.current_chapter}")
            pygame.mixer.music.play()
            self.is_playing = True

    def on_close(self, event=None):
        # Save Progress
        self.meta["last_chapter"] = self.current_chapter
        self.meta["last_timestamp"] = self.get_current_time()
        
        with open(self.metadata_path, 'w') as f:
            json.dump(self.meta, f, indent=2)
            
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(self.settings, f)
            
        self.running = False
        if self._after_id:
            self.root.after_cancel(self._after_id)
        self.root.destroy()

    def inject_gaps(self, data):
        """Adds empty 'gap' entries between words based on timing threshold."""
        if not data: return []
        new_data = []
        threshold = self.settings.get("gap_threshold", 0.3)
        
        for i in range(len(data)):
            new_data.append(data[i])
            if i < len(data) - 1:
                gap = data[i+1]["start"] - data[i]["end"]
                if gap > threshold:
                    new_data.append({
                        "word": "", 
                        "start": data[i]["end"], 
                        "end": data[i+1]["start"],
                        "is_gap": True
                    })
        return new_data

    def render(self, center_idx):
        if not self.words:
            return

        self.canvas.delete("all")
        w_cv = self.canvas.winfo_width()
        h_cv = self.canvas.winfo_height()
        cx, cy = w_cv // 2, h_cv // 2

        # Hard budget based on canvas pixels (not fs)
        center_max_w = int(w_cv * 0.92)

        def ellipsize(text, fnt, max_w):
            if fnt.measure(text) <= max_w:
                return text
            if max_w <= fnt.measure("…"):
                return "…"
            s = text
            while s and fnt.measure(s + "…") > max_w:
                s = s[:-1]
            return (s + "…") if s else "…"

        word = self.words[center_idx].get("word", "")
        txt = ellipsize(word, self.main_font, center_max_w)

        # Nuclear Bypass: Use a raw Tcl-style font tuple with NEGATIVE size (pixels)
        sz_px = int(self.settings["font_size"] * 1.25)
        raw_font = ("Arial", -sz_px, "bold")
        
        item = self.canvas.create_text(cx, cy, text=txt, font=raw_font, fill=self.center_col)

        # PROOF: print what Tk actually used + the real pixel height
        if center_idx % 20 == 0:
            bbox = self.canvas.bbox(item)
            actual_font = self.canvas.itemcget(item, "font")
            print(f"--- PROOF (v12) ---")
            print(f"RAW FONT USED: {raw_font}")
            print(f"CANVAS reported font: {actual_font}")
            print(f"BBOX Height: {(bbox[3]-bbox[1]) if bbox else 0}")
            print(f"Canvas Size: {w_cv}x{h_cv}")

    def update_loop(self):
        if not self.running: return
        
        if self.is_playing and self.words:
            t = self.get_current_time() + self.settings["sync_offset"]
            idx = self.find_index_at_time(t)
            if idx != -1: 
                self.render(idx)
            else:
                # print(f"DEBUG: No word at t={t:.2f}")
                pass
        self._after_id = self.root.after(16, self.update_loop)

    def get_current_time(self):
        if self.is_playing:
            return (pygame.mixer.music.get_pos() / 1000.0) + self.start_offset
        return self.start_offset

    def toggle_play(self, event=None):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.start_offset = self.get_current_time()
        else:
            if pygame.mixer.music.get_pos() == -1: # Music not playing/stopped
                pygame.mixer.music.play(start=self.start_offset)
            else:
                pygame.mixer.music.unpause()
            self.is_playing = True
            
    def seek(self, amt):
        t = max(0, self.get_current_time() + amt)
        self.start_offset = t
        pygame.mixer.music.play(start=t)
        if not self.is_playing: pygame.mixer.music.pause()

    def find_index_at_time(self, t):
        # We can optimize this with binary search if words are many
        for i, w in enumerate(self.words):
            if w["start"] <= t <= w["end"]: return i
        return -1
        
    def set_index_from_time(self, t):
        idx = self.find_index_at_time(t)
        if idx != -1: self.render(idx)

    def change_chain(self, amt):
        self.settings["chain_size"] = max(1, self.settings["chain_size"]+amt)
        self.render(self.find_index_at_time(self.get_current_time() + self.settings["sync_offset"]) or 0)

    def change_font(self, amt):
        self.settings["font_size"] = max(10, self.settings["font_size"] + amt)
        # push directly into the persistent font (negative = pixels)
        self.main_font.configure(size=-int(self.settings["font_size"] * 1.25), weight="bold")
        self.side_font.configure(size=-int(self.settings["font_size"] * 1.00), weight="normal")

        idx = self.find_index_at_time(self.get_current_time() + self.settings["sync_offset"])
        self.render(idx if idx != -1 else 0)
    
    def draw_message(self, msg):
        self.canvas.delete("all")
        self.canvas.create_text(550, 300, text=msg, fill="#FFF", font=("Arial", 30))

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    loaded = json.load(f)
                if loaded.get("settings_version") != DEFAULT_SETTINGS["settings_version"]:
                    return DEFAULT_SETTINGS
                return {**DEFAULT_SETTINGS, **loaded}
            except:
                pass
        return DEFAULT_SETTINGS

    def get_font(self, family, size, weight="normal"):
        key = (family, size, weight)
        f = self._font_cache.get(key)
        if f is None:
            f = font.Font(family=family, size=size, weight=weight)
            self._font_cache[key] = f
        return f
