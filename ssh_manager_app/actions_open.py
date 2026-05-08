from __future__ import annotations

import subprocess
import time
from tkinter import messagebox

from .constants import _SSH_CONFIG_FILE
from .core import _find_winscp
from .dialogs_settings_misc import SshConfigInspectDialog
from .models import Session


def inspect_ssh_config(app, session: Session) -> None:
    """Zeigt die effektive SSH-Konfiguration für einen Alias."""
    SshConfigInspectDialog(app, session.display_name)



def open_ssh_config_in_vscode(app) -> None:
    """Öffnet ~/.ssh/config in VS Code."""
    try:
        subprocess.Popen(f'code "{_SSH_CONFIG_FILE}"', shell=True)
    except OSError as exc:
        messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{exc}", parent=app)



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
    try:
        winscp_settings = getattr(getattr(app, "settings", None), "winscp", None)
        open_mode = getattr(winscp_settings, "open_mode", "tabs")
        if open_mode not in {"tabs", "windows"}:
            open_mode = "tabs"
        for index, session in enumerate(sessions):
            full_path = "/".join(session.folder_path + [session.display_name])
            cmd = [winscp, full_path]
            if open_mode == "windows":
                cmd.append("/newinstance")
            subprocess.Popen(cmd)
            if open_mode == "tabs" and index < len(sessions) - 1:
                time.sleep(0.25)
    except OSError as exc:
        messagebox.showerror("Fehler", f"Fehler beim Starten von WinSCP:\n{exc}", parent=app)
