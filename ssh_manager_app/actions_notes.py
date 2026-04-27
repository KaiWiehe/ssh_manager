from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .dialogs_toast import ToastNotification
from .storage import save_notes


def edit_session_note(app, session) -> None:
    dialog = tk.Toplevel(app)
    dialog.title("Notiz bearbeiten")
    dialog.resizable(False, False)
    dialog.transient(app)
    dialog.grab_set()

    frame = ttk.Frame(dialog, padding=16)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(0, weight=1)

    ttk.Label(frame, text=f"Notiz für {session.display_name}:").grid(row=0, column=0, sticky="w", pady=(0, 6))
    note_text = tk.Text(frame, width=48, height=6)
    note_text.grid(row=1, column=0, sticky="ew")
    current = app._notes.get(session.key, "")
    if current:
        note_text.insert("1.0", current)
    note_text.focus_set()

    result = {"saved": False}

    def on_ok() -> None:
        note = note_text.get("1.0", "end").strip()
        if note:
            app._notes[session.key] = note
        else:
            app._notes.pop(session.key, None)
        save_notes(app._notes)
        result["saved"] = True
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=2, column=0, pady=(12, 0))
    ttk.Button(btn_frame, text="OK", command=on_ok, width=10).pack(side="left", padx=4)
    ttk.Button(btn_frame, text="Abbrechen", command=on_cancel, width=10).pack(side="left", padx=4)

    dialog.update_idletasks()
    pw = app.winfo_width()
    ph = app.winfo_height()
    px = app.winfo_x()
    py = app.winfo_y()
    w = dialog.winfo_reqwidth()
    h = dialog.winfo_reqheight()
    x = px + (pw - w) // 2
    y = py + (ph - h) // 2
    dialog.geometry(f"+{x}+{y}")
    dialog.bind("<Escape>", lambda _e: on_cancel())
    dialog.bind("<Control-Return>", lambda _e: on_ok())
    app.wait_window(dialog)
    if result["saved"]:
        app._tree.refresh(app._sessions)
        app._update_notes_info(session)
        app._persist_ui_state()
        ToastNotification(app, "Notiz gespeichert")
