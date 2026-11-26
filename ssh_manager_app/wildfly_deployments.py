"""Read-only Standalone WildFly deployment checks shared with exported scripts."""
from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address
import json
import posixpath
import shlex


WILDFLY_LOCAL_ADDRESS_ERROR = 80
WILDFLY_CLI_ERROR = 81
WILDFLY_SCANNER_ERROR = 82
WILDFLY_CGROUP_ERROR = 83
WILDFLY_READ_STEPS = (
    '{operation=read-attribute,address=[{core-service=server-environment}],name=base-dir}',
    '{operation=read-children-resources,address=[],child-type=deployment,include-runtime=true}',
    '{operation=read-children-names,address=[],child-type=subsystem}',
    '{operation=read-attribute,address=[{core-service=platform-mbean},{type=runtime}],name=name}',
)
WILDFLY_SCANNER_STEP = ('{operation=read-children-resources,address=[{subsystem=deployment-scanner}],'
                        'child-type=scanner,resolve-expressions=true}')
WILDFLY_MARKER_STATES = {".failed": "FAILED", ".pending": "wartet", ".dodeploy": "wartet",
                         ".isdeploying": "wird deployt", ".isundeploying": "wird entfernt"}


def _wildfly_text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 1024 or not value.isprintable():
        raise ValueError(f"WildFly: {label} fehlt oder ist ungültig.")
    return value.strip()


def _wildfly_path(value, label):
    path = _wildfly_text(value, label)
    if not path.startswith("/") or path.startswith("//") or ".." in path.split("/"):
        raise ValueError(f"WildFly: {label} als absoluten Linux-Pfad angeben.")
    normalized = posixpath.normpath(path)
    if normalized == "/":
        raise ValueError(f"WildFly: Für {label} einen konkreten Pfad angeben.")
    return normalized


def _wildfly_list(values, label, normalize):
    if not isinstance(values, list) or len(values) > 500:
        raise ValueError(f"WildFly: für {label} eine Liste mit bis zu 500 Einträgen angeben.")
    return list(dict.fromkeys(normalize(value, label) for value in values))


def _wildfly_deployment_name(value, label):
    name = _wildfly_text(value, label)
    if "/" in name or name in (".", ".."):
        raise ValueError(f"WildFly: für {label} Deployment-Namen ohne Verzeichnispfad angeben.")
    return name


def validate_wildfly_settings(settings):
    if not isinstance(settings, dict) or settings.keys() - {
        "cli_path", "base_dir", "address", "port", "https", "expected", "scanner_dirs",
    }:
        raise ValueError("WildFly: ungültige Einstellungen für die Deployment-Prüfung.")
    cli = _wildfly_path(settings.get("cli_path"), "CLI-Pfad")
    if posixpath.basename(cli) != "jboss-cli.sh":
        raise ValueError("WildFly: den vollständigen Pfad zu jboss-cli.sh angeben.")
    base = _wildfly_path(settings.get("base_dir"), "Basisverzeichnis")
    address = _wildfly_text(settings.get("address", "127.0.0.1"), "Management-IP")
    try:
        ip = ip_address(address)
    except ValueError:
        raise ValueError("WildFly: lokale IPv4- oder IPv6-Adresse des SSH-Ziels angeben.") from None
    if ip.is_unspecified or ip.is_multicast or "%" in address:
        raise ValueError("WildFly: konkrete lokale Management-IP ohne Schnittstellenzusatz angeben.")
    port, https = settings.get("port", 9990), settings.get("https", False)
    if type(port) is not int or not 1 <= port <= 65535 or type(https) is not bool:
        raise ValueError("WildFly: Management-Port 1 bis 65535 und gültiges HTTPS-Flag erforderlich.")
    expected = _wildfly_list(settings.get("expected", []), "Soll-Deployments", _wildfly_deployment_name)
    scanner = _wildfly_list(settings.get("scanner_dirs", []), "Scanner-Verzeichnisse", _wildfly_path)
    if scanner and not expected:
        raise ValueError("WildFly: Bei Scanner-Verzeichnissen sind Soll-Deployments erforderlich.")
    return {"cli_path": cli, "base_dir": base, "address": str(ip), "port": port,
            "https": https, "expected": expected, "scanner_dirs": scanner}


