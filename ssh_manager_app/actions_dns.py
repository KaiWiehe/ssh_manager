from __future__ import annotations

import threading
from tkinter import messagebox

from .dialogs_dns import DnsLookupDialog, DnsLookupResultsDialog
from .dialogs_toast import ToastNotification
from .dns_lookup import DnsLookupResult, resolve_dns_value
from .models import Session


def open_dns_lookup_dialog(app) -> None:
    dialog = DnsLookupDialog(app)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    query, mode = dialog.result
    _resolve_values_async(app, [(query, mode)])


def resolve_dns_for_sessions(app, sessions: list[Session]) -> None:
    values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for session in sessions:
        hostname = (session.hostname or "").strip()
        if not hostname or hostname.lower() in seen:
            continue
        seen.add(hostname.lower())
        values.append((hostname, "auto"))
    if not values:
        messagebox.showwarning("Keine Hosts", "Für die Auswahl sind keine Hostnamen oder IP-Adressen hinterlegt.", parent=app)
        return
    _resolve_values_async(app, values)


def _resolve_values_async(app, values: list[tuple[str, str]]) -> None:
    ToastNotification(app, "DNS/IP-Auflösung läuft...")

    def worker() -> None:
        results: list[DnsLookupResult] = []
        for value, mode in values:
            results.append(resolve_dns_value(value, mode=mode))

        def show_results() -> None:
            try:
                DnsLookupResultsDialog(app, results)
            except Exception as exc:
                messagebox.showerror("DNS/IP-Auflösung", f"Ergebnisse konnten nicht angezeigt werden:\n{exc}", parent=app)

        try:
            app.after(0, show_results)
        except Exception:
            return

    threading.Thread(target=worker, daemon=True).start()
