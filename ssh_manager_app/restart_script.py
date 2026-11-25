"""Console entry point copied into the standalone restart script."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from getpass import GetPassWarning, getpass
import queue
import shutil
import sys
import threading
import warnings

from .restart_runtime import (MODE_LABELS, RestartResult, RestartScheduler, execution_policy,
                              monitor_template_restart, service_check, validate_execution_options)
from .ssh_utils import connection_value, valid_port


def main(plan, raw_targets):
    parser = argparse.ArgumentParser(description="Massen-Neustart über OpenSSH", allow_abbrev=False)
    parser.add_argument("--execute", action="store_true", help="Neustarts tatsächlich ausführen")
    args = parser.parse_args()
    try:
        targets = validate_plan(plan, raw_targets)
    except ValueError as error:
        parser.error(str(error))
    limit, on_error = execution_policy({**plan, "targets": targets})
    show_plan(plan, targets, limit, on_error)
    if not args.execute:
        print("\nVorschau. Zum Ausführen --execute angeben.")
        return 0
    if shutil.which("ssh") is None:
        parser.error("OpenSSH (ssh) wurde im PATH nicht gefunden.")
    if (on_error == "pause" or any(password_required(plan, target) for target in targets)) and not sys.stdin.isatty():
        parser.error("sudo-Passwortabfrage oder Fehlerpause benötigt ein interaktives Terminal.")
    try:
        passwords = read_passwords(plan, targets)
    except (EOFError, GetPassWarning):
        parser.error("Verdeckte sudo-Eingabe nicht verfügbar. Kein Neustart gestartet.")
    except ValueError as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print("\nAbgebrochen. Kein Neustart gestartet.")
        return 130

    results, interrupted = run_targets(plan, targets, passwords, limit, on_error)
    show_results(targets, results)
    if interrupted:
        return 130
    return 0 if all(result.status == "online" for result in results.values()) else 1


@dataclass
class RestartTarget:
    label: str
    user: str
    hostname: str
    port: int
    alias: str
    checks: list[dict]
    sudo_password_required: bool

    @property
    def display_name(self):
        return self.alias or self.label

    @property
    def is_ssh_config_session(self):
        return bool(self.alias)

    @property
    def ssh_user_override(self):
        return self.user if self.alias else ""


def validate_plan(plan, targets):
    """Check all edited settings locally before prompting or invoking SSH."""
    if not isinstance(plan, dict) or not isinstance(plan.get("name"), str) or not plan["name"].strip():
        raise ValueError("Einen Namen für den Neustartplan angeben.")
    validate_execution_options(plan)
    for field in ("password_per_connection", "sudo_password_required"):
        if type(plan.get(field)) is not bool:
            raise ValueError(f"{field} muss True oder False sein.")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 1000:
        raise ValueError("1 bis 1000 Server angeben.")

    validated = []
    for index, target in enumerate(targets, 1):
        if not isinstance(target, dict) or ("host" in target) == ("alias" in target):
            raise ValueError(f"Ziel {index}: genau einen Host oder SSH-Alias angeben.")
        user = connection_value(target.get("user"), f"Benutzer in Ziel {index}")
        if "alias" in target:
            alias = connection_value(target["alias"], f"SSH-Alias in Ziel {index}")
            if "port" in target:
                raise ValueError(f"Ziel {index}: der Port eines SSH-Alias kommt aus der SSH-Konfiguration.")
            host, port = "", 22
        else:
            alias = ""
            host = connection_value(target["host"], f"Hostname in Ziel {index}")
            port = valid_port(target.get("port", 22))
        label = target.get("label", alias or host)
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"Ziel {index}: einen Anzeigenamen angeben.")
        services = target.get("services", {})
        if not isinstance(services, dict) or len(services) > 100:
            raise ValueError(f"Ziel {index}: bis zu 100 Dienste mit Sollzustand angeben.")
        checks = [service_check(unit, expected) for unit, expected in services.items() if isinstance(unit, str)]
        if len(checks) != len(services) or len({check["unit"] for check in checks}) != len(checks):
            raise ValueError(f"Ziel {index}: Dienstnamen müssen gültig und eindeutig sein.")
        needs_password = target.get("sudo_password_required", False)
        if type(needs_password) is not bool:
            raise ValueError(f"Ziel {index}: sudo_password_required muss True oder False sein.")
        validated.append(RestartTarget(label, user, host, port, alias, checks, needs_password))
    return validated


def console_text(value):
    return "".join(char if char.isprintable() or char == "\n" else "?" for char in value)


def target_text(target):
    endpoint = f"Alias {target.alias}" if target.alias else f"Host {target.hostname} · Port {target.port}"
    return console_text(f"{target.label} ({endpoint} · Benutzer {target.user})")


def password_required(plan, target):
    return target.sudo_password_required if plan["password_per_connection"] else plan["sudo_password_required"]


def show_plan(plan, targets, limit, on_error):
    print(f"Massen-Neustart · {console_text(plan['name'])}")
    mode = MODE_LABELS[plan["mode"]]
    if plan["mode"] == "parallel":
        mode += f" (max. {limit} gleichzeitig)"
    policy = {"continue": "weiterlaufen", "stop": "weitere Neustarts stoppen", "pause": "pausieren und nachfragen"}
    print(f"Ablauf: {mode} · Bei Fehlern: {policy[on_error]}")
    print(f"Neustart/SSH: {plan['reboot_timeout']} s · danach Services: {plan['service_timeout']} s")
    for number, target in enumerate(targets, 1):
        sudo = "Passwortabfrage" if password_required(plan, target) else "ohne Passwort"
        print(f"{number:>3}. {target_text(target)} · sudo {sudo}")
        for check in target.checks:
            print(f"     {check['unit']}: {check['expected']}")


def read_passwords(plan, targets):
    """Collect every required sudo password before the first restart."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        if plan["password_per_connection"]:
            passwords = [getpass(f"sudo-Passwort für {target_text(target)}: ") if target.sudo_password_required else ""
                         for target in targets]
        elif plan["sudo_password_required"]:
            passwords = [getpass("Gemeinsames sudo-Passwort: ")] * len(targets)
        else:
            return [""] * len(targets)
    if any(password_required(plan, target) and not password for target, password in zip(targets, passwords)):
        raise ValueError("Ein benötigtes sudo-Passwort fehlt. Kein Neustart gestartet.")
    return passwords