def wildfly_controller(settings):
    address = settings["address"]
    host = f"[{address}]" if ":" in address else address
    return f"remote+{'https' if settings['https'] else 'http'}://{host}:{settings['port']}"


def wildfly_plan_text(settings):
    expected = ", ".join(settings["expected"]) or "vor dem Neustart ermitteln"
    scanner = ", ".join(settings["scanner_dirs"])
    return (f"WildFly-Deployments · {wildfly_controller(settings)} · {settings['base_dir']}\n"
            f"CLI {settings['cli_path']} · Soll-Deployments {expected}"
            + (f"\nScanner-Verzeichnisse {scanner}" if scanner else ""))


def wildfly_probe_command(settings, token, unit, *, inspect_scanners=False):
    ip = ip_address(settings["address"])
    cli = settings["cli_path"]
    command = []
    if not ip.is_loopback:
        prefix = shlex.quote(f"{ip}/{ip.max_prefixlen}")
        command.append(f"ip -o address show to {prefix} | grep -q . || exit {WILDFLY_LOCAL_ADDRESS_ERROR}")
    command.append(f"test -f {shlex.quote(cli)} && test -x {shlex.quote(cli)} || exit {WILDFLY_CLI_ERROR}")
    command.append(f"printf '%s\\n' {shlex.quote(token)}")
    steps = WILDFLY_READ_STEPS + ((WILDFLY_SCANNER_STEP,) if inspect_scanners else ())
    operation = ":composite(steps=[" + ",".join(steps) + "])"
    command.append(shlex.join([cli, "--connect", f"--controller={wildfly_controller(settings)}", "--output-json",
                              "--no-color-output", "--command-timeout=5", f"--command={operation}"])
                   + " </dev/null || exit 1")
    command.append(f"printf '\\n%s\\n' {shlex.quote(token)}")
    command.append(
        f'group=$(systemctl show --property=ControlGroup --value -- {shlex.quote(unit)}) || exit {WILDFLY_CGROUP_ERROR}; '
        f'case "$group" in /|*/../*|*/..) exit {WILDFLY_CGROUP_ERROR};; /*) ;; *) exit {WILDFLY_CGROUP_ERROR};; esac; '
        'cg=; for mount in /sys/fs/cgroup /sys/fs/cgroup/systemd; do '
        'if test -r "$mount$group/cgroup.procs"; then cg="$mount$group"; break; fi; done; '
        f'test -n "$cg" || exit {WILDFLY_CGROUP_ERROR}; '
        f'pids=$(find "$cg" -name cgroup.procs -exec cat {{}} +) || exit {WILDFLY_CGROUP_ERROR}; '
        f'host=$(uname -n) || exit {WILDFLY_CGROUP_ERROR}; '
        'printf \'%s\\0\' "$host" "$pids"'
    )
    if settings["scanner_dirs"]:
        directories = shlex.join(settings["scanner_dirs"])
        markers = " ".join(f'"$directory"/*{suffix}' for suffix in WILDFLY_MARKER_STATES)
        command.append(
            f'for directory in {directories}; do '
            f'test -d "$directory" && test -r "$directory" && test -x "$directory" || exit {WILDFLY_SCANNER_ERROR}; '
            f'for marker in {markers}; do '
            'if test -f "$marker"; then printf \'%s\\0\' "${marker##*/}"; fi; done; done'
        )
    return "; ".join(command)


@dataclass(frozen=True)
class WildFlySnapshot:
    deployments: dict
    markers: tuple


class WildFlyScannerInspectionRequired(ValueError):
    pass


