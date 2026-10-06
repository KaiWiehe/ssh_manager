from __future__ import annotations

import subprocess
import time
from tkinter import messagebox

from .constants import _SSH_CONFIG_FILE
from .core import _find_winscp
from .dialogs_settings_misc import SshConfigInspectDialog
from .models import Session
from .workers import run_worker
from .editor import open_in_vscode


def inspect_ssh_config(app, session: Session) -> None:
    """Zeigt die effektive SSH-Konfiguration für einen Alias."""
    SshConfigInspectDialog(app, session.display_name)



def open_ssh_config_in_vscode(app) -> None:
    """Öffnet ~/.ssh/config in VS Code."""
    try:
        open_in_vscode(_SSH_CONFIG_FILE)
    except (OSError, ValueError) as exc:
        messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{exc}", parent=app)



def _set_winscp_external_sessions_in_existing_window(enabled: bool) -> None:
    r"""Setzt die WinSCP-Option für extern geöffnete Sessions auf vorhandenes Fenster.

    WinSCP entscheidet über Tabs vs. neue Fenster nicht allein pro CLI-Aufruf,
    sondern über die persistente Einstellung
    Configuration\Interface\ExternalSessionInExistingInstance. /rawconfig wäre
    hier ungeeignet, weil WinSCP dann laut eigener Startlogik nicht an eine
    vorhandene Instanz weiterreicht.
    """
    try:
        import winreg
    except ImportError:
        return

    key_path = r"Software\Martin Prikryl\WinSCP 2\Configuration\Interface"
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ExternalSessionInExistingInstance", 0, winreg.REG_DWORD, 1 if enabled else 0)
    except (OSError, AttributeError):
        # Öffnen soll nicht komplett scheitern, nur weil die Preference nicht
        # geschrieben werden konnte. WinSCP nutzt dann seine vorhandene Einstellung.
        return


def open_in_winscp(app, sessions: list[Session]) -> None:
    """Öffnet eine oder mehrere WinSCP-Sessions direkt in WinSCP."""
    winscp = _find_winscp()
    if not winscp:
        messagebox.showerror(
            "WinSCP nicht gefunden",
            "WinSCP.exe wurde nicht gefunden.\n"
            "Bitte WinSCP installieren oder zum PATH hinzufügen.",
            parent=app,
        )
        return
    if getattr(app, "_winscp_opening", False) is True:
        return
    winscp_settings = getattr(getattr(app, "settings", None), "winscp", None)
    open_mode = getattr(winscp_settings, "open_mode", "tabs")
    if open_mode not in {"tabs", "windows"}:
        open_mode = "tabs"
    paths = ["/".join(session.folder_path + [session.display_name]) for session in sessions]
    app._winscp_opening = True

    def worker():
        if open_mode == "tabs":
            _set_winscp_external_sessions_in_existing_window(True)
        for index, full_path in enumerate(paths):
            cmd = [winscp, full_path]
            if open_mode == "windows":
                cmd.append("/newinstance")
            process = subprocess.Popen(cmd)
            if open_mode == "tabs" and index < len(paths) - 1:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    time.sleep(2)

    def done(_):
        app._winscp_opening = False

    def failed(error):
        app._winscp_opening = False
        messagebox.showerror("Fehler", f"Fehler beim Starten von WinSCP:\n{error}", parent=app)

    run_worker(app, worker, done, failed)
