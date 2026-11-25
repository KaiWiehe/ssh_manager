"""Console entry point copied into the standalone restart script."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from getpass import GetPassWarning, getpass
import shutil
import signal
import sys
import threading
import time
import warnings

from .mass_restart import MassRestartRun, duplicate_restart_targets, validate_sudo_password
from .restart_terminal import restart_live_terminal, restart_terminal_view
from .restart_runtime import (MODE_LABELS, RestartResult, execution_policy, service_check,
                              validate_execution_options)
from .ssh_utils import connection_value, valid_port


def main(plan, raw_targets):
    parser = argparse.ArgumentParser(description="Massen-Neustart über OpenSSH", allow_abbrev=False)
    parser.add_argument("--execute", action="store_true", help="Neustarts tatsächlich ausführen")
    parser.add_argument("--sudo", choices=("common", "per-connection", "none"),
                        help="sudo-Abfragemodus für diesen Lauf wählen")
    parser.add_argument("--confirm-all", action="store_true", help="Alle parallelen Starts ausdrücklich bestätigen")
    parser.add_argument("--log", action="store_true", help="Ausführliches Textprotokoll ausgeben")
    args = parser.parse_args()
    try:
        targets = validate_plan(plan, raw_targets)
    except ValueError as error:
        parser.error(str(error))
    if args.sudo:
        plan = {**plan, "password_per_connection": args.sudo == "per-connection",
                "sudo_password_required": args.sudo == "common"}
        if args.sudo == "per-connection":
            for target in targets:
                target.sudo_password_required = True
    limit, on_error = execution_policy({**plan, "targets": targets})
    live = args.execute and not args.log and restart_live_terminal()
    show_plan(plan, targets, limit, on_error)
    if not args.execute:
        print("\nVorschau. Zum Ausführen --execute angeben.")
        return 0
    if shutil.which("ssh") is None:
        parser.error("OpenSSH (ssh) wurde im PATH nicht gefunden.")
    if (on_error == "pause" or any(password_required(plan, target) for target in targets)) and not sys.stdin.isatty():
        parser.error("sudo-Passwortabfrage oder Fehlerpause benötigt ein interaktives Terminal.")
    try:
        if plan["mode"] == "all_parallel" and not args.confirm_all:
            if not sys.stdin.isatty():
                parser.error("Für alle parallelen Starts --confirm-all angeben.")
            answer = input(f"Alle {len(targets)} Server parallel neu starten? Zielanzahl eingeben: ").strip()
            if answer != str(len(targets)):
                print("Abgebrochen. Kein Neustart gestartet.")
                return 1
        passwords = read_passwords(plan, targets)
    except (EOFError, GetPassWarning):
        parser.error("Erforderliche Terminaleingabe abgebrochen. Kein Neustart gestartet.")
    except ValueError as error:
        parser.error(str(error))
    except KeyboardInterrupt:
        print("\nAbgebrochen. Kein Neustart gestartet.")
        return 130

    with restart_terminal_view(plan, targets, enabled=live) as display:
        if display:
            results, interrupted = run_targets(plan, targets, passwords, display=display)
            display.show_result(results)
        else:
            results, interrupted = run_targets(plan, targets, passwords)
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
    duplicate_restart_targets([(target, target.user, target.checks) for target in validated])
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
    for password in passwords:
        validate_sudo_password(password)
    return passwords


def continue_after_failure(failures, targets):
    for index, result in failures:
        print(f"{target_text(targets[index])}: {console_text(result.detail)}")
    try:
        return input("Weitere Neustarts fortsetzen? Laufende Server werden weiter überwacht. [j/N] ").strip().lower() == "j"
    except EOFError:
        return False


def run_targets(plan, targets, passwords, *, display=None):
    """Display worker events and make admission decisions in one console thread."""
    cancel = threading.Event()
    run = MassRestartRun(plan, [(target, target.user, target.checks) for target in targets], passwords, cancel)
    interrupted = False
    asking = False
    announced = False

    def stop_run(_signum, _frame):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            cancel.set()
        if asking:
            raise KeyboardInterrupt

    # Keep Ctrl+C from interrupting scheduler bookkeeping during thread startup.
    previous_handler = signal.signal(signal.SIGINT, stop_run)
    try:
        while True:
            if interrupted and not announced and not display:
                print("\nAbbruch angefordert. Warte auf das Ende der lokalen SSH-Aufrufe.", flush=True)
                announced = True
            run.tick()
            while not run.events.empty():
                timestamp, index, state, detail = run.events.get_nowait()
                if display:
                    display.update(timestamp, index, state, detail)
                else:
                    print_restart_event(timestamp, targets[index], detail)
            if run.done:
                return run.results, interrupted
            failures = run.pause_failures()
            if display:
                visible_failures = failures if not interrupted else ()
                display.draw(failures=visible_failures, interrupted=interrupted)
                try:
                    decision = display.read_decision(failures=visible_failures)
                except KeyboardInterrupt:
                    stop_run(None, None)
                else:
                    if visible_failures and not interrupted:
                        if decision:
                            run.continue_after_failures(visible_failures)
                        elif decision is False:
                            run.decide(False)
            elif failures and not interrupted:
                try:
                    asking = True
                    if not interrupted:
                        run.decide(continue_after_failure(failures, targets))
                except KeyboardInterrupt:
                    asking = False
                    stop_run(None, None)
                finally:
                    asking = False
            time.sleep(.08)
    finally:
        try:
            if not run.done:
                cancel.set()
                while not run.done:
                    run.tick()
                    time.sleep(.08)
        finally:
            signal.signal(signal.SIGINT, previous_handler)


def print_restart_event(timestamp, target, detail):
    label = console_text(target.label).replace("\n", " ")
    for line in console_text(detail).splitlines():
        print(f"{timestamp:%H:%M:%S} [{label}] {line}", flush=True)


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
