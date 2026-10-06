"""Validated SSH data and argument lists, shared by all launch paths."""
from __future__ import annotations

import re
import shlex

from .models import Session


def connection_value(value: str, label: str = "SSH-Ziel") -> str:
    if not isinstance(value, str) or not value or value.startswith("-") or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError(f"Ungültiger Wert für {label}.")
    # These are connection identifiers, never commands or SSH options.
    if any(c in value for c in "\"'`$;&|<>\\"):
        raise ValueError(f"Ungültiger Wert für {label}.")
    return value


def ssh_argv(session: Session, user: str | None = None, options: list[str] | None = None) -> list[str]:
    args = ["ssh", *(options or [])]
    if session.is_ssh_config_session:
        target = connection_value(session.display_name, "SSH-Alias")
    else:
        host = connection_value(session.hostname, "Hostname")
        effective_user = (user or session.username).strip()
        target = f"{connection_value(effective_user, 'Benutzer')}@{host}" if effective_user else host
        if session.port != 22:
            args.extend(["-p", str(valid_port(session.port))])
    return [*args, "--", target]


def valid_port(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ValueError("Port muss zwischen 1 und 65535 liegen.")
    return value


def shell_command(args: list[str]) -> str:
    return shlex.join(args)


def scp_target(session: Session, user: str) -> str:
    if session.is_ssh_config_session:
        return connection_value(session.display_name, "SSH-Alias")
    host = connection_value(session.hostname, "Hostname")
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{connection_value(user, 'Benutzer')}@{host}"


def valid_color(value: str | None) -> str | None:
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else None
