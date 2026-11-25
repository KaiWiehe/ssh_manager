"""SSH operations, monitoring and admission rules shared by the app and script."""
from __future__ import annotations

from dataclasses import dataclass
import queue
import re
import shlex
import subprocess
import threading
import time
from typing import Protocol

from .ssh_failures import SSH_AUTHENTICATION_HELP, ssh_authentication_failed
from .ssh_utils import connection_value


UNIT = re.compile(r"(?!-)[A-Za-z0-9_.:@-]{1,200}\.service\Z")
MODE_LABELS = {"parallel": "parallel", "serial": "nacheinander", "all_parallel": "Alle parallel durchstarten"}


def validate_execution_options(plan):
    if plan.get("mode") not in tuple(MODE_LABELS) or plan.get("on_error") not in ("continue", "stop", "pause"):
        raise ValueError("Ungültiger Ablauf oder Fehlerverhalten.")
    for field, maximum in (("max_parallel", 128), ("reboot_timeout", 3600), ("service_timeout", 3600)):
        value = plan.get(field)
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f"{field}: ganze Zahl zwischen 1 und {maximum} erforderlich.")


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


POLL_INTERVAL_SECONDS = 2.0
SSH_PROBE_TIMEOUT_SECONDS = 8
SSH_REBOOT_TIMEOUT_SECONDS = 20
_CONNECTED_MARKER = "__SSH_MANAGER_CONNECTED__"
_BOOT_ID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
MASS_RESTART_SSH_OPTIONS = (
    "StrictHostKeyChecking=yes", "ForwardAgent=no", "ClearAllForwardings=yes",
    "ControlMaster=no", "ControlPath=none", "RequestTTY=no",
)


class SshTarget(Protocol):
    @property
    def display_name(self) -> str: ...

    @property
    def hostname(self) -> str: ...

    @property
    def port(self) -> int: ...

    @property
    def is_ssh_config_session(self) -> bool: ...

    @property
    def ssh_user_override(self) -> str: ...


@dataclass(frozen=True)
class RestartResult:
    status: str
    detail: str
    includes_service_states: bool = False


def _ssh_args(session: SshTarget, user: str, connect_timeout: int = 5, *, strict=False) -> list[str]:
    args = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={max(1, int(connect_timeout))}",
        "-o",
        "ConnectionAttempts=1",
    ]
    if strict:
        for option in MASS_RESTART_SSH_OPTIONS:
            args.extend(["-o", option])
    if session.is_ssh_config_session:
        if session.ssh_user_override:
            args.extend(["-l", connection_value(session.ssh_user_override)])
        args.extend(["--", connection_value(session.display_name)])
        return args
    if session.port and session.port != 22:
        args.extend(["-p", str(session.port)])
    args.extend(["--", f"{connection_value(user)}@{connection_value(session.hostname)}"])
    return args


def _run_ssh(
    session: SshTarget,
    user: str,
    remote_command: str,
    *,
    input_text: str | None = None,
    timeout: int = SSH_PROBE_TIMEOUT_SECONDS,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*_ssh_args(session, user), remote_command],
        stdin=subprocess.DEVNULL if input_text is None else None,
        input=input_text,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def _process_error(completed: subprocess.CompletedProcess[str], fallback: str, *, secret="") -> str:
    if ssh_authentication_failed(completed.returncode, completed.stderr):
        return SSH_AUTHENTICATION_HELP
    value = completed.stderr or completed.stdout or fallback
    if secret:
        value = value.replace(secret, "[ausgeblendet]")
    compact = " ".join(value.split())
    return compact if compact else fallback


def _read_boot_id(session: SshTarget, user: str, *, timeout=SSH_PROBE_TIMEOUT_SECONDS) -> tuple[bool, str | None, str]:
    command = f"printf '%s\\n' '{_CONNECTED_MARKER}'; cat /proc/sys/kernel/random/boot_id 2>/dev/null || true"
    try:
        completed = _run_ssh(session, user, command, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, None, "SSH-Verbindung hat das Zeitlimit überschritten."
    except OSError as exc:
        return False, None, str(exc)
    if completed.returncode != 0 or _CONNECTED_MARKER not in completed.stdout.splitlines():
        return False, None, _process_error(completed, "SSH-Verbindung fehlgeschlagen.")
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip() and line.strip() != _CONNECTED_MARKER]
    boot_id = next((line for line in lines if _BOOT_ID_RE.fullmatch(line)), None)
    return True, boot_id, ""


