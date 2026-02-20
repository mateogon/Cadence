QSS = """
QWidget {
  background: #1f232a;
  color: #e6ebf2;
  font-family: "Segoe UI";
  font-size: 13px;
}

QWidget#RootWindow {
  background: transparent;
}

QFrame#WindowShell {
  background: #242a33;
  border: 1px solid #323c49;
  border-radius: 10px;
}

QLabel {
  background: transparent;
}

QCheckBox {
  background: transparent;
}

QFrame#Sidebar, QFrame#MainArea, QFrame#Footer {
  background: #242a33;
}

QWidget#LibraryPageRoot, QWidget#PlayerPageRoot, QWidget#PlayerContentRoot {
  background: #242a33;
}

QStackedWidget#MainViewStack {
  background: #242a33;
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

QFrame#BottomCornerCap {
  background: #242a33;
  border: 1px solid #323c49;
  border-top: none;
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

QFrame#BottomCapDivider {
  background: #3f4a5a;
  border: none;
}

QFrame#WindowTitleBar {
  background: __TITLE_BG__;
  border-bottom: 1px solid __TITLE_BORDER__;
  border-top-left-radius: 10px;
  border-top-right-radius: 10px;
}

QFrame#Footer {
  border-bottom-left-radius: 10px;
  border-bottom-right-radius: 10px;
}

QLabel#WindowTitleLabel {
  color: __TITLE_TEXT__;
  font-size: 14px;
  font-weight: 600;
  padding-bottom: 2px;
}

QLabel#WindowLogo {
  background: transparent;
}

QPushButton#TitleBarButton, QPushButton#TitleBarMaxButton {
  color: __TITLE_TEXT__;
  border: none;
  background: transparent;
  border-radius: 0px;
  min-width: 36px;
  max-width: 36px;
  min-height: 36px;
  max-height: 36px;
  padding: 0;
  font-size: 13px;
}

QPushButton#TitleBarButton:hover, QPushButton#TitleBarMaxButton:hover {
  background: __TITLE_HOVER__;
}

QPushButton#TitleBarMaxButton {
  font-size: 20px;
  font-weight: 400;
  padding-bottom: 6px;
}

QPushButton#TitleBarCloseButton {
  color: __TITLE_TEXT__;
  border: none;
  background: transparent;
  border-radius: 0px;
  border-top-right-radius: 10px;
  min-width: 40px;
  max-width: 40px;
  min-height: 36px;
  max-height: 36px;
  padding: 0;
  font-size: 20px;
  font-weight: 600;
}

QPushButton#TitleBarCloseButton:hover {
  background: __TITLE_CLOSE_HOVER__;
  color: __TITLE_CLOSE_TEXT__;
  border-top-right-radius: 10px;
}

QFrame#ControlsCard, QFrame#LogCard {
  background: #2d3642;
  border: 1px solid #3f4a5a;
  border-radius: 10px;
}

QFrame#ListShell {
  background: #27303b;
  border: 1px solid #3f4a5a;
  border-radius: 10px;
}

QFrame#BrandCard {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-left: 4px solid #2CC985;
  border-radius: 10px;
}

QLabel#BrandTitle {
  font-size: 32px;
  font-weight: 700;
  color: #d7dee8;
}

QLabel#BrandBadge {
  background: transparent;
}

QLabel#SectionLabel {
  color: #aeb7c3;
  font-size: 12px;
  font-weight: 600;
}

QLabel#MainTitle {
  font-size: 22px;
  font-weight: 600;
}

QLineEdit, QComboBox, QPlainTextEdit {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-radius: 8px;
  padding: 6px;
}

QComboBox {
  padding-right: 26px;
}

QComboBox:hover {
  background: #343d4a;
}

QComboBox::drop-down {
  subcontrol-origin: padding;
  subcontrol-position: top right;
  width: 22px;
  border-left: 1px solid #3f4a5a;
  border-top-right-radius: 8px;
  border-bottom-right-radius: 8px;
  background: #343d4a;
}

QComboBox::drop-down:hover {
  background: #3c4656;
}

QComboBox::down-arrow {
  image: url(qt/assets/chevron_down_white.svg);
  width: 10px;
  height: 6px;
  margin-right: 7px;
  margin-left: 2px;
}

QComboBox::down-arrow:on {
  top: 0px;
  left: 0px;
}

QComboBox QAbstractItemView {
  background: #242a33;
  border: 1px solid #3f4a5a;
  selection-background-color: #343d4a;
  selection-color: #e6ebf2;
  outline: 0;
}

QPushButton {
  background: #2b323d;
  border: 1px solid #3f4a5a;
  border-top: 1px solid #4d596b;
  border-radius: 8px;
  padding: 6px 10px;
  min-height: 24px;
  font-weight: 600;
}

QPushButton:hover {
  background: #343d4a;
}

QPushButton:pressed {
  background: #3c4656;
}

QPushButton:focus {
  border-color: #3f4a5a;
  border-top-color: #4d596b;
}

QPushButton#ImportButton {
  background: #2CC985;
  color: #0e1612;
  border: 1px solid #2CC985;
  border-top: 1px solid #2CC985;
  font-weight: 600;
}

QPushButton#ImportButton:hover {
  background: #229966;
}

QPushButton#ContinueButton {
  background: #8b6c2d;
  border: 1px solid #8b6c2d;
  color: #f2ead6;
}

QPushButton#ContinueButton:hover {
  background: #7a5e28;
}

QPushButton#ReadButton {
  background: #2CC985;
  border: 1px solid #2CC985;
  border-top: 1px solid #2CC985;
  color: #0e1612;
  font-weight: 600;
}

QPushButton#ReadButton:hover {
  background: #229966;
}

QProgressBar {
  border: 1px solid #3f4a5a;
  border-radius: 8px;
  background: #2b323d;
  text-align: center;
  outline: none;
}

QProgressBar::chunk {
  background-color: #2CC985;
  border-radius: 7px;
}

QSlider::groove:horizontal {
  height: 8px;
  background: #242a33;
  border: none;
  border-radius: 5px;
}

QSlider:focus {
  outline: none;
}

QSlider {
  background: transparent;
  border: none;
}

QSlider::sub-page:horizontal {
  background: #2CC985;
  border: none;
  border-radius: 5px;
}

QSlider::add-page:horizontal {
  background: #242a33;
  border: none;
  border-radius: 5px;
}

QSlider::handle:horizontal {
  background: #d7dde8;
  border: 1px solid #7a8799;
  width: 16px;
  margin: -5px 0;
  border-radius: 8px;
}

QSlider::handle:horizontal:hover {
  background: #ffffff;
}

QScrollArea {
  border: none;
  background: #27303b;
}

QScrollArea > QWidget > QWidget {
  background: #27303b;
}

QFrame#BookCard {
  border: 1px solid #3f4a5a;
  border-radius: 10px;
  background: #27303b;
}

QFrame#BookCard:hover {
  background: #334252;
}

QLabel#BookTitle {
  font-size: 16px;
  font-weight: 600;
}

QLabel#BookMeta {
  color: #aeb7c3;
}

QLabel#BookStatusComplete {
  color: #5ac18e;
  font-weight: 600;
}

QLabel#BookStatusIncomplete {
  color: #f0b34a;
  font-weight: 600;
}

QFrame#BookCardShell {
  border: none;
  background: transparent;
}

QFrame#BookCardShell > QWidget {
  border: 1px solid #3f4a5a;
  border-radius: 10px;
  background: #27303b;
}

QFrame#PlayerSettingsCard {
  border: 1px solid #3f4a5a;
  border-radius: 10px;
  background: #27303b;
}

QScrollArea#RuntimeSettingsScroll {
  background: #1f232a;
  border: none;
}

QScrollArea#RuntimeSettingsScroll > QWidget > QWidget {
  background: #1f232a;
}

QFrame#PlayerPanel {
  background: #27303b;
  border: 1px solid #3f4a5a;
  border-radius: 12px;
}

QListWidget {
  background: transparent;
  border: none;
  border-radius: 10px;
  outline: none;
}

QListWidget::item {
  padding: 6px 8px;
  border-radius: 8px;
}

QListWidget::item:hover {
  background: #3c4656;
}

QListWidget::item:selected {
  background: #343d4a;
  color: #e6ebf2;
}

QListWidget::item:selected:active,
QListWidget::item:selected:!active {
  background: #343d4a;
  color: #e6ebf2;
}

QScrollBar:vertical {
  background: #242a33;
  width: 12px;
  margin: 1px;
  border-radius: 6px;
  border: none;
}

QScrollBar::handle:vertical {
  background: #4a5668;
  min-height: 30px;
  border-radius: 7px;
}

QScrollBar::handle:vertical:hover {
  background: #5a6880;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::up-arrow:vertical,
QScrollBar::down-arrow:vertical {
  height: 0px;
  background: transparent;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
  background: transparent;
}

QScrollBar:horizontal {
  background: #242a33;
  height: 12px;
  margin: 1px;
  border-radius: 6px;
  border: none;
}

QScrollBar::handle:horizontal {
  background: #4a5668;
  min-width: 30px;
  border-radius: 7px;
}

QScrollBar::handle:horizontal:hover {
  background: #5a6880;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::left-arrow:horizontal,
QScrollBar::right-arrow:horizontal {
  width: 0px;
  background: transparent;
}

QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal {
  background: transparent;
}
"""


