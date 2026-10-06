"""Deliver background results through a queue polled only by the Tk thread."""
from __future__ import annotations

import queue
import threading
from tkinter import messagebox


def run_worker(owner, work, on_success, on_error=None):
    events = queue.SimpleQueue()

    def worker():
        try:
            events.put((True, work()))
        except Exception as error:
            events.put((False, error))

    def pump():
        if not owner.winfo_exists():
            return
        try:
            ok, value = events.get_nowait()
        except queue.Empty:
            owner.after(50, pump)
            return
        if ok:
            on_success(value)
        elif on_error is not None:
            on_error(value)
        else:
            messagebox.showerror("Hintergrundaufgabe fehlgeschlagen", "Die Aufgabe konnte nicht abgeschlossen werden.", parent=owner)

    owner.after(50, pump)
    thread = threading.Thread(target=worker, daemon=True)
    try:
        thread.start()
    except (RuntimeError, OSError) as error:
        events.put((False, error))
    return thread
