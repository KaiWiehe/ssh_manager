from __future__ import annotations

import threading
from dataclasses import replace
from tkinter import messagebox

from .dialogs_dns import DnsLookupDialog, DnsLookupProgressDialog, DnsLookupResultsDialog
from .dns_lookup import DnsLookupResult, resolve_dns_value
from .models import Session


def open_dns_lookup_dialog(app) -> None:
    dialog = DnsLookupDialog(app)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    query, mode = dialog.result
    _resolve_values_async(app, [(query, mode, "")])


def resolve_dns_for_sessions(app, sessions: list[Session]) -> None:
    values: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for session in sessions:
        hostname = (session.hostname or "").strip()
        session_key = session.key.lower()
        if not hostname or session_key in seen:
            continue
        seen.add(session_key)
        values.append((hostname, "auto", session.display_name or hostname))
    if not values:
        messagebox.showwarning("Keine Hosts", "Für die Auswahl sind keine Hostnamen oder IP-Adressen hinterlegt.", parent=app)
        return
    _resolve_values_async(app, values)


def _resolve_values_async(app, values: list[tuple[str, str, str]]) -> None:
    progress = DnsLookupProgressDialog(app, len(values))

    def worker() -> None:
        results: list[DnsLookupResult] = []
        cache: dict[tuple[str, str], DnsLookupResult] = {}
        for value, mode, connection_name in values:
            if progress.cancelled:
                return
            cache_key = (value.lower(), mode)
            result = cache.get(cache_key)
            if result is None:
                result = resolve_dns_value(value, mode=mode)
                cache[cache_key] = result
            results.append(replace(result, connection_name=connection_name))

        if progress.cancelled:
            return
        try:
            app.after(0, lambda: _show_dns_lookup_results(app, progress, results))
        except Exception:
            return

    threading.Thread(target=worker, daemon=True).start()


def _show_dns_lookup_results(app, progress: DnsLookupProgressDialog, results: list[DnsLookupResult]) -> None:
    if progress.cancelled:
        return
    try:
        progress.close()
        DnsLookupResultsDialog(app, results)
    except Exception as exc:
        try:
            progress.close()
        except Exception:
            pass
        messagebox.showerror("DNS/IP-Auflösung", f"Ergebnisse konnten nicht angezeigt werden:\n{exc}", parent=app)
