import customtkinter as ctk
import tkinter as tk

from ui.player_core import PlayerCore


class PlayerView(ctk.CTkFrame):
    def __init__(self, parent, app, on_back, debug=False):
        super().__init__(parent)
        self.app = app
        self.on_back = on_back
        self.debug = debug
        self.core = None
        self.book_data = None
        self.settings_visible = False
        self.saved_settings_snapshot = None
        self._updating_controls = False
        self._control_refs = {}
        self._debounce_after = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)

        self.top_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        self.top_bar.grid_columnconfigure(1, weight=1)

        self.back_button = ctk.CTkButton(
            self.top_bar,
            text="← Library",
            width=110,
            command=self.handle_back,
        )
        self.back_button.grid(row=0, column=0, sticky="w")

        self.title_label = ctk.CTkLabel(
            self.top_bar, text="No book open", font=ctk.CTkFont(size=18, weight="bold")
        )
        self.title_label.grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.settings_button = ctk.CTkButton(
            self.top_bar,
            text="⚙ Settings",
            width=100,
            command=self.toggle_settings,
        )
        self.settings_button.grid(row=0, column=2, sticky="e", padx=(8, 8))

        self.chapter_label = ctk.CTkLabel(self.top_bar, text="Chapter -/-", text_color="gray")
        self.chapter_label.grid(row=0, column=3, sticky="e")

        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6))
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, mode="determinate")
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="00:00 / 00:00",
            text_color="gray",
            font=ctk.CTkFont(size=12),
        )
        self.progress_label.grid(row=1, column=0, sticky="e", pady=(2, 0))

        self.speed_status_label = ctk.CTkLabel(
            self.progress_frame,
            text="Adjusting pitch...",
            text_color="#d4a017",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.speed_status_label.grid(row=2, column=0, sticky="w", pady=(2, 0))
        self.speed_status_label.grid_remove()

        self.speed_status_bar = ctk.CTkProgressBar(self.progress_frame, mode="indeterminate")
        self.speed_status_bar.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.speed_status_bar.grid_remove()

        self.player_container = ctk.CTkFrame(self, corner_radius=8)
        self.player_container.grid(row=2, column=0, sticky="nsew", padx=(12, 8), pady=6)

        self.settings_drawer = ctk.CTkFrame(self, width=300)
        self.settings_drawer.grid(row=2, column=1, sticky="ns", padx=(0, 12), pady=6)
        self.settings_drawer.grid_propagate(False)
        self.settings_drawer.grid_remove()

        self.settings_title = ctk.CTkLabel(
            self.settings_drawer, text="Player Settings", font=ctk.CTkFont(size=16, weight="bold")
        )
        self.settings_title.pack(anchor="w", padx=12, pady=(12, 8))

        self.settings_body = ctk.CTkScrollableFrame(self.settings_drawer, width=276, height=360)
        self.settings_body.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        self.drawer_buttons = ctk.CTkFrame(self.settings_drawer, fg_color="transparent")
        self.drawer_buttons.pack(fill="x", padx=12, pady=(0, 12))
        self.drawer_buttons.grid_columnconfigure(0, weight=1)
        self.drawer_buttons.grid_columnconfigure(1, weight=1)

        self.cancel_settings_button = ctk.CTkButton(
            self.drawer_buttons,
            text="Cancel",
            fg_color="#555555",
            hover_color="#666666",
            command=self.cancel_settings,
        )
        self.cancel_settings_button.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.save_settings_button = ctk.CTkButton(
            self.drawer_buttons,
            text="Save",
            fg_color="#2CC985",
            hover_color="#229966",
            command=self.save_settings,
        )
        self.save_settings_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.hint_label = ctk.CTkLabel(
            self,
            text="Esc returns to library. Space toggles playback.",
            text_color="gray",
        )
        self.hint_label.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))

    def open_book(self, book_data):
        self.close_book()
        self.book_data = book_data
        self.title_label.configure(text=book_data.get("title", "Unknown"))
        self.core = PlayerCore(
            parent=self.player_container,
            book_path=book_data["path"],
            on_exit=self.handle_back,
            on_state_change=self.handle_state_change,
            debug=self.debug,
        )
        self.core.mount()
        self.saved_settings_snapshot = self.core.get_settings()
        self.build_settings_controls()
        self.apply_settings_to_controls(self.saved_settings_snapshot)

    def close_book(self):
        for after_id in self._debounce_after.values():
            try:
                self.after_cancel(after_id)
            except Exception:
                pass
        self._debounce_after = {}
        if self.core is None:
            return
        self.core.unmount()
        self.core = None
        self.book_data = None
        self.saved_settings_snapshot = None
        self.chapter_label.configure(text="Chapter -/-")
        self.progress_label.configure(text="00:00 / 00:00")
        self.progress_bar.set(0)
        self.hide_speed_loading()
        self.settings_drawer.grid_remove()
        self.settings_visible = False
        self.settings_button.configure(text="⚙ Settings")

    def safe_close(self):
        if self.core is not None:
            self.core.unmount()
            self.core = None

    def toggle_settings(self):
        if self.core is None:
            return
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.settings_drawer.grid()
            self.settings_button.configure(text="✕ Close")
        else:
            self.settings_drawer.grid_remove()
            self.settings_button.configure(text="⚙ Settings")

    def build_settings_controls(self):
        for widget in self.settings_body.winfo_children():
            widget.destroy()
        self._control_refs = {}
        if self.core is None:
            return

        schema = self.core.get_settings_schema()
        for spec in schema:
            key = spec["key"]
            group = spec.get("group", "")
            label_text = spec.get("label", key)
            kind = spec.get("type")

            block = ctk.CTkFrame(self.settings_body)
            block.pack(fill="x", pady=6, padx=0)

            ctk.CTkLabel(block, text=f"{group} · {label_text}", anchor="w").pack(
                fill="x", padx=10, pady=(8, 2)
            )

            if kind == "bool":
                variable = tk.BooleanVar(value=False)
                switch = ctk.CTkSwitch(
                    block,
                    text="Enabled",
                    variable=variable,
                    command=lambda k=key, v=variable: self.on_bool_change(k, v.get()),
                )
                switch.pack(anchor="w", padx=10, pady=(0, 8))
                self._control_refs[key] = {"kind": "bool", "var": variable}
            elif kind == "float":
                min_value = float(spec.get("min", 0.0))
                max_value = float(spec.get("max", 1.0))
                step = float(spec.get("step", 0.1))
                value_label = ctk.CTkLabel(block, text="", text_color="gray")
                value_label.pack(anchor="e", padx=10, pady=(0, 2))
                slider = ctk.CTkSlider(
                    block,
                    from_=min_value,
                    to=max_value,
                    command=lambda raw, k=key, s=step, l=value_label: self.on_slider_change(k, raw, s, l),
                )
                slider.pack(fill="x", padx=10, pady=(0, 10))
                self._control_refs[key] = {
                    "kind": "float",
                    "slider": slider,
                    "step": step,
                    "label": value_label,
                }

    def on_bool_change(self, key, value):
        if self._updating_controls or self.core is None:
            return
        self.core.update_settings({key: bool(value)})

    def on_slider_change(self, key, raw_value, step, value_label):
        if self._updating_controls or self.core is None:
            return
        quantized = round(float(raw_value) / step) * step
        value_label.configure(text=self.format_setting_value(key, quantized))
        if key == "playback_speed":
            after_id = self._debounce_after.get(key)
            if after_id:
                self.after_cancel(after_id)
            self._debounce_after[key] = self.after(
                220, lambda k=key, v=quantized: self.apply_debounced_setting(k, v)
            )
            return
        self.core.update_settings({key: quantized})

    def apply_debounced_setting(self, key, value):
        self._debounce_after.pop(key, None)
        if self.core is None:
            return
        self.core.update_settings({key: value})

    def apply_settings_to_controls(self, settings):
        self._updating_controls = True
        try:
            for key, ref in self._control_refs.items():
                if key not in settings:
                    continue
                if ref["kind"] == "bool":
                    ref["var"].set(bool(settings[key]))
                elif ref["kind"] == "float":
                    value = float(settings[key])
                    ref["slider"].set(value)
                    ref["label"].configure(text=self.format_setting_value(key, value))
        finally:
            self._updating_controls = False

    def save_settings(self):
        if self.core is None:
            return
        self.core.save_settings()
        self.saved_settings_snapshot = self.core.get_settings()

    def cancel_settings(self):
        if self.core is None or self.saved_settings_snapshot is None:
            return
        self.core.update_settings(dict(self.saved_settings_snapshot))
        self.apply_settings_to_controls(self.saved_settings_snapshot)
        self.settings_visible = False
        self.settings_drawer.grid_remove()
        self.settings_button.configure(text="⚙ Settings")

    def handle_back(self):
        if callable(self.on_back):
            self.on_back()

    def handle_state_change(self, state):
        title = state.get("title", "Unknown")
        chapter = state.get("chapter", "-")
        total = state.get("total_chapters", "-")
        position = float(state.get("position_s", 0.0))
        duration = float(state.get("duration_s", 0.0))
        speed_processing = bool(state.get("speed_processing", False))
        speed_status_text = state.get("speed_status_text", "Adjusting pitch...")
        self.title_label.configure(text=title)
        self.chapter_label.configure(text=f"Chapter {chapter}/{total}")

        ratio = 0.0 if duration <= 0 else max(0.0, min(1.0, position / duration))
        self.progress_bar.set(ratio)
        self.progress_label.configure(
            text=f"{self.format_time(position)} / {self.format_time(duration)}"
        )
        if speed_processing:
            self.show_speed_loading(speed_status_text)
        else:
            self.hide_speed_loading()

    def format_time(self, seconds):
        total = max(0, int(seconds))
        minutes, secs = divmod(total, 60)
        return f"{minutes:02d}:{secs:02d}"

    def format_setting_value(self, key, value):
        if key == "playback_speed":
            return f"{value:.2f}x"
        if key in {"sync_offset", "gap_threshold"}:
            return f"{value:.2f}s"
        if key == "font_size":
            return f"{int(value)} px"
        return f"{value:.2f}"

    def show_speed_loading(self, status_text):
        self.speed_status_label.configure(text=status_text or "Adjusting pitch...")
        if not self.speed_status_label.winfo_ismapped():
            self.speed_status_label.grid()
            self.speed_status_bar.grid()
            self.speed_status_bar.start()

    def hide_speed_loading(self):
        if self.speed_status_label.winfo_ismapped():
            self.speed_status_bar.stop()
            self.speed_status_label.grid_remove()
            self.speed_status_bar.grid_remove()
