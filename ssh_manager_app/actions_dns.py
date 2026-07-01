from __future__ import annotations

import ipaddress
import threading
from dataclasses import replace
from tkinter import messagebox

from .dialogs_dns import DnsLookupDialog, DnsLookupProgressDialog, DnsLookupResultsDialog, DnsServerDialog
from .dns_lookup import DnsLookupResult, resolve_dns_value
from .models import Session


def open_dns_lookup_dialog(app) -> None:
    dialog = DnsLookupDialog(app)
    app.wait_window(dialog)
    if dialog.result is None:
        return
    query, mode, dns_server = dialog.result
    _resolve_values_async(
        app,
        [(query, mode, "")],
        dns_server=dns_server,
        match_sessions=_all_sessions(app),
    )


def resolve_dns_for_sessions(app, sessions: list[Session]) -> None:
    values = _session_lookup_values(sessions)
    if not values:
        messagebox.showwarning("Keine Hosts", "Für die Auswahl sind keine Hostnamen oder IP-Adressen hinterlegt.", parent=app)
        return
    _resolve_values_async(app, values)


def resolve_dns_for_sessions_with_server_selection(app, sessions: list[Session]) -> None:
    values = _session_lookup_values(sessions)
    if not values:
        messagebox.showwarning("Keine Hosts", "Für die Auswahl sind keine Hostnamen oder IP-Adressen hinterlegt.", parent=app)
        return
    dialog = DnsServerDialog(app, len(values))
    app.wait_window(dialog)
    if dialog.result is None:
        return
    _resolve_values_async(app, values, dns_server=dialog.result or None)


def _session_lookup_values(sessions: list[Session]) -> list[tuple[str, str, str]]:
    values: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for session in sessions:
        hostname = (session.hostname or "").strip()
        session_key = session.key.lower()
        if not hostname or session_key in seen:
            continue
        seen.add(session_key)
        values.append((hostname, "auto", session.display_name or hostname))
    return values


def _resolve_values_async(
    app,
    values: list[tuple[str, str, str]],
    *,
    dns_server: str | None = None,
    match_sessions: list[Session] | None = None,
) -> None:
    progress = DnsLookupProgressDialog(app, len(values))

    def worker() -> None:
        results: list[DnsLookupResult] = []
        cache: dict[tuple[str, str, str | None], DnsLookupResult] = {}
        for value, mode, connection_name in values:
            if progress.cancelled:
                return
            cache_key = (value.lower(), mode, dns_server)
            result = cache.get(cache_key)
            if result is None:
                if dns_server:
                    result = resolve_dns_value(value, mode=mode, dns_server=dns_server)
                else:
                    result = resolve_dns_value(value, mode=mode)
                cache[cache_key] = result
            matched_name = connection_name
            if not matched_name and match_sessions:
                matched_name = _matching_connection_names(result, match_sessions)
            results.append(replace(result, connection_name=matched_name))

        if progress.cancelled:
            return
        try:
            app.after(0, lambda: _show_dns_lookup_results(app, progress, results))
        except Exception:
            return

    threading.Thread(target=worker, daemon=True).start()


def _all_sessions(app) -> list[Session]:
    sessions: list[Session] = []
    seen: set[str] = set()
    source_names = ("_winscp_sessions", "_app_sessions", "_ssh_config_sessions", "_filezilla_sessions")
    sources_found = False
    for source_name in source_names:
        source_sessions = getattr(app, source_name, None)
        if source_sessions is None:
            continue
        sources_found = True
        for session in source_sessions:
            if session.key in seen:
                continue
            seen.add(session.key)
            sessions.append(session)
    if not sources_found:
        for session in getattr(app, "_sessions", []):
            if session.key in seen:
                continue
            seen.add(session.key)
            sessions.append(session)
    return sessions


def _matching_connection_names(result: DnsLookupResult, sessions: list[Session]) -> str:
    if result.mode != "forward" or result.status != "ok":
        return ""

    targets = {_normalize_host(result.query)}
    targets.update(_normalize_host(value) for value in result.results)
    names: list[str] = []
    seen_names: set[str] = set()
    seen_sessions: set[str] = set()
    for session in sessions:
        if session.key in seen_sessions or _normalize_host(session.hostname) not in targets:
            continue
        seen_sessions.add(session.key)
        name = (session.display_name or session.hostname).strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        names.append(name)
    return ", ".join(names)


def _normalize_host(value: str) -> str:
    cleaned = (value or "").strip().rstrip(".")
    try:
        return str(ipaddress.ip_address(cleaned))
    except ValueError:
        return cleaned.lower()


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