STYLE_PROFILES = {
    "cadence": {
        "bg_root": "#1f232a",
        "bg_shell": "#242a33",
        "bg_panel": "#2b323d",
        "bg_panel_l2": "#2d3642",
        "bg_panel_l3": "#27303b",
        "bg_panel_l3_hover": "#334252",
        "border_main": "#323c49",
        "border_panel": "#3f4a5a",
        "border_top": "#4d596b",
        "accent": "#2CC985",
        "accent_hover": "#229966",
        "accent_text": "#0e1612",
        "ui_hover": "#343d4a",
        "ui_hover_strong": "#3c4656",
        "scroll_thumb": "#4a5668",
        "scroll_thumb_hover": "#5a6880",
        "text_main": "#e6ebf2",
        "text_muted": "#aeb7c3",
        "shadow_color": "#000000",
        "shadow_alpha": 78,
        "shadow_blur": 24,
        "shadow_offset_x": 0,
        "shadow_offset_y": 3,
        "title_bg": "#1b2430",
        "title_border": "#323c49",
        "title_text": "#d7dee8",
        "title_hover": "rgba(215, 222, 232, 0.14)",
        "title_close_hover": "#d9534f",
        "title_close_text": "#ffffff",
    },
    "professional": {
        "bg_root": "#1c1f24",
        "bg_shell": "#24282f",
        "bg_panel": "#2c323b",
        "bg_panel_l2": "#313844",
        "bg_panel_l3": "#2a313d",
        "bg_panel_l3_hover": "#364051",
        "border_main": "#3a414d",
        "border_panel": "#4a5362",
        "border_top": "#5b677a",
        "accent": "#3BA5F0",
        "accent_hover": "#2f8dcd",
        "accent_text": "#0d1a26",
        "ui_hover": "#3a4453",
        "ui_hover_strong": "#465466",
        "scroll_thumb": "#56667d",
        "scroll_thumb_hover": "#6a7e99",
        "text_main": "#e9edf4",
        "text_muted": "#b6c0cd",
        "shadow_color": "#000000",
        "shadow_alpha": 72,
        "shadow_blur": 26,
        "shadow_offset_x": 0,
        "shadow_offset_y": 3,
        "title_bg": "#1f2835",
        "title_border": "#3a414d",
        "title_text": "#e9edf4",
        "title_hover": "rgba(233, 237, 244, 0.16)",
        "title_close_hover": "#c94f4f",
        "title_close_text": "#ffffff",
    },
    "gold": {
        "bg_root": "#1f232a",
        "bg_shell": "#242a33",
        "bg_panel": "#2b323d",
        "bg_panel_l2": "#2d3642",
        "bg_panel_l3": "#27303b",
        "bg_panel_l3_hover": "#334252",
        "border_main": "#45403a",
        "border_panel": "#615749",
        "border_top": "#756b5a",
        "accent": "#D4AF37",
        "accent_hover": "#b5942f",
        "accent_text": "#1a1406",
        "ui_hover": "#343d4a",
        "ui_hover_strong": "#3c4656",
        "scroll_thumb": "#4a5668",
        "scroll_thumb_hover": "#5a6880",
        "text_main": "#f0eadf",
        "text_muted": "#cdbf9f",
        "shadow_color": "#000000",
        "shadow_alpha": 84,
        "shadow_blur": 24,
        "shadow_offset_x": 0,
        "shadow_offset_y": 3,
        "title_bg": "#2a2620",
        "title_border": "#45403a",
        "title_text": "#f0eadf",
        "title_hover": "rgba(240, 234, 223, 0.16)",
        "title_close_hover": "#b74c43",
        "title_close_text": "#ffffff",
    },
    "graphite": {
        "bg_root": "#1a1c1f",
        "bg_shell": "#23262b",
        "bg_panel": "#2c3138",
        "bg_panel_l2": "#313740",
        "bg_panel_l3": "#2a3038",
        "bg_panel_l3_hover": "#37404c",
        "border_main": "#3a414b",
        "border_panel": "#4b5562",
        "border_top": "#5f6c7d",
        "accent": "#7aa2f7",
        "accent_hover": "#6285cc",
        "accent_text": "#0d1323",
        "ui_hover": "#3b4450",
        "ui_hover_strong": "#485464",
        "scroll_thumb": "#5a687a",
        "scroll_thumb_hover": "#6c7e94",
        "text_main": "#e7ebf2",
        "text_muted": "#acb6c5",
        "shadow_color": "#000000",
        "shadow_alpha": 80,
        "shadow_blur": 24,
        "shadow_offset_x": 0,
        "shadow_offset_y": 3,
        "title_bg": "#20242a",
        "title_border": "#3a414b",
        "title_text": "#e7ebf2",
        "title_hover": "rgba(231, 235, 242, 0.16)",
        "title_close_hover": "#c04c4c",
        "title_close_text": "#ffffff",
    },
    "midnight": {
        "bg_root": "#111823",
        "bg_shell": "#162130",
        "bg_panel": "#1d2b3f",
        "bg_panel_l2": "#213349",
        "bg_panel_l3": "#1c2b3f",
        "bg_panel_l3_hover": "#28405c",
        "border_main": "#2b3a50",
        "border_panel": "#3a4d69",
        "border_top": "#4b6488",
        "accent": "#4cc9f0",
        "accent_hover": "#3aa8ca",
        "accent_text": "#04121a",
        "ui_hover": "#2d4059",
        "ui_hover_strong": "#375070",
        "scroll_thumb": "#4b678b",
        "scroll_thumb_hover": "#5f80aa",
        "text_main": "#e6edf7",
        "text_muted": "#9fb0c8",
        "shadow_color": "#000000",
        "shadow_alpha": 86,
        "shadow_blur": 26,
        "shadow_offset_x": 0,
        "shadow_offset_y": 4,
        "title_bg": "#142033",
        "title_border": "#2b3a50",
        "title_text": "#e6edf7",
        "title_hover": "rgba(230, 237, 247, 0.16)",
        "title_close_hover": "#c44d48",
        "title_close_text": "#ffffff",
    },
    "ember": {
        "bg_root": "#1d1816",
        "bg_shell": "#26201d",
        "bg_panel": "#312925",
        "bg_panel_l2": "#3a302b",
        "bg_panel_l3": "#322a26",
        "bg_panel_l3_hover": "#41352f",
        "border_main": "#463933",
        "border_panel": "#5b4a41",
        "border_top": "#725d52",
        "accent": "#e07a3f",
        "accent_hover": "#ba6533",
        "accent_text": "#1f1108",
        "ui_hover": "#463831",
        "ui_hover_strong": "#58463d",
        "scroll_thumb": "#6e584d",
        "scroll_thumb_hover": "#83685b",
        "text_main": "#f1e8df",
        "text_muted": "#c8b8ab",
        "shadow_color": "#000000",
        "shadow_alpha": 88,
        "shadow_blur": 24,
        "shadow_offset_x": 0,
        "shadow_offset_y": 4,
        "title_bg": "#2a211d",
        "title_border": "#463933",
        "title_text": "#f1e8df",
        "title_hover": "rgba(241, 232, 223, 0.16)",
        "title_close_hover": "#b24c41",
        "title_close_text": "#ffffff",
    },
    "forest": {
        "bg_root": "#162019",
        "bg_shell": "#1d2a21",
        "bg_panel": "#26352a",
        "bg_panel_l2": "#2b3d31",
        "bg_panel_l3": "#26382b",
        "bg_panel_l3_hover": "#304536",
        "border_main": "#33473a",
        "border_panel": "#425d4b",
        "border_top": "#547663",
        "accent": "#6fcf97",
        "accent_hover": "#58ad7d",
        "accent_text": "#0c1a12",
        "ui_hover": "#365040",
        "ui_hover_strong": "#42624f",
        "scroll_thumb": "#557865",
        "scroll_thumb_hover": "#67947c",
        "text_main": "#e8f1ea",
        "text_muted": "#acc2b2",
        "shadow_color": "#000000",
        "shadow_alpha": 84,
        "shadow_blur": 24,
        "shadow_offset_x": 0,
        "shadow_offset_y": 4,
        "title_bg": "#1f2d24",
        "title_border": "#33473a",
        "title_text": "#e8f1ea",
        "title_hover": "rgba(232, 241, 234, 0.16)",
        "title_close_hover": "#b84a47",
        "title_close_text": "#ffffff",
    },
    "rose": {
        "bg_root": "#231820",
        "bg_shell": "#2c1f29",
        "bg_panel": "#382734",
        "bg_panel_l2": "#412d3d",
        "bg_panel_l3": "#392938",
        "bg_panel_l3_hover": "#4a3550",
        "border_main": "#4a3550",
        "border_panel": "#614567",
        "border_top": "#7a5a80",
        "accent": "#f284b6",
        "accent_hover": "#c96c95",
        "accent_text": "#220d18",
        "ui_hover": "#533c57",
        "ui_hover_strong": "#67486b",
        "scroll_thumb": "#7e5b84",
        "scroll_thumb_hover": "#97709d",
        "text_main": "#f4e9f0",
        "text_muted": "#ccb1c1",
        "shadow_color": "#000000",
        "shadow_alpha": 86,
        "shadow_blur": 24,
        "shadow_offset_x": 0,
        "shadow_offset_y": 4,
        "title_bg": "#2f2130",
        "title_border": "#4a3550",
        "title_text": "#f4e9f0",
        "title_hover": "rgba(244, 233, 240, 0.16)",
        "title_close_hover": "#ba4a69",
        "title_close_text": "#ffffff",
    },
    "arctic": {
        "bg_root": "#e7ecf3",
        "bg_shell": "#edf2f8",
        "bg_panel": "#f6f8fc",
        "bg_panel_l2": "#f3f6fb",
        "bg_panel_l3": "#ffffff",
        "bg_panel_l3_hover": "#eef3fb",
        "border_main": "#c8d3e2",
        "border_panel": "#b5c3d8",
        "border_top": "#a8bad2",
        "accent": "#3b82f6",
        "accent_hover": "#2f69c9",
        "accent_text": "#ffffff",
        "ui_hover": "#e6edf8",
        "ui_hover_strong": "#d9e4f4",
        "scroll_thumb": "#bac8dc",
        "scroll_thumb_hover": "#a8bad2",
        "text_main": "#1d2a3a",
        "text_muted": "#4f647e",
        "shadow_color": "#000000",
        "shadow_alpha": 45,
        "shadow_blur": 22,
        "shadow_offset_x": 0,
        "shadow_offset_y": 2,
        "title_bg": "#dde7f5",
        "title_border": "#c8d3e2",
        "title_text": "#1d2a3a",
        "title_hover": "rgba(29, 42, 58, 0.10)",
        "title_close_hover": "#cf4c4c",
        "title_close_text": "#ffffff",
    },
}


