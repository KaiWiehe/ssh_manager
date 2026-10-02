from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24


def build_dialog_header(
    parent: ttk.Frame,
    title: str,
    subtitle: str = "",
    *,
    row: int = 0,
    columnspan: int = 1,
) -> ttk.Frame:
    """Create the shared title/subtitle block used by modal dialogs."""
    header = ttk.Frame(parent, style="DialogHeader.TFrame")
    header.grid(row=row, column=0, columnspan=columnspan, sticky="ew", pady=(0, SPACE_LG))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, text=title, style="DialogTitle.TLabel").grid(row=0, column=0, sticky="w")
    if subtitle:
        ttk.Label(
            header,
            text=subtitle,
            style="DialogSubtitle.TLabel",
            wraplength=520,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(SPACE_XS, 0))
    return header


def build_dialog_actions(
    parent: ttk.Frame,
    *,
    row: int,
    primary_text: str,
    primary_command: Callable[[], None],
    cancel_command: Callable[[], None],
    columnspan: int = 1,
    primary_style: str = "Accent.TButton",
) -> ttk.Frame:
    """Create the shared right-aligned modal footer."""
    footer = ttk.Frame(parent, style="DialogActions.TFrame")
    footer.grid(row=row, column=0, columnspan=columnspan, sticky="ew", pady=(SPACE_LG, 0))
    footer.columnconfigure(0, weight=1)
    ttk.Separator(footer, orient="horizontal").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, SPACE_MD))
    ttk.Button(footer, text="Abbrechen", command=cancel_command, width=12).grid(row=1, column=1, padx=(0, SPACE_SM))
    ttk.Button(
        footer,
        text=primary_text,
        command=primary_command,
        width=12,
        style=primary_style,
    ).grid(row=1, column=2)
    return footer


def center_on_parent(window: tk.Toplevel, parent: tk.Misc) -> None:
    """Center a dialog while keeping its top-left corner on the visible screen."""
    window.update_idletasks()
    width = window.winfo_reqwidth()
    height = window.winfo_reqheight()
    x = parent.winfo_x() + (parent.winfo_width() - width) // 2
    y = parent.winfo_y() + (parent.winfo_height() - height) // 2
    try:
        screen_width = max(1, window.winfo_screenwidth())
        screen_height = max(1, window.winfo_screenheight())
    except (AttributeError, tk.TclError):
        # Lightweight test doubles and pre-initialization callers have no Tk screen handle.
        screen_width = screen_height = None
    if screen_width is not None and screen_height is not None:
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
    window.geometry(f"+{x}+{y}")