def _service_load_state(session: SshTarget, user: str, service: str) -> tuple[bool, str, str]:
    command = f"systemctl show --property=LoadState --value {shlex.quote(service)}"
    try:
        completed = _run_ssh(session, user, command)
    except subprocess.TimeoutExpired:
        return False, "", "Service-Prüfung hat das Zeitlimit überschritten."
    except OSError as exc:
        return False, "", str(exc)
    state = completed.stdout.strip().splitlines()[0].strip() if completed.stdout.strip() else ""
    if completed.returncode != 0:
        return False, state, _process_error(completed, f"systemd-Unit '{service}' konnte nicht geprüft werden.")
    if not state or state == "not-found":
        return True, state or "not-found", f"systemd-Unit '{service}' ist nicht vorhanden."
    return True, state, ""


def _service_active(session: SshTarget, user: str, service: str) -> tuple[bool, bool, str]:
    command = f"systemctl is-active {shlex.quote(service)}"
    try:
        completed = _run_ssh(session, user, command)
    except subprocess.TimeoutExpired:
        return False, False, "SSH-Zeitüberschreitung"
    except OSError as exc:
        return False, False, str(exc)
    if completed.returncode == 255:
        return False, False, _process_error(completed, "SSH nicht erreichbar")
    state = (completed.stdout or completed.stderr).strip().splitlines()
    state_text = state[0].strip() if state else "unbekannt"
    return True, completed.returncode == 0 and state_text == "active", state_text


