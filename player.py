import sys
import os
import json
import tkinter as tk
from tkinter import messagebox, font
import pygame
from pathlib import Path

# --- Configuration ---
SETTINGS_FILE = "player_settings.json"
DEFAULT_SETTINGS = {
    "chain_size": 3, "font_size": 70, "dark_mode": True, 
    "gap_threshold": 0.3, "sync_offset": -0.15
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
        
        # --- UI Setup ---
        self.root.title(f"Reading: {self.meta.get('title', 'Book')}")
        self.root.geometry("1100x600")
        self.bg_col = "#121212" if self.settings["dark_mode"] else "#F5F5F5"
        self.fg_col = "#E0E0E0" if self.settings["dark_mode"] else "#121212"
        self.center_col = "#FFD700" 
        self.dim_col = "#555555"
        
        self.root.configure(bg=self.bg_col)
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

    def load_chapter(self, chapter_num):
        # Format: ch_001.wav
        wav_file = self.content_dir / f"ch_{chapter_num:03d}.wav"
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
            
        self.root.destroy()

    # --- Standard Rendering & Playback Logic (From previous version) ---
    def inject_gaps(self, data):
        # ... (Same logic as V4) ...
        # Simplified for brevity here, paste the V4 logic
        return data # Placeholder

    def render(self, center_idx):
        # ... (Same render logic as V4) ...
        # Need to ensure self.words exists before rendering
        if not self.words: return
        self.canvas.delete("all")
        w_cv = self.canvas.winfo_width()
        h_cv = self.canvas.winfo_height()
        cx, cy = w_cv // 2, h_cv // 2
        
        fs = self.settings["font_size"]
        
        try:
            center_text = self.words[center_idx]["word"]
            self.canvas.create_text(cx, cy, text=center_text, 
                                    font=("Arial", int(fs*1.1), "bold"), fill=self.center_col)
        except: pass

    def update_loop(self):
        if self.is_playing and self.words:
            t = self.get_current_time() + self.settings["sync_offset"]
            idx = self.find_index_at_time(t)
            if idx != -1: self.render(idx)
        self.root.after(16, self.update_loop)

    def get_current_time(self):
        if not pygame.mixer.music.get_busy() and not self.is_playing:
             return self.start_offset
        return (pygame.mixer.music.get_pos() / 1000.0) + self.start_offset

    def toggle_play(self, event=None):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.start_offset = self.get_current_time()
        else:
            pygame.mixer.music.unpause()
            if not pygame.mixer.music.get_busy():
                pygame.mixer.music.play(start=self.start_offset)
            self.is_playing = True
            
    def seek(self, amt):
        t = max(0, self.get_current_time() + amt)
        self.start_offset = t
        pygame.mixer.music.rewind()
        pygame.mixer.music.play(start=t)
        if not self.is_playing: pygame.mixer.music.pause()

    def find_index_at_time(self, t):
        # Simple loop
        for i, w in enumerate(self.words):
            if w.get("start",0) <= t <= w.get("end",0): return i
        return -1
        
    def set_index_from_time(self, t):
        idx = self.find_index_at_time(t)
        if idx != -1: self.render(idx)

    def change_chain(self, amt):
        self.settings["chain_size"] = max(1, self.settings["chain_size"]+amt)
    
    def draw_message(self, msg):
        self.canvas.delete("all")
        self.canvas.create_text(550, 300, text=msg, fill="#FFF", font=("Arial", 30))

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f: return {**DEFAULT_SETTINGS, **json.load(f)}
            except: pass
        return DEFAULT_SETTINGS
