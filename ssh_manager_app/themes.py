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
        bg="#f3f4f6",
        surface="#ffffff",
        surface_alt="#f9fafb",
        nav="#eef2f7",
        border="#d1d5db",
        text="#111827",
        muted="#6b7280",
        selected="#dbeafe",
        button_active="#eef2ff",
        toast_bg="#111827",
        toast_text="#f9fafb",
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
