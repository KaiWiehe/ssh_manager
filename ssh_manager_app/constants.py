from __future__ import annotations

import os
from pathlib import Path

REGISTRY_PATH = r"Software\Martin Prikryl\WinSCP 2\Sessions"
SKIP_SESSIONS = {"Default Settings"}
QUICK_USERS = ["tool-admin", "dev-sys", "de-nb-statist"]
DEFAULT_USER = "tool-admin"
WINDOW_TITLE = "SSH-Manager"
WINDOW_MIN_SIZE = (600, 450)
_APPDATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "SSH-Manager"
_STATE_FILE = _APPDATA_DIR / "ui_state.json"
_SETTINGS_FILE = _APPDATA_DIR / "settings.json"
_APP_SESSIONS_FILE = _APPDATA_DIR / "app_sessions.json"
_NOTES_FILE = _APPDATA_DIR / "notes.json"
_APP_PREFIX = "__app__"
_SSH_CONFIG_FILE = Path.home() / ".ssh" / "config"
_SSH_CONFIG_PREFIX = "__sshcfg__"
_SSH_ALIAS_PREFIX = "__sshalias__"
_SSH_CONFIG_DEFAULT_FOLDER = "SSH Config"
_FILEZILLA_CONFIG_DEFAULT_FOLDER = "FileZilla Config"

PALETTE: list[tuple[str, str]] = [
    ("Grün (Test)",  "#2d8653"),
    ("Rot (Live)",   "#c0392b"),
    ("Blau",         "#2980b9"),
    ("Orange",       "#d35400"),
    ("Lila",         "#8e44ad"),
    ("Türkis",       "#16a085"),
    ("Grau",         "#7f8c8d"),
    ("Gelb",         "#b7950b"),
]
