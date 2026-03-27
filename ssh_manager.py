"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import unquote
import winreg

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
REGISTRY_PATH = r"Software\Martin Prikryl\WinSCP 2\Sessions"
SKIP_SESSIONS = {"Default Settings"}
QUICK_USERS = ["tool-admin", "dev-sys", "de-nb-statist"]
DEFAULT_USER = "tool-admin"
WINDOW_TITLE = "SSH-Manager"
WINDOW_MIN_SIZE = (600, 450)

# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------
@dataclass
class Session:
    """Repräsentiert eine WinSCP-Session aus der Registry."""
    key: str                        # originaler Registry-Subkey-Name
    display_name: str               # URL-dekodierter Session-Name (letzter Teil)
    folder_path: list[str]          # URL-dekodierte Ordnerpfad-Teile
    hostname: str                   # HostName-Wert aus der Registry
    username: str = ""              # UserName-Wert (optional)
    port: int = 22                  # PortNumber (default 22)

    @property
    def folder_key(self) -> str:
        """Ordner-Pfad als String, z.B. 'Extern/Sub'."""
        return "/".join(self.folder_path)


# ---------------------------------------------------------------------------
# Reine Hilfsfunktionen (testbar ohne GUI/Registry)
# ---------------------------------------------------------------------------
def parse_session_key(key: str) -> tuple[list[str], str]:
    """
    Zerlegt einen WinSCP-Registry-Subkey-Namen in Ordner-Pfad und Session-Name.
    URL-Encoding wird dekodiert.

    Beispiele:
      "Extern/Bundo"                  → (["Extern"], "Bundo")
      "Others/10.120.137.10%20-%20DB" → (["Others"], "10.120.137.10 - DB")
      "tool-admin@10.120.67.31"       → ([], "tool-admin@10.120.67.31")
    """
    parts = key.split("/")
    folder_path = [unquote(p) for p in parts[:-1]]
    name = unquote(parts[-1])
    return folder_path, name


def build_wt_command(sessions: list[Session], user: str) -> str:
    """
    Erzeugt den wt.exe-Befehl, der alle Sessions als neue Tabs öffnet.
    Alle Tabs landen im selben Windows Terminal Fenster.

    Format:
      wt.exe new-tab -p "Git Bash" -- ssh USER@HOST
        ; new-tab -p "Git Bash" -- ssh -p PORT USER@HOST2
        ...
    """
    parts = []
    for i, session in enumerate(sessions):
        if session.port != 22:
            ssh_cmd = f"ssh -p {session.port} {user}@{session.hostname}"
        else:
            ssh_cmd = f"ssh {user}@{session.hostname}"

        if i == 0:
            parts.append(f'wt.exe new-tab -p "Git Bash" -- {ssh_cmd}')
        else:
            parts.append(f'new-tab -p "Git Bash" -- {ssh_cmd}')

    return " ; ".join(parts)


# ---------------------------------------------------------------------------
# TerminalLauncher
# ---------------------------------------------------------------------------
class TerminalLauncher:
    """Startet wt.exe mit mehreren SSH-Tabs."""

    @staticmethod
    def launch(sessions: list[Session], user: str) -> None:
        """
        Öffnet alle Sessions als neue Tabs in einem Windows Terminal Fenster.
        Hinweis: Da shell=True genutzt wird, wirft Popen keine Exception wenn
        wt.exe fehlt – cmd.exe startet, aber wt.exe schlägt intern fehl.
        """
        if not sessions:
            return
        cmd = build_wt_command(sessions, user)
        # shell=True nötig: wt.exe parst `;` als eigenen Subcommand-Separator,
        # cmd.exe behandelt `;` nicht als Sonderzeichen und reicht es durch.
        subprocess.Popen(cmd, shell=True)


# ---------------------------------------------------------------------------
# RegistryReader
# ---------------------------------------------------------------------------

# Allowlist patterns for input validation (defence against shell injection via
# registry data that ends up in build_wt_command which uses shell=True).
_HOSTNAME_RE = re.compile(r'^[A-Za-z0-9.\-:_]+$')
_USERNAME_RE = re.compile(r'^[A-Za-z0-9.\-_]*$')


class RegistryReader:
    """Liest WinSCP-Sessions aus der Windows-Registry."""

    REGISTRY_BASE = winreg.HKEY_CURRENT_USER

    def load_sessions(self) -> list[Session]:
        """
        Gibt alle gültigen Sessions aus der Registry zurück.
        Sortiert nach folder_key + display_name.
        Raises OSError wenn der Registry-Pfad nicht existiert.
        """
        sessions: list[Session] = []

        with winreg.OpenKey(self.REGISTRY_BASE, REGISTRY_PATH) as base_key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(base_key, index)
                    index += 1
                except OSError:
                    break

                # "Default Settings" überspringen
                decoded_name = unquote(subkey_name)
                if decoded_name == "Default Settings":
                    continue

                session = self._read_session(base_key, subkey_name)
                if session is not None:
                    sessions.append(session)

        sessions.sort(key=lambda s: (s.folder_key.lower(), s.display_name.lower()))
        return sessions

    def _read_session(self, base_key, subkey_name: str) -> Optional[Session]:
        """Liest eine einzelne Session. Gibt None zurück wenn kein HostName oder Validierung fehlschlägt."""
        full_path = REGISTRY_PATH + "\\" + subkey_name
        try:
            with winreg.OpenKey(self.REGISTRY_BASE, full_path) as session_key:
                try:
                    hostname, _ = winreg.QueryValueEx(session_key, "HostName")
                except FileNotFoundError:
                    return None  # Session ohne Hostname überspringen

                if not hostname:
                    return None

                username = ""
                try:
                    username, _ = winreg.QueryValueEx(session_key, "UserName")
                except FileNotFoundError:
                    pass

                port = 22
                try:
                    port, _ = winreg.QueryValueEx(session_key, "PortNumber")
                except FileNotFoundError:
                    pass

        except OSError:
            return None

        # Input validation: reject entries with shell metacharacters
        if not _HOSTNAME_RE.match(hostname):
            print(
                f"WARNING: Skipping session '{subkey_name}' – "
                f"hostname contains invalid characters: {hostname!r}",
                file=sys.stderr,
            )
            return None

        if username and not _USERNAME_RE.match(username):
            print(
                f"WARNING: Skipping session '{subkey_name}' – "
                f"username contains invalid characters: {username!r}",
                file=sys.stderr,
            )
            return None

        folder_path, display_name = parse_session_key(subkey_name)
        return Session(
            key=subkey_name,
            display_name=display_name,
            folder_path=folder_path,
            hostname=hostname,
            username=username,
            port=port,
        )
