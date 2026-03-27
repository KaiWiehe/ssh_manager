"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import subprocess
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
