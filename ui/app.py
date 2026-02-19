import argparse
import sys

import customtkinter as ctk

from system.runtime_settings import apply_settings_to_environ, load_settings
from ui.views.library_view import LibraryView
from ui.views.player_view import PlayerView


def configure_dpi_awareness():
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class App(ctk.CTk):
    def __init__(self, debug=False):
        super().__init__()
        self.debug = debug
        self.title("Cadence")
        self.geometry("1100x700")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self.views_container = ctk.CTkFrame(self, fg_color="transparent")
        self.views_container.grid(row=0, column=0, sticky="nsew")
        self.views_container.grid_columnconfigure(0, weight=1)
        self.views_container.grid_rowconfigure(0, weight=1)

        self.library_view = LibraryView(self.views_container, app=self)
        self.library_view.grid(row=0, column=0, sticky="nsew")

        self.player_view = PlayerView(
            self.views_container,
            app=self,
            on_back=self.show_library,
            debug=self.debug,
        )
        self.player_view.grid(row=0, column=0, sticky="nsew")

        self.import_footer = ctk.CTkFrame(self)
        self.import_footer.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.import_footer.grid_columnconfigure(0, weight=1)

        self.import_progress = ctk.CTkProgressBar(self.import_footer, mode="determinate")
        self.import_progress.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
        self.import_progress.set(0)

        self.import_status_label = ctk.CTkLabel(
            self.import_footer,
            text="Ready",
            height=18,
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.import_status_label.grid(row=1, column=0, sticky="w", padx=10, pady=(2, 8))

        self.protocol("WM_DELETE_WINDOW", self.on_app_close)
        self.show_library()

    def debug_log(self, message):
        if self.debug:
            print(f"[DEBUG] {message}")

    def show_player(self, book_data):
        self.debug_log(f"Opening player for: {book_data.get('title', 'Unknown')}")
        self.player_view.open_book(book_data)
        self.player_view.tkraise()

    def show_library(self):
        self.debug_log("Returning to library")
        self.player_view.close_book()
        self.library_view.refresh_library()
        self.library_view.tkraise()

    def on_app_close(self):
        self.debug_log("App close requested")
        self.player_view.safe_close()
        self.destroy()

    def set_import_status(self, progress, message):
        progress = max(0.0, min(1.0, float(progress)))
        self.import_progress.set(progress)
        self.import_status_label.configure(text=message)


def build_parser():
    parser = argparse.ArgumentParser(description="Cadence")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging in the app and player core.",
    )
    return parser


def main(argv=None):
    apply_settings_to_environ(load_settings())
    configure_dpi_awareness()
    ctk.set_appearance_mode("Dark")
    ctk.set_default_color_theme("blue")

    args = build_parser().parse_args(argv)
    app = App(debug=args.debug)
    app.mainloop()


if __name__ == "__main__":
    main()
