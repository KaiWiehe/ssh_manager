"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from dataclasses import asdict, dataclass, field
from typing import Optional, Callable
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
_APPDATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "SSH-Manager"
_STATE_FILE = _APPDATA_DIR / "ui_state.json"
_SETTINGS_FILE = _APPDATA_DIR / "settings.json"
_APP_SESSIONS_FILE = Path(os.environ.get("APPDATA", Path.home())) / "SSH-Manager" / "app_sessions.json"
_APP_PREFIX = "__app__"
_SSH_CONFIG_FILE = Path.home() / ".ssh" / "config"
_SSH_CONFIG_PREFIX = "__sshcfg__"
_SSH_ALIAS_PREFIX = "__sshalias__"
_SSH_CONFIG_DEFAULT_FOLDER = "SSH Config"

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


def _color_tag(hex_color: str) -> str:
    """Tag-Name für eine Hex-Farbe, z.B. '#2d8653' → 'color_2d8653'."""
    return f"color_{hex_color.lstrip('#')}"

# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------
@dataclass
class Session:
    """Repräsentiert eine SSH-Session (aus WinSCP-Registry oder eigene App-Session)."""
    key: str                        # originaler Registry-Subkey-Name oder __app__<uuid>
    display_name: str               # URL-dekodierter Session-Name (letzter Teil)
    folder_path: list[str]          # URL-dekodierte Ordnerpfad-Teile
    hostname: str                   # HostName-Wert
    username: str = ""              # UserName-Wert (optional)
    port: int = 22                  # PortNumber (default 22)
    source: str = "winscp"          # "winscp" | "app" | "ssh_config" | "ssh_alias"

    @property
    def folder_key(self) -> str:
        """Ordner-Pfad als String, z.B. 'Extern/Sub'."""
        return "/".join(self.folder_path)

    @property
    def is_app_session(self) -> bool:
        return self.source == "app"

    @property
    def is_ssh_config_session(self) -> bool:
        """True für ssh_config (aus Config-Datei) und ssh_alias (Kopie, in JSON)."""
        return self.source in ("ssh_config", "ssh_alias")

    @property
    def is_ssh_alias_copy(self) -> bool:
        """True wenn SSH-Alias-Kopie (dupliziert, löschbar, in JSON gespeichert)."""
        return self.source == "ssh_alias"


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


def _build_ssh_command(session: Session, user: str | None = None) -> str:
    """Erzeugt das passende ssh-Kommando für eine Session."""
    if session.is_ssh_config_session:
        return f"ssh {session.display_name}"
    effective_user = (user or session.username).strip()
    if session.port != 22:
        return f"ssh -p {session.port} {effective_user}@{session.hostname}"
    return f"ssh {effective_user}@{session.hostname}"


def _terminal_profile_flag(profile_name: str) -> str:
    profile = (profile_name or "Git Bash").strip() or "Git Bash"
    return f'-p "{profile}" '


def _terminal_title_flag(session: Session, user: str, title_mode: str) -> str:
    mode = (title_mode or "default").strip()
    if mode == "default":
        return ""
    if mode == "name":
        title = session.display_name
    elif mode == "host":
        title = session.hostname or session.display_name
    elif mode == "user_host":
        effective_user = (user or session.username).strip()
        host = session.hostname or session.display_name
        title = f"{effective_user}@{host}" if effective_user else host
    elif mode == "name_host":
        host = session.hostname or session.display_name
        title = f"{session.display_name} ({host})"
    else:
        return ""
    return f'--title "{title}" ' if title else ""


def build_wt_command(sessions: list[Session], user: str, session_colors: dict[str, str] | None = None, terminal_settings: WindowsTerminalSettings | None = None) -> str:
    """
    Erzeugt den wt.exe-Befehl, der alle Sessions als neue Tabs öffnet.
    Alle Tabs landen im selben Windows Terminal Fenster.

    Format:
      wt.exe new-tab --tabColor #2d8653 -p "Git Bash" -- ssh USER@HOST
        ; new-tab -p "Git Bash" -- ssh -p PORT USER@HOST2
        ...
    """
    colors = session_colors or {}
    settings = terminal_settings or WindowsTerminalSettings()
    profile_flag = _terminal_profile_flag(settings.profile_name)
    parts = []
    for i, session in enumerate(sessions):
        ssh_cmd = _build_ssh_command(session, user)
        color = colors.get(session.key) if settings.use_tab_color else None
        color_flag = f'--tabColor "{color}" ' if color else ""
        title_flag = _terminal_title_flag(session, user, settings.title_mode)
        tab_cmd = f'new-tab {color_flag}{title_flag}{profile_flag}-- {ssh_cmd}'
        parts.append(f"wt.exe {tab_cmd}" if i == 0 else tab_cmd)

    return " ; ".join(parts)


def _shell_single_quote(text: str) -> str:
    """Quoted Text für Bash in Single Quotes."""
    return "'" + text.replace("'", "'\"'\"'") + "'"

def _ssh_target(hostname: str, user: str | None = None, port: int = 22) -> str:
    """Erzeugt ein ssh-Ziel inklusive optionalem User und Port."""
    target = hostname
    if user and user.strip():
        target = f"{user.strip()}@{target}"
    if port and port != 22:
        return f"-p {port} {target}"
    return target


def _build_jump_ssh_command(session: Session, target_user: str, jump_host: str, jump_user: str | None = None, jump_port: int = 22) -> str:
    """Erzeugt ein ssh-Kommando mit ProxyJump für eine Session."""
    jump_target = _ssh_target(jump_host, jump_user, jump_port)
    if session.is_ssh_config_session:
        return f"ssh -J {jump_target} {session.display_name}"
    effective_user = (target_user or session.username).strip()
    if session.port != 22:
        return f"ssh -J {jump_target} -p {session.port} {effective_user}@{session.hostname}"
    return f"ssh -J {jump_target} {effective_user}@{session.hostname}"


def build_jump_wt_command(
    session: Session,
    target_user: str,
    jump_host: str,
    jump_user: str | None = None,
    jump_port: int = 22,
    session_color: str | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
) -> str:
    """Erzeugt den WT-Befehl für eine einzelne Session über ProxyJump."""
    settings = terminal_settings or WindowsTerminalSettings()
    ssh_cmd = _build_jump_ssh_command(session, target_user, jump_host, jump_user, jump_port)
    color = session_color if settings.use_tab_color else None
    color_flag = f'--tabColor "{color}" ' if color else ""
    title_flag = _terminal_title_flag(session, target_user, settings.title_mode)
    profile_flag = _terminal_profile_flag(settings.profile_name)
    return f'wt.exe new-tab {color_flag}{title_flag}{profile_flag}-- {ssh_cmd}'


def _append_ssh_config_alias(alias: str, target: Session, target_user: str, jump_host: str, jump_user: str | None = None, jump_port: int = 22) -> None:
    """Hängt einen neuen Host-Alias mit ProxyJump an ~/.ssh/config an."""
    alias = alias.strip()
    if not alias or ' ' in alias or '*' in alias or '?' in alias:
        raise ValueError('Alias darf keine Leerzeichen oder Wildcards enthalten.')

    existing = {s.display_name.lower() for s in _load_ssh_config_sessions()}
    if alias.lower() in existing:
        raise ValueError(f"Alias '{alias}' existiert bereits in ~/.ssh/config.")

    lines = [
        f'Host {alias}',
        f'    HostName {target.hostname or target.display_name}',
        f'    User {target_user}',
    ]
    if target.port and target.port != 22:
        lines.append(f'    Port {target.port}')
    proxy_jump = jump_host
    if jump_user and jump_user.strip():
        proxy_jump = f"{jump_user.strip()}@{proxy_jump}"
    if jump_port and jump_port != 22:
        proxy_jump = f"{proxy_jump}:{jump_port}"
    lines.append(f'    ProxyJump {proxy_jump}')

    _SSH_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    prefix = "\n"
    if _SSH_CONFIG_FILE.exists():
        existing_text = _SSH_CONFIG_FILE.read_text(encoding='utf-8')
        if existing_text and not existing_text.endswith("\n"):
            prefix = "\n\n"
        elif existing_text:
            prefix = "\n"
    with _SSH_CONFIG_FILE.open('a', encoding='utf-8') as f:
        f.write(prefix + "\n".join(lines) + "\n")



def build_remote_command_wt_command(
    session_commands: list[tuple[Session, str, str]],
    *,
    close_on_success: bool,
    session_colors: dict[str, str] | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
) -> str:
    """Erzeugt WT-Tabs, die pro Host ein lokales Bash-Skript starten."""
    settings = terminal_settings or WindowsTerminalSettings()
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    colors = session_colors or {}
    profile_flag = _terminal_profile_flag(settings.profile_name)
    parts = []
    for i, (session, user, remote_script) in enumerate(session_commands):
        ssh_cmd = _build_ssh_command(session, user)
        start_label = f"Start: {remote_script.strip() or '-'}"
        script_lines = [
            "#!/usr/bin/env bash",
            f"printf '%s\\n' {_shell_single_quote('Remote-Befehl')}",
            f"printf '%s\\n' {_shell_single_quote(f'Host: {session.display_name} ({session.hostname})')}",
            f"printf '%s\\n' {_shell_single_quote(f'User: {user}')}",
            f"printf '%s\\n\\n' {_shell_single_quote(start_label)}",
        ]
        if close_on_success:
            script_lines.append(f"{ssh_cmd} <<'__REMOTE_CMD__'")
        else:
            script_lines.append(f"{ssh_cmd} -t <<'__REMOTE_CMD__'")
        script_lines.append(remote_script)
        script_lines.append("__REMOTE_CMD__")
        script_lines.append("status=$?")
        if not close_on_success:
            script_lines.append("if [ $status -eq 0 ]; then exec bash; fi")
        script_lines.append("if [ $status -ne 0 ]; then read; fi")
        script_lines.append("exit $status")
        script_path = _write_temp_bash_script("remote_cmd_", "\n".join(script_lines) + "\n")
        color = colors.get(session.key) if settings.use_tab_color else None
        color_flag = f'--tabColor "{color}" ' if color else ""
        title_flag = _terminal_title_flag(session, user, settings.title_mode)
        tab_cmd = f'new-tab {color_flag}{title_flag}{profile_flag}-- "{git_bash}" "{script_path}"'
        parts.append(f"wt.exe {tab_cmd}" if i == 0 else tab_cmd)
    return " ; ".join(parts)




def _write_temp_bash_script(prefix: str, content: str) -> str:
    """Schreibt ein temporäres Bash-Skript für WT/Git Bash und gibt den Windows-Pfad zurück."""
    script_dir = _STATE_FILE.parent / "tmp"
    script_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".sh", prefix=prefix, dir=script_dir, delete=False) as f:
        f.write(content)
        script_path = Path(f.name)
    return str(script_path)

def _find_git_bash() -> str:
    """
    Sucht bash.exe von Git for Windows.
    Wichtig: 'bash' aus dem System-PATH ist unter Windows mit WSL die WSL-Bash
    (C:\\Windows\\System32\\bash.exe), nicht Git Bash.
    """
    git = shutil.which("git")
    if git:
        bash = Path(git).parent.parent / "bin" / "bash.exe"
        if bash.exists():
            return str(bash)
    for candidate in [
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    ]:
        if candidate.exists():
            return str(candidate)
    return "bash"


def _find_winscp() -> str | None:
    """Sucht WinSCP.exe in üblichen Installationspfaden."""
    local_app = os.environ.get("LOCALAPPDATA", "")
    for candidate in [
        Path(local_app) / "Programs" / "WinSCP" / "WinSCP.exe",
        Path(r"C:\Program Files (x86)\WinSCP\WinSCP.exe"),
        Path(r"C:\Program Files\WinSCP\WinSCP.exe"),
    ]:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("WinSCP")
    return found if found else None


def build_ssh_copy_id_command(sessions: list[Session], key_filename: str, user: str, terminal_settings: WindowsTerminalSettings | None = None) -> str:
    """
    Erzeugt den wt.exe-Befehl für ssh-copy-id. Pro Host ein eigener WT-Tab.
    - Expliziter Git-Bash-Pfad statt 'bash' (System-bash = WSL unter Windows).
    - Kein ';' im bash-Befehl (WT parst es als Subcommand-Separator).
    - 'read' hält den Tab offen, braucht keine Anführungszeichen.
    - '~' unquoted → Tilde-Expansion funktioniert.
    """
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    profile_flag = _terminal_profile_flag(settings.profile_name)
    parts = []
    for i, session in enumerate(sessions):
        target = f"{user}@{session.hostname}"
        inner = f"ssh-copy-id -i ~/.ssh/{key_filename} {target} && read || read"
        bash_cmd = f'"{git_bash}" -c "{inner}"'
        title_flag = _terminal_title_flag(session, user, settings.title_mode)
        tab_cmd = f'new-tab {title_flag}{profile_flag}-- {bash_cmd}'
        parts.append(f"wt.exe {tab_cmd}" if i == 0 else tab_cmd)
    return " ; ".join(parts)


def build_ssh_remove_key_command(sessions: list[Session], key_filename: str, user: str, terminal_settings: WindowsTerminalSettings | None = None) -> str:
    """
    Erzeugt den wt.exe-Befehl zum Entfernen eines SSH Public Keys aus authorized_keys.
    Pro Host ein eigener WT-Tab.
    - Stdin-Redirect (< ~/.ssh/key.pub) statt KEY-Variable → keine nested double quotes.
    - grep -vxFf /dev/stdin: liest Muster aus stdin (Public Key), Fixed-String, ganze Zeile.
    - Single-Quotes für den Remote-Befehl (in bash -c "..." literal, für SSH quote-delimiter).
    - '~' unquoted außerhalb der äußeren Anführungszeichen → Tilde-Expansion.
    """
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    profile_flag = _terminal_profile_flag(settings.profile_name)
    parts = []
    for i, session in enumerate(sessions):
        target = f"{user}@{session.hostname}"
        remote_cmd = (
            "grep -vxFf /dev/stdin ~/.ssh/authorized_keys > /tmp/ak_tmp "
            "&& mv /tmp/ak_tmp ~/.ssh/authorized_keys"
        )
        inner = (
            f"ssh {target} '{remote_cmd}' "
            f"< ~/.ssh/{key_filename} && echo OK || echo FEHLER && read"
        )
        bash_cmd = f'"{git_bash}" -c "{inner}"'
        title_flag = _terminal_title_flag(session, user, settings.title_mode)
        tab_cmd = f'new-tab {title_flag}{profile_flag}-- {bash_cmd}'
        parts.append(f"wt.exe {tab_cmd}" if i == 0 else tab_cmd)
    return " ; ".join(parts)


def check_host_reachable(hostname: str, port: int = 22, timeout: int = 3) -> bool:
    """Prüft per TCP-Connect ob hostname:port erreichbar ist."""
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def build_ssh_tunnel_command(
    ssh_server: str, local_port: int, remote_host: str, remote_port: int, user: str, terminal_settings: WindowsTerminalSettings | None = None
) -> list[str]:
    """Erzeugt den wt.exe-Aufruf für SSH Local Port Forwarding."""
    git_bash = _find_git_bash()
    tunnel_target = f"{local_port} -> {remote_host}:{remote_port} via {user}@{ssh_server}"
    script = "\n".join([
        "#!/usr/bin/env bash",
        f"printf '%s\\n' {_shell_single_quote('SSH-Tunnel aktiv')}",
        f"printf '%s\\n\\n' {_shell_single_quote(tunnel_target)}",
        f"ssh -N -L {local_port}:{remote_host}:{remote_port} {user}@{ssh_server}",
        "read",
    ]) + "\n"
    script_path = _write_temp_bash_script("ssh_tunnel_", script)
    cmd = ["wt.exe", "new-tab"]
    if settings.title_mode != "default":
        cmd.extend(["--title", f"{user}@{ssh_server}"])
    cmd.extend(["-p", settings.profile_name or "Git Bash", "--", git_bash, script_path])
    return cmd


