import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

import customtkinter as ctk

from system.book_manager import BookManager
from system.runtime_settings import DEFAULTS, apply_settings_to_environ, load_settings, save_settings
from ui.theme import PALETTE, RADIUS, SPACING, frame_style, option_menu_style


class LibraryView(ctk.CTkFrame):
    RESIZE_SETTLE_MS = 500

    CARD_COLOR = PALETTE["card"]
    CARD_HOVER_COLOR = PALETTE["card_hover"]
    RUNTIME_ENV_FIELDS = [
        ("CADENCE_EXTRACT_WORKERS", "Extract Workers"),
        ("CADENCE_SYNTH_WORKERS", "TTS Workers"),
        ("CADENCE_TTS_MAX_CHARS", "TTS Max Chars"),
        ("CADENCE_FORCE_CPU", "Force CPU (0/1)"),
        ("CADENCE_USE_TENSORRT", "Use TensorRT (0/1)"),
        ("CADENCE_CUDA_ONLY", "CUDA Only (0/1)"),
        ("CADENCE_SUPPRESS_ORT_WARNINGS", "Suppress ORT Warnings (0/1)"),
        ("CADENCE_ADD_SYSTEM_CUDA_DLL_PATH", "Add System CUDA DLL Path (0/1)"),
        ("CADENCE_ORT_LOG_LEVEL", "ORT Log Level (0-4)"),
        ("CADENCE_WHISPERX_MODEL", "WhisperX Model"),
        ("CADENCE_WHISPERX_BATCH_SIZE", "WhisperX Batch Size"),
        ("CADENCE_WHISPERX_COMPUTE_TYPE", "WhisperX Compute Type"),
        ("CADENCE_WHISPERX_DEVICE", "WhisperX Device"),
        ("CADENCE_WHISPERX_PYTHON", "WhisperX Python"),
    ]

    def __init__(self, parent, app):
        super().__init__(parent)
        self.configure(fg_color=PALETTE["surface"])
        self.app = app
        self.runtime_vars = {}
        self.runtime_defaults = {}
        self._title_marquee_jobs = {}
        self._resize_done_after_id = None
        self._last_size_sig = None
        self._list_hidden_for_resize = False
        self._last_live_refresh_ts = 0.0

        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self,
            width=220,
            fg_color=PALETTE["panel"],
            corner_radius=0,
            border_width=0,
        )
        self.sidebar.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=0,
            pady=0,
        )

        self.main_divider = ctk.CTkFrame(self, width=1, fg_color=PALETTE["card_border"])
        self.main_divider.grid(row=0, column=1, sticky="ns", padx=0, pady=0)

        self.logo = ctk.CTkLabel(
            self.sidebar, text="CADENCE", font=ctk.CTkFont(size=24, weight="bold")
        )
        self.logo.grid(
            row=0,
            column=0,
            padx=SPACING["outer"] + SPACING["section_gap"],
            pady=SPACING["outer"] + SPACING["section_gap"],
        )

        self.controls_card = ctk.CTkFrame(
            self.sidebar, **frame_style(PALETTE["card"], RADIUS["control"])
        )
        self.controls_card.grid(
            row=1,
            column=0,
            padx=SPACING["outer"],
            pady=(0, SPACING["outer"]),
            sticky="ew",
        )
        self.controls_card.grid_columnconfigure(0, weight=1)

        self.import_row = ctk.CTkFrame(self.controls_card, fg_color="transparent")
        self.import_row.grid(
            row=0, column=0, padx=SPACING["outer"], pady=SPACING["outer"], sticky="ew"
        )
        self.import_row.grid_columnconfigure(0, weight=1)

        self.btn_import = ctk.CTkButton(
            self.import_row,
            text="Import EPUB",
            command=self.import_book_dialog,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
        )
        self.btn_import.grid(
            row=0, column=0, padx=(0, SPACING["section_gap"]), pady=0, sticky="ew"
        )

        self.btn_runtime_settings = ctk.CTkButton(
            self.import_row,
            text="⚙",
            width=36,
            command=self.open_runtime_settings,
            fg_color=PALETTE["button_neutral"],
            hover_color=PALETTE["button_neutral_hover"],
        )
        self.btn_runtime_settings.grid(row=0, column=1, padx=0, pady=0)

        self.voice_label = ctk.CTkLabel(
            self.controls_card, text="Voice", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.voice_label.grid(
            row=1, column=0, padx=SPACING["outer"], pady=(0, SPACING["micro"]), sticky="w"
        )

        self.voice_select_shell = ctk.CTkFrame(
            self.controls_card,
            fg_color=PALETTE["option_shell_bg"],
            corner_radius=RADIUS["control"],
            border_width=0,
        )
        self.voice_select_shell.grid(
            row=2, column=0, padx=SPACING["outer"], pady=(0, SPACING["outer"]), sticky="ew"
        )

        self.voice_select = ctk.CTkOptionMenu(
            self.voice_select_shell,
            values=["M3", "M1", "F1", "F3"],
            **option_menu_style(),
        )
        self.voice_select.pack(
            fill="x", padx=SPACING["compact"], pady=SPACING["compact"]
        )
        self.voice_select.set("M3")

        self.log_card = ctk.CTkFrame(self.sidebar, **frame_style(PALETTE["card"], RADIUS["control"]))
        self.log_card.grid(
            row=2, column=0, padx=SPACING["outer"], pady=(0, SPACING["outer"]), sticky="nsew"
        )
        self.log_card.grid_columnconfigure(0, weight=1)
        self.log_card.grid_rowconfigure(1, weight=1)

        self.console_label = ctk.CTkLabel(
            self.log_card, text="Process Log", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.console_label.grid(
            row=0,
            column=0,
            padx=SPACING["outer"],
            pady=(SPACING["control_x"], 0),
            sticky="w",
        )

        self.console = ctk.CTkTextbox(
            self.log_card, height=300, font=ctk.CTkFont(size=10, family="Consolas")
        )
        self.console.grid(
            row=1,
            column=0,
            padx=SPACING["control_x"],
            pady=SPACING["section_gap"],
            sticky="nsew",
        )
        self.console.configure(state="disabled")
        self.sidebar.grid_rowconfigure(2, weight=1)

        self.main_area = ctk.CTkFrame(
            self,
            fg_color=PALETTE["panel"],
            corner_radius=0,
            border_width=0,
        )
        self.main_area.grid(
            row=0, column=2, sticky="nsew", padx=0, pady=0
        )

        self.lbl_title = ctk.CTkLabel(
            self.main_area, text="My Library", font=ctk.CTkFont(size=20)
        )
        self.lbl_title.pack(
            anchor="w",
            padx=SPACING["outer"],
            pady=(SPACING["outer"], SPACING["control_x"]),
        )

        self.search_row = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.search_row.pack(
            fill="x",
            padx=SPACING["outer"],
            pady=(0, SPACING["outer"]),
        )
        self.search_row.grid_columnconfigure(0, weight=1)

        self.search_entry = ctk.CTkEntry(
            self.search_row,
            placeholder_text="Search book title...",
            placeholder_text_color=PALETTE["muted_text"],
            width=320,
        )
        self.search_entry.grid(row=0, column=0, sticky="w")
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_library())

        self.refresh_button = ctk.CTkButton(
            self.search_row,
            text="Refresh",
            width=92,
            command=self.refresh_library,
        )
        self.refresh_button.grid(
            row=0, column=1, sticky="e", padx=(SPACING["section_gap"], 0)
        )

        self.list_container = ctk.CTkFrame(
            self.main_area, **frame_style(PALETTE["panel_alt"], RADIUS["control"])
        )
        self.list_container.pack(fill="both", expand=True, padx=SPACING["outer"], pady=(0, SPACING["outer"]))
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.list_container, label_text="", fg_color=PALETTE["panel_alt"], corner_radius=RADIUS["control"]
        )
        self.scroll_frame.pack(
            fill="both", expand=True, padx=SPACING["compact"], pady=SPACING["compact"]
        )
        self._boost_scrollable_frame_speed(self.scroll_frame, factor=6)

        self.bind("<Configure>", self._on_view_configure)
        self.refresh_library()

    def _boost_scrollable_frame_speed(self, scrollable_frame, factor=6):
        # Match Player Settings scroll responsiveness across all CTk scroll frames.
        try:
            canvas = getattr(scrollable_frame, "_parent_canvas", None)
            if canvas is None:
                return
            current = canvas.cget("yscrollincrement")
            base = int(float(current)) if str(current).strip() not in {"", "0"} else 1
            boosted = max(1, base * int(factor))
            canvas.configure(yscrollincrement=boosted)
        except Exception:
            pass

    def log(self, message):
        self.console.configure(state="normal")
        self.console.insert("end", message + "\n")
        self.console.see("end")
        self.console.configure(state="disabled")

    def refresh_library(self):
        for job in self._title_marquee_jobs.values():
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._title_marquee_jobs.clear()

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        books = BookManager.get_books()
        query = self.search_entry.get().strip().lower()
        if query:
            books = [b for b in books if query in b.get("title", "").lower()]
        books.sort(
            key=lambda b: (
                not b.get("is_incomplete", False),
                b.get("title", "").lower(),
            )
        )

        if not books:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No matching books." if query else "No books found. Import an EPUB to start.",
            ).pack(pady=50)
            return

        for book in books:
            self.create_book_card(book)

    def _hide_list_for_resize(self):
        if self._list_hidden_for_resize:
            return
        try:
            if self.list_container.winfo_manager():
                self.list_container.pack_forget()
            self._list_hidden_for_resize = True
        except Exception:
            self._list_hidden_for_resize = False

    def _show_list_after_resize(self):
        if not self._list_hidden_for_resize:
            return
        self._list_hidden_for_resize = False
        self.list_container.pack(
            fill="both",
            expand=True,
            padx=SPACING["outer"],
            pady=(0, SPACING["outer"]),
        )

    def _on_view_configure(self, _event):
        size_sig = (int(self.winfo_width()), int(self.winfo_height()))
        if self._last_size_sig == size_sig:
            return
        self._last_size_sig = size_sig
        self._hide_list_for_resize()
        if self._resize_done_after_id:
            try:
                self.after_cancel(self._resize_done_after_id)
            except Exception:
                pass
        self._resize_done_after_id = self.after(self.RESIZE_SETTLE_MS, self._on_resize_settled)

    def _on_resize_settled(self):
        self._resize_done_after_id = None
        self._show_list_after_resize()

    def create_book_card(self, book):
        card = ctk.CTkFrame(self.scroll_frame, **frame_style(self.CARD_COLOR, RADIUS["card"]))
        card.pack(fill="x", pady=SPACING["card_gap"] // 2, padx=0)
        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)

        title_text = book["title"]
        title_label = ctk.CTkLabel(
            card,
            text=title_text,
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
            justify="left",
        )
        title_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=SPACING["outer"],
            pady=(SPACING["control_x"], 0),
        )

        last = book.get("last_chapter", 0)
        total = book.get("total_chapters", book.get("chapters", "?"))
        info = f"Ch {last} / {total}  •  Voice: {book.get('voice', '?')}"
        ctk.CTkLabel(card, text=info, text_color=PALETTE["muted_text"]).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=SPACING["outer"],
            pady=(0, SPACING["micro"]),
        )

        expected = book.get("content_chapters", 0)
        audio_ready = book.get("audio_chapters_ready", 0)
        aligned_ready = book.get("aligned_chapters_ready", 0)
        if book.get("is_incomplete", False):
            status_text = (
                f"Incomplete  •  Audio {audio_ready}/{expected}  •  "
                f"Alignment {aligned_ready}/{expected}  •  "
                f"Available chapters readable"
            )
            status_color = PALETTE["warning"]
        else:
            status_text = (
                f"Complete  •  Audio {audio_ready}/{expected}  •  "
                f"Alignment {aligned_ready}/{expected}"
            )
            status_color = PALETTE["success"]

        ctk.CTkLabel(card, text=status_text, text_color=status_color).grid(
            row=2,
            column=0,
            sticky="w",
            padx=SPACING["outer"],
            pady=(0, 1),
        )
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(
            row=2,
            column=1,
            sticky="e",
            padx=SPACING["outer"],
            pady=(0, SPACING["control_x"]),
        )

        action_widgets = []
        if book.get("is_incomplete", False):
            can_continue = bool(book.get("stored_epub_exists", False))
            btn_continue = ctk.CTkButton(
                actions,
                text="Continue Import",
                width=122,
                height=30,
                fg_color=PALETTE["accent_alt"],
                hover_color=PALETTE["accent_alt_hover"],
                command=lambda b=book: self.continue_import_book(b),
                state="normal" if can_continue else "disabled",
            )
            btn_continue.grid(
                row=0, column=0, padx=(0, SPACING["compact"])
            )
            action_widgets.append(btn_continue)

        btn_read = ctk.CTkButton(
            actions,
            text="Read",
            width=84 if book.get("is_incomplete", False) else 100,
            height=30,
            command=lambda b=book: self.app.show_player(b),
        )
        btn_read.grid(row=0, column=1 if book.get("is_incomplete", False) else 0, padx=0)
        action_widgets.append(btn_read)

        def set_hover(on):
            card.configure(fg_color=self.CARD_HOVER_COLOR if on else self.CARD_COLOR)

        widgets_for_hover = [card]
        widgets_for_hover.extend(action_widgets)
        widgets_for_hover.extend(card.winfo_children())
        for w in widgets_for_hover:
            w.bind("<Enter>", lambda _e: set_hover(True))
            w.bind("<Leave>", lambda _e: set_hover(False))

        title_label.bind(
            "<Enter>", lambda _e, lbl=title_label, text=title_text: self.start_title_marquee(lbl, text)
        )
        title_label.bind("<Leave>", lambda _e, lbl=title_label, text=title_text: self.stop_title_marquee(lbl, text))

    def start_title_marquee(self, label, full_text):
        if label in self._title_marquee_jobs:
            return
        if not full_text:
            return
        try:
            font_obj = tkfont.Font(font=label.cget("font"))
            available_width = max(20, label.winfo_width() - 8)
            text_width = font_obj.measure(full_text)
            if text_width <= available_width:
                return
        except Exception:
            return

        padded = f"{full_text}     "
        state = {"idx": 0}

        def tick():
            idx = state["idx"]
            rotated = padded[idx:] + padded[:idx]
            label.configure(text=rotated)
            state["idx"] = (idx + 1) % len(padded)
            self._title_marquee_jobs[label] = self.after(85, tick)

        tick()

    def stop_title_marquee(self, label, full_text):
        job = self._title_marquee_jobs.pop(label, None)
        if job:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        label.configure(text=full_text)

    def import_book_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("EPUB", "*.epub")])
        if not path:
            return
        self.btn_import.configure(state="disabled")
        voice = self.voice_select.get()
        self.log(f"--- Starting Import: {path} ---")
        self.app.set_import_status(0.0, "Step 1/3: Extracting EPUB...")
        thread = threading.Thread(target=self.run_import_thread, args=(path, voice), daemon=True)
        thread.start()

    def run_import_thread(self, path, voice):
        def progress(pct, msg):
            now = time.monotonic()
            should_refresh = (now - self._last_live_refresh_ts) >= 1.0
            if should_refresh:
                self._last_live_refresh_ts = now
                self.after(0, self.refresh_library)
            self.after(0, lambda: self.app.set_import_status(pct, msg))

        success = BookManager.import_book(path, voice, progress, log_callback=self.log)

        def finalize():
            self.btn_import.configure(state="normal")
            self.app.set_import_status(0.0, "Ready" if success else "Import failed")
            self.log("--- Import Finished ---" if success else "--- Import Failed ---")
            self.refresh_library()

        self.after(0, finalize)

    def continue_import_book(self, book):
        stored_epub = book.get("stored_epub_path", "").strip()
        if not stored_epub:
            self.log(f"No stored EPUB found for {book.get('title', 'book')}.")
            return
        voice = book.get("voice", self.voice_select.get() or "M3")
        self.btn_import.configure(state="disabled")
        self.log(f"--- Continuing Import: {book.get('title', '')} ---")
        self.log(f"Using stored EPUB: {stored_epub}")
        self.app.set_import_status(0.0, "Resuming import from stored EPUB...")
        thread = threading.Thread(
            target=self.run_import_thread,
            args=(stored_epub, voice),
            daemon=True,
        )
        thread.start()

    def open_runtime_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Runtime Settings")
        dlg.geometry("760x620")
        dlg.configure(fg_color=PALETTE["surface"])
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        header = ctk.CTkFrame(
            dlg, fg_color=PALETTE["panel"], corner_radius=RADIUS["card"], border_width=0
        )
        header.pack(
            fill="x",
            padx=SPACING["modal_outer"],
            pady=(SPACING["modal_outer"], SPACING["section_gap"]),
        )

        ctk.CTkLabel(
            header,
            text="Cadence Runtime Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(
            anchor="w",
            padx=SPACING["modal_outer"],
            pady=(SPACING["outer"], SPACING["compact"]),
        )

        ctk.CTkLabel(
            header,
            text="Saved in cadence_settings.json and applied immediately.",
            text_color=PALETTE["muted_text"],
        ).pack(
            anchor="w",
            padx=SPACING["modal_outer"],
            pady=(0, SPACING["outer"]),
        )

        body_wrap = ctk.CTkFrame(
            dlg, fg_color=PALETTE["panel"], corner_radius=RADIUS["card"], border_width=0
        )
        body_wrap.pack(
            fill="both",
            expand=True,
            padx=SPACING["outer"],
            pady=(0, SPACING["section_gap"]),
        )

        body = ctk.CTkScrollableFrame(
            body_wrap,
            label_text="",
            fg_color=PALETTE["panel_alt"],
            corner_radius=RADIUS["control"],
        )
        body.pack(
            fill="both",
            expand=True,
            padx=SPACING["section_gap"],
            pady=SPACING["section_gap"],
        )
        self._boost_scrollable_frame_speed(body, factor=6)

        section_map = {
            "TTS": {
                "CADENCE_EXTRACT_WORKERS",
                "CADENCE_SYNTH_WORKERS",
                "CADENCE_TTS_MAX_CHARS",
                "CADENCE_FORCE_CPU",
            },
            "ONNX / CUDA": {
                "CADENCE_USE_TENSORRT",
                "CADENCE_CUDA_ONLY",
                "CADENCE_SUPPRESS_ORT_WARNINGS",
                "CADENCE_ADD_SYSTEM_CUDA_DLL_PATH",
                "CADENCE_ORT_LOG_LEVEL",
            },
            "WhisperX": {
                "CADENCE_WHISPERX_MODEL",
                "CADENCE_WHISPERX_BATCH_SIZE",
                "CADENCE_WHISPERX_COMPUTE_TYPE",
                "CADENCE_WHISPERX_DEVICE",
                "CADENCE_WHISPERX_PYTHON",
            },
        }
        ordered_sections = ["TTS", "ONNX / CUDA", "WhisperX", "Other"]

        current_settings = load_settings()
        self.runtime_vars = {}
        self.runtime_defaults = {}
        grouped = {name: [] for name in ordered_sections}
        for env_key, label in self.RUNTIME_ENV_FIELDS:
            section_name = "Other"
            for candidate, keys in section_map.items():
                if env_key in keys:
                    section_name = candidate
                    break
            grouped[section_name].append((env_key, label))

        for section_name in ordered_sections:
            rows = grouped.get(section_name, [])
            if not rows:
                continue
            section = ctk.CTkFrame(
                body, fg_color=PALETTE["panel"], corner_radius=RADIUS["card"], border_width=0
            )
            section.pack(
                fill="x",
                padx=SPACING["section_gap"],
                pady=(0, SPACING["control_x"]),
            )

            ctk.CTkLabel(
                section,
                text=section_name,
                font=ctk.CTkFont(size=14, weight="bold"),
            ).pack(
                anchor="w",
                padx=SPACING["outer"],
                pady=(SPACING["control_x"], SPACING["section_gap"]),
            )

            for env_key, label in rows:
                row = ctk.CTkFrame(
                    section,
                    fg_color=PALETTE["card"],
                    corner_radius=RADIUS["control"],
                    border_width=0,
                )
                row.pack(
                    fill="x",
                    padx=SPACING["control_x"],
                    pady=(0, SPACING["section_gap"]),
                )
                row.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(row, text=label, width=210, anchor="w").grid(
                    row=0,
                    column=0,
                    sticky="w",
                    padx=(SPACING["control_x"], SPACING["control_x"]),
                    pady=(SPACING["section_gap"], 0),
                )

                var = tk.StringVar(value=current_settings.get(env_key, DEFAULTS.get(env_key, "")))
                entry = ctk.CTkEntry(row, textvariable=var)
                entry.grid(
                    row=0,
                    column=1,
                    sticky="ew",
                    padx=(0, SPACING["control_x"]),
                    pady=(SPACING["section_gap"], 0),
                )
                self.runtime_vars[env_key] = var
                self.runtime_defaults[env_key] = DEFAULTS.get(env_key, "")

                ctk.CTkLabel(row, text=env_key, text_color=PALETTE["muted_text"]).grid(
                    row=1,
                    column=0,
                    columnspan=2,
                    sticky="w",
                    padx=SPACING["control_x"],
                    pady=(SPACING["micro"], SPACING["section_gap"]),
                )

        footer = ctk.CTkFrame(
            dlg, fg_color=PALETTE["panel"], corner_radius=RADIUS["card"], border_width=0
        )
        footer.pack(
            fill="x",
            padx=SPACING["modal_outer"],
            pady=(0, SPACING["modal_outer"]),
        )
        footer.grid_columnconfigure(0, weight=1)

        def apply_runtime_settings():
            updated_settings = {key: var.get().strip() for key, var in self.runtime_vars.items()}
            save_settings(updated_settings)
            apply_settings_to_environ(updated_settings, override=True)
            self.log("Saved runtime settings to cadence_settings.json.")
            self.log(
                "Note: running imports use new values immediately; existing loaded models may need restart."
            )
            dlg.destroy()

        def reset_runtime_settings():
            for key, var in self.runtime_vars.items():
                var.set(self.runtime_defaults.get(key, ""))
            self.log("Reset runtime settings form to defaults.")

        ctk.CTkButton(
            footer,
            text="Cancel",
            width=110,
            fg_color=PALETTE["button_neutral"],
            hover_color=PALETTE["button_neutral_hover"],
            command=dlg.destroy,
        ).grid(
            row=0, column=1, padx=SPACING["compact"]
        )
        ctk.CTkButton(
            footer,
            text="Reset",
            width=110,
            fg_color=PALETTE["accent_alt"],
            hover_color=PALETTE["accent_alt_hover"],
            command=reset_runtime_settings,
        ).grid(
            row=0, column=2, padx=SPACING["compact"]
        )
        ctk.CTkButton(
            footer,
            text="Apply",
            width=110,
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            command=apply_runtime_settings,
        ).grid(
            row=0, column=3, padx=SPACING["compact"], pady=SPACING["control_x"]
        )
