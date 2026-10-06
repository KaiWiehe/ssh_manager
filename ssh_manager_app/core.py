from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import tkinter as tk
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
import winreg

from . import PALETTE, REGISTRY_PATH, SKIP_SESSIONS, Session, WindowsTerminalSettings
from .constants import _SSH_CONFIG_FILE, _STATE_FILE
from .secret_scripts import write_protected_script, cleanup_script, managed_scripts
from .ssh_utils import connection_value, ssh_argv, shell_command, scp_target, valid_color, valid_port

def parse_session_key(key: str) -> tuple[list[str], str]:
    """
    Zerlegt einen WinSCP-Registry-Subkey-Namen in Ordner-Pfad und Session-Name.
    URL-Encoding wird dekodiert.

    Beispiele:
      "Extern/Bundo"                  → (["Extern"], "Bundo")
      "Others/10.120.137.10%20-%20DB" → (["Others"], "10.120.137.10 - DB")
      "tool-admin@10.120.67.31"       → ([], "tool-admin@10.120.67.31")
    """
    parts = [unquote(part) for part in key.split("/")]

    # WinSCP tolerates a UTF-8 BOM at the beginning of a stored session path
    # and does not show it in its tree. Strip it here as well, otherwise two
    # visually identical root folders are treated as separate paths.
    parts[0] = parts[0].lstrip("\ufeff")

    return parts[:-1], parts[-1]


def _build_ssh_command(session: Session, user: str | None = None) -> str:
    return shell_command(ssh_argv(session, user))


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


def build_wt_command(sessions: list[Session], user: str, session_colors: dict[str, str] | None = None, terminal_settings: WindowsTerminalSettings | None = None) -> TerminalCommand:
    """
    Erzeugt den wt.exe-Befehl, der alle Sessions als neue Tabs öffnet.
    Alle Tabs landen im selben Windows Terminal Fenster.

    Format:
      wt.exe new-tab --tabColor #2d8653 -p "Git Bash" -- ssh USER@HOST
        ; new-tab -p "Git Bash" -- ssh -p PORT USER@HOST2
        ...
    """
    settings = terminal_settings or WindowsTerminalSettings()
    colors = session_colors or {}
    return TerminalCommand([
        _make_tab(session, session.username or user, ssh_argv(session, session.username or user), settings, colors.get(session.key))
        for session in sessions
    ])


def _shell_single_quote(text: str) -> str:
    """Quoted Text für Bash in Single Quotes."""
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _sudo_password_prelude(sudo_password: str | None) -> list[str]:
    """Return a remote-shell wrapper for a one-off sudo password.

    The password is deliberately kept out of command-line arguments.  It is
    streamed to SSH at runtime. Local scripts are encrypted with user-bound
    Windows DPAPI; no plaintext password is written to a script file.
    """
    if not sudo_password:
        return []
    return [
        f"SSH_MANAGER_SUDO_PASSWORD={_shell_single_quote(sudo_password)}",
        "sudo() {",
        "  printf '%s\\n' \"$SSH_MANAGER_SUDO_PASSWORD\" | command sudo -S -p '' \"$@\"",
        "}",
    ]

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
    host = connection_value(jump_host, "Jumphost")
    if ':' in host and not host.startswith('['):
        host = f"[{host}]"
    jump_target = f"{connection_value(jump_user, 'Jumphost-Benutzer')}@{host}" if jump_user else host
    if jump_port != 22:
        jump_target += f":{valid_port(jump_port)}"
    return shell_command(ssh_argv(session, target_user, ["-J", jump_target]))


def build_jump_wt_command(
    session: Session,
    target_user: str,
    jump_host: str,
    jump_user: str | None = None,
    jump_port: int = 22,
    session_color: str | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
) -> TerminalCommand:
    """Erzeugt den WT-Befehl für eine einzelne Session über ProxyJump."""
    settings = terminal_settings or WindowsTerminalSettings()
    import shlex
    argv = shlex.split(_build_jump_ssh_command(session, target_user, jump_host, jump_user, jump_port))
    return TerminalCommand([_make_tab(session, target_user, argv, settings, session_color)])


def _append_ssh_config_alias(alias: str, target: Session, target_user: str, jump_host: str, jump_user: str | None = None, jump_port: int = 22) -> None:
    """Hängt einen neuen Host-Alias mit ProxyJump an ~/.ssh/config an."""
    alias = alias.strip()
    if not alias or ' ' in alias or '*' in alias or '?' in alias:
        raise ValueError('Alias darf keine Leerzeichen oder Wildcards enthalten.')

    for value in (alias, target.hostname or target.display_name, target_user, jump_host):
        connection_value(value)
    if jump_user:
        connection_value(jump_user)
    valid_port(target.port)
    valid_port(jump_port)
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
    if _SSH_CONFIG_FILE.exists():
        shutil.copy2(_SSH_CONFIG_FILE, _SSH_CONFIG_FILE.with_suffix('.bak'))
    from .storage import atomic_write_text
    atomic_write_text(_SSH_CONFIG_FILE, (_SSH_CONFIG_FILE.read_text(encoding='utf-8') if _SSH_CONFIG_FILE.exists() else '') + prefix + "\n".join(lines) + "\n")