def build_qss(profile: str = "cadence") -> str:
    selected = STYLE_PROFILES.get(profile, STYLE_PROFILES["cadence"])
    qss = QSS
    replacements = {
        "#1f232a": selected["bg_root"],
        "#242a33": selected["bg_shell"],
        "#2b323d": selected["bg_panel"],
        "#2d3642": selected.get("bg_panel_l2", selected["bg_panel"]),
        "#27303b": selected.get("bg_panel_l3", selected["bg_panel"]),
        "#334252": selected.get("bg_panel_l3_hover", selected.get("bg_panel_l3", selected["bg_panel"])),
        "#323c49": selected["border_main"],
        "#3f4a5a": selected["border_panel"],
        "#4d596b": selected.get("border_top", selected.get("border_panel", "#3f4a5a")),
        "#2CC985": selected["accent"],
        "#229966": selected["accent_hover"],
        "#0e1612": selected["accent_text"],
        "#343d4a": selected.get("ui_hover", "#343d4a"),
        "#3c4656": selected.get("ui_hover_strong", selected.get("ui_hover", "#3c4656")),
        "#4a5668": selected.get("scroll_thumb", "#4a5668"),
        "#5a6880": selected.get("scroll_thumb_hover", "#5a6880"),
        "#e6ebf2": selected["text_main"],
        "#aeb7c3": selected["text_muted"],
        "__TITLE_BG__": selected.get("title_bg", selected.get("bg_shell", "#242a33")),
        "__TITLE_BORDER__": selected.get("title_border", selected.get("border_main", "#323c49")),
        "__TITLE_TEXT__": selected.get("title_text", selected.get("text_main", "#e6ebf2")),
        "__TITLE_HOVER__": selected.get("title_hover", "rgba(215, 222, 232, 0.14)"),
        "__TITLE_CLOSE_HOVER__": selected.get("title_close_hover", "#d9534f"),
        "__TITLE_CLOSE_TEXT__": selected.get("title_close_text", "#ffffff"),
        "__FOCUS_RING__": selected.get("accent", "#2CC985"),
    }
    for source, target in replacements.items():
        qss = qss.replace(source, target)
    return qss


