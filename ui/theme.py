PALETTE = {
    "surface": "#1f232a",
    "panel": "#242a33",
    "panel_alt": "#2a313c",
    "card": "#2b323d",
    "card_hover": "#343d4a",
    "card_border": "#3f4a5a",
    "muted_text": "#aeb7c3",
    "warning": "#f0b34a",
    "success": "#5ac18e",
    "accent": "#2CC985",
    "accent_hover": "#229966",
    "accent_alt": "#8b6c2d",
    "accent_alt_hover": "#7a5e28",
    "button_neutral": "#555f6e",
    "button_neutral_hover": "#677283",
    "option_fg": "#2b323d",
    "option_button": "#4a576a",
    "option_button_hover": "#5a6a81",
    "option_dropdown_fg": "#242a33",
    "option_dropdown_hover": "#343d4a",
    "option_text": "#e6ebf2",
    "option_shell_bg": "#1f252e",
}

SPACING = {
    "outer": 12,
    "inner": 10,
    "section_gap": 8,
    "card_gap": 8,
    "compact": 6,
    "control_y": 8,
    "control_x": 10,
    "viewport_inset": 10,
    "modal_outer": 16,
    "micro": 2,
}

RADIUS = {
    "card": 10,
    "control": 8,
    "tiny": 4,
}


def frame_style(fg_color, radius):
    return {
        "fg_color": fg_color,
        "corner_radius": radius,
        "border_width": 1,
        "border_color": PALETTE["card_border"],
    }


def option_menu_style():
    return {
        "height": 32,
        "corner_radius": RADIUS["control"],
        "fg_color": PALETTE["option_fg"],
        "button_color": PALETTE["option_button"],
        "button_hover_color": PALETTE["option_button_hover"],
        "text_color": PALETTE["option_text"],
        "dropdown_fg_color": PALETTE["option_dropdown_fg"],
        "dropdown_hover_color": PALETTE["option_dropdown_hover"],
        "dropdown_text_color": PALETTE["option_text"],
    }
