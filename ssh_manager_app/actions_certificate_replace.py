from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from tkinter import messagebox

from .actions_remote import resolve_users_for_sessions
from .actions_ui import persist_ui_state
from .core import build_certificate_replace_wt_command
from .dialogs_certificate_replace import CertificateReplaceDialog, CertificateReplacePreviewDialog, CertificateReplaceScanProgressDialog
from .models import Session


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _scan_host(session: Session, user: str, roots: list[str], names: list[str], sudo_password: str, keystore_password: str = "") -> dict:
    if session.is_ssh_config_session:
        command = ["ssh", "-o", "BatchMode=yes", session.display_name, "bash", "-s"]
    else:
        command = ["ssh", "-o", "BatchMode=yes"]
        if session.port != 22: command.extend(["-p", str(session.port)])
        command.extend([f"{user}@{session.hostname}", "bash", "-s"])
    script = ["set -u"]
    if sudo_password:
        script.extend([f"SSH_MANAGER_SUDO_PASSWORD={_quote(sudo_password)}", "sudo() { printf '%s\\n' \"$SSH_MANAGER_SUDO_PASSWORD\" | command sudo -S -p '' \"$@\"; }"])
    if keystore_password:
        script.extend([
            f"KEYSTORE_PASSWORD={_quote(keystore_password)}",
            "keystore_password_file=$(mktemp /tmp/ssh-manager-keystore-pass-XXXXXX)",
            "printf '%s' \"$KEYSTORE_PASSWORD\" > \"$keystore_password_file\"",
            "chmod 600 \"$keystore_password_file\"",
            "trap 'rm -f \"$keystore_password_file\"' EXIT",
        ])
    script.append("roots=(" + " ".join(_quote(root) for root in roots) + ")")
    script.append("names=(" + " ".join(_quote(name) for name in names) + ")")
    script.extend([
        "for root in \"${roots[@]}\"; do",
        "  if ! sudo test -d \"$root\"; then printf 'E\\t%s\\tNicht erreichbar oder kein Ordner\\n' \"$root\"; continue; fi",
        "  for name in \"${names[@]}\"; do",
        "    while IFS= read -r target; do",
        "      modified=$(sudo stat -c '%y' -- \"$target\" 2>/dev/null || true)",
        "      expiry=''",
        "      case \"$name\" in",
        "        *.crt|*.pem) expiry=$(sudo openssl x509 -in \"$target\" -noout -enddate 2>/dev/null | sed 's/^notAfter=//') ;;",
        "        *.p12|*.pfx) if [ -n \"${KEYSTORE_PASSWORD:-}\" ]; then expiry=$(sudo openssl pkcs12 -in \"$target\" -passin file:\"$keystore_password_file\" -clcerts -nokeys 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | sed 's/^notAfter=//'); fi ;;",
        "        *.jks) if [ -n \"${KEYSTORE_PASSWORD:-}\" ]; then expiry=$(LC_ALL=C sudo keytool -list -v -keystore \"$target\" -storepass:file \"$keystore_password_file\" 2>/dev/null | awk -F'until: ' '/Valid from:/{print $2}' | paste -sd ', ' -); fi ;;",
        "      esac",
        "      printf 'M\\tf\\t%s\\t%s\\t%s\\t%s\\n' \"$name\" \"$target\" \"$modified\" \"$expiry\"",
        "    done < <(sudo find -P \"$root\" -type f -name \"$name\" -print 2>/dev/null)",
        "    sudo find -P \"$root\" -type l -name \"$name\" -printf 'M\\tl\\t%f\\t%p\\n' 2>/dev/null || true",
        "  done",
        "done",
    ])
    try:
        completed = subprocess.run(command, input=("\n".join(script) + "\n").encode("utf-8"), capture_output=True, timeout=40, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"matches": [], "symlinks": [], "errors": [str(exc)], "warnings": []}
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout).decode("utf-8", errors="replace").strip() or "SSH-Scan fehlgeschlagen"
        return {"matches": [], "symlinks": [], "errors": [error], "warnings": []}
    matches, symlinks, warnings = [], [], []
    for line in completed.stdout.decode("utf-8", errors="replace").splitlines():
        kind, _, rest = line.partition("\t")
        if kind == "E": warnings.append(rest.replace("\t", ": ", 1)); continue
        fields = line.split("\t")
        if len(fields) >= 4 and fields[0] == "M":
            target = (fields[2], fields[3], fields[4] if len(fields) > 4 else "", fields[5] if len(fields) > 5 else "")
            (matches if fields[1] == "f" else symlinks).append(target)
    return {"matches": list(dict.fromkeys(matches)), "symlinks": list(dict.fromkeys(symlinks)), "errors": [], "warnings": warnings}


