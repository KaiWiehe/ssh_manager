"""Render an editable restart plan and the same runtime the app uses."""
from __future__ import annotations

import ast
from pathlib import Path
from pprint import pformat
import sys
from textwrap import indent

from .restart_script import validate_plan


def _source(filename):
    directory = Path(sys._MEIPASS) / "restart_export_sources" if getattr(sys, "frozen", False) else Path(__file__).parent
    source = (directory / filename).read_text(encoding="utf-8")
    return source, ast.parse(source, filename).body


def _helpers(filename, *names):
    source, statements = _source(filename)
    definitions = {}
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.ClassDef)):
            definitions[statement.name] = statement
        elif isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name):
            definitions[statement.targets[0].id] = statement
    lines = source.splitlines()
    parts = []
    for name in names:
        node = definitions[name]
        decorators = getattr(node, "decorator_list", ())
        start = decorators[0].lineno if decorators else node.lineno
        parts.append("\n".join(lines[start - 1:node.end_lineno]))
    return "\n\n\n".join(parts)


def _standalone_module(filename):
    source, statements = _source(filename)
    imports = [node for node in statements if isinstance(node, (ast.Import, ast.ImportFrom))]
    # Relative imports resolve to definitions copied into the same output file.
    standard_imports = [ast.get_source_segment(source, node) for node in imports
                        if isinstance(node, ast.Import) or (not node.level and node.module != "__future__")]
    return standard_imports, "\n".join(source.splitlines()[imports[-1].end_lineno:]).strip()


def _mapping_literal(mapping):
    fields = [indent(f"{key!r}: {pformat(value, width=80, sort_dicts=False)},", "    ")
              for key, value in mapping.items()]
    return "{\n" + "\n".join(fields) + "\n}"


def render_restart_script(template, resolved, *, common_password_required, target_passwords_required):
    plan = {key: template[key] for key in ("name", "mode", "max_parallel", "on_error", "reboot_timeout",
                                            "service_timeout", "password_per_connection")}
    plan["sudo_password_required"] = common_password_required
    targets = []
    for (session, user, checks), required in zip(resolved, target_passwords_required, strict=True):
        target = {"label": session.display_name, "user": user}
        if session.is_ssh_config_session:
            target["alias"] = session.display_name
        else:
            target.update(host=session.hostname, port=session.port)
        target["services"] = {
            check["unit"]: {"expected": check["expected"], "wildfly": check["wildfly"]}
            if "wildfly" in check else check["expected"] for check in checks
        }
        if plan["password_per_connection"]:
            target["sudo_password_required"] = required
        targets.append(target)
    validate_plan(plan, targets)

    runtime_imports, _ = _standalone_module("restart_runtime.py")
    runtime = _helpers("restart_runtime.py", "UNIT", "MODE_LABELS", "validate_execution_options", "execution_policy",
                       "service_check", "configured_service_check", "MASS_RESTART_SSH_OPTIONS", "SshTarget", "RestartResult", "_ssh_args",
                       "service_probe_result", "RestartScheduler")
    console_imports, console = _standalone_module("restart_script.py")
    terminal_imports, terminal = _standalone_module("restart_terminal.py")
    mass_imports, mass_runtime = _standalone_module("mass_restart.py")
    wildfly_imports, wildfly_runtime = _standalone_module("wildfly_deployments.py")
    windows_imports, windows_jobs = _standalone_module("restart_winjob.py")
    imports = "\n".join(sorted(set(runtime_imports + console_imports + terminal_imports + mass_imports
                                   + windows_imports + wildfly_imports)))
    identifiers = _helpers("ssh_utils.py", "connection_value", "valid_port")
    authentication = _helpers("ssh_failures.py", "SSH_AUTHENTICATION_HELP", "ssh_authentication_failed")
    target_lines = "\n".join(indent(_mapping_literal(target), "    ") + "," for target in targets)
    settings = _mapping_literal(plan)
    script = f'''#!/usr/bin/env python3
# Massen-Neustart aus SSH Manager. Benötigt Python 3 und OpenSSH (ssh).
# python massen-neustart.py             # lokale Vorschau
# python massen-neustart.py --execute   # Neustarts auslösen
# python massen-neustart.py --execute --sudo common   # Ein Passwort für alle
# python massen-neustart.py --execute --log           # Ausführliches Textprotokoll
# Alias-Ziele verwenden die SSH-Konfiguration des ausführenden Rechners.
# Hostschlüssel müssen vor dem Lauf vertrauenswürdig hinterlegt sein.
# sudo_password_required steuert die verdeckte Abfrage beim Ausführen.
from __future__ import annotations


# Ablauf und Ziele
# mode: serial, parallel, all_parallel
# on_error: continue, stop, pause (bei all_parallel gilt continue)
PLAN = {settings}

TARGETS = [
{target_lines}
]


# Konsolenbedienung
{imports}


{console}


# Live-Ansicht im Terminal
{terminal}


# SSH, Neustartnachweis, Dienstprüfungen und parallele Starts
{identifiers}


{authentication}


{runtime}


# Lesende WildFly-Prüfung
{wildfly_runtime}


{mass_runtime}


# Prozessverwaltung für Windows
{windows_jobs}


if __name__ == "__main__":
    raise SystemExit(main(PLAN, TARGETS))
'''
    compile(script, "massen-neustart.py", "exec")
    return script
