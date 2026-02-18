import threading
from tkinter import filedialog

import customtkinter as ctk

from system.book_manager import BookManager


class LibraryView(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.logo = ctk.CTkLabel(
            self.sidebar, text="CADENCE", font=ctk.CTkFont(size=24, weight="bold")
        )
        self.logo.grid(row=0, column=0, padx=20, pady=20)

        self.btn_import = ctk.CTkButton(
            self.sidebar,
            text="Import EPUB",
            command=self.import_book_dialog,
            fg_color="#2CC985",
            hover_color="#229966",
        )
        self.btn_import.grid(row=1, column=0, padx=20, pady=10)

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
        self.lbl_title.pack(anchor="w", pady=(0, 20))

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
        if not books:
            ctk.CTkLabel(
                self.scroll_frame, text="No books found. Import an EPUB to start."
            ).pack(pady=50)
            return

        for book in books:
            self.create_book_card(book)

    def create_book_card(self, book):
        card = ctk.CTkFrame(self.scroll_frame, fg_color="#2b2b2b")
        card.pack(fill="x", pady=5, padx=5)

        ctk.CTkLabel(
            card, text=book["title"], font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=10, pady=(10, 0))

        last = book.get("last_chapter", 0)
        total = book.get("total_chapters", book.get("chapters", "?"))
        info = f"Ch {last} / {total}  •  Voice: {book.get('voice', '?')}"
        ctk.CTkLabel(card, text=info, text_color="gray").pack(
            anchor="w", padx=10, pady=(0, 10)
        )

        ctk.CTkButton(
            card,
            text="Read / Listen",
            width=120,
            command=lambda b=book: self.app.show_player(b),
        ).pack(anchor="e", padx=10, pady=10)

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
