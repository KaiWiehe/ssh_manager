from __future__ import annotations

import ipaddress
from concurrent.futures import ThreadPoolExecutor
from .workers import run_worker
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
    from .parallelism import choose_parallelism
    limit = choose_parallelism(app, len(values), default=4, title="DNS/IP auflösen") if len(values) > 1 else 4
    if limit is not None:
        _resolve_values_async(app, values, max_parallel=limit)


def resolve_dns_for_sessions_with_server_selection(app, sessions: list[Session]) -> None:
    values = _session_lookup_values(sessions)
    if not values:
        messagebox.showwarning("Keine Hosts", "Für die Auswahl sind keine Hostnamen oder IP-Adressen hinterlegt.", parent=app)
        return
    dialog = DnsServerDialog(app, len(values))
    app.wait_window(dialog)
    if dialog.result is None:
        return
    _resolve_values_async(app, values, dns_server=dialog.result or None, max_parallel=dialog.max_parallel)


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
    max_parallel: int = 4,
) -> None:
    progress = DnsLookupProgressDialog(app, len(values))

    def worker() -> None:
        results: list[DnsLookupResult] = []
        unique = {(value.lower(), mode, dns_server): (value, mode) for value, mode, _ in values}
        def resolve(entry):
            key, (value, mode) = entry
            if progress.cancelled:
                return key, None
            from .dns_lookup import socket_lookup_executor
            token = socket_lookup_executor.set(socket_pool)
            try:
                result = resolve_dns_value(value, mode=mode, **({"dns_server": dns_server} if dns_server else {}))
            finally:
                socket_lookup_executor.reset(token)
            return key, result
        from .parallelism import worker_count
        count = worker_count(len(unique), max_parallel)
        socket_pool = ThreadPoolExecutor(max_workers=count, thread_name_prefix="dns-socket")
        try:
            with ThreadPoolExecutor(max_workers=count, thread_name_prefix="dns-batch") as pool:
                cache = dict(pool.map(resolve, unique.items()))
        finally:
            socket_pool.shutdown(wait=False, cancel_futures=True)
        for value, mode, connection_name in values:
            if progress.cancelled:
                return
            result = cache[(value.lower(), mode, dns_server)]
            matched_name = connection_name
            if not matched_name and match_sessions:
                matched_name = _matching_connection_names(result, match_sessions)
            results.append(replace(result, connection_name=matched_name))

        return results

    def done(results):
        if not progress.cancelled:
            _show_dns_lookup_results(app, progress, results)

    def failed(error):
        if not progress.cancelled:
            progress.close()
            messagebox.showerror("DNS/IP-Auflösung", "Die Auflösung ist unerwartet fehlgeschlagen. Bitte erneut versuchen.", parent=app)

    run_worker(app, worker, done, failed)



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