# ---------------------------------------------------------------------------
# TerminalLauncher
# ---------------------------------------------------------------------------
class TerminalLauncher:
    """Startet wt.exe mit mehreren SSH-Tabs."""

    @staticmethod
    def launch(sessions: list[Session], user: str, session_colors: dict[str, str] | None = None, terminal_settings: WindowsTerminalSettings | None = None) -> None:
        """
        Öffnet alle Sessions als neue Tabs in einem Windows Terminal Fenster.
        Hinweis: Da shell=True genutzt wird, wirft Popen keine Exception wenn
        wt.exe fehlt – cmd.exe startet, aber wt.exe schlägt intern fehl.
        """
        if not sessions:
            return
        cmd = build_wt_command(sessions, user, session_colors, terminal_settings=terminal_settings)
        # shell=True nötig: wt.exe parst `;` als eigenen Subcommand-Separator,
        # cmd.exe behandelt `;` nicht als Sonderzeichen und reicht es durch.
        subprocess.Popen(cmd, shell=True)


# ---------------------------------------------------------------------------
# RegistryReader
# ---------------------------------------------------------------------------

# Allowlist patterns for input validation (defence against shell injection via
# registry data that ends up in build_wt_command which uses shell=True).
# Colon allowed for IPv6 addresses.
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
                if decoded_name in SKIP_SESSIONS:
                    continue

                session = self._read_session(subkey_name)
                if session is not None:
                    sessions.append(session)

        sessions.sort(key=lambda s: (s.folder_key.lower(), s.display_name.lower()))
        return sessions

    def _read_session(self, subkey_name: str) -> Optional[Session]:
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


# ---------------------------------------------------------------------------
# Checkbox-Images (werden in SessionTree und SSHManagerApp verwendet)
# ---------------------------------------------------------------------------
def _create_checkbox_images(root: tk.Tk) -> tuple[tk.PhotoImage, tk.PhotoImage]:
    """
    Erzeugt zwei 16×16 PhotoImages für checked/unchecked Checkboxen.
    Gibt (img_unchecked, img_checked) zurück.
    """
    size = 16
    border_color = "#808080"
    bg_color = "#ffffff"
    check_color = "#1a7a3a"

    def make(checked: bool) -> tk.PhotoImage:
        img = tk.PhotoImage(width=size, height=size)
        # Alle Pixel mit Hintergrundfarbe füllen
        row_bg = "{" + " ".join([bg_color] * size) + "}"
        for y in range(size):
            img.put(row_bg, to=(0, y, size, y + 1))
        # Rahmen zeichnen
        border_row = "{" + " ".join([border_color] * size) + "}"
        img.put(border_row, to=(0, 0, size, 1))        # oben
        img.put(border_row, to=(0, size - 1, size, size))  # unten
        for y in range(size):
            img.put("{" + border_color + "}", to=(0, y, 1, y + 1))       # links
            img.put("{" + border_color + "}", to=(size - 1, y, size, y + 1))  # rechts
        if checked:
            # Häkchen: kurzer Abstieg (3,9)→(6,12), dann Aufstieg (6,12)→(13,5)
            check_px = "{" + check_color + "}"
            coords_down = [(3, 9), (4, 10), (5, 11), (6, 12)]
            coords_up = [(7, 11), (8, 10), (9, 9), (10, 8), (11, 7), (12, 6), (13, 5)]
            for x, y in coords_down + coords_up:
                if 0 < x < size and 0 < y < size:
                    img.put(check_px, to=(x, y, x + 1, y + 1))
                    # Doppelt breit für bessere Sichtbarkeit
                    if y + 1 < size:
                        img.put(check_px, to=(x, y + 1, x + 1, y + 2))
        return img

    return make(False), make(True)


# ---------------------------------------------------------------------------
# UI-State Persistenz
# ---------------------------------------------------------------------------
@dataclass
class ToolbarSettings:
    show_select_all: bool = True
    show_deselect_all: bool = True
    show_expand_all: bool = True
    show_collapse_all: bool = True
    show_add_connection: bool = True
    show_reload: bool = True
    show_open_tunnel: bool = True
    show_check_hosts: bool = True


@dataclass
class WindowsTerminalSettings:
    profile_name: str = "Git Bash"
    use_tab_color: bool = True
    title_mode: str = "default"


@dataclass
class AppSettings:
    quick_users: list[str] = field(default_factory=lambda: list(QUICK_USERS))
    default_user: str = DEFAULT_USER
    toolbar: ToolbarSettings = field(default_factory=ToolbarSettings)
    host_check_timeout_seconds: int = 3
    startup_expand_mode: str = "remember"
    windows_terminal: WindowsTerminalSettings = field(default_factory=WindowsTerminalSettings)


def _default_settings() -> AppSettings:
    return AppSettings()


def _settings_to_dict(settings: AppSettings) -> dict:
    return asdict(settings)


def _load_settings() -> AppSettings:
    try:
        return _load_settings_from_path(_SETTINGS_FILE)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return _default_settings()


