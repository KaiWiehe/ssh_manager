from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24


def install_context_help(dialog, topic, *, layout="pack", row=1):
    """Expose task help and temporarily transfer a modal grab to the help."""
    def show(_event=None):
        from .help import open_help
        app = dialog._root()
        previous = dialog.grab_current()
        window = open_help(app, topic)
        if previous is not None and previous is not window:
            window._return_grab = previous
            window.transient(previous)
            window.grab_set()
        window.lift()
        window.focus_force()
        return "break"
    bar = ttk.Frame(dialog, padding=(12, 4))
    if layout == "grid":
        bar.grid(row=row, column=0, sticky="ew")
    else:
        bar.pack(side="bottom", fill="x")
    button = ttk.Button(bar, text="Was passiert hier?", command=show)
    button.pack(side="left")
    dialog._context_help_button = button
    dialog.bind("<F1>", show, add="+")
    return button


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


def fit_window_to_parent(
    window: tk.Toplevel,
    parent: tk.Misc,
    preferred_width: int,
    preferred_height: int,
    *,
    min_width: int = 420,
    min_height: int = 300,
    margin: int = 40,
) -> None:
    """Size complex dialogs to the usable parent/screen area and center them."""
    window.update_idletasks()
    try:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
    except (AttributeError, tk.TclError):
        screen_width = max(parent.winfo_width(), preferred_width)
        screen_height = max(parent.winfo_height(), preferred_height)
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()
    parent_available_width = parent_width - margin if parent_width > 1 else screen_width - margin
    parent_available_height = parent_height - margin if parent_height > 1 else screen_height - margin
    available_width = max(320, min(screen_width - margin, parent_available_width))
    available_height = max(240, min(screen_height - margin, parent_available_height))
    width = min(preferred_width, available_width)
    height = min(preferred_height, available_height)
    window.minsize(min(min_width, width), min(min_height, height))
    x = parent.winfo_x() + max((parent_width - width) // 2, 0)
    y = parent.winfo_y() + max((parent_height - height) // 2, 0)
    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))
    window.geometry(f"{width}x{height}+{x}+{y}")


def set_validation_state(
    widget: ttk.Widget | None,
    error_var: tk.StringVar | None,
    message: str = "",
    *,
    normal_style: str = "TEntry",
    invalid_style: str = "Invalid.TEntry",
) -> None:
    """Show an inline field error while retaining existing dialog validation behavior."""
    if error_var is not None:
        error_var.set(message)
    if widget is not None:
        widget.configure(style=invalid_style if message else normal_style)
        if message:
            widget.focus_set()


class TooltipPopup:
    """Theme-aware tooltip surface shared by tree rows and the command palette."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        x: int,
        y: int,
        *,
        wraplength: int = 440,
        offset: tuple[int, int] = (12, 16),
    ) -> None:
        self._window = tk.Toplevel(master)
        self._window.wm_overrideredirect(True)
        try:
            self._window.attributes("-topmost", True)
        except tk.TclError:
            pass
        style = ttk.Style(master)
        background = style.lookup("TFrame", "background") or "SystemWindow"
        foreground = style.lookup("TLabel", "foreground") or "SystemWindowText"
        border = style.lookup("TEntry", "bordercolor") or background
        label = tk.Label(
            self._window,
            text=text,
            justify="left",
            background=background,
            foreground=foreground,
            relief="solid",
            borderwidth=1,
            highlightbackground=border,
            padx=8,
            pady=6,
            wraplength=wraplength,
        )
        label.pack()
        self._window.update_idletasks()
        target_x = x + offset[0]
        target_y = y + offset[1]
        target_x = min(target_x, max(0, self._window.winfo_screenwidth() - self._window.winfo_reqwidth() - 4))
        target_y = min(target_y, max(0, self._window.winfo_screenheight() - self._window.winfo_reqheight() - 4))
        self._window.geometry(f"+{max(0, target_x)}+{max(0, target_y)}")

    def destroy(self) -> None:
        self._window.destroy()