def _wildfly_management_result(response):
    if not isinstance(response, dict) or response.get("outcome") != "success" or "result" not in response:
        raise ValueError("WildFly-Management hat die lesende Abfrage abgelehnt oder unvollständig beantwortet.")
    headers = response.get("response-headers", {})
    if not isinstance(headers, dict) or headers.get("access-control"):
        raise ValueError("WildFly-Management hat Daten gefiltert. Leserechte prüfen.")
    return response["result"]


def _check_wildfly_scanner_dirs(response, settings):
    scanners = _wildfly_management_result(response)
    if not isinstance(scanners, dict):
        raise ValueError("WildFly lieferte keine lesbare Scanner-Konfiguration.")
    directories = set()
    for scanner in scanners.values():
        if not isinstance(scanner, dict) or type(scanner.get("scan-enabled")) is not bool:
            raise ValueError("WildFly meldet einen unbekannten Scanner-Status.")
        if not scanner["scan-enabled"]:
            continue
        path, relative_to = scanner.get("path"), scanner.get("relative-to")
        if not isinstance(path, str) or not path or relative_to not in (None, "undefined", "jboss.server.base.dir"):
            raise ValueError("WildFly-Scanner-Pfad konnte nicht eindeutig aufgelöst werden.")
        if relative_to == "jboss.server.base.dir":
            path = posixpath.join(settings["base_dir"], path)
        directories.add(_wildfly_path(path, "Scanner-Pfad"))
    if set(settings["scanner_dirs"]) != directories:
        if directories and not settings["scanner_dirs"]:
            raise ValueError("WildFly hat aktive Scanner. Die aktiven Scanner-Verzeichnisse und Soll-Deployments angeben.")
        raise ValueError("Die bestätigten Scanner-Verzeichnisse stimmen nicht mit den aktiven WildFly-Scannern überein.")


def parse_wildfly_snapshot(stdout, token, settings, *, inspect_scanners=False):
    prefix, marker, payload = stdout.partition(token + "\n")
    if not marker or (prefix and not prefix.endswith("\n")):
        raise ValueError("WildFly-Abfrage ohne eindeutige Ergebnisgrenze.")
    body, separator, raw_markers = payload.partition("\n" + token + "\n")
    if not separator or (raw_markers and not raw_markers.endswith("\0")):
        raise ValueError("WildFly-Abfrage ohne vollständiges Ergebnis.")
    try:
        response = json.loads(body)
    except ValueError:
        raise ValueError("WildFly-Management lieferte kein gültiges JSON.") from None
    steps = _wildfly_management_result(response)
    if not isinstance(steps, dict):
        raise ValueError("Unvollständige WildFly-Management-Antwort.")
    base = _wildfly_management_result(steps.get("step-1"))
    if not isinstance(base, str) or posixpath.normpath(base) != settings["base_dir"]:
        raise ValueError("WildFly-Instanz stimmt nicht mit dem Basisverzeichnis der Unit überein.")
    deployments = _wildfly_management_result(steps.get("step-2"))
    if not isinstance(deployments, dict):
        raise ValueError("WildFly-Management lieferte keine gültige Deployment-Liste.")
    subsystems = _wildfly_management_result(steps.get("step-3"))
    if not isinstance(subsystems, list) or not all(isinstance(name, str) for name in subsystems):
        raise ValueError("WildFly lieferte keine lesbare Liste der Subsysteme.")
    runtime = _wildfly_management_result(steps.get("step-4"))
    records = raw_markers.split("\0")[:-1]
    if len(records) < 2 or not isinstance(runtime, str):
        raise ValueError("WildFly-JVM oder lokale Prozessgruppe konnten nicht eindeutig identifiziert werden.")
    hostname, pids, *marker_names = records
    pid, at, jvm_host = runtime.partition("@")
    if (not at or not pid.isascii() or not pid.isdecimal() or not hostname
            or jvm_host.rstrip(".").casefold() != hostname.rstrip(".").casefold() or pid not in pids.splitlines()):
        raise ValueError("WildFly-JVM gehört nicht nachweisbar zur lokalen systemd-Unit. Management-IP und Port prüfen.")
    if "deployment-scanner" in subsystems:
        if not inspect_scanners:
            raise WildFlyScannerInspectionRequired
        _check_wildfly_scanner_dirs(steps.get("step-5"), settings)
    elif settings["scanner_dirs"]:
        raise ValueError("WildFly meldet kein Deployment-Scanner-Subsystem für die angegebenen Verzeichnisse.")
    observed = {}
    for name, deployment in deployments.items():
        if not isinstance(deployment, dict) or type(deployment.get("enabled")) is not bool:
            raise ValueError("WildFly-Management lieferte unvollständige Deployment-Daten.")
        if deployment.get("persistent") is False and not settings["scanner_dirs"]:
            raise ValueError("WildFly meldet Scanner-Deployments. Scanner-Verzeichnisse und Soll-Deployments angeben.")
        state = deployment.get("status")
        if not deployment["enabled"] and state == "OK":
            raise ValueError("WildFly meldete widersprüchliche Daten für ein deaktiviertes Deployment.")
        observed[name] = (deployment["enabled"], state if state in ("OK", "FAILED", "STOPPED") else "unbekannt")
    markers = []
    for filename in marker_names:
        name, suffix = posixpath.splitext(filename)
        if not name or suffix not in WILDFLY_MARKER_STATES or not settings["scanner_dirs"]:
            raise ValueError("WildFly-Scanner lieferte einen ungültigen Status.")
        markers.append((name, WILDFLY_MARKER_STATES[suffix]))
    return WildFlySnapshot(observed, tuple(markers))