@managed_scripts
def build_remote_command_wt_command(
    session_commands: list[tuple[Session, str, str]],
    *,
    close_on_success: bool,
    session_colors: dict[str, str] | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
    sudo_password: str | None = None,
) -> TerminalCommand:
    """Erzeugt WT-Tabs, die pro Host ein lokales Bash-Skript starten."""
    settings = terminal_settings or WindowsTerminalSettings()
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    colors = session_colors or {}

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
        if sudo_password:
            script_lines.append("trap 'unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"' EXIT")
        if close_on_success:
            script_lines.append(f"{ssh_cmd} <<'__REMOTE_CMD__'")
        else:
            script_lines.append(f"{ssh_cmd} -t <<'__REMOTE_CMD__'")
        script_lines.extend(_sudo_password_prelude(sudo_password))
        script_lines.append(remote_script)
        script_lines.append("__REMOTE_CMD__")
        script_lines.append("status=$?")
        if not close_on_success:
            if sudo_password:
                script_lines.append(f"if [ $status -eq 0 ]; then unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"; exec {ssh_cmd}; fi")
            else:
                script_lines.append(f'if [ $status -eq 0 ]; then rm -f "$0"; exec {ssh_cmd}; fi')
        script_lines.append("if [ $status -ne 0 ]; then read; fi")
        script_lines.append("exit $status")
        script_path = _write_temp_bash_script("remote_cmd_", "\n".join(script_lines) + "\n")
        parts.append(_make_tab(session, user, [git_bash, script_path], settings, colors.get(session.key)))
    return TerminalCommand(parts)





def _remote_output_header(title: str) -> str:
    return "\n".join([
        "printf '\\n'",
        "printf '%s\\n' '========================================'",
        f"printf '%s\\n' {_shell_single_quote(title)}",
        "printf '%s\\n' '========================================'",
        "printf '\\n'",
    ])


def _join_remote_steps(before: str, script_line: str, after: str) -> str:
    steps: list[str] = []
    if before.strip():
        steps.append(_remote_output_header("Output vom Vor-Befehl"))
        steps.append(before.strip())
    if script_line.strip():
        steps.append(_remote_output_header("Output vom Skript"))
        steps.append(script_line.strip())
    if after.strip():
        steps.append(_remote_output_header("Output vom Nach-Befehl"))
        steps.append(after.strip())
    return "\n".join(steps)


def _format_remote_execution_preview(spec: dict) -> str:
    mode = str(spec.get("mode", "command"))
    command = str(spec.get("command", ""))
    if mode == "command":
        return f"1. Remote-Befehl:\n{command}".strip()
    lines: list[str] = []
    step = 1
    before = str(spec.get("before_command", "")).strip()
    if before:
        lines.append(f"{step}. Vor-Befehl:")
        lines.append(before)
        lines.append("")
        step += 1
    if mode == "local_script":
        lines.append(f"{step}. Lokales Skript hochladen und ausführen:")
        lines.append(str(spec.get("local_path") or spec.get("path") or ""))
    else:
        lines.append(f"{step}. Remote-Skript ausführen:")
        lines.append(str(spec.get("remote_path") or spec.get("path") or ""))
    interpreter = str(spec.get("interpreter", "")).strip()
    arguments = str(spec.get("arguments", "")).strip()
    if interpreter:
        lines.append(f"Interpreter: {interpreter}")
    if arguments:
        lines.append(f"Argumente: {arguments}")
    step += 1
    after = str(spec.get("after_command", "")).strip()
    if after:
        lines.append("")
        lines.append(f"{step}. Nach-Befehl:")
        lines.append(after)
    return "\n".join(lines).strip()


@managed_scripts
def build_remote_script_wt_command(
    session_commands: list[tuple[Session, str, dict]],
    *,
    close_on_success: bool,
    session_colors: dict[str, str] | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
    sudo_password: str | None = None,
) -> TerminalCommand:
    """Erzeugt WT-Tabs für Remote-Befehle sowie lokale/remote Python- oder Shell-Skripte."""
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    colors = session_colors or {}

    parts = []
    for i, (session, user, spec) in enumerate(session_commands):
        ssh_cmd = _build_ssh_command(session, user)
        mode = str(spec.get("mode", "command"))
        interpreter = str(spec.get("interpreter", "bash") or "bash")
        command = str(spec.get("command", ""))
        before_command = str(spec.get("before_command", ""))
        after_command = str(spec.get("after_command", ""))
        arguments = str(spec.get("arguments", ""))
        remote_path = str(spec.get("remote_path", ""))
        local_path = str(spec.get("local_path", ""))

        if mode == "remote_script":
            script_line = f"{interpreter} {_shell_single_quote(remote_path)} {arguments}" if interpreter != "direct" else f"{_shell_single_quote(remote_path)} {arguments}"
            remote_script = _join_remote_steps(before_command, script_line, after_command)
            title = f"Remote-Skript: {remote_path}"
            remote_body = f"{ssh_cmd} -t <<'__REMOTE_CMD__'\n{remote_script}\n__REMOTE_CMD__"
        elif mode == "local_script":
            basename = Path(local_path).name or "script"
            remote_tmp = f"/tmp/ssh-manager-$(date +%s)-$$-{basename}"
            if session.is_ssh_config_session:
                upload_target = scp_target(session, user)
                scp_port = ""
            else:
                upload_target = scp_target(session, user)
                scp_port = f"-P {session.port} " if session.port != 22 else ""
            upload = f"scp {scp_port}-- {_shell_single_quote(local_path)} {_shell_single_quote(upload_target + ":" + remote_tmp)}"
            script_line = f"chmod +x {_shell_single_quote(remote_tmp)} && "
            script_line += f"{interpreter} {_shell_single_quote(remote_tmp)} {arguments}" if interpreter != "direct" else f"{_shell_single_quote(remote_tmp)} {arguments}"
            remote_script = _join_remote_steps(before_command, script_line, after_command)
            remote_script += f"\nstatus=$?\nrm -f {_shell_single_quote(remote_tmp)}\nexit $status"
            title = f"Lokales Skript: {local_path}"
            remote_body = f"{upload}\nif [ $? -ne 0 ]; then exit 1; fi\n{ssh_cmd} -t <<'__REMOTE_CMD__'\n{remote_script}\n__REMOTE_CMD__"
        else:
            title = f"Remote-Befehl: {command.strip() or '-'}"
            remote_body = f"{ssh_cmd} {'-t ' if not close_on_success else ''}<<'__REMOTE_CMD__'\n{command}\n__REMOTE_CMD__"

        if sudo_password:
            remote_body = remote_body.replace(
                "<<'__REMOTE_CMD__'\n",
                "<<'__REMOTE_CMD__'\n" + "\n".join(_sudo_password_prelude(sudo_password)) + "\n",
            )

        execution_preview = _format_remote_execution_preview(spec)
        script_lines = [
            "#!/usr/bin/env bash",
            f"printf '%s\n' {_shell_single_quote('SSH Manager Ausführung')}",
            f"printf '%s\n' {_shell_single_quote(f'Host: {session.display_name} ({session.hostname})')}",
            f"printf '%s\n' {_shell_single_quote(f'User: {user}')}",
            "printf '%s\n' 'Reihenfolge:'",
            f"printf '%s\n\n' {_shell_single_quote(execution_preview)}",
            remote_body,
            "status=$?",
        ]
        if sudo_password:
            script_lines.insert(1, "trap 'unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"' EXIT")
        if not close_on_success:
            if sudo_password:
                script_lines.append(f"if [ $status -eq 0 ]; then unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"; exec {ssh_cmd}; fi")
            else:
                script_lines.append(f'if [ $status -eq 0 ]; then rm -f "$0"; exec {ssh_cmd}; fi')
        script_lines.append("if [ $status -ne 0 ]; then read; fi")
        script_lines.append("exit $status")
        script_path = _write_temp_bash_script("remote_script_", "\n".join(script_lines) + "\n")
        parts.append(_make_tab(session, user, [git_bash, script_path], settings, colors.get(session.key)))
    return TerminalCommand(parts)


@managed_scripts
def build_certificate_deploy_wt_command(
    session_deployments: list[tuple[Session, str, dict]],
    *,
    session_colors: dict[str, str] | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
) -> TerminalCommand:
    """Build one Windows Terminal tab per host for a certificate deployment."""
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    colors = session_colors or {}

    parts = []

    for index, (session, user, spec) in enumerate(session_deployments):
        files = [str(path) for path in spec["files"]]
        target_dirs = [str(path) for path in (spec.get("target_dirs") or [spec["target_dir"]])]
        overwrite = bool(spec.get("overwrite"))
        sudo_password = str(spec.get("sudo_password") or "")
        post_command = str(spec.get("post_command") or "").strip()
        close_on_success = bool(spec.get("close_on_success"))
        run_id = uuid.uuid4().hex
        remote_tmp_files = [f"/tmp/ssh-manager-cert-{run_id}-{file_index}" for file_index in range(len(files))]

        if session.is_ssh_config_session:
            upload_target = scp_target(session, user)
            scp_port = ""
        else:
            upload_target = scp_target(session, user)
            scp_port = f"-P {session.port} " if session.port != 22 else ""

        script_lines = [
            "#!/usr/bin/env bash",
            "trap 'rm -f \"$0\"' EXIT",
            "set -u",
            f"printf '%s\\n' {_shell_single_quote('Dateiübertragung')}",
            f"printf '%s\\n' {_shell_single_quote(f'Host: {session.display_name} ({session.hostname})')}",
            f"printf '%s\\n' {_shell_single_quote('Zielordner: ' + ', '.join(target_dirs))}",
            "printf '%s\\n' 'Upload nach /tmp:'",
        ]
        for local_path, remote_tmp in zip(files, remote_tmp_files):
            script_lines.append(f"printf '%s\\n' {_shell_single_quote('  - ' + Path(local_path).name)}")
            script_lines.append(f"scp {scp_port}-- {_shell_single_quote(local_path)} {_shell_single_quote(upload_target + ":" + remote_tmp)}")
            script_lines.append("if [ $? -ne 0 ]; then")
            script_lines.append("  echo 'FEHLER: Upload fehlgeschlagen. Der Nach-Befehl wird nicht ausgeführt.'")
            script_lines.append("  exit 1")
            script_lines.append("fi")

        ssh_cmd = _build_ssh_command(session, user)
        remote_lines = [
            "set -u",
            *(_sudo_password_prelude(sudo_password)),
            "header() {",
            "  printf '\\n==================================================\\n'",
            "  printf ' %s\\n' \"$1\"",
            "  printf '==================================================\\n'",
            "}",
            "cleanup() { rm -f -- " + " ".join(_shell_single_quote(path) for path in remote_tmp_files) + "; }",
            "trap cleanup EXIT",
            "header 'Dateien installieren'",
            "target_dirs=(" + " ".join(_shell_single_quote(path) for path in target_dirs) + ")",
            "for target_dir in \"${target_dirs[@]}\"; do",
            "  if ! sudo mkdir -p -- \"$target_dir\"; then",
            "    echo \"FEHLER: Zielordner konnte nicht erstellt oder geöffnet werden: $target_dir\"",
            "    exit 1",
            "  fi",
            "done",
        ]
        if not overwrite:
            remote_lines.append("echo 'Prüfe, ob vorhandene Dateien überschrieben würden …'")
            remote_lines.append("for target_dir in \"${target_dirs[@]}\"; do")
            for local_path in files:
                filename = Path(local_path).name
                remote_lines.extend([
                    f"  target_file=\"$target_dir\"/{_shell_single_quote(filename)}",
                    "  if [ -e \"$target_file\" ]; then",
                    "    echo \"AUSGELASSEN: Zieldatei existiert bereits: $target_file\"",
                    "    echo 'Es wurde keine Datei dieses Hosts ersetzt und kein Nach-Befehl ausgeführt.'",
                    "    exit 2",
                    "  fi",
                ])
            remote_lines.append("done")
        else:
            remote_lines.append("echo 'Vorhandene Zieldateien dürfen überschrieben werden.'")

        remote_lines.append("echo 'Installiere Dateien:'")
        remote_lines.append("for target_dir in \"${target_dirs[@]}\"; do")
        for local_path, remote_tmp in zip(files, remote_tmp_files):
            filename = Path(local_path).name
            remote_lines.extend([
                f"  target_file=\"$target_dir\"/{_shell_single_quote(filename)}",
                f"  if ! sudo cp -f -- {_shell_single_quote(remote_tmp)} \"$target_file\"; then",
                "    echo \"FEHLER: Datei konnte nicht installiert werden: $target_file\"",
                "    exit 1",
                "  fi",
                "  echo \"  OK: $target_file\"",
            ])
        remote_lines.append("done")
        if post_command:
            remote_lines.extend([
                "header 'Nach-Befehl nach erfolgreichem Upload'",
                post_command,
                "post_status=$?",
                "if [ $post_status -ne 0 ]; then",
                "  echo \"FEHLER: Nach-Befehl fehlgeschlagen (Exit-Code: $post_status).\"",
                "  exit $post_status",
                "fi",
            ])
        remote_lines.extend([
            "header 'ZUSAMMENFASSUNG'",
            f"echo {_shell_single_quote(f'Erfolgreich übertragen: {len(files)} Datei(en) in {len(target_dirs)} Zielordner')}",
            "echo 'Temporäre Dateien werden bereinigt.'",
        ])
        script_lines.extend([
            "printf '%s\\n' 'Alle Uploads erfolgreich. Installiere Dateien auf dem Zielhost …'",
            f"{ssh_cmd} -t <<'__CERT_DEPLOY__'",
            *remote_lines,
            "__CERT_DEPLOY__",
            "status=$?",
            "if [ $status -eq 0 ]; then",
        ])
        if close_on_success:
            script_lines.extend([
                "  exit 0",
            ])
        else:
            script_lines.extend([
                "  rm -f \"$0\"",
                f"  exec {ssh_cmd}",
            ])
        script_lines.extend([
            "fi",
            "echo \"Übertragung fehlgeschlagen (Exit-Code: $status).\"",
            "read",
            "exit $status",
        ])
        script_path = _write_temp_bash_script("certificate_deploy_", "\n".join(script_lines) + "\n")
        parts.append(_make_tab(session, user, [git_bash, script_path], settings, colors.get(session.key)))
    return TerminalCommand(parts)


@managed_scripts
def build_certificate_replace_wt_command(
    session_replacements: list[tuple[Session, str, dict]],
    *,
    session_colors: dict[str, str] | None = None,
    terminal_settings: WindowsTerminalSettings | None = None,
) -> TerminalCommand:
    """Create per-host terminal tabs that replace scanned certificate matches."""
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    colors = session_colors or {}

    parts = []
    for index, (session, user, spec) in enumerate(session_replacements):
        all_files_by_name = {Path(path).name: str(path) for path in spec["files"]}
        matches = [(str(name), str(path)) for name, path in spec["matches"]]
        files_by_name = {name: all_files_by_name[name] for name, _target in matches if name in all_files_by_name}
        sudo_password = str(spec.get("sudo_password") or "")
        post_command = str(spec.get("post_command") or "").strip()
        close_on_success = bool(spec.get("close_on_success"))
        run_id = uuid.uuid4().hex
        temp_paths = {name: f"/tmp/ssh-manager-replace-{run_id}-{item_index}" for item_index, name in enumerate(files_by_name)}
        ssh_cmd = _build_ssh_command(session, user)
        if session.is_ssh_config_session:
            upload_target, scp_port = scp_target(session, user), ""
        else:
            upload_target = scp_target(session, user)
            scp_port = f"-P {session.port} " if session.port != 22 else ""

        script_lines = ["#!/usr/bin/env bash", "trap 'rm -f \"$0\"' EXIT", "set -u", "echo 'Zertifikate ersetzen'"]
        for name, local_path in files_by_name.items():
            script_lines.extend([
                f"scp {scp_port}-- {_shell_single_quote(local_path)} {_shell_single_quote(upload_target + ":" + temp_paths[name])}",
                "if [ $? -ne 0 ]; then echo 'FEHLER: Upload fehlgeschlagen.'; exit 1; fi",
            ])
        remote_lines = [
            "set -u",
            *(_sudo_password_prelude(sudo_password)),
            "cleanup() { rm -f -- " + " ".join(_shell_single_quote(path) for path in temp_paths.values()) + "; }",
            "trap cleanup EXIT",
            "echo 'Ersetze gefundene Zertifikate …'",
        ]
        for name, target in matches:
            temp_path = temp_paths[name]
            remote_lines.extend([
                f"target={_shell_single_quote(target)}",
                "metadata=$(sudo stat -c '%u:%g:%a' -- \"$target\") || { echo \"FEHLER: Metadaten nicht lesbar: $target\"; exit 1; }",
                f"sudo cp -f -- {_shell_single_quote(temp_path)} \"$target\" || {{ echo \"FEHLER: Kopieren fehlgeschlagen: $target\"; exit 1; }}",
                "IFS=':' read -r owner group mode <<< \"$metadata\"",
                "sudo chown \"$owner:$group\" -- \"$target\" && sudo chmod \"$mode\" -- \"$target\" || { echo \"FEHLER: Metadaten nicht wiederhergestellt: $target\"; exit 1; }",
                "echo \"  OK: $target\"",
            ])
        if post_command:
            remote_lines.extend(["echo 'Führe Nach-Befehl aus …'", post_command, "post_status=$?", "[ $post_status -eq 0 ] || exit $post_status"])
        remote_lines.append("echo 'ZUSAMMENFASSUNG: Zertifikate erfolgreich ersetzt.'")
        cleanup_paths = " ".join(temp_paths.values())
        script_lines.extend([
            f"{ssh_cmd} <<'__CERT_REPLACE__'",
            *remote_lines,
            "__CERT_REPLACE__",
            "status=$?",
            f"if [ $status -ne 0 ]; then {ssh_cmd} \"rm -f -- {cleanup_paths}\" >/dev/null 2>&1 || true; fi",
        ])
        if close_on_success:
            script_lines.append("if [ $status -eq 0 ]; then exit 0; fi")
        else:
            script_lines.append(f"if [ $status -eq 0 ]; then rm -f \"$0\"; exec {ssh_cmd}; fi")
        script_lines.extend(["echo \"Ersetzen fehlgeschlagen (Exit-Code: $status).\"", "read", "exit $status"])
        script_path = _write_temp_bash_script("certificate_replace_", "\n".join(script_lines) + "\n")
        parts.append(_make_tab(session, user, [git_bash, script_path], settings, colors.get(session.key)))
    return TerminalCommand(parts)

def _write_temp_bash_script(prefix: str, content: str) -> str:
    """Schreibt ein temporäres Bash-Skript für WT/Git Bash und gibt den Windows-Pfad zurück."""
    return write_protected_script(_STATE_FILE.parent / "tmp", prefix, content)


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
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidates = []
    if local_app:
        candidates.append(Path(local_app) / "Programs" / "Git" / "bin" / "bash.exe")
    candidates.extend([
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    ])
    for candidate in candidates:
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


def _public_key_filename(value: str) -> str:
    if not value or Path(value).name != value or not value.endswith('.pub') or any(ord(c) < 32 for c in value):
        raise ValueError("Bitte den Dateinamen eines öffentlichen SSH-Keys (.pub) angeben.")
    return value


def _remove_key_remote_script() -> str:
    return "\n".join([
        'set -u',
        'auth="$HOME/.ssh/authorized_keys"',
        'tmp=$(mktemp "$HOME/.ssh/authorized_keys.ssh-manager.XXXXXX") || exit 1',
        "trap 'rm -f -- \"$tmp\"' EXIT",
        'grep -vxFf /dev/stdin -- "$auth" > "$tmp"',
        'status=$?',
        '# grep 1 means a successful empty result, not an I/O error.',
        '[ "$status" -le 1 ] || exit "$status"',
        'cat -- "$tmp" > "$auth" || exit 1',
    ])


@managed_scripts
def _build_key_command(sessions: list[Session], key_filename: str, user: str, settings: WindowsTerminalSettings, *, remove: bool) -> TerminalCommand:
    key = _public_key_filename(key_filename)
    connection_value(user, "Benutzer")
    git_bash = _find_git_bash()
    tabs = []
    for session in sessions:
        argv = ssh_argv(session, user)
        key_path = '\"$HOME/.ssh/\"' + _shell_single_quote(key)
        if remove:
            inner = shell_command(argv) + ' ' + _shell_single_quote(_remove_key_remote_script()) + ' < ' + key_path
        else:
            port = f" -p {valid_port(session.port)}" if session.port != 22 else ""
            inner = 'ssh-copy-id -i ' + key_path + port + ' -- ' + _shell_single_quote(argv[-1])
        content = '#!/usr/bin/env bash\ntrap \'rm -f "$0"\' EXIT\n' + inner + '\nstatus=$?\nif [ $status -eq 0 ]; then echo OK; else echo FEHLER; fi\nread\nexit $status\n'
        path = _write_temp_bash_script("ssh_key_", content)
        tabs.append(_make_tab(session, user, [git_bash, path], settings))
    return TerminalCommand(tabs)


def build_ssh_copy_id_command(sessions: list[Session], key_filename: str, user: str, terminal_settings: WindowsTerminalSettings | None = None) -> TerminalCommand:
    return _build_key_command(sessions, key_filename, user, terminal_settings or WindowsTerminalSettings(), remove=False)


def build_ssh_remove_key_command(sessions: list[Session], key_filename: str, user: str, terminal_settings: WindowsTerminalSettings | None = None) -> TerminalCommand:
    return _build_key_command(sessions, key_filename, user, terminal_settings or WindowsTerminalSettings(), remove=True)


def check_host_reachable(hostname: str, port: int = 22, timeout: int = 3) -> bool:
    """Prüft per TCP-Connect ob hostname:port erreichbar ist."""
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


@managed_scripts
def build_ssh_tunnel_command(
    ssh_server: str, local_port: int, remote_host: str, remote_port: int, user: str, terminal_settings: WindowsTerminalSettings | None = None
) -> TerminalCommand:
    """Erzeugt den wt.exe-Aufruf für SSH Local Port Forwarding."""
    settings = terminal_settings or WindowsTerminalSettings()
    git_bash = _find_git_bash()
    tunnel_target = f"{local_port} -> {remote_host}:{remote_port} via {user}@{ssh_server}"
    connection_value(ssh_server)
    connection_value(remote_host)
    connection_value(user, "Benutzer")
    valid_port(local_port)
    valid_port(remote_port)
    script = "\n".join([
        "#!/usr/bin/env bash",
        f"printf '%s\\n' {_shell_single_quote('SSH-Tunnel aktiv')}",
        f"printf '%s\\n\\n' {_shell_single_quote(tunnel_target)}",
        shell_command(["ssh", "-N", "-L", f"{local_port}:{remote_host}:{remote_port}", "--", f"{user}@{ssh_server}"]),
        "read",
    ]) + "\n"
    script_path = _write_temp_bash_script("ssh_tunnel_", script)
    session = Session("tunnel", f"{user}@{ssh_server}", [], ssh_server, username=user)
    return TerminalCommand([_make_tab(session, user, [git_bash, script_path], settings)])


# ---------------------------------------------------------------------------
# TerminalLauncher
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TerminalTabSpec:
    label: str
    command: str
    session: Session | None = None
    argv: tuple[str, ...] = ()
    options: tuple[str, ...] = ()


class TerminalCommand:
    """A launch plan; never parse an already-rendered shell command."""
    def __init__(self, tabs: list[TerminalTabSpec]):
        self.tabs = tabs

    def cleanup(self) -> None:
        for tab in self.tabs:
            if len(tab.argv) == 2 and tab.argv[-1].endswith(".sh"):
                cleanup_script(tab.argv[-1])

    @property
    def argv(self) -> list[str]:
        result = ["wt.exe"]
        for index, tab in enumerate(self.tabs):
            if index:
                result.append(";")
            # WT itself treats semicolons as separators, even without cmd.exe.
            values = ["new-tab", *tab.options, "--", *tab.argv]
            result.extend(value.replace(";", r"\;") for value in values)
        return result


def _make_tab(session: Session, user: str, argv: list[str], settings: WindowsTerminalSettings, color: str | None = None) -> TerminalTabSpec:
    title = ""
    if settings.title_mode == "name":
        title = session.display_name
    elif settings.title_mode == "host":
        title = session.hostname or session.display_name
    elif settings.title_mode == "user_host":
        title = f"{user}@{session.hostname or session.display_name}"
    elif settings.title_mode == "name_host":
        title = f"{session.display_name} ({session.hostname or session.display_name})"
    options = []
    color = valid_color(color) if settings.use_tab_color else None
    if color:
        options.extend(["--tabColor", color])
    if title:
        options.extend(["--title", title])
    profile = (settings.profile_name or "Git Bash").strip() or "Git Bash"
    if any(ord(c) < 32 for c in profile):
        raise ValueError("Terminal-Profil enthält Steuerzeichen.")
    options.extend(["-p", profile])
    pane_argv = [value.replace("\\", "/") if i == 0 or (i == 1 and argv[0].lower().endswith(('bash.exe', 'bash'))) else value for i, value in enumerate(argv)]
    return TerminalTabSpec(session.display_name, shell_command(pane_argv), session, tuple(argv), tuple(options))


class TerminalLaunchError(RuntimeError):
    """Fehler nach einem teilweise erfolgreichen Terminal-Start."""

    def __init__(self, message: str, started_sessions: list[Session] | None = None):
        super().__init__(message)
        self.started_sessions = list(started_sessions or [])


class HerdrUnavailableError(RuntimeError):
    """Herdr konnte vor dem Erzeugen des ersten Tabs nicht verwendet werden."""


class HerdrLauncher:
    """Öffnet normale SSH-Verbindungen in einem persistenten Herdr-Workspace."""

    WORKSPACE_LABEL = "SSH Manager"

    @staticmethod
    def _run(executable: str, args: list[str], timeout: float = 5.0) -> subprocess.CompletedProcess[str]:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=creationflags,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Unbekannter Fehler").strip()
            raise RuntimeError(detail)
        return result

    @classmethod
    def _run_json(cls, executable: str, args: list[str], timeout: float = 5.0) -> dict:
        result = cls._run(executable, args, timeout=timeout)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Herdr hat keine gültige JSON-Antwort geliefert.") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("Herdr hat ein unerwartetes Antwortformat geliefert.")
        return payload

    @classmethod
    def _ensure_server(cls, executable: str) -> None:
        try:
            status = cls._run_json(executable, ["status", "server", "--json"], timeout=2.0)
            if status.get("running") is True:
                return
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen(
                [executable, "server"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise HerdrUnavailableError(f"Herdr-Server konnte nicht gestartet werden: {exc}") from exc

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                status = cls._run_json(executable, ["status", "server", "--json"], timeout=1.0)
                if status.get("running") is True:
                    return
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
            time.sleep(0.1)
        raise HerdrUnavailableError("Der Herdr-Server war nach 5 Sekunden noch nicht erreichbar.")

    @classmethod
    def _find_workspace(cls, executable: str) -> str | None:
        payload = cls._run_json(executable, ["workspace", "list"])
        workspaces = payload.get("result", {}).get("workspaces", [])
        matches = [item for item in workspaces if isinstance(item, dict) and item.get("label") == cls.WORKSPACE_LABEL]
        if not matches:
            return None
        matches.sort(key=lambda item: int(item.get("number", 0)))
        workspace_id = matches[0].get("workspace_id")
        return str(workspace_id) if workspace_id else None

    @staticmethod
    def _created_tab(payload: dict) -> tuple[str, str, str]:
        result = payload.get("result", {})
        workspace = result.get("workspace", {})
        tab = result.get("tab", {})
        root_pane = result.get("root_pane", {})
        workspace_id = workspace.get("workspace_id") or tab.get("workspace_id")
        tab_id = tab.get("tab_id")
        pane_id = root_pane.get("pane_id")
        if not workspace_id or not tab_id or not pane_id:
            raise RuntimeError("Herdr hat für den neuen Tab keine vollständigen IDs geliefert.")
        return str(workspace_id), str(tab_id), str(pane_id)

    @classmethod
    def _has_visible_client(cls, executable: str) -> bool:
        """Unterscheidet interaktive Herdr-Clients von den Serverprozessen."""
        try:
            sessions = cls._run_json(executable, ["session", "list", "--json"])
            running_servers = sum(1 for item in sessions.get("sessions", []) if isinstance(item, dict) and item.get("running"))
            image_name = Path(executable).name
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            process_count = sum(1 for line in result.stdout.splitlines() if line.strip().lower().startswith(f'"{image_name.lower()}"'))
            return process_count > running_servers
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            return False

    @classmethod
    def _best_effort(cls, executable: str, args: list[str]) -> None:
        try:
            cls._run(executable, args)
        except (OSError, RuntimeError, subprocess.TimeoutExpired):
            pass

    @classmethod
    def launch(cls, sessions: list[Session], user: str, terminal_settings: WindowsTerminalSettings) -> None:
        tabs = [
            TerminalTabSpec(
                label=session.display_name,
                command=_build_ssh_command(session, session.username or user),
                session=session,
            )
            for session in sessions
        ]
        cls.launch_tabs(tabs, terminal_settings)

    @classmethod
    def launch_tabs(cls, tabs: list[TerminalTabSpec], terminal_settings: WindowsTerminalSettings) -> None:
        if not tabs:
            return
        executable = shutil.which("herdr")
        if not executable:
            raise HerdrUnavailableError("Herdr wurde nicht im PATH gefunden.")

        cls._ensure_server(executable)
        try:
            workspace_id = cls._find_workspace(executable)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            raise HerdrUnavailableError(f"Herdr-Workspace konnte nicht ermittelt werden: {exc}") from exc

        created_tabs: list[tuple[TerminalTabSpec, str, str]] = []
        try:
            remaining_tabs = list(tabs)
            if workspace_id is None:
                first_spec = remaining_tabs.pop(0)
                payload = cls._run_json(executable, ["workspace", "create", "--label", cls.WORKSPACE_LABEL, "--no-focus"])
                workspace_id, tab_id, pane_id = cls._created_tab(payload)
                created_tabs.append((first_spec, tab_id, pane_id))
                cls._best_effort(executable, ["tab", "rename", tab_id, first_spec.label])

            for spec in remaining_tabs:
                payload = cls._run_json(
                    executable,
                    ["tab", "create", "--workspace", workspace_id, "--label", spec.label, "--no-focus"],
                )
                _workspace_id, tab_id, pane_id = cls._created_tab(payload)
                created_tabs.append((spec, tab_id, pane_id))
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            if created_tabs:
                raise TerminalLaunchError(
                    f"Herdr konnte nicht alle Tabs anlegen ({len(created_tabs)} angelegt): {exc}",
                ) from exc
            raise HerdrUnavailableError(f"Herdr konnte keinen SSH-Tab anlegen: {exc}") from exc

        started_sessions: list[Session] = []
        try:
            for spec, _tab_id, pane_id in created_tabs:
                # pane run bestätigt Erfolg über den Exitcode, gibt dabei aber
                # bewusst keine JSON-Nutzlast aus.
                cls._run(executable, ["pane", "run", pane_id, spec.command])
                if spec.session is not None:
                    started_sessions.append(spec.session)

            first_tab_id = created_tabs[0][1]
            cls._best_effort(executable, ["workspace", "focus", workspace_id])
            cls._best_effort(executable, ["tab", "focus", first_tab_id])

            if not cls._has_visible_client(executable):
                profile = (terminal_settings.profile_name or "Git Bash").strip() or "Git Bash"
                clean_env = {
                    key: value
                    for key, value in os.environ.items()
                    if not key.upper().startswith("HERDR_")
                }
                subprocess.Popen(
                    ["wt.exe", "new-tab", "--reloadEnvironment", "-p", profile, "--", executable],
                    env=clean_env,
                )
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            raise TerminalLaunchError(
                f"Herdr hat den Terminal-Start nur teilweise abgeschlossen: {exc}",
                started_sessions=started_sessions,
            ) from exc


class TerminalLauncher:
    """Startet Terminal-Tabs in Windows Terminal oder Herdr."""

    @staticmethod
    def _tabs_from_windows_command(command: TerminalCommand, labels: list[str]) -> list[TerminalTabSpec]:
        if not isinstance(command, TerminalCommand) or len(command.tabs) != len(labels):
            raise ValueError("Ungültiger Terminal-Startplan.")
        from dataclasses import replace
        return [replace(tab, label=label) for tab, label in zip(command.tabs, labels)]

    @staticmethod
    def _launch_windows_command(command: TerminalCommand) -> None:
        if not isinstance(command, TerminalCommand):
            raise ValueError("Terminal-Start benötigt einen strukturierten Startplan.")
        if command.tabs:
            try:
                subprocess.Popen(command.argv, shell=False)
            except OSError:
                command.cleanup()
                raise

    @classmethod
    def launch_built_command(
        cls,
        command: TerminalCommand,
        labels: list[str],
        terminal_settings: WindowsTerminalSettings | None = None,
    ) -> None:
        settings = terminal_settings or WindowsTerminalSettings()
        if settings.ssh_open_mode == "herdr":
            tabs = cls._tabs_from_windows_command(command, labels)
            try:
                HerdrLauncher.launch_tabs(tabs, settings)
                return
            except HerdrUnavailableError:
                pass
        cls._launch_windows_command(command)

    @staticmethod
    def launch(sessions: list[Session], user: str, session_colors: dict[str, str] | None = None, terminal_settings: WindowsTerminalSettings | None = None) -> None:
        """
        Öffnet alle Sessions im konfigurierten Terminal-Ziel.
        Windows Terminal erhält Argumentlisten mit expliziten Tab-Trennern.
        """
        if not sessions:
            return
        settings = terminal_settings or WindowsTerminalSettings()
        if settings.ssh_open_mode == "herdr":
            try:
                HerdrLauncher.launch(sessions, user, settings)
                return
            except HerdrUnavailableError:
                # Solange Herdr noch keinen Tab erzeugt hat, ist der bisherige
                # Windows-Terminal-Weg der sichere und erwartete Fallback.
                pass
        cmd = build_wt_command(sessions, user, session_colors, terminal_settings=terminal_settings)
        TerminalLauncher._launch_windows_command(cmd)


# ---------------------------------------------------------------------------
# RegistryReader
# ---------------------------------------------------------------------------

# Allowlist patterns for input validation (defence against shell injection via
# registry data that ends up in build_wt_command which uses shell=True).
# Colon allowed for IPv6 addresses.
_HOSTNAME_RE = re.compile(r'^(?!-)[A-Za-z0-9.\-:_]+$')
_USERNAME_RE = re.compile(r'^(?!-)[A-Za-z0-9.\-_]*$')


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
        if not _HOSTNAME_RE.fullmatch(hostname) or hostname.startswith("-"):
            print(
                f"WARNING: Skipping session '{subkey_name}' – "
                f"hostname contains invalid characters: {hostname!r}",
                file=sys.stderr,
            )
            return None

        if username and (not _USERNAME_RE.fullmatch(username) or username.startswith("-")):
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
def _create_checkbox_images(
    root: tk.Tk,
    *,
    background: str = "#ffffff",
    border: str = "#808080",
    check: str = "#1a7a3a",
) -> tuple[tk.PhotoImage, tk.PhotoImage]:
    """
    Erzeugt zwei 16×16 PhotoImages für checked/unchecked Checkboxen.
    Gibt (img_unchecked, img_checked) zurück.
    """
    size = 16
    border_color = border
    bg_color = background
    check_color = check

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