def _save_settings(settings: AppSettings) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(
        json.dumps(_settings_to_dict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_settings_from_path(path: Path) -> AppSettings:
    defaults = _default_settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    toolbar_raw = raw.get("toolbar", {}) if isinstance(raw, dict) else {}
    wt_raw = raw.get("windows_terminal", {}) if isinstance(raw, dict) else {}

    quick_users = raw.get("quick_users", defaults.quick_users)
    if not isinstance(quick_users, list):
        quick_users = defaults.quick_users
    quick_users = [str(user).strip() for user in quick_users if str(user).strip()] or list(defaults.quick_users)

    default_user = str(raw.get("default_user", defaults.default_user)).strip() or quick_users[0]
    if default_user not in quick_users:
        quick_users.insert(0, default_user)

    host_timeout = raw.get("host_check_timeout_seconds", defaults.host_check_timeout_seconds)
    try:
        host_timeout = max(1, int(host_timeout))
    except (TypeError, ValueError):
        host_timeout = defaults.host_check_timeout_seconds

    startup_expand_mode = str(raw.get("startup_expand_mode", defaults.startup_expand_mode))
    if startup_expand_mode not in {"remember", "expanded", "collapsed"}:
        startup_expand_mode = defaults.startup_expand_mode

    return AppSettings(
        quick_users=quick_users,
        default_user=default_user,
        toolbar=ToolbarSettings(
            show_select_all=bool(toolbar_raw.get("show_select_all", defaults.toolbar.show_select_all)),
            show_deselect_all=bool(toolbar_raw.get("show_deselect_all", defaults.toolbar.show_deselect_all)),
            show_expand_all=bool(toolbar_raw.get("show_expand_all", defaults.toolbar.show_expand_all)),
            show_collapse_all=bool(toolbar_raw.get("show_collapse_all", defaults.toolbar.show_collapse_all)),
            show_add_connection=bool(toolbar_raw.get("show_add_connection", defaults.toolbar.show_add_connection)),
            show_reload=bool(toolbar_raw.get("show_reload", defaults.toolbar.show_reload)),
            show_open_tunnel=bool(toolbar_raw.get("show_open_tunnel", defaults.toolbar.show_open_tunnel)),
            show_check_hosts=bool(toolbar_raw.get("show_check_hosts", defaults.toolbar.show_check_hosts)),
        ),
        host_check_timeout_seconds=host_timeout,
        startup_expand_mode=startup_expand_mode,
        windows_terminal=WindowsTerminalSettings(
            profile_name=str(wt_raw.get("profile_name", defaults.windows_terminal.profile_name)).strip() or defaults.windows_terminal.profile_name,
            use_tab_color=bool(wt_raw.get("use_tab_color", defaults.windows_terminal.use_tab_color)),
            title_mode=str(wt_raw.get("title_mode", defaults.windows_terminal.title_mode)),
        ),
    )


def _load_ui_state() -> tuple[set[str], dict[str, str], dict[str, str]]:
    """Lädt UI-Zustand aus JSON. Gibt leere Defaults zurück wenn nicht vorhanden."""
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        return (
            set(data.get("expanded_folders", [])),
            dict(data.get("session_colors", {})),
            dict(data.get("toolbar_search_texts", {})),
        )
    except (OSError, json.JSONDecodeError, ValueError):
        return set(), {}, {}


def _save_ui_state(expanded_folders: set[str], session_colors: dict[str, str], toolbar_search_texts: dict[str, str] | None = None) -> None:
    """Speichert UI-Zustand als JSON in %APPDATA%\\SSH-Manager\\."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(
        json.dumps(
            {
                "expanded_folders": sorted(expanded_folders),
                "session_colors": session_colors,
                "toolbar_search_texts": toolbar_search_texts or {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _load_app_sessions() -> list[Session]:
    """Lädt eigene App-Sessions und SSH-Alias-Kopien aus JSON."""
    try:
        data = json.loads(_APP_SESSIONS_FILE.read_text(encoding="utf-8"))
        sessions = []
        for entry in data.get("sessions", []):
            source = entry.get("source", "app")
            folder_str = entry.get("folder", "")
            folder_path = [p for p in folder_str.split("/") if p] if folder_str else []
            key = (_SSH_ALIAS_PREFIX if source == "ssh_alias" else _APP_PREFIX) + entry["id"]
            sessions.append(Session(
                key=key,
                display_name=entry["name"],
                folder_path=folder_path,
                hostname=entry["hostname"],
                username=entry.get("username", ""),
                port=int(entry.get("port", 22)),
                source=source,
            ))
        return sessions
    except (OSError, json.JSONDecodeError, ValueError, KeyError):
        return []


def _save_app_sessions(sessions: list[Session]) -> None:
    """Speichert eigene App-Sessions und SSH-Alias-Kopien als JSON in %APPDATA%\\SSH-Manager\\."""
    _APP_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    entries = []
    for s in sessions:
        if s.source not in ("app", "ssh_alias"):
            continue
        prefix = _SSH_ALIAS_PREFIX if s.source == "ssh_alias" else _APP_PREFIX
        session_id = s.key[len(prefix):]
        entries.append({
            "id": session_id,
            "name": s.display_name,
            "folder": s.folder_key,
            "hostname": s.hostname,
            "username": s.username,
            "port": s.port,
            "source": s.source,
        })
    _APP_SESSIONS_FILE.write_text(
        json.dumps({"sessions": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_ssh_config_sessions() -> list[Session]:
    """
    Parst ~/.ssh/config und gibt alle Host-Einträge als Sessions zurück.
    Wildcards (* ?) und Multi-Pattern-Hosts (Leerzeichen) werden übersprungen.
    Alle Sessions landen im Ordner 'SSH Config'.
    """
    try:
        text = _SSH_CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return []

    sessions: list[Session] = []
    current_alias: str | None = None
    current_hostname: str | None = None
    current_user: str = ""
    current_port: int = 22

    def _flush() -> None:
        nonlocal current_alias, current_hostname, current_user, current_port
        if current_alias and '*' not in current_alias and '?' not in current_alias:
            sessions.append(Session(
                key=_SSH_CONFIG_PREFIX + current_alias,
                display_name=current_alias,
                folder_path=[_SSH_CONFIG_DEFAULT_FOLDER],
                hostname=current_hostname or current_alias,
                username=current_user,
                port=current_port,
                source="ssh_config",
            ))
        current_alias = None
        current_hostname = None
        current_user = ""
        current_port = 22

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        parts = stripped.split(None, 1)
        if len(parts) < 2:
            continue
        kw, val = parts[0].lower(), parts[1].strip()
        if kw == "host":
            _flush()
            current_alias = val if ' ' not in val else None
        elif kw == "hostname" and current_alias:
            current_hostname = val
        elif kw == "user" and current_alias:
            current_user = val
        elif kw == "port" and current_alias:
            try:
                current_port = int(val)
            except ValueError:
                pass
    _flush()
    return sessions


# ---------------------------------------------------------------------------
# SessionTree
# ---------------------------------------------------------------------------
class SessionTree(ttk.Frame):
    """
    ttk.Treeview-Wrapper mit Checkbox-Unterstützung.
    Zeigt Sessions gruppiert nach Ordnern an.
    Unterstützt Live-Filter, Rechtsklick-Kontextmenü, Checkbox-Toggle.
    """

    # Tag-Konstanten
    TAG_SESSION = "session"
    TAG_FOLDER = "folder"

    def __init__(
        self,
        parent: tk.Widget,
        sessions: list[Session],
        img_unchecked: tk.PhotoImage,
        img_checked: tk.PhotoImage,
        on_selection_changed,  # Callable[[int], None]
        initial_open_folders: set[str] | None = None,
        initial_session_colors: dict[str, str] | None = None,
        on_quick_connect=None,           # Callable[[Session], None] | None
        on_edit_session=None,            # Callable[[Session], None] | None
        on_delete_session=None,          # Callable[[Session], None] | None
        on_delete_folder=None,           # Callable[[list[Session], str], None] | None
        on_rename_folder=None,           # Callable[[str, str], None] | None  (folder_key, new_name)
        on_add_session_in_folder=None,   # Callable[[str], None] | None  (folder_key)
        on_duplicate_ssh_alias=None,     # Callable[[Session], None] | None
        on_inspect_ssh_config=None,      # Callable[[Session], None] | None
        on_duplicate_app_session=None,   # Callable[[Session], None] | None
        on_move_session=None,            # Callable[[Session], None] | None
        on_move_sessions=None,           # Callable[[list[Session]], None] | None
        on_open_ssh_config_in_vscode=None,  # Callable[[], None] | None
        on_deploy_ssh_key=None,             # Callable[[list[Session]], None] | None
        on_remove_ssh_key=None,             # Callable[[list[Session]], None] | None
        on_open_tunnel=None,                # Callable[[Session], None] | None
        on_open_in_winscp=None,             # Callable[[list[Session]], None] | None
        on_run_remote_command=None,         # Callable[[list[Session]], None] | None
        on_open_via_jumphost=None,          # Callable[[Session], None] | None
        on_ui_state_changed=None,           # Callable[[], None] | None
    ):
        super().__init__(parent)
        self._sessions = sessions
        self._img_unchecked = img_unchecked
        self._img_checked = img_checked
        self._on_selection_changed = on_selection_changed
        self._on_quick_connect = on_quick_connect
        self._on_edit_session = on_edit_session
        self._on_delete_session = on_delete_session
        self._on_delete_folder = on_delete_folder
        self._on_rename_folder = on_rename_folder
        self._on_add_session_in_folder = on_add_session_in_folder
        self._on_duplicate_ssh_alias = on_duplicate_ssh_alias
        self._on_inspect_ssh_config = on_inspect_ssh_config
        self._on_duplicate_app_session = on_duplicate_app_session
        self._on_move_session = on_move_session
        self._on_move_sessions = on_move_sessions
        self._on_open_ssh_config_in_vscode = on_open_ssh_config_in_vscode
        self._on_deploy_ssh_key = on_deploy_ssh_key
        self._on_remove_ssh_key = on_remove_ssh_key
        self._on_open_tunnel = on_open_tunnel
        self._on_open_in_winscp = on_open_in_winscp
        self._on_run_remote_command = on_run_remote_command
        self._on_open_via_jumphost = on_open_via_jumphost
        self._on_ui_state_changed = on_ui_state_changed
        self._suppress_next_click = False

        # item_id → Session (nur für Session-Zeilen, nicht Ordner)
        self._item_to_session: dict[str, Session] = {}
        # item_id → checked state
        self._checked: dict[str, bool] = {}
        # item_id → folder_key (z.B. "Extern/Sub")
        self._item_to_folder_key: dict[str, str] = {}
        # item_id → Status "ok" | "fail" | "checking" | None
        self._item_to_status: dict[str, str | None] = {}
        # session.key → hex-Farbe
        self._session_colors: dict[str, str] = dict(initial_session_colors or {})
        self._pre_search_open_folders: set[str] | None = None

        self._build()
        self.populate(sessions, open_folders=initial_open_folders or set())

    def _build(self) -> None:
        """Erstellt Treeview + Scrollbar."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._tv = ttk.Treeview(
            self,
            columns=("hostname", "port"),
            selectmode="none",  # Selektion via Checkboxen, nicht Highlight
        )
        self._tv.heading("#0", text="Name", anchor="w")
        self._tv.heading("hostname", text="Hostname", anchor="w")
        self._tv.heading("port", text="Port", anchor="w")
        self._tv.column("#0", width=340, stretch=True)
        self._tv.column("hostname", width=130, stretch=False)
        self._tv.column("port", width=60, stretch=False)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)

        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Events
        self._tv.bind("<ButtonRelease-1>", self._on_left_click)
        self._tv.bind("<Double-Button-1>", self._on_double_click)
        self._tv.bind("<ButtonRelease-3>", self._on_right_click)
        self._tv.bind("<<TreeviewOpen>>", lambda _e: self._notify_ui_state_changed())
        self._tv.bind("<<TreeviewClose>>", lambda _e: self._notify_ui_state_changed())

        self._configure_color_tags()

    def _configure_color_tags(self) -> None:
        """Registriert für jede Palettenfarbe einen Treeview-Tag."""
        for _, hex_color in PALETTE:
            self._tv.tag_configure(_color_tag(hex_color), foreground=hex_color)

    def get_open_folders(self) -> set[str]:
        """Gibt folder_keys aller aktuell geöffneten Ordner zurück."""
        return {
            fkey
            for item_id, fkey in self._item_to_folder_key.items()
            if self._tv.item(item_id, "open")
        }

    def get_session_colors(self) -> dict[str, str]:
        """Gibt eine Kopie des aktuellen session_key → hex Mappings zurück."""
        return dict(self._session_colors)

    def _notify_ui_state_changed(self) -> None:
        if self._on_ui_state_changed:
            self._on_ui_state_changed()

    def set_session_color(self, session_key: str, hex_color: str | None) -> None:
        """Setzt oder entfernt die Textfarbe einer Session sofort im Tree."""
        if hex_color:
            self._session_colors[session_key] = hex_color
        else:
            self._session_colors.pop(session_key, None)
        for item_id, session in self._item_to_session.items():
            if session.key == session_key:
                color_tag = _color_tag(hex_color) if hex_color else None
                tags = (self.TAG_SESSION,) + ((color_tag,) if color_tag else ())
                self._tv.item(item_id, tags=tags)
                break
        self._notify_ui_state_changed()

    def populate(self, sessions: list[Session], open_folders: set[str] | None = None) -> None:
        """Füllt den Baum mit Sessions. Löscht vorherige Inhalte."""
        # Zustand merken (welche Ordner waren offen?) – falls nicht extern übergeben
        if open_folders is None:
            open_folders = self.get_open_folders()

        # Alles löschen
        self._tv.delete(*self._tv.get_children())
        self._item_to_session.clear()
        self._checked.clear()
        self._item_to_folder_key.clear()
        self._item_to_status.clear()

        # Ordner-Nodes: folder_key → item_id
        folder_items: dict[str, str] = {}

        for session in sessions:
            # Ordner-Hierarchie aufbauen
            parent_id = ""
            for depth, folder_name in enumerate(session.folder_path):
                folder_key = "/".join(session.folder_path[: depth + 1])
                if folder_key not in folder_items:
                    was_open = folder_key in open_folders
                    folder_label = f"  ⚙ {folder_name}" if folder_key == _SSH_CONFIG_DEFAULT_FOLDER else f"  {folder_name}"
                    folder_id = self._tv.insert(
                        parent_id, "end",
                        text=folder_label,
                        open=was_open,
                        tags=(self.TAG_FOLDER,),
                    )
                    self._tv.tag_bind(folder_id, "<<TreeviewOpen>>", lambda e: None)
                    folder_items[folder_key] = folder_id
                    self._item_to_folder_key[folder_id] = folder_key
                parent_id = folder_items[folder_key]

            # Session-Zeile
            port_str = str(session.port) if session.port != 22 else ""
            _ctag = _color_tag(self._session_colors[session.key]) if session.key in self._session_colors else None
            _tags = (self.TAG_SESSION,) + ((_ctag,) if _ctag else ())
            label = self._session_label(session, None)
            item_id = self._tv.insert(
                parent_id, "end",
                image=self._img_unchecked,
                text=label,
                values=(session.hostname, port_str),
                tags=_tags,
            )
            self._item_to_session[item_id] = session
            self._checked[item_id] = False

    def _on_left_click(self, event: tk.Event) -> None:
        """Checkbox togglen wenn auf eine Session-Zeile geklickt wird."""
        if self._suppress_next_click:
            self._suppress_next_click = False
            return
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._toggle(item_id)

    def _on_double_click(self, event: tk.Event) -> None:
        """Einzelne Session per Doppelklick direkt öffnen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._suppress_next_click = True
        if self._on_quick_connect:
            self._on_quick_connect(self._item_to_session[item_id])

    def _toggle(self, item_id: str) -> None:
        """Checkbox-Zustand einer Session-Zeile umschalten."""
        new_state = not self._checked.get(item_id, False)
        self._checked[item_id] = new_state
        self._tv.item(
            item_id,
            image=self._img_checked if new_state else self._img_unchecked,
        )
        self._notify_count()
        self._notify_ui_state_changed()

    def _notify_count(self) -> None:
        count = sum(1 for v in self._checked.values() if v)
        self._on_selection_changed(count)

    def get_selected_sessions(self) -> list[Session]:
        """Gibt alle ausgewählten (gecheckte) Sessions zurück."""
        return [
            self._item_to_session[iid]
            for iid, checked in self._checked.items()
            if checked
        ]

    def set_all_checked(self, state: bool) -> None:
        """Alle sichtbaren Session-Zeilen an-/abhaken."""
        for item_id in self._checked:
            self._checked[item_id] = state
            self._tv.item(
                item_id,
                image=self._img_checked if state else self._img_unchecked,
            )
        self._notify_count()
        self._notify_ui_state_changed()

    def _set_folder_checked(self, folder_item_id: str, state: bool) -> None:
        """Alle Session-Zeilen unter einem Ordner an-/abhaken (rekursiv)."""
        self._set_folder_checked_inner(folder_item_id, state)
        self._notify_count()
        self._notify_ui_state_changed()

    def _set_folder_checked_inner(self, folder_item_id: str, state: bool) -> None:
        """Rekursiver Kern ohne Notification – nur von _set_folder_checked aufrufen."""
        for child_id in self._tv.get_children(folder_item_id):
            tags = self._tv.item(child_id, "tags")
            if self.TAG_SESSION in tags:
                self._checked[child_id] = state
                self._tv.item(
                    child_id,
                    image=self._img_checked if state else self._img_unchecked,
                )
            elif self.TAG_FOLDER in tags:
                self._set_folder_checked_inner(child_id, state)

    def _on_right_click(self, event: tk.Event) -> None:
        """Kontextmenü je nach Zeilentyp anzeigen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        tags = self._tv.item(item_id, "tags")
        if self.TAG_FOLDER in tags:
            self._show_folder_menu(item_id, event)
        elif self.TAG_SESSION in tags:
            self._show_session_menu(item_id, event)

    def _set_folder_open_recursive(self, folder_item_id: str, state: bool) -> None:
        """Klappt einen Ordner rekursiv auf oder zu."""
        self._tv.item(folder_item_id, open=state)
        for child_id in self._tv.get_children(folder_item_id):
            if self.TAG_FOLDER in self._tv.item(child_id, "tags"):
                self._set_folder_open_recursive(child_id, state)
        self._notify_ui_state_changed()

    def _show_folder_menu(self, item_id: str, event: tk.Event) -> None:
        """Kontextmenü für Ordner-Zeilen."""
        folder_key = self._item_to_folder_key.get(item_id, "")
        menu = tk.Menu(self, tearoff=False)
        if folder_key == _SSH_CONFIG_DEFAULT_FOLDER and self._on_open_ssh_config_in_vscode:
            menu.add_command(
                label="In VS Code öffnen",
                command=self._on_open_ssh_config_in_vscode,
            )
            menu.add_separator()
        if self._on_add_session_in_folder:
            menu.add_command(
                label="Neue Verbindung hier…",
                command=lambda fk=folder_key: self._on_add_session_in_folder(fk),
            )
            menu.add_separator()
        menu.add_command(
            label="Alle im Ordner auswählen",
            command=lambda: self._set_folder_checked(item_id, True),
        )
        menu.add_command(
            label="Alle im Ordner abwählen",
            command=lambda: self._set_folder_checked(item_id, False),
        )
        menu.add_separator()
        menu.add_command(
            label="Alle Unterordner ausklappen",
            command=lambda: self._set_folder_open_recursive(item_id, True),
        )
        menu.add_command(
            label="Alle Unterordner einklappen",
            command=lambda: self._set_folder_open_recursive(item_id, False),
        )
        folder_sessions = self._get_folder_sessions(item_id)
        if folder_sessions:
            winscp_sessions = [s for s in folder_sessions if s.source == "winscp"]
            if winscp_sessions and self._on_open_in_winscp:
                menu.add_command(
                    label=f"Alle in WinSCP öffnen ({len(winscp_sessions)})",
                    command=lambda ss=winscp_sessions: self._on_open_in_winscp(ss),
                )
            if self._on_run_remote_command:
                menu.add_command(
                    label=f"Befehl auf Ordner ausführen… ({len(folder_sessions)})",
                    command=lambda ss=list(folder_sessions): self._on_run_remote_command(ss),
                )
            hostnames = [s.hostname for s in folder_sessions if s.hostname]
            menu.add_command(
                label="Hostnames kopieren",
                command=lambda hs=hostnames: (
                    self.clipboard_clear(),
                    self.clipboard_append("\n".join(hs)),
                ),
            )
            menu.add_command(
                label="Hosts prüfen",
                command=lambda fid=item_id: self.check_folder_hosts(fid),
            )
        if folder_sessions and all(s.source in ("app", "ssh_alias") for s in folder_sessions):
            menu.add_separator()
            if self._on_rename_folder:
                menu.add_command(
                    label="Umbenennen…",
                    command=lambda fk=folder_key: self._on_rename_folder(fk),
                )
            if self._on_delete_folder:
                menu.add_command(
                    label="Ordner löschen",
                    command=lambda ss=list(folder_sessions), fk=folder_key: self._on_delete_folder(ss, fk),
                )
        if folder_sessions:
            color_menu = tk.Menu(menu, tearoff=False)
            for name, hex_color in PALETTE:
                color_menu.add_command(
                    label=f"  {name}",
                    command=lambda hc=hex_color, ss=list(folder_sessions): [
                        self.set_session_color(s.key, hc) for s in ss
                    ],
                )
            color_menu.add_separator()
            color_menu.add_command(
                label="✕ Farbe entfernen",
                command=lambda ss=list(folder_sessions): [
                    self.set_session_color(s.key, None) for s in ss
                ],
            )
            menu.add_separator()
            menu.add_cascade(label="Farbe für alle…", menu=color_menu)
        if folder_sessions and (self._on_deploy_ssh_key or self._on_remove_ssh_key):
            menu.add_separator()
            if self._on_deploy_ssh_key:
                menu.add_command(
                    label="SSH Key übertragen…",
                    command=lambda ss=list(folder_sessions): self._on_deploy_ssh_key(ss),
                )
            if self._on_remove_ssh_key:
                menu.add_command(
                    label="SSH Key entfernen…",
                    command=lambda ss=list(folder_sessions): self._on_remove_ssh_key(ss),
                )
        menu.tk_popup(event.x_root, event.y_root)

    def _show_session_menu(self, item_id: str, event: tk.Event) -> None:
        """Kontextmenü für Session-Zeilen mit Farb-Submenu."""
        session = self._item_to_session[item_id]
        current_color = self._session_colors.get(session.key)

        menu = tk.Menu(self, tearoff=False)
        color_menu = tk.Menu(menu, tearoff=False)
        for name, hex_color in PALETTE:
            prefix = "✓" if hex_color == current_color else "  "
            color_menu.add_command(
                label=f"{prefix} {name}",
                command=lambda hc=hex_color, sk=session.key: self.set_session_color(sk, hc),
            )
        color_menu.add_separator()
        color_menu.add_command(
            label="✕ Farbe entfernen",
            command=lambda sk=session.key: self.set_session_color(sk, None),
        )
        if self._on_quick_connect:
            menu.add_command(
                label="Verbindung öffnen",
                command=lambda s=session: self._on_quick_connect(s),
            )
        if self._on_open_in_winscp and session.source == "winscp":
            selected_winscp = [s for s in self.get_selected_sessions() if s.source == "winscp"]
            if len(selected_winscp) >= 2:
                menu.add_command(
                    label=f"Alle {len(selected_winscp)} in WinSCP öffnen",
                    command=lambda ss=selected_winscp: self._on_open_in_winscp(ss),
                )
            else:
                menu.add_command(
                    label="In WinSCP öffnen",
                    command=lambda s=session: self._on_open_in_winscp([s]),
                )
        if self._on_open_tunnel:
            menu.add_command(
                label="Tunnel öffnen…",
                command=lambda s=session: self._on_open_tunnel(s),
            )
        if self._on_open_via_jumphost:
            menu.add_command(
                label="Über Jumphost öffnen…",
                command=lambda s=session: self._on_open_via_jumphost(s),
            )
        if self._on_run_remote_command:
            menu.add_command(
                label="Befehl ausführen…",
                command=lambda s=session: self._on_run_remote_command([s]),
            )
            selected_runnable = [s for s in self.get_selected_sessions() if s.hostname]
            if len(selected_runnable) >= 2:
                menu.add_command(
                    label=f"Befehl auf Auswahl ausführen… ({len(selected_runnable)})",
                    command=lambda ss=selected_runnable: self._on_run_remote_command(ss),
                )
        if self._on_quick_connect or self._on_open_tunnel or self._on_open_via_jumphost or self._on_run_remote_command:
            menu.add_separator()
        if self._on_deploy_ssh_key or self._on_remove_ssh_key:
            if self._on_deploy_ssh_key:
                menu.add_command(
                    label="SSH Key übertragen…",
                    command=lambda s=session: self._on_deploy_ssh_key([s]),
                )
            if self._on_remove_ssh_key:
                menu.add_command(
                    label="SSH Key entfernen…",
                    command=lambda s=session: self._on_remove_ssh_key([s]),
                )
            menu.add_separator()
        if session.is_app_session:
            if self._on_edit_session:
                menu.add_command(
                    label="Bearbeiten…",
                    command=lambda s=session: self._on_edit_session(s),
                )
            if self._on_duplicate_app_session:
                menu.add_command(
                    label="Duplizieren…",
                    command=lambda s=session: self._on_duplicate_app_session(s),
                )
            if self._on_move_session:
                menu.add_command(
                    label="In Ordner verschieben…",
                    command=lambda s=session: self._on_move_session(s),
                )
            if self._on_delete_session:
                menu.add_command(
                    label="Löschen",
                    command=lambda s=session: self._on_delete_session(s),
                )
            menu.add_separator()
        elif session.source == "ssh_config":
            if self._on_duplicate_ssh_alias:
                menu.add_command(
                    label="Als Alias in Ordner duplizieren…",
                    command=lambda s=session: self._on_duplicate_ssh_alias(s),
                )
            if self._on_inspect_ssh_config:
                menu.add_command(
                    label="Konfiguration anzeigen (ssh -G)…",
                    command=lambda s=session: self._on_inspect_ssh_config(s),
                )
            if self._on_open_ssh_config_in_vscode:
                menu.add_command(
                    label="In VS Code öffnen",
                    command=self._on_open_ssh_config_in_vscode,
                )
            menu.add_separator()
        elif session.is_ssh_alias_copy:
            if self._on_delete_session:
                menu.add_command(
                    label="Löschen",
                    command=lambda s=session: self._on_delete_session(s),
                )
            if self._on_move_session:
                menu.add_command(
                    label="In Ordner verschieben…",
                    command=lambda s=session: self._on_move_session(s),
                )
            if self._on_inspect_ssh_config:
                menu.add_command(
                    label="Konfiguration anzeigen (ssh -G)…",
                    command=lambda s=session: self._on_inspect_ssh_config(s),
                )
            if self._on_open_ssh_config_in_vscode:
                menu.add_command(
                    label="In VS Code öffnen",
                    command=self._on_open_ssh_config_in_vscode,
                )
            menu.add_separator()
        menu.add_command(
            label="Hostname kopieren",
            command=lambda h=session.hostname: (self.clipboard_clear(), self.clipboard_append(h)),
        )
        selected = self.get_selected_sessions()
        if len(selected) >= 2:
            hostnames = "\n".join(s.hostname for s in selected)
            menu.add_command(
                label=f"Alle {len(selected)} Hostnamen kopieren",
                command=lambda hs=hostnames: (self.clipboard_clear(), self.clipboard_append(hs)),
            )
        # Hosts prüfen
        if len(selected) >= 2:
            checked_pairs = [
                (iid, s) for iid, s in self._item_to_session.items()
                if self._checked.get(iid) and s.hostname
            ]
            menu.add_command(
                label=f"Alle {len(selected)} Hosts prüfen",
                command=lambda p=checked_pairs: self.check_hosts(p),
            )
        elif session.hostname:
            menu.add_command(
                label="Host prüfen",
                command=lambda iid=item_id, s=session: self.check_hosts([(iid, s)]),
            )
        menu.add_separator()
        if len(selected) >= 2:
            bulk_color_menu = tk.Menu(menu, tearoff=False)
            for name, hex_color in PALETTE:
                bulk_color_menu.add_command(
                    label=f"  {name}",
                    command=lambda hc=hex_color, ss=list(selected): [
                        self.set_session_color(s.key, hc) for s in ss
                    ],
                )
            bulk_color_menu.add_separator()
            bulk_color_menu.add_command(
                label="✕ Farbe entfernen",
                command=lambda ss=list(selected): [
                    self.set_session_color(s.key, None) for s in ss
                ],
            )
            menu.add_cascade(label=f"Farbe für Auswahl ({len(selected)})…", menu=bulk_color_menu)
            moveable = [s for s in selected if s.source in ("app", "ssh_alias")]
            if moveable and self._on_move_sessions:
                menu.add_command(
                    label=f"Ordner für Auswahl ({len(moveable)})…",
                    command=lambda ss=moveable: self._on_move_sessions(ss),
                )
        else:
            menu.add_cascade(label="Farbe…", menu=color_menu)
        menu.tk_popup(event.x_root, event.y_root)

    def filter(self, query: str) -> None:
        """
        Filtert sichtbare Sessions nach query (case-insensitive, Name + Hostname).
        Bei leerem query werden alle Sessions wieder angezeigt.
        Checkbox-Zustände bleiben beim Filtern erhalten.
        Während einer aktiven Suche wird der Tree vollständig aufgeklappt;
        beim Leeren wird der Zustand von vor der Suche wiederhergestellt.
        """
        q = query.strip().lower()

        # Checkbox-Zustände vor dem Neuaufbau sichern (item_id ändert sich)
        checked_keys = {
            self._item_to_session[iid].key
            for iid, v in self._checked.items()
            if v
        }

        # Zustand beim ersten Suchzeichen einmalig sichern
        if q and self._pre_search_open_folders is None:
            self._pre_search_open_folders = self.get_open_folders()

        if q:
            filtered = [
                s for s in self._sessions
                if q in s.display_name.lower() or q in s.hostname.lower()
            ]
            # Alle Ordner der Treffer aufklappen
            open_folders: set[str] | None = {
                "/".join(s.folder_path[:d + 1])
                for s in filtered
                for d in range(len(s.folder_path))
            }
        else:
            filtered = self._sessions
            # Vorherigen Zustand wiederherstellen
            open_folders = self._pre_search_open_folders
            self._pre_search_open_folders = None

        self.populate(filtered, open_folders=open_folders)

        # Checkbox-Zustände wiederherstellen
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)

        self._notify_count()

    def expand_all(self) -> None:
        """Klappt alle Ordner auf."""
        for item_id in self._item_to_folder_key:
            self._tv.item(item_id, open=True)
        self._notify_ui_state_changed()

    def collapse_all(self) -> None:
        """Klappt alle Ordner zu."""
        for item_id in self._item_to_folder_key:
            self._tv.item(item_id, open=False)
        self._notify_ui_state_changed()

    def refresh(self, sessions: list[Session]) -> None:
        """Baut den Baum mit neuen Sessions neu auf, behält Ordner-Status und Checkboxen."""
        open_folders = self.get_open_folders()
        checked_keys = {
            s.key for iid, s in self._item_to_session.items() if self._checked.get(iid)
        }
        self._sessions = sessions
        self.populate(sessions, open_folders=open_folders)
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)
        self._notify_count()

    def _session_label(self, session: Session, status: str | None) -> str:
        """Baut den Anzeigetext einer Session-Zeile inkl. Status-Symbol."""
        symbol = {"ok": "✓", "fail": "✗", "checking": "⏳"}.get(status or "", "")
        if session.is_ssh_config_session:
            type_icon = "⚙ "
        elif session.is_app_session:
            type_icon = "★ "
        else:
            type_icon = ""
        prefix = f"  {symbol + ' ' if symbol else ''}"
        return f"{prefix}{type_icon}{session.display_name}"

    def _set_item_status(self, item_id: str, status: str | None) -> None:
        """Setzt den Status einer Session-Zeile und aktualisiert den Label-Text."""
        self._item_to_status[item_id] = status
        session = self._item_to_session.get(item_id)
        if session:
            self._tv.item(item_id, text=self._session_label(session, status))

    def check_hosts(self, item_session_pairs: list[tuple[str, Session]]) -> None:
        """Prüft TCP-Erreichbarkeit aller übergebenen Sessions asynchron."""
        for item_id, _ in item_session_pairs:
            self._set_item_status(item_id, "checking")

        def _probe(item_id: str, hostname: str, port: int) -> None:
            ok = check_host_reachable(hostname, port)
            self.after(0, lambda iid=item_id, s=ok: self._set_item_status(iid, "ok" if s else "fail"))

        for item_id, session in item_session_pairs:
            if session.hostname:
                threading.Thread(
                    target=_probe,
                    args=(item_id, session.hostname, session.port or 22),
                    daemon=True,
                ).start()

    def check_selected_hosts(self, timeout: int = 3) -> None:
        """Prüft alle aktuell ausgewählten Sessions."""
        pairs = [
            (iid, s) for iid, s in self._item_to_session.items()
            if self._checked.get(iid) and s.hostname
        ]
        if pairs:
            self.check_hosts(pairs)

    def check_folder_hosts(self, folder_item_id: str) -> None:
        """Prüft alle Sessions eines Ordners."""
        pairs = [
            (iid, s)
            for iid, s in self._item_to_session.items()
            if s.hostname and self._tv.parent(iid) == folder_item_id
               or self._is_in_folder(iid, folder_item_id)
        ]
        # eindeutige Paare (durch zwei Bedingungen oben keine Duplikate nötig)
        seen: set[str] = set()
        unique = []
        for iid, s in pairs:
            if iid not in seen and self._is_in_folder(iid, folder_item_id) and s.hostname:
                seen.add(iid)
                unique.append((iid, s))
        if unique:
            self.check_hosts(unique)

    def _is_in_folder(self, item_id: str, folder_item_id: str) -> bool:
        """Prüft rekursiv ob item_id unter folder_item_id liegt."""
        parent = self._tv.parent(item_id)
        if not parent:
            return False
        if parent == folder_item_id:
            return True
        return self._is_in_folder(parent, folder_item_id)

    def _get_folder_sessions(self, folder_item_id: str) -> list[Session]:
        """Gibt alle Sessions rekursiv unter einem Ordner-Item zurück."""
        result = []
        for child_id in self._tv.get_children(folder_item_id):
            tags = self._tv.item(child_id, "tags")
            if self.TAG_SESSION in tags:
                result.append(self._item_to_session[child_id])
            elif self.TAG_FOLDER in tags:
                result.extend(self._get_folder_sessions(child_id))
        return result


