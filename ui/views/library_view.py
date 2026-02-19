import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from system.book_manager import BookManager
from system.runtime_settings import DEFAULTS, apply_settings_to_environ, load_settings, save_settings


class LibraryView(ctk.CTkFrame):
    CARD_COLOR = "#232323"
    CARD_HOVER_COLOR = "#2d2d2d"
    RUNTIME_ENV_FIELDS = [
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
        self.app = app
        self.search_var = tk.StringVar()
        self.runtime_vars = {}
        self.runtime_defaults = {}

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo = ctk.CTkLabel(
            self.sidebar, text="CADENCE", font=ctk.CTkFont(size=24, weight="bold")
        )
        self.logo.grid(row=0, column=0, padx=20, pady=20)

        self.import_row = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.import_row.grid(row=1, column=0, padx=16, pady=10, sticky="ew")
        self.import_row.grid_columnconfigure(0, weight=1)

        self.btn_import = ctk.CTkButton(
            self.import_row,
            text="Import EPUB",
            command=self.import_book_dialog,
            fg_color="#2CC985",
            hover_color="#229966",
        )
        self.btn_import.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="ew")

        self.btn_runtime_settings = ctk.CTkButton(
            self.import_row,
            text="⚙",
            width=36,
            command=self.open_runtime_settings,
        )
        self.btn_runtime_settings.grid(row=0, column=1, padx=0, pady=0)

        self.voice_select = ctk.CTkOptionMenu(self.sidebar, values=["M3", "M1", "F1", "F3"])
        self.voice_select.grid(row=2, column=0, padx=20, pady=10)
        self.voice_select.set("M3")

        self.console_label = ctk.CTkLabel(
            self.sidebar, text="Process Log", font=ctk.CTkFont(size=12, weight="bold")
        )
        self.console_label.grid(row=3, column=0, padx=20, pady=(20, 0), sticky="w")

        self.console = ctk.CTkTextbox(
            self.sidebar, height=300, font=ctk.CTkFont(size=10, family="Consolas")
        )
        self.console.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        self.sidebar.grid_rowconfigure(4, weight=1)

        self.main_area = ctk.CTkFrame(self, fg_color="transparent")
        self.main_area.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        self.lbl_title = ctk.CTkLabel(
            self.main_area, text="My Library", font=ctk.CTkFont(size=20)
        )
        self.lbl_title.pack(anchor="w", pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            self.main_area,
            textvariable=self.search_var,
            placeholder_text="Search by title...",
            width=320,
        )
        self.search_entry.pack(anchor="w", pady=(0, 12))
        self.search_entry.bind("<KeyRelease>", lambda _e: self.refresh_library())

        self.scroll_frame = ctk.CTkScrollableFrame(self.main_area, label_text="")
        self.scroll_frame.pack(fill="both", expand=True)

        self.status_bar = ctk.CTkProgressBar(self, mode="determinate")
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.status_bar.set(0)

        self.lbl_status = ctk.CTkLabel(self, text="Ready", height=20, font=("Arial", 10))
        self.lbl_status.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.refresh_library()

    def log(self, message):
        self.console.insert("end", message + "\n")
        self.console.see("end")

    def refresh_library(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        books = BookManager.get_books()
        query = self.search_var.get().strip().lower()
        if query:
            books = [b for b in books if query in b.get("title", "").lower()]

        if not books:
            ctk.CTkLabel(
                self.scroll_frame,
                text="No matching books." if query else "No books found. Import an EPUB to start.",
            ).pack(pady=50)
            return

        for book in books:
            self.create_book_card(book)

    def create_book_card(self, book):
        card = ctk.CTkFrame(
            self.scroll_frame,
            fg_color=self.CARD_COLOR,
            corner_radius=10,
            border_width=1,
            border_color="#343434",
        )
        card.pack(fill="x", pady=6, padx=5)

        ctk.CTkLabel(
            card, text=book["title"], font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=12, pady=(10, 0))

        last = book.get("last_chapter", 0)
        total = book.get("total_chapters", book.get("chapters", "?"))
        info = f"Ch {last} / {total}  •  Voice: {book.get('voice', '?')}"
        ctk.CTkLabel(card, text=info, text_color="gray").pack(
            anchor="w", padx=12, pady=(0, 6)
        )

        btn = ctk.CTkButton(
            card,
            text="Read",
            width=100,
            height=30,
            command=lambda b=book: self.app.show_player(b),
        )
        btn.pack(anchor="e", padx=12, pady=(0, 8))

        def set_hover(on):
            card.configure(fg_color=self.CARD_HOVER_COLOR if on else self.CARD_COLOR)

        widgets_for_hover = [card, btn]
        widgets_for_hover.extend(card.winfo_children())
        for w in widgets_for_hover:
            w.bind("<Enter>", lambda _e: set_hover(True))
            w.bind("<Leave>", lambda _e: set_hover(False))

    def import_book_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("EPUB", "*.epub")])
        if not path:
            return
        self.btn_import.configure(state="disabled")
        voice = self.voice_select.get()
        self.log(f"--- Starting Import: {path} ---")
        thread = threading.Thread(target=self.run_import_thread, args=(path, voice), daemon=True)
        thread.start()

    def run_import_thread(self, path, voice):
        def progress(pct, msg):
            self.after(0, lambda: self.status_bar.set(pct))
            self.after(0, lambda: self.lbl_status.configure(text=msg))

        success = BookManager.import_book(path, voice, progress, log_callback=self.log)

        def finalize():
            self.btn_import.configure(state="normal")
            self.status_bar.set(0)
            self.lbl_status.configure(text="Ready" if success else "Error")
            self.log("--- Import Finished ---" if success else "--- Import Failed ---")
            self.refresh_library()

        self.after(0, finalize)

    def open_runtime_settings(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Runtime Settings")
        dlg.geometry("640x500")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        ctk.CTkLabel(
            dlg,
            text="Cadence Runtime Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            dlg,
            text="Saved in cadence_settings.json and applied immediately.",
            text_color="gray",
        ).pack(anchor="w", padx=16, pady=(0, 10))

        body = ctk.CTkScrollableFrame(dlg, label_text="")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        current_settings = load_settings()
        self.runtime_vars = {}
        self.runtime_defaults = {}
        for env_key, label in self.RUNTIME_ENV_FIELDS:
            row = ctk.CTkFrame(body, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=6)
            row.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(row, text=label, width=210, anchor="w").grid(
                row=0, column=0, sticky="w", padx=(0, 10)
            )

            var = tk.StringVar(value=current_settings.get(env_key, DEFAULTS.get(env_key, "")))
            entry = ctk.CTkEntry(row, textvariable=var)
            entry.grid(row=0, column=1, sticky="ew")
            self.runtime_vars[env_key] = var
            self.runtime_defaults[env_key] = DEFAULTS.get(env_key, "")

            ctk.CTkLabel(row, text=env_key, text_color="gray").grid(
                row=1, column=0, columnspan=2, sticky="w", pady=(2, 0)
            )

        footer = ctk.CTkFrame(dlg, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(0, 12))
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

        ctk.CTkButton(footer, text="Cancel", width=110, command=dlg.destroy).grid(
            row=0, column=1, padx=6
        )
        ctk.CTkButton(footer, text="Reset", width=110, command=reset_runtime_settings).grid(
            row=0, column=2, padx=6
        )
        ctk.CTkButton(footer, text="Apply", width=110, command=apply_runtime_settings).grid(
            row=0, column=3, padx=6
        )