def wildfly_expected_deployments(settings, snapshot):
    enabled = {name for name, (active, state) in snapshot.deployments.items() if active or state == "FAILED"}
    if not snapshot.deployments and not snapshot.markers:
        raise ValueError("WildFly meldet keine Deployments. Soll-Liste, Instanz und Leserechte prüfen.")
    markers = {name for name, _ in snapshot.markers}
    missing = set(settings["expected"]) - set(snapshot.deployments) - markers
    if missing:
        raise ValueError("WildFly-Soll-Deployments weder im Management-Modell noch als Scanner-Status sichtbar: "
                         + ", ".join(sorted(missing)))
    if any(active and state == "unbekannt" for active, state in snapshot.deployments.values()):
        raise ValueError("WildFly lieferte für aktivierte Deployments keinen verlässlichen Laufzeitstatus.")
    expected = set(settings["expected"]) | enabled | markers
    if not expected:
        raise ValueError("WildFly meldet keine erwarteten oder aktivierten Deployments.")
    return frozenset(expected)


def wildfly_deployment_result(snapshot, expected, *, show_ok=False):
    deployments = snapshot.deployments
    names = set(expected) | {name for name, (enabled, state) in deployments.items() if enabled or state == "FAILED"}
    marker_states = {}
    for name, state in snapshot.markers:
        marker_states.setdefault(name, set()).add(state)
    names.update(marker_states)
    okay, failed, details = 0, False, []

    def display_name(name):
        return "".join(char if char.isprintable() else "?" for char in name)

    for name in sorted(names, key=lambda item: (item.casefold(), item)):
        enabled, state = deployments.get(name, (False, "fehlt"))
        markers = marker_states.get(name, set())
        if enabled and state == "OK" and not markers:
            okay += 1
            if show_ok:
                details.append(f"{display_name(name)} · OK")
            continue
        failed |= state == "FAILED" or "FAILED" in markers
        if not enabled and state == "OK":
            state = "deaktiviert"
        suffix = " · Scanner " + ", ".join(sorted(markers)) if markers else ""
        details.append(f"{display_name(name)} · {state}{suffix}")
    disabled = sorted(set(deployments) - names, key=lambda item: (item.casefold(), item))
    if disabled:
        details.append("Deaktiviert: " + ", ".join(display_name(name) for name in disabled))
    if not names:
        details.append("Keine erwarteten Deployments gefunden.")
    return bool(names) and okay == len(names), failed, "\n".join([f"{okay} von {len(names)} Deployments OK", *details])