# ---------------------------------------------------------------------------
# UserDialog
# ---------------------------------------------------------------------------
class UserDialog(tk.Toplevel):
    """
    Modaler Dialog zur Benutzernamen-Auswahl.
    Nach Schließen: self.result = gewählter Username (str) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, title: str = "Benutzername auswählen", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result: Optional[str] = None
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        # Modal machen
        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        # Tastaturkürzel
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        quick_count = max(len(self._quick_users), 1)
        ttk.Label(frame, text="Quickselect:").grid(
            row=0, column=0, columnspan=quick_count, sticky="w", pady=(0, 4)
        )

        self._user_var = tk.StringVar(value=self._default_user)

        # Quickselect-Buttons
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=1, column=col, padx=2, pady=(0, 8))

        # Freitext-Eingabe
        ttk.Label(frame, text="Benutzername:").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=3, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.select_range(0, "end")
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(
            side="left", padx=4
        )

    def _on_ok(self) -> None:
        user = self._user_var.get().strip()
        if not user:
            return  # Leeres Feld: Dialog bleibt offen
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = user
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


class JumpHostDialog(tk.Toplevel):
    """Dialog zum temporären Öffnen einer Session über ProxyJump."""

    def __init__(self, parent: tk.Tk, target_session: Session, sessions: list[Session], open_folders_getter: Callable[[], set[str]] | None = None):
        super().__init__(parent)
        self.title("Über Jumphost öffnen")
        self.resizable(True, True)
        self.minsize(760, 520)
        self.result: tuple[str, str, int, str | None] | None = None
        self.save_result: tuple[str, str, int, str, str] | None = None
        self._target_session = target_session
        self._sessions = sessions
        self._open_folders_getter = open_folders_getter

        self.transient(parent)
        self.grab_set()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        self._build()
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(4, weight=1)

        target_label = f"Ziel: {self._target_session.display_name} ({self._target_session.hostname})"
        ttk.Label(frame, text=target_label, font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        help_text = (
            "Jumphost frei eingeben oder unten im Baum eine bestehende Verbindung auswählen.\n"
            "Aus einer Verbindung werden Host, User und Port übernommen, wenn vorhanden."
        )
        ttk.Label(frame, text=help_text, foreground="#555555", justify="left").grid(row=1, column=0, sticky="w", pady=(0, 10))

        form = ttk.Frame(frame)
        form.grid(row=2, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        self._jump_host_var = tk.StringVar()
        default_user = getattr(parent, "get_default_user", lambda: DEFAULT_USER)()
        self._jump_user_var = tk.StringVar(value=default_user)
        self._jump_port_var = tk.StringVar(value="22")
        self._filter_var = tk.StringVar()

        ttk.Label(form, text="Jumphost:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        host_entry = ttk.Entry(form, textvariable=self._jump_host_var)
        host_entry.grid(row=0, column=1, sticky="ew", pady=4)
        host_entry.focus()

        ttk.Label(form, text="Jumphost-User:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(form, textvariable=self._jump_user_var).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(form, text="Jumphost-Port:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        ttk.Entry(form, textvariable=self._jump_port_var, width=8).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Label(form, text="Filter:").grid(row=3, column=0, sticky="w", pady=(10, 4), padx=(0, 8))
        filter_entry = ttk.Entry(form, textvariable=self._filter_var)
        filter_entry.grid(row=3, column=1, sticky="ew", pady=(10, 4))
        self._filter_var.trace_add("write", lambda *_: self._rebuild_tree())

        tree_frame = ttk.Frame(frame)
        tree_frame.grid(row=4, column=0, sticky="nsew", pady=(8, 8))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(tree_frame, columns=("host",), show="tree headings", selectmode="browse")
        self._tree.heading("#0", text="Verbindungen")
        self._tree.heading("host", text="Host")
        self._tree.column("#0", width=320, stretch=True)
        self._tree.column("host", width=280, stretch=True)
        self._tree.grid(row=0, column=0, sticky="nsew")
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-Button-1>", lambda _: self._on_open())

        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self._tree.configure(yscrollcommand=scroll.set)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, sticky="e", pady=(6, 0))
        ttk.Button(btn_frame, text="Als SSH-Config speichern…", command=self._on_save).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Öffnen", command=self._on_open).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel).pack(side="left", padx=4)

        self._session_by_item: dict[str, Session] = {}
        self._rebuild_tree()

    def _matches_filter(self, session: Session, query: str) -> bool:
        if not query:
            return True
        hay = f"{session.folder_key} {session.display_name} {session.hostname}".lower()
        return query in hay

    def _ensure_folder(self, folder_key: str, folder_map: dict[str, str]) -> str:
        if not folder_key:
            return ""
        parts = folder_key.split("/")
        current = ""
        parent = ""
        for part in parts:
            current = part if not current else f"{current}/{part}"
            if current not in folder_map:
                folder_map[current] = self._tree.insert(parent, "end", text=part, values=("",), open=False)
            parent = folder_map[current]
        return folder_map[current]

    def _rebuild_tree(self) -> None:
        query = self._filter_var.get().strip().lower()
        open_folders = self._open_folders_getter() if self._open_folders_getter else set()
        self._tree.delete(*self._tree.get_children())
        self._session_by_item.clear()
        folder_map: dict[str, str] = {}
        for session in sorted(self._sessions, key=lambda s: (s.folder_key.lower(), s.display_name.lower())):
            if session.key == self._target_session.key:
                continue
            if not self._matches_filter(session, query):
                continue
            parent = self._ensure_folder(session.folder_key, folder_map)
            item = self._tree.insert(parent, "end", text=session.display_name, values=(session.hostname,))
            self._session_by_item[item] = session
        for folder_key, iid in folder_map.items():
            self._tree.item(iid, open=(folder_key in open_folders) or not query)

    def _on_tree_select(self, _event=None) -> None:
        selected = self._tree.selection()
        if not selected:
            return
        session = self._session_by_item.get(selected[0])
        if not session:
            return
        self._jump_host_var.set(session.hostname or session.display_name)
        self._jump_user_var.set(session.username or "")
        self._jump_port_var.set(str(session.port or 22))

    def _validate(self) -> tuple[str, str, int] | None:
        jump_host = self._jump_host_var.get().strip()
        if not jump_host:
            messagebox.showwarning("Kein Jumphost", "Bitte einen Jumphost eingeben oder auswählen.", parent=self)
            return None
        if not _HOSTNAME_RE.match(jump_host):
            messagebox.showwarning("Ungültiger Jumphost", "Nur Buchstaben, Ziffern, Punkte, Doppelpunkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return None
        jump_user = self._jump_user_var.get().strip()
        if jump_user and not _USERNAME_RE.match(jump_user):
            messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return None
        try:
            jump_port = int(self._jump_port_var.get().strip() or "22")
        except ValueError:
            messagebox.showwarning("Ungültiger Port", "Jumphost-Port muss eine Zahl sein.", parent=self)
            return None
        if not 1 <= jump_port <= 65535:
            messagebox.showwarning("Ungültiger Port", "Jumphost-Port muss zwischen 1 und 65535 liegen.", parent=self)
            return None
        return jump_host, jump_user, jump_port

    def _on_open(self) -> None:
        validated = self._validate()
        if not validated:
            return
        self.result = validated
        self.destroy()

    def _on_save(self) -> None:
        validated = self._validate()
        if not validated:
            return
        alias = simpledialog.askstring("SSH-Config speichern", "Name für den neuen SSH-Config-Host:", parent=self)
        if alias is None:
            return
        alias = alias.strip()
        if not alias:
            messagebox.showwarning("Kein Name", "Bitte einen Namen für den SSH-Config-Host eingeben.", parent=self)
            return
        jump_host, jump_user, jump_port = validated
        self.save_result = (alias, jump_host, jump_port, jump_user, self._target_session.key)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.save_result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = min(max(self.winfo_reqwidth(), 760), max(pw - 40, 760))
        h = min(max(self.winfo_reqheight(), 520), max(ph - 40, 520))
        x = px + max((pw - w) // 2, 0)
        y = py + max((ph - h) // 2, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")


# ---------------------------------------------------------------------------
# SshCopyIdDialog
# ---------------------------------------------------------------------------
class SshCopyIdDialog(tk.Toplevel):
    """
    Modaler Dialog zur Auswahl von SSH Public Key und Benutzername für ssh-copy-id.
    Nach Schließen: self.result = (key_filename, user) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, target_count: int = 1, quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("SSH Key übertragen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._target_count = target_count
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        # Info bei mehreren Zielen
        if self._target_count > 1:
            ttk.Label(
                frame,
                text=f"Key wird auf {self._target_count} Host(s) übertragen.",
                foreground="#555555",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        # Key-Auswahl
        ttk.Label(frame, text="Public Key:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        pub_keys = sorted(p.name for p in (_SSH_CONFIG_FILE.parent).glob("*.pub"))
        self._key_var = tk.StringVar(value=pub_keys[0] if pub_keys else "")
        key_cb = ttk.Combobox(
            frame, textvariable=self._key_var, values=pub_keys, width=30, state="readonly" if pub_keys else "normal"
        )
        key_cb.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        if not pub_keys:
            ttk.Label(frame, text="Keine *.pub-Dateien in ~/.ssh gefunden.", foreground="red").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )

        # Benutzer
        ttk.Label(frame, text="Quickselect:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=4, column=col, padx=2, pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=5, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=6, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            messagebox.showwarning("Kein Key", "Bitte einen Public Key auswählen.", parent=self)
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (key, user)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SshRemoveKeyDialog
# ---------------------------------------------------------------------------
class SshRemoveKeyDialog(tk.Toplevel):
    """
    Modaler Dialog zur Auswahl von SSH Public Key und Benutzername zum Entfernen
    des Keys aus authorized_keys auf Remote-Hosts.
    Nach Schließen: self.result = (key_filename, user) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, target_count: int = 1, quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("SSH Key entfernen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self._target_count = target_count
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        if self._target_count > 1:
            ttk.Label(
                frame,
                text=f"Key wird von {self._target_count} Host(s) entfernt.",
                foreground="#555555",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Public Key:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        pub_keys = sorted(p.name for p in (_SSH_CONFIG_FILE.parent).glob("*.pub"))
        self._key_var = tk.StringVar(value=pub_keys[0] if pub_keys else "")
        key_cb = ttk.Combobox(
            frame, textvariable=self._key_var, values=pub_keys, width=30, state="readonly" if pub_keys else "normal"
        )
        key_cb.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4))
        if not pub_keys:
            ttk.Label(frame, text="Keine *.pub-Dateien in ~/.ssh gefunden.", foreground="red").grid(
                row=2, column=0, columnspan=2, sticky="w"
            )

        ttk.Label(frame, text="Quickselect:").grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=4, column=col, padx=2, pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=5, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=6, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        key = self._key_var.get().strip()
        if not key:
            messagebox.showwarning("Kein Key", "Bitte einen Public Key auswählen.", parent=self)
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (key, user)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")




class RemoteCommandDialog(tk.Toplevel):
    """Dialog für Remote-Befehl und Ausführungsoptionen."""

    def __init__(self, parent: tk.Tk, target_count: int, last_command: str = "", quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("Befehl ausführen")
        self.geometry("720x480")
        self.minsize(620, 420)
        self.result: tuple[str, str, bool] | None = None
        self._last_command = last_command
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()
        self._build(target_count)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, target_count: int) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(
            frame,
            text=f"Remote-Befehl für {target_count} Host(s)",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Label(
            frame,
            text="Der Befehl wird als mehrzeiliges Remote-Script per SSH ausgeführt.",
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        mode_frame = ttk.LabelFrame(frame, text="Benutzer-Auswahl", padding=12)
        mode_frame.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        mode_frame.columnconfigure(0, weight=1)
        self._user_mode = tk.StringVar(value="all")
        ttk.Radiobutton(
            mode_frame,
            text="Ein Benutzer für alle Hosts",
            variable=self._user_mode,
            value="all",
        ).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(
            mode_frame,
            text="Benutzer pro Host auswählen",
            variable=self._user_mode,
            value="per_host",
        ).grid(row=1, column=0, sticky="w", pady=(4, 8))

        ttk.Label(mode_frame, text="Quickselect:").grid(row=2, column=0, sticky="w", pady=(0, 4))
        quick_frame = ttk.Frame(mode_frame)
        quick_frame.grid(row=3, column=0, sticky="w")
        self._user_var = tk.StringVar(value=self._default_user)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                quick_frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=0, column=col, padx=2, pady=(0, 6))

        user_entry_frame = ttk.Frame(mode_frame)
        user_entry_frame.grid(row=4, column=0, sticky="ew")
        user_entry_frame.columnconfigure(1, weight=1)
        ttk.Label(user_entry_frame, text="Benutzername:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(user_entry_frame, textvariable=self._user_var).grid(row=0, column=1, sticky="ew")

        script_frame = ttk.LabelFrame(frame, text="Remote-Befehl", padding=8)
        script_frame.grid(row=3, column=0, sticky="nsew")
        script_frame.columnconfigure(0, weight=1)
        script_frame.rowconfigure(0, weight=1)
        self._command_text = scrolledtext.ScrolledText(script_frame, wrap="word", height=12)
        self._command_text.grid(row=0, column=0, sticky="nsew")
        if self._last_command:
            self._command_text.insert("1.0", self._last_command)
        self._command_text.focus()

        options = ttk.Frame(frame)
        options.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self._close_on_success = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            options,
            text="Tab direkt schließen, wenn der Befehl erfolgreich war",
            variable=self._close_on_success,
        ).pack(anchor="w")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=5, column=0, pady=(14, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        command = self._command_text.get("1.0", "end").strip()
        if not command:
            messagebox.showwarning("Kein Befehl", "Bitte einen Befehl eingeben.", parent=self)
            return
        user_value = self._user_var.get().strip()
        if self._user_mode.get() == "all":
            if not user_value:
                messagebox.showwarning("Kein Benutzername", "Bitte einen Benutzernamen eingeben oder per Quickselect wählen.", parent=self)
                return
            if not _USERNAME_RE.match(user_value):
                messagebox.showwarning("Ungültiger Benutzername", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
                return
        self.result = (self._user_mode.get(), command, self._close_on_success.get())
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


class RemoteCommandConfirmDialog(tk.Toplevel):
    """Bestätigungsdialog für Remote-Befehle."""

    def __init__(self, parent: tk.Tk, command: str, session_users: list[tuple[Session, str]], close_on_success: bool):
        super().__init__(parent)
        self.title("Remote-Befehl bestätigen")
        self.geometry("760x520")
        self.minsize(680, 420)
        self.result = False

        self.transient(parent)
        self.grab_set()
        self._build(command, session_users, close_on_success)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, command: str, session_users: list[tuple[Session, str]], close_on_success: bool) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(
            frame,
            text=f"Befehl auf {len(session_users)} Host(s) ausführen?",
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        behavior = "Tabs schließen sich bei Erfolg direkt." if close_on_success else "Tabs bleiben nach dem Befehl offen."
        ttk.Label(frame, text=behavior, foreground="#666666").grid(row=1, column=0, sticky="w", pady=(0, 12))

        hosts_frame = ttk.LabelFrame(frame, text="Hosts", padding=8)
        hosts_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 12))
        hosts_frame.columnconfigure(0, weight=1)
        hosts_frame.rowconfigure(0, weight=1)
        hosts_text = scrolledtext.ScrolledText(hosts_frame, wrap="word", height=10)
        hosts_text.grid(row=0, column=0, sticky="nsew")
        hosts_text.insert(
            "1.0",
            "\n".join(
                f"- {session.display_name} ({session.hostname})  User: {user}"
                for session, user in session_users
            ),
        )
        hosts_text.configure(state="disabled")

        cmd_frame = ttk.LabelFrame(frame, text="Befehl", padding=8)
        cmd_frame.grid(row=3, column=0, sticky="nsew")
        cmd_frame.columnconfigure(0, weight=1)
        cmd_frame.rowconfigure(0, weight=1)
        cmd_text = scrolledtext.ScrolledText(cmd_frame, wrap="word", height=8)
        cmd_text.grid(row=0, column=0, sticky="nsew")
        cmd_text.insert("1.0", command)
        cmd_text.configure(state="disabled")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, pady=(14, 0))
        ttk.Button(btn_frame, text="Ausführen", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        self.result = True
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = False
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

# ---------------------------------------------------------------------------
# SshTunnelDialog
# ---------------------------------------------------------------------------
class SshTunnelDialog(tk.Toplevel):
    """
    Modaler Dialog für SSH Local Port Forwarding (-N -L).
    Nach Schließen: self.result = (ssh_server, local_port, remote_host, remote_port, user) oder None.
    remote_host ist 'localhost' wenn kein Jumphost-Ziel angegeben wurde (direkter Tunnel).
    """

    def __init__(self, parent: tk.Tk, session: Session | None = None, quick_users: list[str] | None = None, default_user: str = DEFAULT_USER):
        super().__init__(parent)
        self.title("Tunnel öffnen")
        self.resizable(False, False)
        self.result: tuple[str, int, str, int, str] | None = None
        self._session = session
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER

        self.transient(parent)
        self.grab_set()
        self._build()
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        # Erklärung
        ttk.Label(
            frame,
            text="SSH verbindet sich zum Server und leitet einen lokalen Port weiter.\nDirekt (kein Jumphost) oder zu einem internen Server dahinter.",
            foreground="#555555",
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))

        # SSH-Server
        ttk.Label(frame, text="SSH-Server:").grid(row=1, column=0, sticky="w", pady=(0, 4))
        prefill = self._session.hostname if self._session else ""
        self._jumphost_var = tk.StringVar(value=prefill)
        ttk.Entry(frame, textvariable=self._jumphost_var, width=30).grid(
            row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(frame, text="Server, zu dem SSH sich verbindet.", foreground="#888888").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 10)
        )

        ttk.Separator(frame, orient="horizontal").grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Port Forwarding
        ttk.Label(frame, text="Lokaler Port:").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self._local_port_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._local_port_var, width=10).grid(
            row=4, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(frame, text="Port auf deinem PC (z. B. 3306).", foreground="#888888").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text="Zielserver: (optional)").grid(row=6, column=0, sticky="w", pady=(0, 4))
        self._remote_host_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._remote_host_var, width=30).grid(
            row=6, column=1, sticky="ew", padx=(8, 0), pady=(0, 4)
        )

        ttk.Label(frame, text="Zielport:").grid(row=7, column=0, sticky="w", pady=(0, 4))
        self._remote_port_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self._remote_port_var, width=10).grid(
            row=7, column=1, sticky="w", padx=(8, 0), pady=(0, 4)
        )
        ttk.Label(
            frame,
            text="Leer lassen = direkter Tunnel (Port des SSH-Servers selbst).\nFür Jumphost-Tunnel: z. B. db.intern / 3306",
            foreground="#888888",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Separator(frame, orient="horizontal").grid(row=9, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        # Benutzer
        ttk.Label(frame, text="Quickselect:").grid(row=10, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self._user_var = tk.StringVar(value=self._default_user)
        quick_count = max(len(self._quick_users), 2)
        for col, username in enumerate(self._quick_users):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=11, column=col, padx=2, pady=(0, 8))

        ttk.Label(frame, text="Benutzername:").grid(row=12, column=0, sticky="w", pady=(0, 4))
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=13, column=0, columnspan=quick_count, sticky="ew", pady=(0, 12))
        entry.focus()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=14, column=0, columnspan=quick_count)
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _parse_port(self, var: tk.StringVar, label: str) -> int | None:
        try:
            port = int(var.get().strip())
        except ValueError:
            messagebox.showwarning("Ungültiger Port", f"{label} muss eine Zahl sein.", parent=self)
            return None
        if not 1 <= port <= 65535:
            messagebox.showwarning("Ungültiger Port", f"{label} muss zwischen 1 und 65535 liegen.", parent=self)
            return None
        return port

    def _on_ok(self) -> None:
        ssh_server = self._jumphost_var.get().strip()
        if not ssh_server:
            messagebox.showwarning("Kein SSH-Server", "Bitte einen SSH-Server eingeben.", parent=self)
            return
        if not _HOSTNAME_RE.match(ssh_server):
            messagebox.showwarning("Ungültiger SSH-Server", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return
        local_port = self._parse_port(self._local_port_var, "Lokaler Port")
        if local_port is None:
            return
        remote_host = self._remote_host_var.get().strip() or "localhost"
        if not _HOSTNAME_RE.match(remote_host):
            messagebox.showwarning("Ungültiger Zielserver", "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.", parent=self)
            return
        remote_port = self._parse_port(self._remote_port_var, "Zielport")
        if remote_port is None:
            return
        user = self._user_var.get().strip()
        if not user:
            return
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = (ssh_server, local_port, remote_host, remote_port, user)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SessionEditDialog
# ---------------------------------------------------------------------------
class SessionEditDialog(tk.Toplevel):
    """
    Modaler Dialog zum Anlegen oder Bearbeiten einer eigenen Session.
    Unterstützt zwei Modi: 'Eigene Verbindung' (Hostname/Port/User) und
    'SSH-Alias' (Alias aus ~/.ssh/config + Ordner).
    Nach Schließen: self.result = Session oder None (Abbrechen).
    """

    def __init__(
        self,
        parent: tk.Tk,
        existing_folders: list[str],
        ssh_aliases: list[str] | None = None,
        session: Optional[Session] = None,
        folder_preset: str = "",
        alias_preset: str = "",
        duplicate: bool = False,
    ):
        super().__init__(parent)
        self._existing_session = session
        self._duplicate = duplicate
        self._existing_folders = existing_folders
        self._ssh_aliases = ssh_aliases or []
        self._alias_preset = alias_preset

        # Startmodus: Alias-Modus wenn Preset gesetzt oder bestehende ssh_alias Session
        if (session and session.is_ssh_alias_copy) or alias_preset:
            self._initial_mode = "alias"
        else:
            self._initial_mode = "verbindung"

        if duplicate:
            self.title("Verbindung duplizieren")
        elif session:
            self.title("Verbindung bearbeiten")
        else:
            self.title("Neue Verbindung")
        self.resizable(False, False)
        self.result: Optional[Session] = None

        self.transient(parent)
        self.grab_set()

        self._build(folder_preset)
        self._center_on_parent(parent)

        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, folder_preset: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        self._mode_var = tk.StringVar(value=self._initial_mode)
        content_row = 0

        # Modus-Auswahl (nur wenn Aliases vorhanden und kein Bearbeitungsmodus)
        can_switch = bool(self._ssh_aliases) and not self._existing_session
        if can_switch:
            mode_frame = ttk.Frame(frame)
            mode_frame.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
            ttk.Radiobutton(
                mode_frame, text="Eigene Verbindung",
                variable=self._mode_var, value="verbindung",
                command=self._on_mode_changed,
            ).pack(side="left", padx=(0, 12))
            ttk.Radiobutton(
                mode_frame, text="SSH-Alias",
                variable=self._mode_var, value="alias",
                command=self._on_mode_changed,
            ).pack(side="left")
            content_row = 1

        s = self._existing_session

        # --- SSH-Alias Frame ---
        self._alias_frame = ttk.Frame(frame)
        self._alias_frame.columnconfigure(1, weight=1)
        self._alias_frame.grid(row=content_row, column=0, columnspan=2, sticky="ew")

        ttk.Label(self._alias_frame, text="Alias:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        alias_val = self._alias_preset or (s.display_name if s and s.is_ssh_alias_copy else "")
        self._alias_var = tk.StringVar(value=alias_val)
        alias_cb_state = "readonly" if self._alias_preset else "normal"
        ttk.Combobox(
            self._alias_frame, textvariable=self._alias_var,
            values=self._ssh_aliases, width=30, state=alias_cb_state,
        ).grid(row=0, column=1, sticky="ew")

        ttk.Label(self._alias_frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        alias_folder_val = (s.folder_key if s and s.is_ssh_alias_copy else folder_preset)
        self._alias_folder_var = tk.StringVar(value=alias_folder_val)
        ttk.Combobox(
            self._alias_frame, textvariable=self._alias_folder_var,
            values=self._existing_folders, width=30,
        ).grid(row=1, column=1, sticky="ew")

        # --- Eigene Verbindung Frame ---
        self._verbindung_frame = ttk.Frame(frame)
        self._verbindung_frame.columnconfigure(1, weight=1)
        self._verbindung_frame.grid(row=content_row, column=0, columnspan=2, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Name:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        if s and self._duplicate:
            name_val = "Kopie von " + s.display_name
        elif s and s.is_app_session:
            name_val = s.display_name
        else:
            name_val = ""
        self._name_var = tk.StringVar(value=name_val)
        ttk.Entry(self._verbindung_frame, textvariable=self._name_var, width=32).grid(row=0, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Ordner:").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=s.folder_key if (s and s.is_app_session) else folder_preset)
        ttk.Combobox(
            self._verbindung_frame, textvariable=self._folder_var,
            values=self._existing_folders, width=30,
        ).grid(row=1, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Hostname:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 8))
        self._host_var = tk.StringVar(value=s.hostname if (s and s.is_app_session) else "")
        ttk.Entry(self._verbindung_frame, textvariable=self._host_var, width=32).grid(row=2, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Benutzername:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 8))
        self._user_var = tk.StringVar(value=s.username if (s and s.is_app_session) else "")
        ttk.Entry(self._verbindung_frame, textvariable=self._user_var, width=32).grid(row=3, column=1, sticky="ew")

        ttk.Label(self._verbindung_frame, text="Port:").grid(row=4, column=0, sticky="w", pady=4, padx=(0, 8))
        self._port_var = tk.StringVar(value=str(s.port) if (s and s.is_app_session) else "22")
        ttk.Entry(self._verbindung_frame, textvariable=self._port_var, width=8).grid(row=4, column=1, sticky="w")

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=content_row + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

        # Initialen Zustand: inaktiven Frame ausblenden
        if self._initial_mode == "alias":
            self._verbindung_frame.grid_remove()
        else:
            self._alias_frame.grid_remove()

    def _on_mode_changed(self) -> None:
        """Zeigt den aktiven Frame, versteckt den anderen."""
        if self._mode_var.get() == "alias":
            self._verbindung_frame.grid_remove()
            self._alias_frame.grid()
        else:
            self._alias_frame.grid_remove()
            self._verbindung_frame.grid()

    def _on_ok(self) -> None:
        if self._mode_var.get() == "alias":
            self._on_ok_alias()
        else:
            self._on_ok_verbindung()

    def _on_ok_alias(self) -> None:
        alias = self._alias_var.get().strip()
        folder_str = self._alias_folder_var.get().strip()
        if not alias:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Alias auswählen.", parent=self)
            return
        folder_path = [p for p in folder_str.split("/") if p]
        if not folder_path:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=self)
            return
        if self._existing_session and self._existing_session.is_ssh_alias_copy:
            session_key = self._existing_session.key
        else:
            session_key = _SSH_ALIAS_PREFIX + str(uuid.uuid4())
        self.result = Session(
            key=session_key,
            display_name=alias,
            folder_path=folder_path,
            hostname=alias,
            username="",
            port=22,
            source="ssh_alias",
        )
        self.destroy()

    def _on_ok_verbindung(self) -> None:
        name = self._name_var.get().strip()
        hostname = self._host_var.get().strip()
        username = self._user_var.get().strip()
        folder_str = self._folder_var.get().strip()
        port_str = self._port_var.get().strip()

        if not name:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Namen eingeben.", parent=self)
            return
        if not hostname:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Hostnamen eingeben.", parent=self)
            return
        if not _HOSTNAME_RE.match(hostname):
            messagebox.showwarning(
                "Ungültiger Hostname",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche, Unterstriche und Doppelpunkte erlaubt.",
                parent=self,
            )
            return
        if username and not _USERNAME_RE.match(username):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning("Ungültiger Port", "Port muss eine Zahl zwischen 1 und 65535 sein.", parent=self)
            return

        folder_path = [p for p in folder_str.split("/") if p]
        session_key = (
            self._existing_session.key
            if self._existing_session and not self._duplicate
            else _APP_PREFIX + str(uuid.uuid4())
        )
        self.result = Session(
            key=session_key,
            display_name=name,
            folder_path=folder_path,
            hostname=hostname,
            username=username,
            port=port,
            source="app",
        )
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SshConfigInspectDialog
# ---------------------------------------------------------------------------
class SshConfigInspectDialog(tk.Toplevel):
    """
    Modaler Dialog der die effektive SSH-Konfiguration eines Alias anzeigt (ssh -G <alias>).
    """

    def __init__(self, parent: tk.Tk, alias: str):
        super().__init__(parent)
        self.title(f"SSH-Konfiguration: {alias}")
        self.resizable(True, True)
        self.geometry("600x450")
        self.transient(parent)
        self.grab_set()
        self._build(alias)
        self._center_on_parent(parent)

    def _build(self, alias: str) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        txt_frame = ttk.Frame(self, padding=(8, 8, 8, 4))
        txt_frame.grid(row=0, column=0, sticky="nsew")
        txt_frame.columnconfigure(0, weight=1)
        txt_frame.rowconfigure(0, weight=1)

        txt = tk.Text(txt_frame, wrap="none", font=("Consolas", 9))
        vsb = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        hsb = ttk.Scrollbar(txt_frame, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        try:
            result = subprocess.run(
                ["ssh", "-G", alias],
                capture_output=True, text=True, timeout=5,
            )
            output = result.stdout or result.stderr or "(keine Ausgabe)"
        except Exception as exc:
            output = f"Fehler: {exc}"

        txt.insert("1.0", output)
        txt.configure(state="disabled")

        btn_frame = ttk.Frame(self, padding=(8, 4, 8, 8))
        btn_frame.grid(row=1, column=0)
        ttk.Button(btn_frame, text="Schließen", command=self.destroy, width=12).pack()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# MoveFolderDialog
# ---------------------------------------------------------------------------
class MoveFolderDialog(tk.Toplevel):
    """
    Minimaler modaler Dialog zum Verschieben einer Session in einen anderen Ordner.
    Nach Schließen: self.result = Ordner-String oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk, existing_folders: list[str], current_folder: str):
        super().__init__(parent)
        self.title("In Ordner verschieben")
        self.resizable(False, False)
        self.result: Optional[str] = None
        self._quick_users = quick_users or list(QUICK_USERS)
        self._default_user = default_user or DEFAULT_USER
        self.transient(parent)
        self.grab_set()
        self._build(existing_folders, current_folder)
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self, existing_folders: list[str], current_folder: str) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Ordner:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 8))
        self._folder_var = tk.StringVar(value=current_folder)
        ttk.Combobox(
            frame, textvariable=self._folder_var,
            values=existing_folders, width=30,
        ).grid(row=0, column=1, sticky="ew")

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        folder = self._folder_var.get().strip()
        if not folder:
            messagebox.showwarning("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=self)
            return
        self.result = folder
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# ToastNotification
# ---------------------------------------------------------------------------
class ToastNotification(tk.Toplevel):
    """Kleines unauffälliges Toast oben rechts."""

    def __init__(self, parent: tk.Tk, message: str, duration_ms: int = 2200):
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)

        frame = ttk.Frame(self, padding=(12, 8), style="Toast.TFrame")
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=message, style="Toast.TLabel").pack()

        self.update_idletasks()
        parent.update_idletasks()

        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        x = parent.winfo_rootx() + parent.winfo_width() - width - 16
        y = parent.winfo_rooty() + 16
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.deiconify()
        self.after(duration_ms, self.destroy)