def _issue_reboot(session: SshTarget, user: str, sudo_password: str, *, timeout=SSH_REBOOT_TIMEOUT_SECONDS) -> tuple[bool, bool, str]:
    if sudo_password:
        remote_command = "sudo -S -p '' reboot"
        input_text = sudo_password + "\n"
    else:
        remote_command = "sudo -n -p '' reboot"
        input_text = None
    try:
        completed = _run_ssh(
            session,
            user,
            remote_command,
            input_text=input_text,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, True, "SSH-Verbindung wurde während des Neustarts beendet."
    except OSError as exc:
        return False, False, str(exc)
    if completed.returncode == 0:
        return True, False, ""
    if completed.returncode == 255:
        error = _process_error(completed, "SSH-Verbindung wurde während des Neustarts beendet.", secret=sudo_password)
        return False, not ssh_authentication_failed(completed.returncode, completed.stderr), error
    return False, False, _process_error(completed, "sudo reboot ist fehlgeschlagen.", secret=sudo_password)


def monitor_server_restart(
    session: SshTarget,
    user: str,
    sudo_password: str,
    service: str,
    timeout_seconds: int,
    cancel_event: threading.Event,
    report,
    *,
    poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    monotonic=time.monotonic,
    evidence_detail=False,
) -> RestartResult:
    """Restart one server and wait until SSH and the optional unit are ready."""
    report("preflight", "SSH und Neustartstatus werden geprüft")
    connected, original_boot_id, error = _read_boot_id(session, user)
    if not connected:
        return RestartResult("error", error)

    if service:
        service_connected, load_state, service_error = _service_load_state(session, user, service)
        if not service_connected:
            return RestartResult("error", service_error)
        if load_state == "not-found" or service_error:
            return RestartResult("error", service_error)

    if cancel_event.is_set():
        return RestartResult("stopped", "Neustart wurde noch nicht ausgelöst")

    report("restarting", "sudo reboot wird ausgeführt")
    deadline = monotonic() + timeout_seconds
    issue_options = {"timeout": min(SSH_REBOOT_TIMEOUT_SECONDS, timeout_seconds)} if evidence_detail else {}
    accepted, uncertain, reboot_error = _issue_reboot(session, user, sudo_password, **issue_options)
    if not accepted and not uncertain:
        return RestartResult("error", reboot_error)

    saw_ssh_down = False
    online_streak = 0
    reboot_confirmed = False
    reboot_evidence = ""
    last_service_state = ""
    last_connected = True

    while monotonic() < deadline:
        if cancel_event.is_set():
            return RestartResult("stopped", "Überwachung durch Benutzer beendet")

        probe_options = {"timeout": max(.001, min(SSH_PROBE_TIMEOUT_SECONDS, deadline - monotonic()))} if evidence_detail else {}
        connected, current_boot_id, _probe_error = _read_boot_id(session, user, **probe_options)
        if evidence_detail and monotonic() >= deadline:
            break
        last_connected = connected
        if not connected:
            if _probe_error == SSH_AUTHENTICATION_HELP:
                return RestartResult("error", _probe_error)
            saw_ssh_down = True
            online_streak = 0
            report("waiting_ssh", "SSH ist noch nicht wieder erreichbar")
        else:
            if original_boot_id and current_boot_id:
                reboot_confirmed = current_boot_id != original_boot_id
                reboot_evidence = "Boot-ID geändert" if reboot_confirmed else ""
            elif saw_ssh_down:
                reboot_confirmed = True
                if not reboot_evidence:
                    reboot_evidence = "SSH-Ausfall und Rückkehr (schwächerer Ersatznachweis)"

            if not reboot_confirmed:
                online_streak = 0
                detail = "SSH antwortet noch mit der bisherigen Boot-ID" if original_boot_id else "Warte auf den SSH-Ausfall"
                report("waiting_down", detail)
            else:
                online_streak += 1
                if online_streak < 2:
                    report("waiting_ssh", "SSH antwortet; Stabilität wird bestätigt")
                elif service:
                    service_connected, active, state = _service_active(session, user, service)
                    if not service_connected:
                        if state == SSH_AUTHENTICATION_HELP:
                            return RestartResult("error", state)
                        online_streak = 0
                        report("waiting_ssh", "SSH ist während der Service-Prüfung nicht erreichbar")
                    elif active:
                        return RestartResult("online", f"SSH und {service} sind verfügbar")
                    else:
                        last_service_state = state
                        report("waiting_service", f"{service}: {state}")
                else:
                    if evidence_detail:
                        return RestartResult("online", f"Neustart bestätigt: {reboot_evidence}; SSH ist wieder erreichbar")
                    return RestartResult("online", "Neustart bestätigt; SSH ist wieder erreichbar")

        delay = poll_interval_seconds
        if evidence_detail:
            delay = min(delay, deadline - monotonic())
        if cancel_event.wait(max(0.0, delay)):
            return RestartResult("stopped", "Überwachung durch Benutzer beendet")

    if service and reboot_confirmed and last_connected:
        detail = f"{service} wurde nicht aktiv"
        if last_service_state:
            detail += f" (letzter Zustand: {last_service_state})"
    elif saw_ssh_down and not last_connected:
        detail = "SSH wurde innerhalb der Wartezeit nicht wieder erreichbar"
    else:
        detail = "Der Server-Neustart konnte innerhalb der Wartezeit nicht bestätigt werden"
    return RestartResult("timeout", detail)


def probe_unit(session, user, unit, timeout=8):
    command = f"systemctl show --property=LoadState --property=ActiveState -- {shlex.quote(unit)}"
    try:
        completed = _run_ssh(session, user, command, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return "connection", "SSH-Abfrage nicht erreichbar oder Zeitüberschreitung"
    if completed.returncode == 255:
        if ssh_authentication_failed(completed.returncode, completed.stderr):
            return "error", SSH_AUTHENTICATION_HELP
        return "connection", "SSH nicht erreichbar"
    return service_probe_result(completed)


def service_probe_result(completed):
    props = dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)
    if props.get("LoadState") == "not-found":
        return "error", "Dienst nicht vorhanden"
    if completed.returncode or props.get("LoadState") not in ("loaded", "masked", "merged") or not props.get("ActiveState"):
        return "error", "Dienst konnte nicht zuverlässig geprüft werden"
    return "state", props["ActiveState"]


class RestartScheduler:
    """Admission and failure gates share a lock, including worker completion."""
    def __init__(self, targets, limit, on_error, work, *, record_error=None, daemon=True, cancel=None):
        self.pending = list(targets)
        self.limit, self.on_error, self.work = limit, on_error, work
        self.record_error = record_error
        self.daemon = daemon
        self.cancel = cancel
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
        try:
            result = self.work(target)
        except Exception as error:
            if self.record_error is not None:
                self.record_error(error)
            result = RestartResult("error", "Unerwarteter Prüffehler. Zustand manuell prüfen; kein automatischer Neustartversuch.")
        self._complete(target, result)

    def tick(self):
        with self.lock:
            if self.stopped:
                for target in self.pending:
                    self.events.put((target, RestartResult("not_started", "Neustart wurde nicht ausgelöst")))
                self.pending.clear()
            while (self.pending and not self.paused and not self.stopped and self.active < self.limit
                   and (self.cancel is None or not self.cancel.is_set())):
                target = self.pending.pop(0)
                self.active += 1
                try:
                    threading.Thread(target=self._run, args=(target,), daemon=self.daemon).start()
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
