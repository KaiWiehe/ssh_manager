"""Foreground SSH with inherited terminal handles and environment."""
from __future__ import annotations

import shutil
import signal
import subprocess
import os
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from .session_catalog import CatalogEntry
from .ssh_utils import ssh_argv


@contextmanager
def restored_console_modes():
    """Restore the caller's console flags even if its SSH client changes them."""
    saved = []
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel.GetStdHandle.restype = wintypes.HANDLE
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        for identifier in (-10, -11, -12):
            handle = kernel.GetStdHandle(identifier & 0xffffffff)
            mode = wintypes.DWORD()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                saved.append((handle, mode.value))
    try:
        yield
    finally:
        for handle, mode in saved:
            kernel.SetConsoleMode(handle, mode)


def launch(entry: CatalogEntry, user: str | None = None) -> tuple[int, str | None]:
    from .storage import record_recent_sessions

    client = shutil.which("ssh")
    if client is None:
        raise OSError("SSH-Client nicht im PATH gefunden. OpenSSH oder Git-SSH bereitstellen.")
    session = entry.session
    if user and session.is_ssh_config_session:
        # `ssh -l` overrides only the alias' User; host, port and keys stay configured.
        session = replace(session, ssh_user_override=user)
    args = ssh_argv(session, entry.user if user is None else user)
    args[0] = client
    msys_bash = Path(client).with_name("bash.exe")
    if os.name == "nt" and Path(client).with_name("msys-2.0.dll").is_file() and msys_bash.is_file():
        # MSYS SSH needs its own foreground job/tty setup when the parent is a
        # native Windows program. A constant exec command keeps every SSH value
        # a separate positional argument; no command text is interpolated.
        args = [str(msys_bash), "--noprofile", "--norc", "-c", 'exec "$@"', "sshm", *args]
    # No shell, pipes, new process group, detached process or terminal launcher.
    previous = signal.getsignal(signal.SIGINT)
    with restored_console_modes():
        try:
            # Install before spawn/metadata I/O so Ctrl+C cannot orphan SSH.
            # Use a handler, not SIG_IGN, which some clients would inherit.
            signal.signal(signal.SIGINT, lambda *_: None)
            child = subprocess.Popen(args)
            warning = None
            try:
                record_recent_sessions([entry.session.key])
            except (OSError, ValueError):
                warning = "SSH wurde gestartet, aber 'Zuletzt verwendet' konnte nicht gespeichert werden."
            return child.wait(), warning
        finally:
            signal.signal(signal.SIGINT, previous)
