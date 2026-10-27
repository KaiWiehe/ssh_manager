"""Validated restart plans and a scheduler that never dequeues work in workers."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import queue
import re
import threading
import uuid

from .models import Session
from .ssh_utils import connection_value

UNIT = re.compile(r"(?!-)[A-Za-z0-9_.:@-]{1,200}\.service\Z")
MODE_LABELS = {"parallel": "parallel", "serial": "nacheinander", "all_parallel": "Alle parallel durchstarten"}


def execution_policy(template):
    if template["mode"] == "all_parallel":
        return len(template["targets"]), "continue"
    return (1 if template["mode"] == "serial" else template["max_parallel"]), template["on_error"]


def service_check(name, expected="active"):
    name = name.strip()
    if not name.endswith(".service"):
        name += ".service"
    if not UNIT.fullmatch(name) or expected not in ("active", "inactive"):
        raise ValueError("Gültigen systemd-Dienst und Sollzustand aktiv/inaktiv angeben.")
    return {"unit": name, "expected": expected}


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
    for field, allowed in (("mode", tuple(MODE_LABELS)), ("on_error", ("continue", "stop", "pause"))):
        if item.get(field) not in allowed:
            raise ValueError("Ungültiger Ablauf oder Fehlerverhalten.")
        result[field] = item[field]
    for field, maximum in (("max_parallel", 128), ("reboot_timeout", 3600), ("service_timeout", 3600)):
        value = item.get(field)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{field}: ganze Zahl zwischen 1 und {maximum} erforderlich.")
        result[field] = value
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


class RestartScheduler:
    """Admission and failure gates share a lock, including worker completion."""
    def __init__(self, targets, limit, on_error, work):
        self.pending = list(targets)
        self.limit, self.on_error, self.work = limit, on_error, work
        self.active = 0
        self.paused = False
        self.stopped = False
        self.failures = []
        self.events = queue.Queue()
        self.lock = threading.RLock()

    def _complete(self, target, result):
        with self.lock:
            self.active -= 1
            if result.status in ("error", "timeout"):
                self.failures.append((target, result))
                self.paused |= self.on_error == "pause"
                self.stopped |= self.on_error == "stop"
            self.events.put((target, result))

    def _run(self, target):
        from .actions_restart import RestartResult
        try:
            result = self.work(target)
        except Exception as error:
            from .errors import record_failure
            record_failure(error)
            result = RestartResult("error", "Unerwarteter Prüffehler. Zustand manuell prüfen; kein automatischer Neustartversuch.")
        self._complete(target, result)

    def tick(self):
        from .actions_restart import RestartResult
        with self.lock:
            if self.stopped:
                for target in self.pending:
                    self.events.put((target, RestartResult("not_started", "Neustart wurde nicht ausgelöst")))
                self.pending.clear()
            while self.pending and not self.paused and not self.stopped and self.active < self.limit:
                target = self.pending.pop(0)
                self.active += 1
                try:
                    threading.Thread(target=self._run, args=(target,), daemon=True).start()
                except (RuntimeError, OSError):
                    self._complete(target, RestartResult("error", "Hintergrundaufgabe konnte nicht gestartet werden."))

    def decide(self, continue_run):
        with self.lock:
            self.paused = False
            self.stopped |= not continue_run
            self.failures.clear()

    @property
    def done(self):
        with self.lock:
            return not self.pending and not self.active
