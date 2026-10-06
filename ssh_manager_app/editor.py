"""Shared VS Code launcher, including Windows' code.cmd entry point."""
import os
from pathlib import Path
import shutil
import subprocess


def open_in_vscode(path: Path) -> None:
    launcher = shutil.which("code")
    if not launcher:
        raise FileNotFoundError("VS Code wurde nicht im PATH gefunden.")
    target = str(path.absolute())
    if any(c in target + launcher for c in '\r\n\x00"'):
        raise ValueError("Ungültiger Editor-Pfad.")
    executable = Path(launcher)
    if os.name == "nt" and executable.suffix.lower() in {".cmd", ".bat"}:
        # Official launchers live in bin beside the installation's GUI binary.
        for name in ("Code.exe", "Code - Insiders.exe", "VSCodium.exe"):
            binary = executable.parent.parent / name
            if binary.is_file():
                subprocess.Popen([str(binary), target], shell=False)
                return
        # Custom launcher: fixed command syntax, paths supplied through the
        # environment. Percent signs in values are not recursively expanded.
        env = os.environ.copy()
        env["SSH_MANAGER_CODE_LAUNCHER"] = launcher
        env["SSH_MANAGER_CODE_TARGET"] = target
        command = '""%SSH_MANAGER_CODE_LAUNCHER%" "%SSH_MANAGER_CODE_TARGET%""'
        cmd = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/cmd.exe")
        if any(c in cmd for c in '\r\n\x00"'):
            raise ValueError("Ungültiger Windows-Pfad.")
        # cmd.exe needs its own outer quoting; list2cmdline's C-runtime quote
        # escapes are not the command processor's syntax.
        subprocess.Popen(f'"{cmd}" /d /v:off /s /c {command}',
                         env=env, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    else:
        subprocess.Popen([launcher, target], shell=False)
