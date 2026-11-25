"""Verified, two-phase restart runs shared by the editor and standalone export."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from ipaddress import ip_address
import os
from pathlib import Path
import queue
import re
from secrets import token_hex
import shlex
import signal
import subprocess
import threading
import time
import traceback

from .restart_runtime import (RestartResult, RestartScheduler, SshTarget, _ssh_args,
                              execution_policy, service_probe_result)
from .restart_winjob import CREATE_SUSPENDED, WindowsRestartJob
from .ssh_failures import SSH_AUTHENTICATION_HELP, ssh_authentication_failed


MACHINE_ID_FILE = "/etc/machine-id"
BOOT_ID_FILE = "/proc/sys/kernel/random/boot_id"
IDENTITY_MARKER = "__SSH_MANAGER_RESTART_ID__"
MACHINE_ID = re.compile(r"[0-9a-f]{32}")
RESTART_BOOT_ID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
EMPTY_BOOT_ID = "00000000-0000-0000-0000-000000000000"
IDENTITY_COMMAND = (
    f"machine=$(cat {MACHINE_ID_FILE}) && boot=$(cat {BOOT_ID_FILE}) "
    f"&& printf '{IDENTITY_MARKER}:%s:%s:%s\\n' \"$machine\" \"$boot\" \"${{SSH_CONNECTION-}}\""
)
IDENTITY_CHANGED = 79
REBOOT_COMMAND = "reboot"
PROBE_TIMEOUT = 8
REBOOT_REQUEST_TIMEOUT = 20


@dataclass(frozen=True)
class RestartIdentity:
    machine_id: str
    boot_id: str
    endpoint: str = ""


@dataclass(frozen=True)
class RestartPreflight(RestartResult):
    identity: RestartIdentity | None = None


class RestartCancelled(Exception):
    pass


def validate_sudo_password(password):
    if not isinstance(password, str) or len(password) > 4096 or any(char in password for char in "\r\n\x00"):
        raise ValueError("sudo-Passwort: maximal 4096 Zeichen, keine Zeilenumbrüche oder Nullzeichen.")


def _terminate_restart_ssh(process, job, *, collect_pipes):
    try:
        if job is not None:
            job.terminate()
            if process.poll() is None:
                process.kill()  # Also handles failure before assignment to the job.
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if collect_pipes:
        try:
            process.communicate(timeout=1)
            return
        except subprocess.TimeoutExpired:
            pass
    process.wait(timeout=1)


def _collect_ssh_stream(stream, output, *, on_line=None):
    with stream:
        for line in iter(stream.readline, b""):
            if on_line:
                on_line(line)
            output.extend(line)


def _wait_for_ssh(process, cancel, deadline, timeout, *, capture_output):
    while not cancel.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        try:
            if capture_output:
                return process.communicate(timeout=min(.1, remaining))
            process.wait(timeout=min(.1, remaining))
            return
        except subprocess.TimeoutExpired:
            continue
    raise RestartCancelled


def _ssh_with_verified_password(process, password, ready, cancel, deadline, timeout):
    """Send the password on this SSH connection after its remote identity check."""
    stdout, stderr = bytearray(), bytearray()
    marker = ready.encode("ascii")
    sent = False
    handoff = threading.Lock()

    def on_stdout(line):
        nonlocal password, sent
        if line.rstrip(b"\r\n") != marker:
            return
        with handoff:
            if not password or cancel.is_set() or time.monotonic() >= deadline:
                return
            value, password = password, ""
            sent = True
        try:
            with process.stdin as stream:
                stream.write((value + "\n").encode("utf-8"))
        except (OSError, UnicodeError):
            pass

    readers = [
        threading.Thread(target=_collect_ssh_stream, args=(process.stdout, stdout),
                         kwargs={"on_line": on_stdout}, daemon=True),
        threading.Thread(target=_collect_ssh_stream, args=(process.stderr, stderr), daemon=True),
    ]
    try:
        for reader in readers:
            reader.start()
        _wait_for_ssh(process, cancel, deadline, timeout, capture_output=False)
        for reader in readers:
            reader.join(timeout=max(0, min(1, deadline - time.monotonic())))
        if any(reader.is_alive() for reader in readers):
            raise subprocess.TimeoutExpired(process.args, timeout)
        return stdout, stderr
    finally:
        with handoff:
            password = ""
        # The stdout reader owns stdin after the readiness marker.
        if not sent and not process.stdin.closed:
            process.stdin.close()


def mass_ssh(session: SshTarget, user, command, cancel, *, timeout=PROBE_TIMEOUT, password="", ready=""):
    if cancel.is_set():
        raise RestartCancelled
    if password and not ready:
        raise ValueError("Interner Fehler: sudo-Passwort erfordert einen verifizierten SSH-Kanal.")
    args = [*_ssh_args(session, user, strict=True), command]
    deadline = time.monotonic() + timeout
    with ExitStack() as resources:
        job = WindowsRestartJob() if os.name == "nt" else None
        if job is not None:
            resources.callback(job.close)
        flags = (getattr(subprocess, "CREATE_NO_WINDOW", 0) | CREATE_SUSPENDED) if job else 0
        process = subprocess.Popen(
            args, stdin=subprocess.PIPE if password else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={**os.environ, "LC_ALL": "C"},
            creationflags=flags, start_new_session=os.name != "nt",
        )
        try:
            if job is not None:
                if cancel.is_set():
                    raise RestartCancelled
                job.attach_and_resume(process.pid)
            if password:
                stdout, stderr = _ssh_with_verified_password(process, password, ready, cancel, deadline, timeout)
            else:
                stdout, stderr = _wait_for_ssh(process, cancel, deadline, timeout, capture_output=True)
            return subprocess.CompletedProcess(args, process.returncode, stdout.decode("utf-8", "replace"),
                                               stderr.decode("utf-8", "replace"))
        except BaseException:
            _terminate_restart_ssh(process, job, collect_pipes=not password)
            raise


def _ssh_verification_error(result):
    if result.returncode != 255:
        return ""
    error = result.stderr.casefold()
    if any(marker in error for marker in ("host key verification failed", "remote host identification has changed",
                                          "requested strict checking", "host key is revoked")):
        return "SSH-Hostschlüssel nicht verifiziert. Vertrauenswürdig hinterlegten Schlüssel für Ziel und Sprunghost prüfen."
    if ssh_authentication_failed(result.returncode, result.stderr):
        return SSH_AUTHENTICATION_HELP
    return ""


def read_restart_identity(session, user, cancel, *, timeout=PROBE_TIMEOUT):
    try:
        result = mass_ssh(session, user, IDENTITY_COMMAND, cancel, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "connection", "SSH-Zeitüberschreitung"
    except OSError:
        return "error", "OpenSSH konnte nicht ausgeführt werden."
    failure = _ssh_verification_error(result)
    if failure:
        return "error", failure
    if result.returncode == 255:
        return "connection", "SSH nicht erreichbar"
    rows = [line.split(":", 3) for line in result.stdout.splitlines() if line.startswith(IDENTITY_MARKER + ":")]
    if (result.returncode or len(rows) != 1 or len(rows[0]) < 3
            or not MACHINE_ID.fullmatch(rows[0][1]) or rows[0][1] == "0" * 32
            or not RESTART_BOOT_ID.fullmatch(rows[0][2]) or rows[0][2] == EMPTY_BOOT_ID):
        return "missing", "Gültige Maschinen- oder Boot-ID nicht ermittelbar."
    connection = rows[0][3] if len(rows[0]) == 4 else ""
    fields = connection.split(" ")
    endpoint = ""
    if len(fields) == 4:
        try:
            ip_address(fields[2])
            if fields[3].isascii() and fields[3].isdigit() and len(fields[3]) <= 5 and 1 <= int(fields[3]) <= 65535:
                endpoint = f"{fields[2]} {fields[3]}"
        except ValueError:
            pass
    return "identity", RestartIdentity(rows[0][1], rows[0][2], endpoint)


def _guarded_command(identity, command, ready=""):
    announce = f"printf '%s\\n' {ready}; " if ready else ""
    guard = (f'test "$(cat {MACHINE_ID_FILE})" = {identity.machine_id} '
             f'&& test "$(cat {BOOT_ID_FILE})" = {identity.boot_id}')
    if identity.endpoint:
        guard += ' && test "${SSH_CONNECTION#* * }" = ' + shlex.quote(identity.endpoint)
    return f"{guard} || exit {IDENTITY_CHANGED}; " + announce + command


def _sudo_command(password, *, permission_check=False):
    mode = "-S" if password else "-n"
    query = "-l " if permission_check else ""
    return f"sudo {mode} -p '' {query}-- {REBOOT_COMMAND}"


def _call_restart_sudo(session, user, password, identity, cancel, *, timeout=PROBE_TIMEOUT, permission_check=False):
    ready = "__SSH_MANAGER_SUDO_READY_" + token_hex(16)
    finished = "__SSH_MANAGER_SUDO_DONE_" + token_hex(16)
    sudo = _sudo_command(password, permission_check=permission_check)
    command = _guarded_command(identity, f"{sudo} && printf '%s\\n' {finished}", ready)
    result = mass_ssh(session, user, command, cancel, timeout=timeout, password=password, ready=ready)
    lines = result.stdout.splitlines()
    confirmed = (lines.count(ready) == 1 and lines.count(finished) == 1 and lines.index(ready) < lines.index(finished))
    return result, confirmed


def _probe_restart_unit(session, user, unit, identity, cancel, *, timeout=PROBE_TIMEOUT):
    command = f"systemctl show --property=LoadState --property=ActiveState -- {shlex.quote(unit)}"
    try:
        result = mass_ssh(session, user, _guarded_command(identity, command), cancel, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "connection", "Zeitüberschreitung der SSH-Abfrage"
    except OSError:
        return "error", "OpenSSH konnte nicht ausgeführt werden."
    failure = _ssh_verification_error(result)
    if failure:
        return "error", failure
    if result.returncode == IDENTITY_CHANGED:
        return "error", "Zielidentität oder Boot-ID hat sich während der Prüfung geändert."
    if result.returncode == 255:
        return "connection", "SSH nicht erreichbar"
    return service_probe_result(result)


def check_restart_target(session, user, checks, password, cancel, report, reserve_identity=None):
    report("preflight", "Vorprüfung gestartet")
    kind, identity = read_restart_identity(session, user, cancel)
    if kind != "identity":
        return RestartResult("error", identity)

    def failed(detail):
        return RestartPreflight("error", detail, identity=identity)

    if reserve_identity:
        conflict = reserve_identity(identity)
        if conflict:
            return failed(conflict)
    boot = RestartIdentity(identity.machine_id, identity.boot_id)
    failures = []
    for check in checks:
        kind, state = _probe_restart_unit(session, user, check["unit"], boot, cancel)
        if kind != "state":
            failures.append(f"{check['unit']}: {state}")
    if failures:
        return failed("Vorprüfung der Dienste fehlgeschlagen\n" + "\n".join(failures))
    try:
        result, confirmed = _call_restart_sudo(session, user, password, boot, cancel, permission_check=True)
    except (OSError, subprocess.TimeoutExpired):
        return failed("sudo-Berechtigung für reboot nicht verifiziert. SSH-Verbindung prüfen.")
    failure = _ssh_verification_error(result)
    if failure:
        return failed(failure)
    if result.returncode == IDENTITY_CHANGED:
        return failed("Zielidentität oder Boot-ID hat sich während der Vorprüfung geändert.")
    if result.returncode or not confirmed:
        return failed("sudo-Berechtigung für reboot nicht verifiziert. sudoers und Passwortmodus prüfen.")
    report("preflight", "Vorprüfung bestanden; wartet auf den gesamten Plan")
    return RestartPreflight("online", "Vorprüfung bestanden", identity=identity)


def _request_verified_reboot(session, user, password, identity, cancel, timeout, report):
    try:
        result, confirmed = _call_restart_sudo(session, user, password, identity, cancel, timeout=timeout)
    except subprocess.TimeoutExpired:
        report("waiting_ssh", "SSH-Zeitüberschreitung nach Neustartanforderung. Warte auf Boot-ID-Nachweis.")
        return None
    except OSError:
        return RestartResult("error", "Lokaler SSH-Fehler. Serverzustand vor einer Wiederholung prüfen.")
    failure = _ssh_verification_error(result)
    if failure:
        return RestartResult("error", failure)
    if result.returncode == IDENTITY_CHANGED:
        return RestartResult("error", "Zielidentität oder Boot-ID hat sich seit der Vorprüfung geändert. Kein Neustart ausgelöst.")
    if result.returncode not in (0, 255):
        return RestartResult("error", "sudo reboot fehlgeschlagen. Berechtigung und Passwortmodus prüfen.")
    if result.returncode == 0 and confirmed:
        report("restarting", "Neustartanforderung bestätigt; warte auf neue Boot-ID")
    else:
        report("waiting_ssh", "Status der Neustartanforderung offen; warte auf Boot-ID-Nachweis")
    return None


def wait_for_new_boot(session, user, original, deadline, cancel, report, monotonic, poll_interval, known_boot_ids=()):
    previous = None
    while (remaining := deadline - monotonic()) > 0 and not cancel.is_set():
        kind, current = read_restart_identity(session, user, cancel, timeout=min(PROBE_TIMEOUT, remaining))
        if monotonic() >= deadline:
            break
        if kind == "error":
            return None, RestartResult("error", current)
        if kind == "identity" and current.machine_id != original.machine_id:
            return None, RestartResult("error", "SSH führt zu einer anderen Maschine. Neustart nicht bestätigt.")
        if kind == "identity" and original.endpoint and current.endpoint != original.endpoint:
            return None, RestartResult("error", "SSH-Zieladresse oder Port hat sich geändert. Neustart nicht bestätigt.")
        if kind == "identity" and current.boot_id != original.boot_id:
            if current.boot_id in known_boot_ids:
                return None, RestartResult("error", "SSH meldet die Boot-ID eines anderen Plan-Ziels. Neustart nicht bestätigt.")
            current = RestartIdentity(current.machine_id, current.boot_id, original.endpoint)
            if previous == current:
                report("waiting_ssh", "SSH online und Boot-ID geändert")
                return current, None
            previous = current
            report("waiting_ssh", "Neue Boot-ID erkannt; warte auf zweite Abfrage")
        else:
            previous = None
            state = "SSH offline" if kind == "connection" else "SSH erreichbar; warte auf neue gültige Boot-ID"
            report("waiting_ssh", state)
        cancel.wait(max(0, min(poll_interval, deadline - monotonic())))
    if cancel.is_set():
        raise RestartCancelled
    return None, RestartResult("timeout", "Neustart nicht bestätigt. Innerhalb der Frist keine stabile neue Boot-ID erhalten.")


def wait_for_restart_services(session, user, checks, identity, timeout, cancel, report, monotonic, poll_interval):
    deadline = monotonic() + timeout
    latest = {check["unit"]: "nicht geprüft" for check in checks}
    evidence = "Boot-ID geändert; SSH wieder erreichbar"

    def result(status, message):
        details = [f"{check['unit']}: Soll {check['expected']}, Ist {latest[check['unit']]}" for check in checks]
        return RestartResult(status, "\n".join([evidence, message, *details]), includes_service_states=True)

    while monotonic() < deadline and not cancel.is_set():
        matches = True
        for check in checks:
            remaining = deadline - monotonic()
            if remaining <= 0 or cancel.is_set():
                matches = False
                break
            unit = check["unit"]
            kind, state = _probe_restart_unit(session, user, unit, identity, cancel, timeout=min(PROBE_TIMEOUT, remaining))
            if latest[unit] != state:
                latest[unit] = state
                report("waiting_service", "\n".join(f"{item}: {value}" for item, value in latest.items()))
            if kind == "error":
                return result("error", "Dienstprüfung fehlgeschlagen")
            matches &= kind == "state" and state == check["expected"]
        if matches and monotonic() <= deadline:
            return result("online", "Alle Service-Sollzustände erfüllt")
        cancel.wait(max(0, min(poll_interval, deadline - monotonic())))
    if cancel.is_set():
        return result("stopped", "Dienstüberwachung abgebrochen")
    return result("timeout", "Service-Wartezeit abgelaufen")


def run_prepared_restart(session, user, checks, take_password, original, reboot_timeout, service_timeout,
                         cancel, report, known_boot_ids=(), *, monotonic=time.monotonic, poll_interval=2):
    if cancel.is_set():
        return RestartResult("not_started", "Neustart wurde nicht ausgelöst")
    deadline = monotonic() + reboot_timeout
    report("restarting", "Sende Neustartanforderung")
    try:
        failure = _request_verified_reboot(session, user, take_password(), original, cancel,
                                           min(REBOOT_REQUEST_TIMEOUT, reboot_timeout), report)
        if failure:
            return failure
        identity, failure = wait_for_new_boot(session, user, original, deadline, cancel, report, monotonic, poll_interval,
                                              known_boot_ids)
        if failure:
            return failure
    except RestartCancelled:
        return RestartResult("stopped", "SSH-Aufruf beendet. Zustand der Neustartanforderung unbekannt; Server prüfen.")
    if not checks:
        return RestartResult("online", "Boot-ID geändert; SSH wieder erreichbar")
    try:
        return wait_for_restart_services(session, user, checks, identity, service_timeout, cancel,
                                         report, monotonic, poll_interval)
    except RestartCancelled:
        return RestartResult("stopped", "Boot-ID geändert; Dienstüberwachung abgebrochen")


def duplicate_restart_targets(targets):
    seen = {}
    for index, (session, _user, _checks) in enumerate(targets):
        if session.is_ssh_config_session:
            key = ("alias", session.display_name.casefold())
        else:
            key = ("host", session.hostname.rstrip(".").casefold(), session.port or 22)
        previous = seen.get(key)
        if previous is not None:
            raise ValueError(f"Doppeltes Ziel: Eintrag {previous + 1} ({targets[previous][0].display_name}) "
                             f"und {index + 1} ({session.display_name}).")
        seen[key] = index


def restart_lock_directory():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return base / "SSH-Manager" / "restart-locks"


def _lock_restart_identity(stack, directory, identity):
    key = sha256(("ssh-manager-restart-v1:" + identity.machine_id).encode("ascii")).hexdigest()
    handle = stack.enter_context((directory / (key + ".lock")).open("a+b"))
    if os.name == "nt":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


class MassRestartRun:
    """Check every target, acquire all target locks, then admit reboots."""

    def __init__(self, plan, targets, passwords, cancel, *, record_error=None):
        duplicate_restart_targets(targets)
        for password in passwords:
            validate_sudo_password(password)
        self.targets, self.plan, self.passwords, self.cancel = targets, plan, passwords, cancel
        self.record_error = record_error
        self.limit, self.error_policy = execution_policy({**plan, "targets": targets})
        self.preflights, self.identity_checks, self.results = {}, {}, {}
        self.known_boot_ids = frozenset()
        self.events = queue.Queue()
        self.notices = {}
        self.locks = ExitStack()
        self.locked_machines = set()
        self.reserve_lock = threading.Lock()
        self.phase = "preflight"
        self.identity_check_count = 0
        self.scheduler = RestartScheduler(range(len(targets)), self.limit, "continue", self._preflight,
                                          daemon=False, cancel=cancel)

    def _report(self, index, state, detail):
        # Each worker reports only for its own target. Full lines retain their event timestamp.
        if self.notices.get(index) != (state, detail):
            self.notices[index] = (state, detail)
            self.events.put((datetime.now(), index, state, detail))

    def _unexpected(self, index, phase, error):
        frames = traceback.extract_tb(error.__traceback__)
        location = f" ({Path(frames[-1].filename).name}:{frames[-1].lineno})" if frames else ""
        detail = f"{phase}: {type(error).__name__}{location}"
        if self.record_error:
            self.record_error(error)
        return RestartResult("error", detail + ". Serverzustand vor einer Wiederholung prüfen.")

    def _preflight(self, index):
        try:
            result = check_restart_target(*self.targets[index], self.passwords[index], self.cancel,
                                          lambda state, detail: self._report(index, state, detail), self._reserve)
        except RestartCancelled:
            result = RestartResult("not_started", "Vorprüfung abgebrochen")
        except Exception as error:
            result = self._unexpected(index, "Vorprüfung", error)
        if result.status != "online":
            self.passwords[index] = ""
        return result

    def _reserve(self, identity):
        with self.reserve_lock:
            if identity.machine_id in self.locked_machines:
                return ""  # Shared machine IDs retain one lock for the whole plan.
            try:
                directory = restart_lock_directory()
                directory.mkdir(parents=True, exist_ok=True)
            except (OSError, RuntimeError):
                return "Lokaler Ordner für Neustart-Sperren nicht zugänglich."
            with ExitStack() as lock:
                try:
                    _lock_restart_identity(lock, directory, identity)
                except OSError:
                    return "Lokale Zielsperre nicht verfügbar. Überlappenden Lauf prüfen."
                self.locks.callback(lock.pop_all().close)
            self.locked_machines.add(identity.machine_id)
        return ""

    def _restart(self, index):
        def take_password():
            password, self.passwords[index] = self.passwords[index], ""
            return password

        try:
            original = self.preflights[index].identity
            if index not in self.identity_checks:
                original = RestartIdentity(original.machine_id, original.boot_id)
            return run_prepared_restart(*self.targets[index], take_password, original,
                                        self.plan["reboot_timeout"], self.plan["service_timeout"], self.cancel,
                                        lambda state, detail: self._report(index, state, detail), self.known_boot_ids)
        except Exception as error:
            return self._unexpected(index, "Neustartüberwachung", error)

    def _recheck_identity(self, index):
        session, user, _checks = self.targets[index]
        self._report(index, "preflight", "Maschinen-ID mehrfach vorhanden; prüfe SSH-Zieladresse und Boot-ID erneut")
        try:
            kind, identity = read_restart_identity(session, user, self.cancel)
        except RestartCancelled:
            return RestartResult("not_started", "Identitätsprüfung abgebrochen")
        except Exception as error:
            return self._unexpected(index, "Identitätsprüfung", error)
        if kind != "identity":
            return RestartResult("error", f"SSH-Zielidentität konnte nicht erneut geprüft werden: {identity}")
        if identity != self.preflights[index].identity:
            return RestartResult("error", "SSH-Zieladresse, Maschinen-ID oder Boot-ID hat sich seit der Vorprüfung geändert.")
        self._report(index, "preflight", "Getrenntes SSH-Ziel und eigene Boot-ID bestätigt")
        return RestartResult("online", "Identität erneut bestätigt")

    def _finish_preflight(self):
        errors = {index: result for index, result in self.preflights.items() if result.status != "online"}
        checks = []
        if not self.cancel.is_set():
            machines, seen_boots = {}, {}
            for index, result in sorted(self.preflights.items()):
                if not isinstance(result, RestartPreflight) or result.identity is None:
                    continue
                identity = result.identity
                previous = seen_boots.get(identity.boot_id)
                if previous is not None:
                    message = f"Doppelte Zielidentität: gleiche Boot-ID bei Eintrag {previous + 1} und {index + 1}."
                    self._add_preflight_error(errors, (previous, index), message)
                seen_boots[identity.boot_id] = index
                machines.setdefault(identity.machine_id, []).append(index)
            for group in machines.values():
                if len(group) < 2:
                    continue
                identities = [self.preflights[index].identity for index in group]
                if len({identity.boot_id for identity in identities}) < len(group):
                    continue  # The duplicate boot already blocks the plan.
                addresses = set()
                for identity in identities:
                    if identity.endpoint:
                        address = ip_address(identity.endpoint.split(" ", 1)[0].split("%", 1)[0])
                        addresses.add(getattr(address, "ipv4_mapped", None) or address)
                if len(addresses) != len(group):
                    entries = ", ".join(str(index + 1) for index in group)
                    message = f"Maschinen-ID mehrfach vorhanden; getrennte SSH-Zieladressen fehlen bei Einträgen {entries}."
                    self._add_preflight_error(errors, group, message)
                else:
                    checks.extend(group)
        if checks and not errors and not self.cancel.is_set():
            self.phase = "identity"
            self.identity_check_count = len(checks)
            self.scheduler = RestartScheduler(sorted(checks), self.limit, "continue", self._recheck_identity,
                                              daemon=False, cancel=self.cancel)
            return
        self._finish_checks(errors)

    @staticmethod
    def _add_preflight_error(errors, indexes, message):
        for index in indexes:
            detail = errors[index].detail + "\n" + message if index in errors else message
            errors[index] = RestartResult("error", detail)

    def _finish_checks(self, errors):
        if not errors and not self.cancel.is_set():
            self.phase = "restart"
            self.known_boot_ids = frozenset(result.identity.boot_id for result in self.preflights.values())
            for index in range(len(self.targets)):
                self._report(index, "pending", "Gesamtvorprüfung bestanden; wartet auf Neustart")
            self.scheduler = RestartScheduler(range(len(self.targets)), self.limit, self.error_policy,
                                              self._restart, daemon=False, cancel=self.cancel)
            return
        reason = "Vorprüfung abgebrochen" if self.cancel.is_set() else "Gesamtvorprüfung fehlgeschlagen; kein Neustart gestartet"
        for index in range(len(self.targets)):
            result = self.results[index] = errors.get(index, RestartResult("not_started", reason))
            self._report(index, result.status, result.detail)

    def tick(self):
        if self.done:
            return
        if self.cancel.is_set():
            self.scheduler.decide(False)
        self.scheduler.tick()
        completed = {"preflight": self.preflights, "identity": self.identity_checks, "restart": self.results}[self.phase]
        while True:
            try:
                index, result = self.scheduler.events.get_nowait()
            except queue.Empty:
                break
            completed[index] = result
            if self.phase == "restart" or result.status != "online":
                self.passwords[index] = ""
                self._report(index, result.status, result.detail)
        if self.phase == "preflight" and len(self.preflights) == len(self.targets):
            self._finish_preflight()
        elif self.phase == "identity" and len(self.identity_checks) == self.identity_check_count:
            self._finish_checks({index: result for index, result in self.identity_checks.items() if result.status != "online"})
        if self.done:
            self.passwords.clear()
            self.locks.close()

    @property
    def done(self):
        return len(self.results) == len(self.targets)

    def pause_failures(self):
        with self.scheduler.lock:
            if self.phase == "restart" and self.scheduler.paused and self.scheduler.pending and not self.scheduler.stopped:
                return list(self.scheduler.failures)
        return []

    def decide(self, keep_going):
        self.scheduler.decide(keep_going)

    def continue_after_failures(self, failures):
        with self.scheduler.lock:
            if not self.cancel.is_set() and self.scheduler.paused and self.scheduler.failures == failures:
                self.scheduler.decide(True)
