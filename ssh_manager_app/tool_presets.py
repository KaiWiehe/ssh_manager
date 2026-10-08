"""Editable tunnel and service defaults with shared validation."""
import re
from .ssh_utils import read_port

DEFAULT_TUNNELS = [
    {"name": "PostgreSQL", "local": 5432, "remote": 5432},
    {"name": "MySQL", "local": 3306, "remote": 3306},
    {"name": "HTTP", "local": 8080, "remote": 80},
    {"name": "HTTPS", "local": 8443, "remote": 443},
]
DEFAULT_SERVICES = ["nginx.service", "wildfly.service", "postgresql.service", "ssh.service"]


def validate_tunnels(values):
    if not isinstance(values, list):
        raise ValueError("Tunnel-Vorgaben müssen eine Liste sein.")
    result, names = [], set()
    for item in values:
        name = item['name'].strip()
        if not name or name == 'Eigene Ports' or name in names or any(c in name for c in '\n\r|'):
            raise ValueError("Tunnel-Namen müssen eindeutig sein und dürfen kein | enthalten.")
        names.add(name)
        result.append(dict(name=name, local=read_port(item['local']), remote=read_port(item['remote'])))
    return result


def parse_tunnels(text):
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split('|')]
        if len(parts) != 3:
            raise ValueError("Tunnel je Zeile: Name | lokaler Port | Zielport")
        rows.append(dict(name=parts[0], local=parts[1], remote=parts[2]))
    return validate_tunnels(rows)


def validate_services(values):
    if not isinstance(values, list) or not all(isinstance(v, str) and re.fullmatch(r'(?!-)[A-Za-z0-9_.:@-]{1,200}', v) for v in values):
        raise ValueError("Ungültiger Dienstname in den Vorgaben.")
    return list(dict.fromkeys(values))
