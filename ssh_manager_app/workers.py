"""Deliver background results through a queue polled only by the Tk thread."""
from __future__ import annotations

import queue
import threading
from tkinter import messagebox


def run_worker(owner, work, on_success, on_error=None):
    events = queue.SimpleQueue()
    timer = None
    binding = None

    def cancel(event):
        if event.widget is owner and timer is not None:
            owner.after_cancel(timer)

    def worker():
        try:
            events.put((True, work()))
        except Exception as error:
            events.put((False, error))

    def pump():
        nonlocal timer
        timer = None
        if not owner.winfo_exists():
            return
        try:
            ok, value = events.get_nowait()
        except queue.Empty:
            timer = owner.after(50, pump)
            return
        if binding is not None:
            owner.unbind("<Destroy>", binding)
        if not ok:
            from .errors import record_failure
            record_failure(value)
        if ok:
            on_success(value)
        elif on_error is not None:
            on_error(value)
        else:
            messagebox.showerror("Hintergrundaufgabe fehlgeschlagen", "Die Aufgabe konnte nicht abgeschlossen werden.", parent=owner)

    binding = owner.bind("<Destroy>", cancel, add="+")
    timer = owner.after(50, pump)
    thread = threading.Thread(target=worker, daemon=True)
    try:
        thread.start()
    except (RuntimeError, OSError) as error:
        events.put((False, error))
    return thread
