import customtkinter as ctk
import tkinter as tk
import tkinter.font as tkfont
from tkinter import colorchooser

from ui.player_core import PlayerCore
from ui.theme import PALETTE, RADIUS, SPACING, frame_style, option_menu_style


class PlayerView(ctk.CTkFrame):
    RESIZE_SETTLE_MS = 600

    def __init__(self, parent, app, on_back, debug=False):
        super().__init__(parent)
        self.configure(fg_color=PALETTE["surface"])
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
        self._section_open_states = {}
        self._full_title_text = "No book open"
        self._title_update_after_id = None
        self._resize_done_after_id = None
        self._last_size_sig = None
        self._settings_controls_built = False
        self._settings_colors = {
            "section_bg": PALETTE["panel"],
            "section_border": PALETTE["card_border"],
            "header_bg": PALETTE["panel_alt"],
            "header_hover": PALETTE["card_hover"],
            "option_bg": PALETTE["card"],
            "option_border": PALETTE["card_border"],
            "sub_row_bg": PALETTE["surface"],
        }

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_columnconfigure(2, weight=0)
        self.grid_rowconfigure(4, weight=1)

        self.top_bar = ctk.CTkFrame(
            self, fg_color=PALETTE["panel"], corner_radius=0, border_width=0
        )
        self.top_bar.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=0,
            pady=0,
        )
        self.top_bar.grid_columnconfigure(1, weight=1)

        self.back_button = ctk.CTkButton(
            self.top_bar,
            text="← Library",
            width=110,
            command=self.handle_back,
        )
        self.back_button.grid(
            row=0, column=0, sticky="w", padx=(SPACING["section_gap"], 0), pady=SPACING["control_y"]
        )

        self.title_label = ctk.CTkLabel(
            self.top_bar,
            text="No book open",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
            fg_color="transparent",
        )
        self.title_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(SPACING["outer"], SPACING["outer"]),
            pady=SPACING["control_y"],
        )
        self.top_bar.bind("<Configure>", lambda _e: self._schedule_title_update())

        self.settings_button = ctk.CTkButton(
            self.top_bar,
            text="⚙ Settings",
            width=100,
            command=self.toggle_settings,
        )
        self.settings_button.grid(
            row=0,
            column=2,
            sticky="e",
            padx=(SPACING["section_gap"], SPACING["section_gap"]),
            pady=SPACING["control_y"],
        )

        self.top_divider = ctk.CTkFrame(self, height=1, fg_color=PALETTE["card_border"])
        self.top_divider.grid(row=1, column=0, columnspan=3, sticky="ew", padx=0, pady=0)

        self.progress_frame = ctk.CTkFrame(
            self, fg_color=PALETTE["panel"], corner_radius=0, border_width=0
        )
        self.progress_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=0,
            pady=(0, 0),
        )
        self.progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, mode="determinate")
        self.progress_bar.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=SPACING["control_x"],
            pady=(SPACING["control_y"], 0),
        )
        self.progress_bar.set(0)

        self.chapter_progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="Chapter -/-",
            text_color=PALETTE["muted_text"],
            font=ctk.CTkFont(size=12),
        )
        self.chapter_progress_label.grid(
            row=1,
            column=0,
            sticky="w",
            padx=SPACING["control_x"],
            pady=(4, SPACING["compact"]),
        )

        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="00:00 / 00:00",
            text_color=PALETTE["muted_text"],
            font=ctk.CTkFont(size=12),
        )
        self.progress_label.grid(
            row=1,
            column=0,
            sticky="e",
            padx=SPACING["control_x"],
            pady=(4, SPACING["compact"]),
        )

        self.speed_status_label = ctk.CTkLabel(
            self.progress_frame,
            text="Adjusting pitch...",
            text_color=PALETTE["warning"],
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.speed_status_label.grid(
            row=2, column=0, sticky="w", padx=SPACING["control_x"], pady=(2, 0)
        )
        self.speed_status_label.grid_remove()

        self.speed_status_bar = ctk.CTkProgressBar(self.progress_frame, mode="indeterminate")
        self.speed_status_bar.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=SPACING["control_x"],
            pady=(2, SPACING["control_y"]),
        )
        self.speed_status_bar.grid_remove()

        self.progress_divider = ctk.CTkFrame(self, height=1, fg_color=PALETTE["card_border"])
        self.progress_divider.grid(row=3, column=0, columnspan=3, sticky="ew", padx=0, pady=0)

        self.player_container = ctk.CTkFrame(
            self, fg_color=PALETTE["surface"], corner_radius=0, border_width=0
        )
        self.player_container.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=0,
            pady=0,
        )
        self.player_container.grid_rowconfigure(0, weight=1)
        self.player_container.grid_columnconfigure(0, weight=1)

        self.player_viewport = ctk.CTkFrame(
            self.player_container, **frame_style(PALETTE["panel"], RADIUS["card"])
        )
        self.player_viewport.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=SPACING["viewport_inset"],
            pady=SPACING["viewport_inset"],
        )

        self.content_divider = ctk.CTkFrame(self, width=1, fg_color=PALETTE["card_border"])
        self.content_divider.grid(row=4, column=1, sticky="ns", padx=0, pady=0)

        self.settings_drawer = ctk.CTkFrame(
            self,
            width=300,
            fg_color=PALETTE["panel"],
            corner_radius=0,
            border_width=0,
        )
        self.settings_drawer.grid(
            row=4,
            column=2,
            sticky="ns",
            padx=0,
            pady=0,
        )
        self.settings_drawer.grid_propagate(False)
        self.settings_drawer.grid_remove()

        self.settings_title = ctk.CTkLabel(
            self.settings_drawer, text="Player Settings", font=ctk.CTkFont(size=16, weight="bold")
        )
        self.settings_title.pack(
            anchor="w",
            padx=SPACING["outer"],
            pady=(SPACING["outer"], SPACING["section_gap"]),
        )

        self.settings_body = ctk.CTkScrollableFrame(
            self.settings_drawer,
            width=276,
            height=360,
            fg_color=PALETTE["panel"],
            corner_radius=0,
        )
        self.settings_body.pack(
            fill="both",
            expand=True,
            padx=SPACING["outer"],
            pady=(0, SPACING["section_gap"]),
        )
        self._boost_scrollable_frame_speed(self.settings_body, factor=6)

        self.drawer_buttons = ctk.CTkFrame(self.settings_drawer, fg_color="transparent")
        self.drawer_buttons.pack(
            fill="x",
            padx=SPACING["outer"],
            pady=(0, SPACING["outer"]),
        )
        self.drawer_buttons.grid_columnconfigure(0, weight=1)
        self.drawer_buttons.grid_columnconfigure(1, weight=1)
        self.drawer_buttons.grid_columnconfigure(2, weight=1)

        self.cancel_settings_button = ctk.CTkButton(
            self.drawer_buttons,
            text="Cancel",
            fg_color=PALETTE["button_neutral"],
            hover_color=PALETTE["button_neutral_hover"],
            command=self.cancel_settings,
        )
        self.cancel_settings_button.grid(
            row=0, column=0, sticky="ew", padx=(0, SPACING["compact"])
        )

        self.reset_settings_button = ctk.CTkButton(
            self.drawer_buttons,
            text="Reset",
            fg_color=PALETTE["accent_alt"],
            hover_color=PALETTE["accent_alt_hover"],
            command=self.reset_settings,
        )
        self.reset_settings_button.grid(
            row=0, column=1, sticky="ew", padx=(SPACING["micro"] + 1, SPACING["micro"] + 1)
        )

        self.save_settings_button = ctk.CTkButton(
            self.drawer_buttons,
            text="Save",
            fg_color=PALETTE["accent"],
            hover_color=PALETTE["accent_hover"],
            command=self.save_settings,
        )
        self.save_settings_button.grid(
            row=0, column=2, sticky="ew", padx=(SPACING["compact"], 0)
        )

        self.hint_label = ctk.CTkLabel(
            self,
            text="Esc returns to library. Space toggles playback.",
            text_color=PALETTE["muted_text"],
        )
        self.hint_label.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=0,
            pady=(0, SPACING["inner"]),
        )
        self.bind("<Configure>", self._on_view_configure)

    def _boost_scrollable_frame_speed(self, scrollable_frame, factor=6):
        # CTkScrollableFrame on Windows defaults to 1px yscrollincrement, which
        # feels sluggish. Raise it for this frame explicitly.
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

    def open_book(self, book_data):
        self.close_book()
        self.book_data = book_data
        self._full_title_text = book_data.get("title", "Unknown")
        self._update_title_label_text()
        self.core = PlayerCore(
            parent=self.player_viewport,
            book_path=book_data["path"],
            on_exit=self.handle_back,
            on_state_change=self.handle_state_change,
            debug=self.debug,
        )
        self.core.mount()
        self.saved_settings_snapshot = self.core.get_settings()
        self._settings_controls_built = False

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
        self._full_title_text = "No book open"
        self._update_title_label_text()
        self.chapter_progress_label.configure(text="Chapter -/-")
        self.progress_label.configure(text="00:00 / 00:00")
        self.progress_bar.set(0)
        self.hide_speed_loading()
        self.settings_drawer.grid_remove()
        self.settings_visible = False
        self.settings_button.configure(text="⚙ Settings")
        self._settings_controls_built = False

    def safe_close(self):
        if self.core is not None:
            self.core.unmount()
            self.core = None

    def toggle_settings(self):
        if self.core is None:
            return
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            if not self._settings_controls_built:
                self.build_settings_controls()
                current = self.core.get_settings()
                self.apply_settings_to_controls(current)
                self._settings_controls_built = True
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
        sections = self._group_settings_schema(schema)
        for section_name, specs in sections:
            section = ctk.CTkFrame(
                self.settings_body,
                fg_color=self._settings_colors["section_bg"],
                corner_radius=RADIUS["card"],
                border_width=0,
            )
            section.pack(fill="x", pady=(0, SPACING["section_gap"]), padx=0)

            header_row = ctk.CTkFrame(section, fg_color="transparent")
            header_row.pack(
                fill="x",
                padx=SPACING["section_gap"],
                pady=(SPACING["section_gap"], SPACING["compact"] - 2),
            )
            header_row.grid_columnconfigure(0, weight=1)

            default_open = section_name in {"Reading Mode", "Typography"}
            is_open = self._section_open_states.get(section_name, default_open)
            self._section_open_states[section_name] = is_open

            title_var = tk.StringVar()
            title_var.set(f"{'▾' if is_open else '▸'}  {section_name}")

            body = ctk.CTkFrame(section, fg_color="transparent")
            if is_open:
                body.pack(
                    fill="x",
                    padx=SPACING["section_gap"],
                    pady=(0, SPACING["section_gap"]),
                )

            def toggle_section(name=section_name, body_frame=body, title=title_var):
                open_now = bool(self._section_open_states.get(name, False))
                next_state = not open_now
                self._section_open_states[name] = next_state
                title.set(f"{'▾' if next_state else '▸'}  {name}")
                if next_state:
                    body_frame.pack(
                        fill="x",
                        padx=SPACING["section_gap"],
                        pady=(0, SPACING["section_gap"]),
                    )
                else:
                    body_frame.pack_forget()

            ctk.CTkButton(
                header_row,
                textvariable=title_var,
                anchor="w",
                fg_color=self._settings_colors["header_bg"],
                hover_color=self._settings_colors["header_hover"],
                command=toggle_section,
            ).grid(row=0, column=0, sticky="ew")

            for spec in specs:
                self._build_setting_control(body, spec)

    def _group_settings_schema(self, schema):
        by_key = {spec["key"]: spec for spec in schema}
        order = [
            ("Reading Mode", ["reading_view_mode", "context_force_center"]),
            ("Typography", ["font_family", "font_size"]),
            ("Colors", ["bg_color", "text_color", "focus_color", "secondary_text_color"]),
            ("Playback", ["playback_speed"]),
            ("Timing & Sync", ["sync_offset", "gap_threshold"]),
        ]
        sections = []
        used = set()
        for name, keys in order:
            group_specs = [by_key[key] for key in keys if key in by_key]
            used.update(key for key in keys if key in by_key)
            if group_specs:
                sections.append((name, group_specs))
        leftovers = [spec for spec in schema if spec["key"] not in used]
        if leftovers:
            sections.append(("Other", leftovers))
        return sections

    def _build_setting_control(self, parent, spec):
        key = spec["key"]
        label_text = spec.get("label", key)
        kind = spec.get("type")
        help_text = spec.get("help", "").strip()

        block = ctk.CTkFrame(
            parent,
            fg_color=self._settings_colors["option_bg"],
            corner_radius=RADIUS["control"],
            border_width=0,
        )
        block.pack(fill="x", pady=SPACING["compact"], padx=0)

        ctk.CTkLabel(block, text=label_text, anchor="w").pack(
            fill="x", padx=SPACING["control_x"], pady=(SPACING["control_y"], SPACING["micro"])
        )

        if kind == "bool":
            variable = tk.BooleanVar(value=False)
            switch = ctk.CTkSwitch(
                block,
                text="Enabled",
                variable=variable,
                command=lambda k=key, v=variable: self.on_bool_change(k, v.get()),
            )
            switch.pack(
                anchor="w",
                padx=SPACING["control_x"],
                pady=(0, SPACING["control_y"]),
            )
            self._control_refs[key] = {"kind": "bool", "var": variable}
        elif kind == "float":
            min_value = float(spec.get("min", 0.0))
            max_value = float(spec.get("max", 1.0))
            step = float(spec.get("step", 0.1))
            value_label = ctk.CTkLabel(block, text="", text_color=PALETTE["muted_text"])
            value_label.pack(
                anchor="e",
                padx=SPACING["control_x"],
                pady=(0, SPACING["micro"]),
            )
            slider = ctk.CTkSlider(
                block,
                from_=min_value,
                to=max_value,
                command=lambda raw, k=key, s=step, l=value_label: self.on_slider_change(
                    k, raw, s, l
                ),
            )
            slider.pack(
                fill="x",
                padx=SPACING["control_x"],
                pady=(0, SPACING["control_x"]),
            )
            self._control_refs[key] = {
                "kind": "float",
                "slider": slider,
                "step": step,
                "label": value_label,
            }
        elif kind == "choice":
            values = list(spec.get("values") or [])
            variable = tk.StringVar(value=values[0] if values else "")
            shell = ctk.CTkFrame(
                block,
                fg_color=PALETTE["option_shell_bg"],
                corner_radius=RADIUS["control"],
                border_width=0,
            )
            shell.pack(fill="x", padx=SPACING["control_x"], pady=(0, SPACING["control_x"]))
            option = ctk.CTkOptionMenu(
                shell,
                values=values if values else [""],
                variable=variable,
                **option_menu_style(),
                command=lambda selected, k=key: self.on_choice_change(k, selected),
            )
            option.pack(fill="x", padx=SPACING["compact"], pady=SPACING["compact"])
            self._control_refs[key] = {
                "kind": "choice",
                "var": variable,
                "option": option,
            }
        elif kind == "color":
            row = ctk.CTkFrame(block, fg_color=self._settings_colors["sub_row_bg"], corner_radius=6)
            row.pack(
                fill="x",
                padx=SPACING["control_x"],
                pady=(0, SPACING["control_x"]),
            )
            row.grid_columnconfigure(0, weight=1)
            value_var = tk.StringVar(value="#000000")
            value_label = ctk.CTkLabel(row, textvariable=value_var, text_color=PALETTE["muted_text"])
            value_label.grid(row=0, column=0, sticky="w")
            swatch = ctk.CTkLabel(
                row,
                text="",
                width=28,
                height=20,
                fg_color="#000000",
                corner_radius=RADIUS["tiny"],
            )
            swatch.grid(
                row=0, column=1, padx=(SPACING["compact"], SPACING["compact"])
            )
            pick = ctk.CTkButton(
                row,
                text="Pick",
                width=64,
                command=lambda k=key: self.pick_color(k),
            )
            pick.grid(row=0, column=2, sticky="e")
            self._control_refs[key] = {
                "kind": "color",
                "var": value_var,
                "label": value_label,
                "swatch": swatch,
            }

        if help_text:
            ctk.CTkLabel(
                block,
                text=help_text,
                text_color=PALETTE["muted_text"],
                anchor="w",
                justify="left",
                wraplength=250,
                font=ctk.CTkFont(size=11),
            ).pack(
                fill="x",
                padx=SPACING["control_x"],
                pady=(0, SPACING["control_y"]),
            )

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

    def on_choice_change(self, key, selected):
        if self._updating_controls or self.core is None:
            return
        self.core.update_settings({key: selected})

    def pick_color(self, key):
        if self.core is None:
            return
        ref = self._control_refs.get(key)
        if not ref or ref.get("kind") != "color":
            return
        initial = ref["var"].get()
        chosen = colorchooser.askcolor(color=initial, parent=self.winfo_toplevel())[1]
        if not chosen:
            return
        ref["var"].set(chosen)
        ref["swatch"].configure(fg_color=chosen)
        if not self._updating_controls:
            self.core.update_settings({key: chosen})

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
                elif ref["kind"] == "choice":
                    value = str(settings[key])
                    option = ref["option"]
                    values = option.cget("values")
                    if value not in values:
                        option.configure(values=[*values, value])
                    ref["var"].set(value)
                elif ref["kind"] == "color":
                    value = str(settings[key])
                    ref["var"].set(value)
                    ref["swatch"].configure(fg_color=value)
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

    def reset_settings(self):
        if self.core is None:
            return
        self.core.reset_settings_defaults()
        defaults = self.core.get_settings()
        self.apply_settings_to_controls(defaults)

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
        self._full_title_text = title
        self._update_title_label_text()
        self.chapter_progress_label.configure(text=f"Chapter {chapter}/{total}")

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

    def _update_title_label_text(self):
        if not hasattr(self, "title_label") or not self.title_label.winfo_exists():
            return
        full = (self._full_title_text or "").strip() or "No book open"
        try:
            available = int(self.title_label.winfo_width()) - 8
            if available <= 30:
                self._schedule_title_update(delay_ms=80)
                return
            f = tkfont.Font(font=self.title_label.cget("font"))
            if f.measure(full) <= available:
                self.title_label.configure(text=full)
                return
            ell = "..."
            if f.measure(ell) >= available:
                self.title_label.configure(text=ell)
                return
            lo, hi = 1, len(full)
            best = ell
            while lo <= hi:
                mid = (lo + hi) // 2
                candidate = full[:mid] + ell
                if f.measure(candidate) <= available:
                    best = candidate
                    lo = mid + 1
                else:
                    hi = mid - 1
            self.title_label.configure(text=best)
        except Exception:
            self.title_label.configure(text=full)

    def _schedule_title_update(self, delay_ms=70):
        if self._title_update_after_id:
            try:
                self.after_cancel(self._title_update_after_id)
            except Exception:
                pass
        self._title_update_after_id = self.after(delay_ms, self._run_title_update)

    def _run_title_update(self):
        self._title_update_after_id = None
        self._update_title_label_text()

    def _on_view_configure(self, _event):
        size_sig = (int(self.winfo_width()), int(self.winfo_height()))
        if self._last_size_sig == size_sig:
            return
        self._last_size_sig = size_sig
        if self.core is not None:
            self.core.set_ui_resizing(True)
        if self._resize_done_after_id:
            try:
                self.after_cancel(self._resize_done_after_id)
            except Exception:
                pass
        self._resize_done_after_id = self.after(self.RESIZE_SETTLE_MS, self._on_resize_settled)

    def _on_resize_settled(self):
        self._resize_done_after_id = None
        if self.core is not None:
            self.core.set_ui_resizing(False)
