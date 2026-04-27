from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ToastNotification(tk.Toplevel):
    """Kleines unauffälliges Toast oben rechts."""

    def __init__(self, parent: tk.Tk, message: str, duration_ms: int = 2200):
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        frame = ttk.Frame(self, padding=(12, 8), style="Toast.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=message, style="Toast.TLabel").pack()

        self.update_idletasks()
        parent.update_idletasks()

        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        x = parent.winfo_rootx() + parent.winfo_width() - width - 16
        y = parent.winfo_rooty() + 16
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.after(duration_ms, self.destroy)


# ---------------------------------------------------------------------------
# SSHManagerApp
# ---------------------------------------------------------------------------
