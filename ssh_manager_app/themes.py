from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemePalette:
    bg: str
    surface: str
    surface_alt: str
    nav: str
    border: str
    text: str
    muted: str
    selected: str
    button_active: str
    toast_bg: str
    toast_text: str


THEME_PALETTES: dict[str, ThemePalette] = {
    "modern_light": ThemePalette(
        bg="#f5f7fa",
        surface="#ffffff",
        surface_alt="#f8fafc",
        nav="#eef2f6",
        border="#d8dee8",
        text="#172033",
        muted="#687386",
        selected="#e8f1ff",
        button_active="#edf3fb",
        toast_bg="#172033",
        toast_text="#ffffff",
    ),
    "dark_neutral": ThemePalette(
        bg="#111111",
        surface="#1f1f1f",
        surface_alt="#2a2a2a",
        nav="#181818",
        border="#3a3a3a",
        text="#f3f4f6",
        muted="#a3a3a3",
        selected="#303a4f",
        button_active="#2b2b2b",
        toast_bg="#050505",
        toast_text="#f9fafb",
    ),
    "midnight": ThemePalette(
        bg="#0f172a",
        surface="#162033",
        surface_alt="#1e293b",
        nav="#111827",
        border="#334155",
        text="#e5edf7",
        muted="#94a3b8",
        selected="#1d3b63",
        button_active="#24324a",
        toast_bg="#020617",
        toast_text="#e5edf7",
    ),
}


def palette_for_theme(theme: str) -> ThemePalette:
    """Resolve persisted theme keys without migrating users' settings files."""
    if theme in {"default", "modern_light"}:
        return THEME_PALETTES["modern_light"]
    return THEME_PALETTES.get(theme, THEME_PALETTES["modern_light"])


def bootstrap_theme_for(theme: str) -> str:
    """Return the ttkbootstrap foundation used by an SSH-Manager theme."""
    if theme == "dark_neutral":
        return "bootstrap-dark"
    if theme == "midnight":
        return "nord-dark"
    return "bootstrap-light"
