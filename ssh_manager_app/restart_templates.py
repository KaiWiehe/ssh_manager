"""Validate restart templates and resolve their current connection references."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import uuid

from .constants import PALETTE
from .restart_runtime import validate_execution_options, service_check
from .ssh_utils import connection_value

TEMPLATE_COLORS = dict([("Ohne Farbe", "")] + PALETTE)


def _organization(item, parent_field):
    parent = item.get(parent_field, "")
    color = item.get("color", "")
    if not isinstance(parent, str) or color not in TEMPLATE_COLORS.values():
        raise ValueError("Ungültiger Ordner oder ungültige Vorlagenfarbe.")
    return {key: value for key, value in ((parent_field, parent), ("color", color)) if value}


def folder_paths(folders):
    """Return folder paths with ancestors inserted before descendants."""
    by_id = {folder["id"]: folder for folder in folders}
    paths = {"": ""}
    for folder in folders:
        current = folder["id"]
        chain = {}
        while current not in paths:
            if current in chain or current not in by_id:
                raise ValueError("Ein Vorlagenordner fehlt oder enthält sich selbst.")
            chain[current] = by_id[current]["name"]
            current = by_id[current].get("parent", "")
        for folder_id, name in reversed(chain.items()):
            path = paths[current]
            paths[folder_id] = f"{path} / {name}" if path else name
            current = folder_id
    del paths[""]
    return paths

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
    result.update(_organization(item, "folder"))
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
    raw_folders = value.get("folders", [])
    if not isinstance(raw_folders, list):
        raise ValueError("Ungültige Vorlagenordner.")
    folders = []
    for folder in raw_folders:
        if not isinstance(folder, dict):
            raise ValueError("Ungültiger Vorlagenordner.")
        folder_id, name = folder.get("id"), folder.get("name")
        if not isinstance(folder_id, str) or not 1 <= len(folder_id) <= 200 or any(c in folder_id for c in "\r\n\x00"):
            raise ValueError("Ungültige Vorlagenordner-ID.")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 200 or any(c in name for c in "/\r\n\x00"):
            raise ValueError("Ein Ordnername benötigt 1 bis 200 Zeichen ohne Schrägstrich.")
        folders.append({"id": folder_id, "name": name.strip(), **_organization(folder, "parent")})
    folder_ids = {folder["id"] for folder in folders}
    sibling_names = {(folder.get("parent", ""), folder["name"].casefold()) for folder in folders}
    if len(folder_ids) != len(folders) or len(sibling_names) != len(folders):
        raise ValueError("Ordner-IDs und Ordnernamen auf derselben Ebene müssen eindeutig sein.")
    folder_paths(folders)
    if any("folder" in item and item["folder"] not in folder_ids for item in items):
        raise ValueError("Der Ordner einer Vorlage existiert nicht mehr.")
    library = {"schema": 1, "items": items}
    if folders:
        library["folders"] = folders
    return library


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