def replace_certificates(app, sessions: list[Session]) -> None:
    runnable = [session for session in sessions if session.hostname]
    if not runnable:
        messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app); return
    users = resolve_users_for_sessions(app, runnable, "all")
    if users is None: return

    def save_whitelist(roots: list[str]) -> None:
        app._initial_toolbar_search_texts["certificate_replace_whitelist"] = roots
        persist_ui_state(app)

    dialog = CertificateReplaceDialog(
        app, len(runnable), list(app._initial_toolbar_search_texts.get("certificate_replace_whitelist", [])),
        list(app._initial_toolbar_search_texts.get("remote_command_favorites", [])), save_whitelist, reference_sessions=users,
    )
    app.wait_window(dialog)
    if dialog.result is None: return
    spec = dialog.result
    names = [Path(path).name for path in spec["files"]]
    progress = CertificateReplaceScanProgressDialog(app, len(users))

    def worker() -> None:
        scanned = []
        for session, user in users:
            if progress.cancelled:
                return
            scanned.append((session, user, _scan_host(session, user, spec["roots"], names, spec["sudo_password"], spec["keystore_password"])))
        if not progress.cancelled:
            app.after(0, lambda: _show_replace_preview(app, progress, scanned, spec))

    threading.Thread(target=worker, daemon=True).start()


def _selected_deployments(scanned, spec, selected_matches: set[tuple[int, str, str]]):
    deployments = []
    for host_index, (session, user, result) in enumerate(scanned):
        if result["errors"]:
            continue
        matches = [
            (name, target)
            for name, target, _modified, _expiry in result["matches"]
            if (host_index, name, target) in selected_matches
        ]
        if matches:
            deployments.append((session, user, {**spec, "matches": matches}))
    return deployments


def _show_replace_preview(app, progress, scanned, spec) -> None:
    progress.close()
    report_lines, selectable_matches = ["ZERTIFIKATE ERSETZEN – VORSCHAU", ""], []
    for host_index, (session, user, result) in enumerate(scanned):
        report_lines.extend([f"{session.display_name} ({session.hostname})", "-" * 50])
        for name, target, modified, expiry in result["matches"]:
            selectable_matches.append((host_index, f"{session.display_name} ({session.hostname})", name, target, modified, expiry))
            report_lines.append(f"  ERSETZEN: {name} → {target}")
            report_lines.append(f"    Dateizeitstempel: {modified or 'nicht ermittelt'}")
            report_lines.append(f"    Zertifikat gültig bis: {expiry or 'nicht ermittelt'}")
        for name, target, _modified, _expiry in result["symlinks"]:
            report_lines.append(f"  AUSLASSEN (Symlink): {name} → {target}")
        for warning in result.get("warnings", []): report_lines.append(f"  HINWEIS: {warning}")
        for error in result["errors"]: report_lines.append(f"  FEHLER: {error}")
        if not result["matches"] and not result["errors"]: report_lines.append("  Keine Treffer.")
        report_lines.append("")
        if result["matches"] and result["errors"]:
            report_lines.append("  AUSGELASSEN: Wegen Scan-Fehlern wird auf diesem Host nichts ersetzt.")
    report_lines.append("Nachaktion: " + ("ausgeführt bei vollständig erfolgreichem Host" if spec["post_command"] else "keine"))
    preview = CertificateReplacePreviewDialog(app, "\n".join(report_lines), selectable_matches)
    app.wait_window(preview)
    if preview.result is None: return
    deployments = _selected_deployments(scanned, spec, preview.result)
    if not deployments:
        messagebox.showinfo("Zertifikate ersetzen", "Es wurden keine Zertifikatsdateien zum Ersetzen ausgewählt.", parent=app)
        return
    try:
        command = build_certificate_replace_wt_command(deployments, session_colors=app._tree.get_session_colors(), terminal_settings=app.settings.windows_terminal)
        subprocess.Popen(command, shell=True)
    except OSError as exc:
        messagebox.showerror("Zertifikate ersetzen", f"Terminal konnte nicht gestartet werden:\n{exc}", parent=app)
