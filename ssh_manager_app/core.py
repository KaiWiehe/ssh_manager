from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
import winreg

from . import PALETTE, REGISTRY_PATH, SKIP_SESSIONS, Session, WindowsTerminalSettings
from .constants import _SSH_CONFIG_FILE, _STATE_FILE

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

    existing = {s.display_name.lower() for s in load_ssh_config_sessions()}
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
    settings = terminal_settings or WindowsTerminalSettings()
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
