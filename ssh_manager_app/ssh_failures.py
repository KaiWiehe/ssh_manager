"""Safe, actionable messages for noninteractive SSH queries."""
from __future__ import annotations


SSH_AUTHENTICATION_HELP = (
    "SSH-Anmeldung fehlgeschlagen. SSH-Schlüssel für den gewählten Benutzer auf dem "
    "Zielserver hinterlegen und den lokalen Schlüssel bzw. SSH-Agent prüfen. "
    "Diese Hintergrundabfrage unterstützt keine SSH-Passworteingabe; ein sudo-Passwort "
    "ersetzt den SSH-Schlüssel nicht."
)


class SshQueryError(ValueError):
    """Only contains a fixed user-facing message, never raw remote output."""


def ssh_authentication_failed(returncode, stderr):
    if returncode != 255:
        return False
    text = (stderr or "").casefold()
    return any(marker in text for marker in (
        "permission denied (", "authentication failed", "no supported authentication methods",
        "too many authentication failures", "no more authentication methods to try",
        "sign_and_send_pubkey: signing failed",
    ))


def ssh_failure_message(returncode, stderr, fallback):
    return SSH_AUTHENTICATION_HELP if ssh_authentication_failed(returncode, stderr) else fallback