# ---------------------------------------------------------------------------
# SSHManagerApp
# ---------------------------------------------------------------------------
class SettingsView(ttk.Frame):
    """Einstellungsansicht im Hauptfenster."""

    STARTUP_LABELS = {
        "remember": "Letzten Ordnerzustand merken",
        "expanded": "Alle Ordner ausgeklappt starten",
        "collapsed": "Alle Ordner eingeklappt starten",
    }
    TITLE_MODE_LABELS = {
        "default": "Wie bisher",
        "name": "Nur Session-Name",
        "host": "Nur Hostname",
        "user_host": "Benutzer@Host",
        "name_host": "Name (Host)",
    }

    def __init__(self, parent: tk.Widget, app: "SSHManagerApp"):
        super().__init__(parent, padding=0)
        self._app = app
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._default_user_var = tk.StringVar()
        self._host_timeout_var = tk.StringVar()
        self._startup_expand_var = tk.StringVar()
        self._profile_name_var = tk.StringVar()
        self._title_mode_var = tk.StringVar()
        self._toolbar_vars: dict[str, tk.BooleanVar] = {}
        self._use_tab_color_var = tk.BooleanVar()
        self._section_frames: dict[str, ttk.Frame] = {}
        self._nav_buttons: dict[str, ttk.Button] = {}
        self._active_section = "general"
        self._build()
        self.load_from_app()

    def _build(self) -> None:
        self.configure(style="SettingsRoot.TFrame")
        root = ttk.Frame(self, style="SettingsRoot.TFrame", padding=0)
        root.grid(row=0, column=0, sticky="nsew")
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        self._root = root

        nav = ttk.Frame(root, style="SettingsNav.TFrame", padding=(16, 20))
        nav.grid(row=0, column=0, sticky="nsw")
        nav.columnconfigure(0, weight=1)
        self._nav = nav

        content_wrap = ttk.Frame(root, style="SettingsContent.TFrame", padding=(28, 22, 28, 16))
        content_wrap.grid(row=0, column=1, sticky="nsew")
        content_wrap.columnconfigure(0, weight=1)
        content_wrap.rowconfigure(1, weight=1)

        header = ttk.Frame(content_wrap, style="SettingsContent.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Einstellungen", style="SettingsTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Direkt im Hauptfenster, optimiert für Fullscreen.", style="SettingsSubtitle.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 0))

        self._content_host = ttk.Frame(content_wrap, style="SettingsContent.TFrame")
        self._content_host.grid(row=1, column=0, sticky="nsew")
        self._content_host.columnconfigure(0, weight=1)
        self._content_host.rowconfigure(0, weight=1)

        actions = ttk.Frame(content_wrap, style="SettingsActions.TFrame", padding=(0, 16, 0, 0))
        actions.grid(row=2, column=0, sticky="ew")
        ttk.Separator(actions, orient="horizontal").pack(fill="x", pady=(0, 14))
        ttk.Button(actions, text="Speichern", command=self._save).pack(side="left")
        ttk.Button(actions, text="Zurück", command=self._app.show_main_view).pack(side="left", padx=(8, 0))

        sections = [
            ("general", "Allgemein"),
            ("users", "Schnellauswahl-Benutzer"),
            ("toolbar", "Toolbar"),
            ("terminal", "Windows Terminal"),
            ("transfer", "Export / Import"),
            ("reset", "Zurücksetzen"),
        ]
        ttk.Label(nav, text="Bereiche", style="SettingsNavTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        for idx, (key, label) in enumerate(sections, start=1):
            btn = ttk.Button(nav, text=f"  {label}", command=lambda k=key: self._show_section(k), style="SettingsNav.TButton")
            btn.grid(row=idx, column=0, sticky="ew", pady=4)
            self._nav_buttons[key] = btn

        self._section_frames["general"] = self._build_general_section()
        self._section_frames["users"] = self._build_users_section()
        self._section_frames["toolbar"] = self._build_toolbar_section()
        self._section_frames["terminal"] = self._build_terminal_section()
        self._section_frames["transfer"] = self._build_transfer_section()
        self._section_frames["reset"] = self._build_reset_section()
        self._show_section(self._active_section)

    def _build_section_frame(self, title: str, description: str) -> ttk.Frame:
        frame = ttk.Frame(self._content_host, style="SettingsPanel.TFrame", padding=22)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=title, style="SettingsSectionTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(frame, text=description, style="SettingsHint.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 18))
        return frame

    def _build_general_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Allgemein", "Globale Vorgaben für Auswahl, Host-Checks und Baumzustand.")
        form = ttk.Frame(frame, style="SettingsPanel.TFrame")
        form.grid(row=2, column=0, sticky="nw")
        form.columnconfigure(0, minsize=220)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Standardbenutzer:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        self._default_user_combo = ttk.Combobox(form, textvariable=self._default_user_var, state="readonly", width=32)
        self._default_user_combo.grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Label(form, text="Hosts prüfen Timeout (s):").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(form, textvariable=self._host_timeout_var, width=10).grid(row=1, column=1, sticky="w", pady=6)
        ttk.Label(form, text="Ordner beim Start:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        self._startup_expand_combo = ttk.Combobox(form, textvariable=self._startup_expand_var, values=list(self.STARTUP_LABELS.values()), state="readonly", width=32)
        self._startup_expand_combo.grid(row=2, column=1, sticky="ew", pady=6)
        return frame

    def _build_users_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Schnellauswahl-Benutzer", "Ein Benutzer pro Zeile. Reihenfolge bleibt erhalten und wird in den Dialogen genutzt.")
        self._quick_users_text = scrolledtext.ScrolledText(frame, wrap="word", height=18)
        self._quick_users_text.grid(row=2, column=0, sticky="nsew")
        frame.rowconfigure(2, weight=1)
        return frame

    def _build_toolbar_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Toolbar", "Lege fest, welche Buttons oben sichtbar sind. Änderungen wirken direkt.")
        grid = ttk.Frame(frame, style="SettingsPanel.TFrame")
        grid.grid(row=2, column=0, sticky="nw")
        grid.columnconfigure(0, minsize=260)
        grid.columnconfigure(1, minsize=260)
        toolbar_items = [
            ("show_select_all", "Alle auswählen"),
            ("show_deselect_all", "Alle abwählen"),
            ("show_expand_all", "Ausklappen"),
            ("show_collapse_all", "Einklappen"),
            ("show_add_connection", "+ Verbindung"),
            ("show_reload", "Neu laden"),
            ("show_open_tunnel", "Tunnel öffnen…"),
            ("show_check_hosts", "Hosts prüfen"),
        ]
        for idx, (key, label) in enumerate(toolbar_items):
            var = tk.BooleanVar()
            self._toolbar_vars[key] = var
            ttk.Checkbutton(grid, text=label, variable=var, command=self._on_toolbar_changed).grid(row=idx // 2, column=idx % 2, sticky="w", padx=(0, 28), pady=6)
        return frame

    def _build_terminal_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Windows Terminal", "Nur optische Übergaben an Windows Terminal, keine SSH-Logik.")
        form = ttk.Frame(frame, style="SettingsPanel.TFrame")
        form.grid(row=2, column=0, sticky="nw")
        form.columnconfigure(0, minsize=220)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Profilname:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(form, textvariable=self._profile_name_var, width=32).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Checkbutton(form, text="Tab-Farben an Windows Terminal übergeben", variable=self._use_tab_color_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(form, text="Tab-Titel:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 12))
        self._title_mode_combo = ttk.Combobox(form, textvariable=self._title_mode_var, values=list(self.TITLE_MODE_LABELS.values()), state="readonly", width=32)
        self._title_mode_combo.grid(row=2, column=1, sticky="ew", pady=6)
        return frame

    def _build_transfer_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Export / Import", "Speichere deine Einstellungen separat oder lade sie aus einer JSON-Datei wieder ein.")
        ttk.Button(frame, text="Einstellungen exportieren…", command=self._export_settings).grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="Einstellungen importieren…", command=self._import_settings).grid(row=3, column=0, sticky="w")
        return frame

    def _build_reset_section(self) -> ttk.Frame:
        frame = self._build_section_frame("Zurücksetzen", "Trenne dauerhaft gespeicherte Einstellungen sauber vom aktuellen Ansichts-Zustand.")
        ttk.Button(frame, text="Einstellungen zurücksetzen", command=self._reset_settings).grid(row=2, column=0, sticky="w", pady=(0, 8))
        ttk.Button(frame, text="Farben und Ordner auf Startzustand zurücksetzen", command=self._reset_view_state).grid(row=3, column=0, sticky="w")
        return frame

    def _export_settings(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Einstellungen exportieren",
            defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
            initialfile="ssh-manager-settings.json",
        )
        if not path:
            return
        settings = self._collect_settings()
        try:
            Path(path).write_text(json.dumps(_settings_to_dict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            messagebox.showerror("Export fehlgeschlagen", f"Datei konnte nicht gespeichert werden:\n{e}", parent=self)
            return
        ToastNotification(self._app, "Einstellungen exportiert")

    def _import_settings(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Einstellungen importieren",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        try:
            settings = _load_settings_from_path(Path(path))
        except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
            messagebox.showerror("Import fehlgeschlagen", f"Datei konnte nicht gelesen werden:\n{e}", parent=self)
            return
        self._app.apply_settings(settings)
        self.load_from_app()
        ToastNotification(self._app, "Einstellungen importiert")

    def _show_section(self, key: str) -> None:
        self._active_section = key
        labels = {
            "general": "Allgemein",
            "users": "Schnellauswahl-Benutzer",
            "toolbar": "Toolbar",
            "terminal": "Windows Terminal",
            "transfer": "Export / Import",
            "reset": "Zurücksetzen",
        }
        for section_key, frame in self._section_frames.items():
            if section_key == key:
                frame.tkraise()
        for section_key, button in self._nav_buttons.items():
            prefix = "▸" if section_key == key else " "
            button.configure(text=f"{prefix} {labels[section_key]}")

    def load_from_app(self) -> None:
        settings = self._app.settings
        self._quick_users_text.delete("1.0", "end")
        self._quick_users_text.insert("1.0", "\n".join(settings.quick_users))
        self._default_user_combo.configure(values=settings.quick_users)
        self._default_user_var.set(settings.default_user)
        self._host_timeout_var.set(str(settings.host_check_timeout_seconds))
        self._startup_expand_var.set(self.STARTUP_LABELS.get(settings.startup_expand_mode, self.STARTUP_LABELS["remember"]))
        for key, var in self._toolbar_vars.items():
            var.set(bool(getattr(settings.toolbar, key)))
        self._profile_name_var.set(settings.windows_terminal.profile_name)
        self._use_tab_color_var.set(settings.windows_terminal.use_tab_color)
        self._title_mode_var.set(self.TITLE_MODE_LABELS.get(settings.windows_terminal.title_mode, self.TITLE_MODE_LABELS["default"]))

    def _on_toolbar_changed(self) -> None:
        self._app.preview_toolbar_visibility(self._collect_toolbar_settings())

    def _collect_toolbar_settings(self) -> ToolbarSettings:
        return ToolbarSettings(**{key: var.get() for key, var in self._toolbar_vars.items()})

    def _collect_settings(self) -> AppSettings:
        quick_users = [line.strip() for line in self._quick_users_text.get("1.0", "end").splitlines() if line.strip()]
        if not quick_users:
            raise ValueError("Mindestens ein Quick-User ist erforderlich.")
        default_user = self._default_user_var.get().strip() or quick_users[0]
        if default_user not in quick_users:
            default_user = quick_users[0]
        try:
            timeout = max(1, int(self._host_timeout_var.get().strip()))
        except ValueError as e:
            raise ValueError("Timeout muss eine ganze Zahl >= 1 sein.") from e
        startup_expand_mode = next((key for key, label in self.STARTUP_LABELS.items() if label == self._startup_expand_var.get()), "remember")
        title_mode = next((key for key, label in self.TITLE_MODE_LABELS.items() if label == self._title_mode_var.get()), "default")
        return AppSettings(
            quick_users=quick_users,
            default_user=default_user,
            toolbar=self._collect_toolbar_settings(),
            host_check_timeout_seconds=timeout,
            startup_expand_mode=startup_expand_mode,
            windows_terminal=WindowsTerminalSettings(
                profile_name=self._profile_name_var.get().strip() or "Git Bash",
                use_tab_color=self._use_tab_color_var.get(),
                title_mode=title_mode,
            ),
        )

    def _save(self) -> None:
        try:
            settings = self._collect_settings()
        except ValueError as e:
            messagebox.showwarning("Einstellungen", str(e), parent=self)
            return
        self._app.apply_settings(settings)
        self._app.show_main_view()

    def _reset_settings(self) -> None:
        self._app.reset_settings()
        self.load_from_app()

    def _reset_view_state(self) -> None:
        self._app.reset_view_state()


class SSHManagerApp(tk.Tk):
    """Hauptfenster der SSH-Manager Applikation."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.geometry("750x550")

        # Stil
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Toast.TFrame", background="#333333", relief="flat")
        style.configure("Toast.TLabel", background="#333333", foreground="#f5f5f5")
        style.configure("SettingsRoot.TFrame", background="#dcd7cf")
        style.configure("SettingsNav.TFrame", background="#d3cdc4")
        style.configure("SettingsContent.TFrame", background="#ebe7df")
        style.configure("SettingsPanel.TFrame", background="#f6f2eb")
        style.configure("SettingsActions.TFrame", background="#ebe7df")
        style.configure("SettingsTitle.TLabel", background="#ebe7df", font=("Segoe UI", 17, "bold"))
        style.configure("SettingsSubtitle.TLabel", background="#ebe7df", foreground="#5f5a52")
        style.configure("SettingsNavTitle.TLabel", background="#d3cdc4", font=("Segoe UI", 10, "bold"))
        style.configure("SettingsSectionTitle.TLabel", background="#f6f2eb", font=("Segoe UI", 13, "bold"))
        style.configure("SettingsHint.TLabel", background="#f6f2eb", foreground="#6b655c")
        style.configure("SettingsValue.TLabel", background="#f6f2eb")
        style.configure("SettingsNav.TButton", padding=(14, 10), anchor="w")

        # Registry laden
        try:
            reader = RegistryReader()
            winscp_sessions = reader.load_sessions()
        except OSError as e:
            messagebox.showerror(
                "Registry-Fehler",
                f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                f"Pfad: HKCU\\{REGISTRY_PATH}"
            )
            winscp_sessions = []

        self.settings = _load_settings()
        self._startup_settings = _load_settings()

        # App-eigene Sessions und SSH-Config-Sessions laden und mergen
        self._app_sessions: list[Session] = _load_app_sessions()
        ssh_config_sessions = _load_ssh_config_sessions()
        self._sessions = sorted(
            winscp_sessions + self._app_sessions + ssh_config_sessions,
            key=lambda s: (0 if s.folder_key == _SSH_CONFIG_DEFAULT_FOLDER else 1, s.folder_key.lower(), s.display_name.lower()),
        )

        # Checkbox-Images (nach Tk-Initialisierung erzeugen!)
        self._img_unchecked, self._img_checked = _create_checkbox_images(self)

        self._initial_open_folders, self._initial_session_colors, self._initial_toolbar_search_texts = _load_ui_state()
        if self.settings.startup_expand_mode == "expanded":
            self._initial_open_folders = {s.folder_key for s in self._sessions if s.folder_key}
        elif self.settings.startup_expand_mode == "collapsed":
            self._initial_open_folders = set()
        self._toolbar_buttons: dict[str, ttk.Button] = {}
        self._main_frame: ttk.Frame | None = None
        self._settings_view: SettingsView | None = None
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        """Erstellt alle UI-Elemente."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        menubar = tk.Menu(self)
        self.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Neue Verbindung", command=self._add_session)
        file_menu.add_command(label="Neu laden", command=self._reload_sessions)
        file_menu.add_separator()
        file_menu.add_command(label="Einstellungen", command=self.show_settings_view)
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self._on_close)
        menubar.add_cascade(label="Datei", menu=file_menu)

        selection_menu = tk.Menu(menubar, tearoff=False)
        selection_menu.add_command(label="Alle auswählen", command=self._select_all)
        selection_menu.add_command(label="Alle abwählen", command=self._deselect_all)
        selection_menu.add_command(label="Auswahl umkehren", command=self._invert_selection)
        menubar.add_cascade(label="Auswahl", menu=selection_menu)

        view_menu = tk.Menu(menubar, tearoff=False)
        view_menu.add_command(label="Ausklappen", command=self._expand_all)
        view_menu.add_command(label="Einklappen", command=self._collapse_all)
        view_menu.add_separator()
        view_menu.add_command(label="Farben zurücksetzen", command=self._reset_session_colors)
        view_menu.add_command(label="Ansicht auf Startzustand zurücksetzen", command=self.reset_view_state)
        menubar.add_cascade(label="Ansicht", menu=view_menu)

        actions_menu = tk.Menu(menubar, tearoff=False)
        actions_menu.add_command(label="Verbinden", command=self._on_connect)
        actions_menu.add_command(label="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
        actions_menu.add_command(label="Tunnel öffnen", command=self._open_tunnel)
        actions_menu.add_command(label="Remote-Befehl ausführen", command=lambda: self._run_remote_command(self._tree.get_selected_sessions()))
        menubar.add_cascade(label="Aktionen", menu=actions_menu)

        settings_menu = tk.Menu(menubar, tearoff=False)
        settings_menu.add_command(label="Einstellungen öffnen", command=self.show_settings_view)
        settings_menu.add_command(label="Einstellungen exportieren…", command=self._export_settings_dialog)
        settings_menu.add_command(label="Einstellungen importieren…", command=self._import_settings_dialog)
        settings_menu.add_separator()
        settings_menu.add_command(label="Einstellungen zurücksetzen", command=self.reset_settings)
        menubar.add_cascade(label="Einstellungen", menu=settings_menu)

        self._main_frame = ttk.Frame(self)
        self._main_frame.grid(row=0, column=0, sticky="nsew")
        self._main_frame.columnconfigure(0, weight=1)
        self._main_frame.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self._main_frame, padding=(8, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Suche:").grid(row=0, column=0, padx=(0, 4))
        self._search_var = tk.StringVar(value=self._initial_toolbar_search_texts.get("main", ""))
        self._search_entry = ttk.Entry(toolbar, textvariable=self._search_var)
        self._search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self._toolbar_buttons["show_select_all"] = ttk.Button(toolbar, text="Alle auswählen", command=self._select_all)
        self._toolbar_buttons["show_deselect_all"] = ttk.Button(toolbar, text="Alle abwählen", command=self._deselect_all)
        self._toolbar_buttons["show_expand_all"] = ttk.Button(toolbar, text="Ausklappen", command=self._expand_all)
        self._toolbar_buttons["show_collapse_all"] = ttk.Button(toolbar, text="Einklappen", command=self._collapse_all)
        self._toolbar_buttons["show_add_connection"] = ttk.Button(toolbar, text="+ Verbindung", command=self._add_session)
        self._toolbar_buttons["show_reload"] = ttk.Button(toolbar, text="Neu laden", command=self._reload_sessions)
        self._toolbar_buttons["show_open_tunnel"] = ttk.Button(toolbar, text="Tunnel öffnen…", command=self._open_tunnel)
        self._toolbar_buttons["show_check_hosts"] = ttk.Button(toolbar, text="Hosts prüfen", command=lambda: self._tree.check_selected_hosts(timeout=self.settings.host_check_timeout_seconds))
        self._layout_toolbar_buttons()

        # SessionTree (Zeile 1)
        self._tree = SessionTree(
            self._main_frame,
            sessions=self._sessions,
            img_unchecked=self._img_unchecked,
            img_checked=self._img_checked,
            on_selection_changed=self._on_selection_changed,
            initial_open_folders=self._initial_open_folders,
            initial_session_colors=self._initial_session_colors,
            on_quick_connect=self._quick_connect_session,
            on_edit_session=self._edit_session,
            on_delete_session=self._delete_session,
            on_delete_folder=self._delete_folder,
            on_rename_folder=self._rename_folder,
            on_add_session_in_folder=self._add_session,
            on_duplicate_ssh_alias=self._duplicate_ssh_alias,
            on_inspect_ssh_config=self._inspect_ssh_config,
            on_duplicate_app_session=self._duplicate_app_session,
            on_move_session=self._move_session,
            on_move_sessions=self._move_sessions,
            on_open_ssh_config_in_vscode=self._open_ssh_config_in_vscode,
            on_deploy_ssh_key=self._deploy_ssh_key,
            on_remove_ssh_key=self._remove_ssh_key,
            on_open_tunnel=self._open_tunnel,
            on_open_in_winscp=self._open_in_winscp,
            on_run_remote_command=self._run_remote_command,
            on_open_via_jumphost=self._open_via_jumphost,
            on_ui_state_changed=self._persist_ui_state,
        )
        self._tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))

        # Verbinden-Button (Zeile 2)
        bottom = ttk.Frame(self._main_frame, padding=(8, 6))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self._connect_btn = ttk.Button(
            bottom,
            text="Verbinden",
            command=self._on_connect,
            state=tk.DISABLED,
        )
        self._connect_btn.grid(row=0, column=0)

        # Suche verdrahten
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())

        self._settings_view = SettingsView(self, self)

    def _persist_ui_state(self) -> None:
        _save_ui_state(
            self._tree.get_open_folders(),
            self._tree.get_session_colors(),
            {
                "main": self._search_var.get(),
                "last_remote_command": self._initial_toolbar_search_texts.get("last_remote_command", ""),
            },
        )

    def _layout_toolbar_buttons(self) -> None:
        col = 2
        order = [
            "show_select_all",
            "show_deselect_all",
            "show_expand_all",
            "show_collapse_all",
            "show_add_connection",
            "show_reload",
            "show_open_tunnel",
            "show_check_hosts",
        ]
        for key in order:
            btn = self._toolbar_buttons[key]
            btn.grid_forget()
            if getattr(self.settings.toolbar, key):
                padx = (8, 2) if key == "show_add_connection" else (2, 2)
                if key == "show_check_hosts":
                    padx = (2, 0)
                btn.grid(row=0, column=col, padx=padx)
                col += 1

    def preview_toolbar_visibility(self, toolbar_settings: ToolbarSettings) -> None:
        self.settings.toolbar = toolbar_settings
        self._layout_toolbar_buttons()

    def get_default_user(self) -> str:
        return self.settings.default_user

    def get_quick_users(self) -> list[str]:
        return list(self.settings.quick_users)

    def get_terminal_settings(self) -> WindowsTerminalSettings:
        return self.settings.windows_terminal

    def _export_settings_dialog(self) -> None:
        if self._settings_view is None:
            return
        self._settings_view._export_settings()

    def _import_settings_dialog(self) -> None:
        if self._settings_view is None:
            return
        self._settings_view._import_settings()

    def show_settings_view(self) -> None:
        if self._settings_view is None or self._main_frame is None:
            return
        self._settings_view.load_from_app()
        self._main_frame.grid_remove()
        self._settings_view.grid(row=0, column=0, sticky="nsew")

    def show_main_view(self) -> None:
        if self._settings_view is not None:
            self._settings_view.grid_remove()
        if self._main_frame is not None:
            self._main_frame.grid()
        self._layout_toolbar_buttons()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        _save_settings(settings)
        self._layout_toolbar_buttons()
        self._search_entry.focus_set()
        ToastNotification(self, "Einstellungen gespeichert")

    def reset_settings(self) -> None:
        self.apply_settings(_default_settings())
        if self._settings_view is not None:
            self._settings_view.load_from_app()

    def _reset_session_colors(self) -> None:
        for session_key in list(self._tree.get_session_colors().keys()):
            self._tree.set_session_color(session_key, None)
        ToastNotification(self, "Farben zurückgesetzt")

    def reset_view_state(self) -> None:
        self._search_var.set("")
        self._tree.populate(self._sessions, open_folders=set(self._initial_open_folders))
        current_colors = set(self._tree.get_session_colors())
        startup_colors = dict(self._initial_session_colors)
        for session_key in current_colors | set(startup_colors):
            self._tree.set_session_color(session_key, startup_colors.get(session_key))
        ToastNotification(self, "Ansicht auf Startzustand zurückgesetzt")

    def _invert_selection(self) -> None:
        self._tree.invert_checked()

    def _on_selection_changed(self, count: int) -> None:
        """Callback vom SessionTree – aktualisiert den Verbinden-Button."""
        if count > 0:
            self._connect_btn.config(
                text=f"Verbinden ({count} ausgewählt)",
                state=tk.NORMAL,
            )
        else:
            self._connect_btn.config(text="Verbinden", state=tk.DISABLED)

    def _on_search_changed(self) -> None:
        self._tree.filter(self._search_var.get())
        self._persist_ui_state()

    def _select_all(self) -> None:
        self._tree.set_all_checked(True)

    def _deselect_all(self) -> None:
        self._tree.set_all_checked(False)

    def _expand_all(self) -> None:
        self._tree.expand_all()

    def _collapse_all(self) -> None:
        self._tree.collapse_all()

    def _on_connect(self) -> None:
        selected = self._tree.get_selected_sessions()
        if not selected:
            return
        dialog = UserDialog(self, quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        if dialog.result is None:
            return  # Abbrechen gedrückt
        user = dialog.result
        try:
            TerminalLauncher.launch(selected, user, self._tree.get_session_colors(), terminal_settings=self.get_terminal_settings())
        except Exception as e:
            messagebox.showerror("Fehler beim Starten", str(e))

    def _resolve_single_session_user(self, session: Session, title: str = "Benutzername auswählen") -> str | None:
        """Löst den Benutzernamen für genau eine Session auf."""
        if session.is_ssh_config_session and session.username:
            return session.username
        dialog = UserDialog(self, title=title, quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        return dialog.result

    def _quick_connect_session(self, session: Session) -> None:
        """Öffnet eine einzelne Session direkt (via Doppelklick oder Kontextmenü)."""
        colors = self._tree.get_session_colors()
        user = self._resolve_single_session_user(session)
        if user is None and not (session.is_ssh_config_session and session.username):
            return
        try:
            TerminalLauncher.launch([session], user or "", colors, terminal_settings=self.get_terminal_settings())
        except Exception as e:
            messagebox.showerror("Fehler beim Starten", str(e))

    def _get_all_folder_names(self) -> list[str]:
        """Gibt alle bekannten Ordnernamen aus allen Session-Quellen zurück."""
        folders = set()
        for s in self._sessions:
            if s.folder_key:
                folders.add(s.folder_key)
        return sorted(folders)

    def _get_ssh_aliases(self) -> list[str]:
        """Gibt alle SSH-Config-Aliases zurück (für Alias-Picker im Dialog)."""
        return sorted(s.display_name for s in self._sessions if s.source == "ssh_config")

    def _rebuild_sessions(self, *, reload_winscp: bool = False) -> None:
        """Merged alle Session-Quellen und aktualisiert den Baum."""
        ssh_config_sessions = _load_ssh_config_sessions()
        if reload_winscp:
            try:
                winscp = RegistryReader().load_sessions()
            except OSError as e:
                messagebox.showerror(
                    "Registry-Fehler",
                    f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                    f"Pfad: HKCU\\{REGISTRY_PATH}",
                    parent=self,
                )
                winscp = []
        else:
            winscp = [s for s in self._sessions if s.source == "winscp"]
        self._sessions = sorted(
            winscp + self._app_sessions + ssh_config_sessions,
            key=lambda s: (0 if s.folder_key == _SSH_CONFIG_DEFAULT_FOLDER else 1, s.folder_key.lower(), s.display_name.lower()),
        )
        self._tree.refresh(self._sessions)

    def _reload_sessions(self) -> None:
        """Lädt WinSCP- und SSH-Config-Sessions erneut ein und aktualisiert die Ansicht."""
        self._rebuild_sessions(reload_winscp=True)
        ToastNotification(self, "Verbindungen neu geladen")

    def _add_session(self, folder_preset: str = "") -> None:
        """Öffnet den Dialog zum Anlegen einer neuen Session (App oder SSH-Alias)."""
        dialog = SessionEditDialog(
            self,
            self._get_all_folder_names(),
            ssh_aliases=self._get_ssh_aliases(),
            folder_preset=folder_preset,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._app_sessions.append(dialog.result)
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _edit_session(self, session: Session) -> None:
        """Öffnet den Dialog zum Bearbeiten einer App-Session."""
        dialog = SessionEditDialog(self, self._get_all_folder_names(), session=session)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        for i, s in enumerate(self._app_sessions):
            if s.key == session.key:
                # Farbe auf neuen Key übertragen falls Key sich geändert hat (sollte nicht passieren)
                self._app_sessions[i] = dialog.result
                break
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _duplicate_app_session(self, session: Session) -> None:
        """Dupliziert eine App-Session (öffnet Dialog mit vorausgefüllten Daten, neue UUID)."""
        dialog = SessionEditDialog(
            self, self._get_all_folder_names(), session=session, duplicate=True
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._app_sessions.append(dialog.result)
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _move_session(self, session: Session) -> None:
        """Verschiebt eine App- oder SSH-Alias-Session in einen anderen Ordner."""
        dialog = MoveFolderDialog(self, self._get_all_folder_names(), session.folder_key)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        folder_path = [p for p in dialog.result.split("/") if p]
        for i, s in enumerate(self._app_sessions):
            if s.key == session.key:
                self._app_sessions[i] = Session(
                    key=s.key,
                    display_name=s.display_name,
                    folder_path=folder_path,
                    hostname=s.hostname,
                    username=s.username,
                    port=s.port,
                    source=s.source,
                )
                break
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _move_sessions(self, sessions: list[Session]) -> None:
        """Verschiebt mehrere App-/SSH-Alias-Sessions in denselben Ordner."""
        dialog = MoveFolderDialog(self, self._get_all_folder_names(), sessions[0].folder_key)
        self.wait_window(dialog)
        if dialog.result is None:
            return
        folder_path = [p for p in dialog.result.split("/") if p]
        keys = {s.key for s in sessions}
        for i, s in enumerate(self._app_sessions):
            if s.key in keys:
                self._app_sessions[i] = Session(
                    key=s.key,
                    display_name=s.display_name,
                    folder_path=folder_path,
                    hostname=s.hostname,
                    username=s.username,
                    port=s.port,
                    source=s.source,
                )
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _delete_session(self, session: Session) -> None:
        """Löscht eine App-Session nach Bestätigung."""
        if not messagebox.askyesno(
            "Verbindung löschen",
            f"Verbindung '{session.display_name}' wirklich löschen?",
            parent=self,
        ):
            return
        self._app_sessions = [s for s in self._app_sessions if s.key != session.key]
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _delete_folder(self, sessions: list[Session], folder_key: str) -> None:
        """Löscht alle App-Sessions in einem Ordner nach Bestätigung."""
        if not messagebox.askyesno(
            "Ordner löschen",
            f"Ordner '{folder_key}' und alle {len(sessions)} Verbindung(en) darin löschen?",
            parent=self,
        ):
            return
        keys_to_delete = {s.key for s in sessions}
        self._app_sessions = [s for s in self._app_sessions if s.key not in keys_to_delete]
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _rename_folder(self, folder_key: str) -> None:
        """Benennt einen Ordner um, indem folder_path aller enthaltenen Sessions angepasst wird."""
        parts = folder_key.split("/")
        depth = len(parts) - 1
        old_name = parts[depth]
        prefix = parts[:depth]

        new_name = simpledialog.askstring(
            "Ordner umbenennen",
            f"Neuer Name für '{old_name}':",
            initialvalue=old_name,
            parent=self,
        )
        if not new_name or new_name.strip() == old_name:
            return
        new_name = new_name.strip()

        for session in self._app_sessions:
            fp = session.folder_path
            if (len(fp) > depth
                    and fp[:depth] == prefix
                    and fp[depth] == old_name):
                session.folder_path = fp[:depth] + [new_name] + fp[depth + 1:]

        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _duplicate_ssh_alias(self, session: Session) -> None:
        """Dupliziert einen SSH-Config-Alias in einen anderen Ordner."""
        dialog = SessionEditDialog(
            self,
            self._get_all_folder_names(),
            ssh_aliases=self._get_ssh_aliases(),
            alias_preset=session.display_name,
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self._app_sessions.append(dialog.result)
        _save_app_sessions(self._app_sessions)
        self._rebuild_sessions()

    def _inspect_ssh_config(self, session: Session) -> None:
        """Zeigt die effektive SSH-Konfiguration für einen Alias."""
        SshConfigInspectDialog(self, session.display_name)

    def _open_ssh_config_in_vscode(self) -> None:
        """Öffnet ~/.ssh/config in VS Code."""
        try:
            subprocess.Popen(f'code "{_SSH_CONFIG_FILE}"', shell=True)
        except OSError as e:
            messagebox.showerror("VS Code nicht gefunden", f"Fehler beim Öffnen:\n{e}")

    def _deploy_ssh_key(self, sessions: list[Session]) -> None:
        """Öffnet den ssh-copy-id Dialog und startet den Key-Transfer im Terminal."""
        dialog = SshCopyIdDialog(self, target_count=len(sessions), quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        key_filename, user = dialog.result
        try:
            cmd = build_ssh_copy_id_command(sessions, key_filename, user, terminal_settings=self.get_terminal_settings())
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}")

    def _remove_ssh_key(self, sessions: list[Session]) -> None:
        """Öffnet den Remove-Key Dialog und entfernt den Key remote via SSH."""
        dialog = SshRemoveKeyDialog(self, target_count=len(sessions), quick_users=self.get_quick_users(), default_user=self.get_default_user())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        key_filename, user = dialog.result
        try:
            cmd = build_ssh_remove_key_command(sessions, key_filename, user, terminal_settings=self.get_terminal_settings())
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}")

    def _open_tunnel(self, session: Session | None = None) -> None:
        """Öffnet den Tunnel-Dialog und startet den SSH-Tunnel im Terminal."""
        dialog = SshTunnelDialog(
            self,
            session=session,
            quick_users=self.get_quick_users(),
            default_user=self.get_default_user(),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        jumphost, local_port, remote_host, remote_port, user = dialog.result
        try:
            cmd = build_ssh_tunnel_command(jumphost, local_port, remote_host, remote_port, user, terminal_settings=self.get_terminal_settings())
            subprocess.Popen(cmd)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}")

    def _open_via_jumphost(self, session: Session) -> None:
        """Öffnet eine einzelne Verbindung temporär über einen Jumphost."""
        dialog = JumpHostDialog(self, session, self._sessions, open_folders_getter=self._tree.get_open_folders)
        self.wait_window(dialog)

        if dialog.save_result is not None:
            alias, jump_host, jump_port, jump_user, _target_key = dialog.save_result
            target_user = self._resolve_single_session_user(session, title=f"Benutzername für {session.display_name}")
            if target_user is None:
                return
            try:
                _append_ssh_config_alias(alias, session, target_user, jump_host, jump_user, jump_port)
            except ValueError as e:
                messagebox.showwarning("SSH-Config", str(e), parent=self)
                return
            except OSError as e:
                messagebox.showerror("SSH-Config", f"Fehler beim Schreiben von ~/.ssh/config:\n{e}", parent=self)
                return
            self._rebuild_sessions(reload_winscp=True)
            ToastNotification(self, f"SSH-Config '{alias}' gespeichert")
            return

        if dialog.result is None:
            return

        jump_host, jump_user, jump_port = dialog.result
        target_user = self._resolve_single_session_user(session, title=f"Benutzername für {session.display_name}")
        if target_user is None:
            return
        try:
            cmd = build_jump_wt_command(
                session,
                target_user,
                jump_host,
                jump_user or None,
                jump_port,
                self._tree.get_session_colors().get(session.key),
                terminal_settings=self.get_terminal_settings(),
            )
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}", parent=self)

    def _resolve_users_for_sessions(self, sessions: list[Session], mode: str) -> list[tuple[Session, str]] | None:
        """Löst Benutzernamen für Sessions auf, global oder pro Host."""
        resolved: list[tuple[Session, str]] = []
        if mode == "all":
            missing = [s for s in sessions if not (s.is_ssh_config_session and s.username)]
            shared_user = None
            if missing:
                dialog = UserDialog(self, title="Benutzername für alle Hosts")
                self.wait_window(dialog)
                if dialog.result is None:
                    return None
                shared_user = dialog.result
            for session in sessions:
                user = session.username if session.is_ssh_config_session and session.username else shared_user
                if not user:
                    messagebox.showwarning("Fehlender Benutzer", f"Für '{session.display_name}' konnte kein Benutzer bestimmt werden.", parent=self)
                    return None
                resolved.append((session, user))
            return resolved

        for session in sessions:
            if session.is_ssh_config_session and session.username:
                resolved.append((session, session.username))
                continue
            dialog = UserDialog(self, title=f"Benutzername für {session.display_name}")
            self.wait_window(dialog)
            if dialog.result is None:
                return None
            resolved.append((session, dialog.result))
        return resolved

    def _run_remote_command(self, sessions: list[Session]) -> None:
        """Führt einen Remote-Befehl auf einem oder mehreren Hosts aus."""
        runnable = [s for s in sessions if s.hostname]
        if not runnable:
            messagebox.showwarning("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=self)
            return

        dialog = RemoteCommandDialog(
            self,
            target_count=len(runnable),
            last_command=self._initial_toolbar_search_texts.get("last_remote_command", ""),
            quick_users=self.get_quick_users(),
            default_user=self.get_default_user(),
        )
        self.wait_window(dialog)
        if dialog.result is None:
            return
        user_mode, command, close_on_success = dialog.result
        self._initial_toolbar_search_texts["last_remote_command"] = command

        session_users = self._resolve_users_for_sessions(runnable, user_mode)
        if session_users is None:
            return

        confirm = RemoteCommandConfirmDialog(self, command, session_users, close_on_success)
        self.wait_window(confirm)
        if not confirm.result:
            return

        cmd = build_remote_command_wt_command(
            [(session, user, command) for session, user in session_users],
            close_on_success=close_on_success,
            session_colors=self._tree.get_session_colors(),
            terminal_settings=self.get_terminal_settings(),
        )
        try:
            subprocess.Popen(cmd, shell=True)
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten:\n{e}", parent=self)

    def _open_in_winscp(self, sessions: list[Session]) -> None:
        """Öffnet eine oder mehrere WinSCP-Sessions direkt in WinSCP."""
        winscp = _find_winscp()
        if not winscp:
            messagebox.showerror(
                "WinSCP nicht gefunden",
                "WinSCP.exe wurde nicht gefunden.\n"
                "Bitte WinSCP installieren oder zum PATH hinzufügen.",
                parent=self,
            )
            return
        try:
            for session in sessions:
                full_path = "/".join(session.folder_path + [session.display_name])
                subprocess.Popen([winscp, full_path])
        except OSError as e:
            messagebox.showerror("Fehler", f"Fehler beim Starten von WinSCP:\n{e}", parent=self)

    def _on_close(self) -> None:
        self._persist_ui_state()
        self.destroy()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
