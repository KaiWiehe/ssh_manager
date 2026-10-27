"""Windows-user-bound restart credentials; only sealed values reach persistence."""
from __future__ import annotations

import base64
import binascii
import ctypes
from ctypes import wintypes

from .secret_scripts import protect

PREFIX = "dpapi-user-v1:"
ERROR = "Passwort kann mit diesem Windows-Konto nicht gelesen werden. Auf dem ursprünglichen Rechner/Konto öffnen oder das betroffene Passwort neu eingeben."


def validate_sealed(value):
    if not isinstance(value, str) or len(value) > 65536:
        raise ValueError("Ungültiges verschlüsseltes Neustart-Passwort.")
    if value:
        try:
            if not value.startswith(PREFIX) or not base64.b64decode(value[len(PREFIX):], validate=True):
                raise ValueError
        except (ValueError, binascii.Error):
            raise ValueError("Ungültiges verschlüsseltes Neustart-Passwort.") from None
    return value


def unseal(value):
    validate_sealed(value)
    if not value:
        return ""
    try:
        data = base64.b64decode(value[len(PREFIX):], validate=True)
        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
        buffer = ctypes.create_string_buffer(data)
        source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = Blob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        crypt.CryptUnprotectData.restype = wintypes.BOOL
        if not crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
            raise OSError
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        try:
            return ctypes.string_at(output.data, output.size).decode("utf-8")
        finally:
            kernel.LocalFree(output.data)
    except (OSError, AttributeError, UnicodeError):
        raise ValueError(ERROR) from None


def seal(password, previous=""):
    if not isinstance(password, str) or len(password) > 4096 or any(c in password for c in "\r\n\x00"):
        raise ValueError("sudo-Passwort: maximal 4096 Zeichen, keine Zeilenumbrüche oder Nullzeichen.")
    if not password:
        return ""
    if previous:
        try:
            if unseal(previous) == password:
                return previous  # DPAPI is randomized; unchanged fields must remain clean.
        except ValueError:
            pass
    try:
        return PREFIX + base64.b64encode(protect(password.encode("utf-8"))).decode("ascii")
    except (OSError, AttributeError):
        raise ValueError("Passwort konnte nicht für dieses Windows-Konto verschlüsselt werden. Vorlage wurde nicht gespeichert.") from None


def passwords_for_run(template, targets, common):
    """Resolve every credential before admitting any reboot, keyed by stable connection ID."""
    if template.get("password_per_connection", False):
        stored = {t["key"]: t.get("password_protected", "") for t in template["targets"]}
        return {s.key: unseal(stored[s.key]) for s, _, _ in targets}
    return {s.key: common for s, _, _ in targets}
