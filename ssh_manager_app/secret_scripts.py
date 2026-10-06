"""User-bound DPAPI payloads; decrypted scripts never go to disk or argv."""
from __future__ import annotations

import base64
import ctypes
import os
from pathlib import Path
import shlex
import tempfile
import contextvars
from functools import wraps
from ctypes import wintypes

_building = contextvars.ContextVar("building_scripts", default=None)


def managed_scripts(builder):
    @wraps(builder)
    def build(*args, **kwargs):
        paths = []
        token = _building.set(paths)
        try:
            return builder(*args, **kwargs)
        except BaseException:
            for path in paths:
                cleanup_script(path)
            raise
        finally:
            _building.reset(token)
    return build


def protect(data: bytes) -> bytes:
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype = wintypes.BOOL
    if not crypt.CryptProtectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ctypes.WinError(ctypes.get_last_error())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def write_protected_script(directory: Path, prefix: str, content: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory, prefix=prefix, suffix=".sh", delete=False) as handle:
        wrapper = Path(handle.name)
    payload = wrapper.with_suffix(".payload")
    try:
        payload.write_bytes(protect(("# SSH_MANAGER_PROTECTED_SCRIPT\n" + content).encode("utf-8")))
        literal = str(payload).replace("'", "''")
        ps = (
            "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; Add-Type -AssemblyName System.Security; "
            f"$p='{literal}'; "
            "try { $b=[Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($p),$null,[Security.Cryptography.DataProtectionScope]::CurrentUser); "
            "$s=[Console]::OpenStandardOutput(); $s.Write($b,0,$b.Length) } finally { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }"
        )
        encoded = base64.b64encode(ps.encode("utf-16le")).decode("ascii")
        powershell = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe").replace("\\", "/")
        cleanup_command = 'rm -f -- "$0" ' + shlex.quote(str(payload).replace(chr(92), '/'))
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            f"trap {shlex.quote(cleanup_command)} EXIT\n"
            # eval is a Bash builtin; no decrypted bytes become process argv.
            f'SSH_MANAGER_SCRIPT="$({shlex.quote(powershell)} -NoProfile -NonInteractive -EncodedCommand {encoded})" || exit $?\n'
            '[[ "$SSH_MANAGER_SCRIPT" == "# SSH_MANAGER_PROTECTED_SCRIPT"* ]] || exit 1\n'
            'eval "$SSH_MANAGER_SCRIPT"\n',
            encoding="utf-8", newline="\n",
        )
        if _building.get() is not None:
            _building.get().append(str(wrapper))
        return str(wrapper)
    except BaseException:
        wrapper.unlink(missing_ok=True)
        payload.unlink(missing_ok=True)
        raise


def cleanup_script(path: str) -> None:
    for candidate in (Path(path), Path(path).with_suffix(".payload")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass


def clear_password_fields(dialog) -> None:
    import tkinter as tk
    for name in ("_sudo_password_var", "_sudo_password", "_keystore_password", "_keystore_password_var", "_password_var"):
        value = getattr(dialog, name, None)
        if isinstance(value, tk.Variable):
            value.set("")


def secure_legacy_scripts(directory: Path) -> None:
    """Protect pending old scripts without deleting still-needed terminal jobs."""
    prefixes = ("remote_cmd_", "remote_script_", "certificate_deploy_", "certificate_replace_", "ssh_tunnel_")
    if not directory.exists():
        return
    for path in directory.glob("*.sh"):
        if not path.name.startswith(prefixes):
            continue
        text = path.read_text(encoding="utf-8")
        if "SSH_MANAGER_SCRIPT=" in text:
            # Payload is consumed before running any remote operation.
            if not path.with_suffix(".payload").exists():
                # A renamed legacy wrapper points to another payload; keep it.
                continue
            continue
        protected = write_protected_script(directory, "migrated_", text)
        os.replace(protected, path)