def transparent_bg_style() -> str:
    return "background: transparent;"


def horizontal_divider_style(color: str = "#3f4a5a") -> str:
    return f"background:{color};"


def vertical_divider_style(color: str = "#3f4a5a") -> str:
    return f"background:{color}; max-width:1px; min-width:1px;"


def color_swatch_style(color: str, border: str = "#3f4a5a") -> str:
    c = (color or "#000000").strip() or "#000000"
    b = (border or "#3f4a5a").strip() or "#3f4a5a"
    return f"border: 1px solid {b}; border-radius: 5px; background: {c};"


def player_panel_style(bg: str) -> str:
    return f"background: {bg}; border: 1px solid #3f4a5a; border-radius: 12px;"


def player_view_stack_style(bg: str) -> str:
    b = (bg or "#121212").strip() or "#121212"
    return f"background: {b}; border: none;"


def player_text_style(
    bg: str,
    text: str,
    *,
    border: str = "#3f4a5a",
    thumb: str = "#4a5668",
    thumb_hover: str = "#5a6880",
) -> str:
    b = (bg or "#121212").strip() or "#121212"
    _ = border
    _ = thumb
    _ = thumb_hover
    # Keep this as plain widget declarations only.
    # Mixing nested selectors here caused parse failures on some Qt builds.
    return (
        f"background: {b}; color: {text};"
        " border: none; padding: 10px;"
        " selection-background-color: #4e6488; selection-color: #ffffff;"
    )


def player_text_viewport_style(bg: str) -> str:
    b = (bg or "#121212").strip() or "#121212"
    return f"background: {b};"


def player_seek_style(
    *,
    shell_bg: str = "#242a33",
    border: str = "#3f4a5a",
    accent: str = "#2CC985",
) -> str:
    shell = (shell_bg or "#242a33").strip() or "#242a33"
    line = (border or "#3f4a5a").strip() or "#3f4a5a"
    fill = (accent or "#2CC985").strip() or "#2CC985"
    return (
        "QSlider::groove:horizontal {"
        f"height: 8px; background: {shell}; border: 1px solid {line}; border-radius: 5px; }}"
        "QSlider::sub-page:horizontal {"
        f"background: {fill}; border: 1px solid {fill}; border-radius: 5px; }}"
        "QSlider::add-page:horizontal {"
        f"background: {shell}; border: 1px solid {line}; border-radius: 5px; }}"
        "QSlider::handle:horizontal {"
        "background: #d7dde8; border: 1px solid #7a8799; width: 16px; margin: -5px 0; border-radius: 8px; }"
        "QSlider::handle:horizontal:hover { background: #ffffff; }"
    )
