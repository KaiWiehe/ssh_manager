"""Validate restart templates and resolve their current connection references."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import uuid

from .restart_runtime import validate_execution_options, service_check
from .ssh_utils import connection_value

def new_template(sessions):
    seen = set()
    targets = []
    for session in sessions:
        if session.key not in seen:
            seen.add(session.key)
            targets.append({"key": session.key, "label": session.display_name,
                            "user": session.username, "checks": []})
    return {"id": uuid.uuid4().hex, "name": "Neue Neustart-Vorlage", "targets": targets,
            "mode": "parallel", "max_parallel": 3, "on_error": "pause",
            "reboot_timeout": 300, "service_timeout": 180}


def validate_template(item, *, runnable=False):
    if not isinstance(item, dict):
        raise ValueError("Ungültige Neustart-Vorlage.")
    # Rebuild a whitelist; plaintext passwords and unexpected payloads are never saved.
    result = {}
    from .restart_passwords import validate_sealed
    if "password_per_connection" in item:
        if type(item["password_per_connection"]) is not bool:
            raise ValueError("Ungültiger Passwortmodus.")
        result["password_per_connection"] = item["password_per_connection"]
    if "password_protected" in item:
        result["password_protected"] = validate_sealed(item["password_protected"])
    for field in ("id", "name"):
        value = item.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(c in value for c in "\r\n\x00"):
            raise ValueError("Vorlagen-ID und Name müssen ausgefüllt sein (maximal 200 Zeichen).")
        result[field] = value.strip()
    validate_execution_options(item)
    for field in ("mode", "on_error", "max_parallel", "reboot_timeout", "service_timeout"):
        result[field] = item[field]
    targets = item.get("targets")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 1000:
        raise ValueError("Eine Vorlage benötigt 1 bis 1000 Server.")
    result["targets"] = []
    seen = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Ungültiger Vorlagenserver.")
        key, label, user = (target.get(k, "") for k in ("key", "label", "user"))
        if not all(isinstance(v, str) for v in (key, label, user)) or not key or key in seen:
            raise ValueError("Serverreferenz fehlt oder ist doppelt.")
        if any(c in key + label + user for c in "\r\n\x00"):
            raise ValueError("Ungültiger Server oder Benutzer.")
        if user.strip():
            connection_value(user.strip(), "Benutzer")
        elif runnable:
            raise ValueError(f"Benutzer fehlt: {label or key}")
        checks = target.get("checks", [])
        if not isinstance(checks, list) or len(checks) > 100:
            raise ValueError("Maximal 100 Serviceprüfungen je Server.")
        normalized = []
        units = set()
        for check in checks:
            if not isinstance(check, dict) or not isinstance(check.get("unit"), str):
                raise ValueError("Ungültige Serviceprüfung.")
            value = service_check(check["unit"], check.get("expected"))
            if value["unit"] in units:
                raise ValueError("Service je Server nur einmal prüfen.")
            units.add(value["unit"])
            normalized.append(value)
        seen.add(key)
        result["targets"].append({"key": key, "label": label, "user": user.strip(), "checks": normalized})
        if "password_protected" in target:
            result["targets"][-1]["password_protected"] = validate_sealed(target["password_protected"])
    return result


def validate_library(value):
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("items"), list):
        raise ValueError("Nicht unterstützte Neustart-Vorlagenbibliothek.")
    items = [validate_template(item) for item in value["items"]]
    for field in ("id", "name"):
        values = [i[field].casefold() for i in items]
        if len(set(values)) != len(values):
            raise ValueError("Vorlagen-ID oder Name ist doppelt.")
    return {"schema": 1, "items": items}


def all_connections(app):
    from .actions_ui import _with_effective_username
    return [_with_effective_username(app, s) for field in
            ("_winscp_sessions", "_ssh_config_sessions", "_filezilla_sessions", "_app_sessions")
            for s in app.__dict__.get(field, [])]


def resolve_targets(template, sessions):
    by_key = {}
    for session in sessions:
        by_key.setdefault(session.key, []).append(session)
    resolved = []
    for target in template["targets"]:
        matches = by_key.get(target["key"], [])
        if len(matches) != 1:
            raise ValueError(f"Verbindung fehlt oder ist nicht eindeutig: {target['label']}. Bitte ersetzen oder entfernen.")
        session = replace(matches[0])
        # Only this run explicitly overrides the alias user; regular SSH actions keep their rules.
        session.ssh_user_override = target["user"] if session.is_ssh_config_session else ""
        resolved.append((session, target["user"], deepcopy(target["checks"])))
    return resolved


def target_fingerprint(resolved):
    return [(s.key, s.display_name, s.hostname, s.port, s.source, user, checks) for s, user, checks in resolved]