def continue_after_failure(failures, targets):
    for index, result in failures:
        print(f"{target_text(targets[index])}: {console_text(result.detail)}")
    try:
        return input("Weitere Neustarts fortsetzen? Laufende Server werden weiter überwacht. [j/N] ").strip().lower() == "j"
    except EOFError:
        return False


def run_targets(plan, targets, passwords, limit, on_error):
    """Admit new work centrally; running targets monitor themselves during a pause."""
    cancel = threading.Event()

    def restart(index):
        target = targets[index]
        return monitor_template_restart(
            target, target.user, passwords[index], target.checks,
            plan["reboot_timeout"], plan["service_timeout"], cancel, lambda _state, _detail: None,
        )

    scheduler = RestartScheduler(range(len(targets)), limit, on_error, restart)
    results = {}
    interrupted = False
    try:
        while len(results) < len(targets):
            scheduler.tick()
            with scheduler.lock:
                failures = list(scheduler.failures) if scheduler.paused and scheduler.pending else []
            if failures:
                scheduler.decide(continue_after_failure(failures, targets))
            try:
                index, result = scheduler.events.get(timeout=.1)
            except queue.Empty:
                continue
            results[index] = result
    except KeyboardInterrupt:
        cancel.set()
        interrupted = True
        with scheduler.lock:
            scheduler.decide(False)
            while not scheduler.events.empty():
                index, result = scheduler.events.get_nowait()
                results[index] = result
            for index in scheduler.pending:
                results[index] = RestartResult("not_started", "Neustart wurde nicht ausgelöst")
        print("Lauf abgebrochen. Bereits ausgelöste Neustarts laufen auf den Servern weiter.")
    return results, interrupted


def show_results(targets, results):
    labels = {"online": "Erfolgreich", "error": "Fehler", "timeout": "Zeitüberschreitung",
              "not_started": "Nicht gestartet", "stopped": "Überwachung beendet"}
    print("\nErgebnisse")
    for index, target in enumerate(targets):
        result = results.get(index, RestartResult("stopped", "Neustartzustand unbekannt"))
        print(f"{target_text(target)} · {labels[result.status]}")
        print("  " + console_text(result.detail).replace("\n", "\n  "))
        if not result.includes_service_states:
            for check in target.checks:
                print(f"  {check['unit']}: Soll {check['expected']}, Ist nicht geprüft")
