"""Remote TCP probes. A negative connect is never proof of a firewall rule."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import ipaddress
import json
import queue
import re
import shlex
import subprocess
import threading
import time

from .ssh_utils import read_port, ssh_argv

STATUS = {"planned": "Noch nicht geprüft", "pending": "Ausstehend", "running": "Prüft", "open": "Erreichbar",
          "refused": "Abgelehnt", "timeout": "Timeout", "network": "Netzwerkfehler",
          "dns": "DNS fehlgeschlagen", "ssh": "Nicht geprüft (SSH)",
          "tool": "Nicht geprüft (Werkzeug)", "error": "Nicht geprüft (Prüffehler)",
          "cancelled": "Abgebrochen"}
NEGATIVE = frozenset(("refused", "timeout", "network", "dns"))
STATE_KEY = "port_check_templates"
MARKER = "SSH_MANAGER_TCP_V1\t"


def target(host, port):
    if not isinstance(host, str):
        raise ValueError("Ziel-IP oder Hostname eingeben.")
    host = host.strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        host = str(ipaddress.ip_address(host))
        if "%" in host:
            raise ValueError("IPv6 ohne lokale Interface-Zonenkennung eingeben.")
    except ValueError:
        try:
            host = host.encode("idna").decode("ascii").lower()
        except UnicodeError as error:
            raise ValueError("Ungültiger Zielhostname.") from error
        if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                     for label in host.rstrip(".").split(".")):
            raise ValueError("Gültige IPv4/IPv6-Adresse oder Hostname ohne Leerzeichen eingeben.")
        if re.fullmatch(r"[0-9.]+", host):
            raise ValueError("Ungültige IP-Adresse.")
    return (host, read_port(port))


def targets(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 100:
        raise ValueError("Eine bis 100 Zielzeilen angeben.")
    result = []
    for item in values:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError("Ziel-IP/Hostname und TCP-Port erforderlich.")
        value = target(*item)
        if value not in result:
            result.append(value)
    return result


def validate_library(value):
    if not isinstance(value, dict) or value.get("schema") != 1 or not isinstance(value.get("items"), list):
        raise ValueError("Ungültige Portprüfvorlagen.")
    if len(value["items"]) > 100:
        raise ValueError("Maximal 100 Portprüfvorlagen speichern.")
    items, seen = [], set()
    for item in value["items"]:
        if not isinstance(item, dict):
            raise ValueError("Ungültige Portprüfvorlage.")
        name = item.get("name", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
            raise ValueError("Vorlagenname: 1 bis 100 Zeichen ohne Steuerzeichen.")
        name = name.strip()
        if name.casefold() in seen:
            raise ValueError("Doppelter Vorlagenname.")
        seen.add(name.casefold())
        items.append({"name": name, "targets": [list(t) for t in targets(item.get("targets"))]})
    return {"schema": 1, "items": items}


def resolve_destination(session):
    """Resolve SSH configuration, never DNS or proxies on behalf of the sources."""
    if not session.is_ssh_config_session:
        return target(session.hostname, 1)[0]
    result = subprocess.run(ssh_argv(session, options=["-G"]), capture_output=True,
                            text=True, timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    fields = dict(line.split(None, 1) for line in result.stdout.splitlines() if len(line.split(None, 1)) == 2)
    if result.returncode or not fields.get("hostname"):
        raise ValueError("SSH-Alias nicht auswertbar. Ziel-IP/Hostname manuell eingeben.")
    return target(fields["hostname"], 1)[0]


@dataclass(frozen=True)
class ProbeResult:
    status: str
    detail: str
    addresses: str = ""
    checked_at: str = ""


# Executed in memory on the source. No remote files or installs. Python provides
# errno-based results, remote DNS and a deadline encompassing DNS and connects.
REMOTE_PYTHON = r'''
import errno, ipaddress, json, signal, socket, sys, time
host, port, seconds = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
def emit(status, detail, addresses=""):
    print("SSH_MANAGER_TCP_V1\t" + json.dumps({"status":status,"detail":detail,"addresses":addresses}), flush=True)
def alarm(*_):
    emit("timeout", "Remote-Gesamtzeitlimit einschließlich DNS überschritten.")
    sys.exit(0)
signal.signal(signal.SIGALRM, alarm)
signal.alarm(int(seconds) + 4)
try:
    addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
except socket.gaierror:
    emit("dns", "Hostname konnte auf diesem Quellserver nicht aufgelöst werden.")
    sys.exit(0)
unique = {}
for family, kind, protocol, _, endpoint in addresses:
    unique[(family, endpoint)] = (family, kind, protocol, endpoint)
deadline = time.monotonic() + seconds
attempts, statuses = [], []
for family, kind, protocol, endpoint in unique.values():
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        statuses.append("timeout")
        break
    status = "network"
    try:
        with socket.socket(family, kind, protocol) as probe:
            probe.settimeout(remaining)
            probe.connect(endpoint)
        status = "open"
    except (TimeoutError, socket.timeout):
        status = "timeout"
    except OSError as error:
        status = "refused" if error.errno == errno.ECONNREFUSED else "network"
    attempts.append(str(endpoint[0]) + ": " + status)
    statuses.append(status)
    if status == "open":
        break
status = "open" if "open" in statuses else "refused" if statuses and all(s == "refused" for s in statuses) else "timeout" if "timeout" in statuses else "network"
detail = "TCP-Verbindungsaufbau; keine Dienstanmeldung.\n" + "\n".join(attempts)
if len(attempts) < len(unique):
    detail += "\nWeitere aufgelöste Adressen nicht geprüft (Erfolg oder Zeitbudget erreicht)."
emit(status, detail, ", ".join(dict.fromkeys(str(a[3][0]) for a in unique.values())))
'''

# OpenBSD netcat fallback is deliberately recognised rather than guessing flags
# of an arbitrary nc implementation. Its output is interpreted only in C locale.
REMOTE_SCRIPT = r'''export LC_ALL=C
host=$1; port=$2; seconds=$3
if command -v python3 >/dev/null 2>&1; then
  exec python3 - "$host" "$port" "$seconds" <<'SSH_MANAGER_PY'
''' + REMOTE_PYTHON + r'''
SSH_MANAGER_PY
fi
emit() { printf 'SSH_MANAGER_TCP_V1\t%s\t%s\t%s\n' "$1" "$2" "$3"; }
if ! command -v timeout >/dev/null 2>&1 || ! command -v nc >/dev/null 2>&1; then
  emit tool '' 'Python 3 oder OpenBSD-netcat mit timeout erforderlich; nichts installiert.'; exit 0
fi
case "$(nc -h 2>&1)" in
  *OpenBSD*) ;;
  *) emit tool '' 'Netcat-Variante nicht unterstützt; Python 3 oder OpenBSD-netcat erforderlich.'; exit 0 ;;
esac
case "$host" in
  *:*) ips=$host ;;
  *[!0-9.]* )
    if ! command -v getent >/dev/null 2>&1; then emit tool '' 'Remote-DNS benötigt getent oder Python 3.'; exit 0; fi
    ips=$(timeout "$seconds" getent ahosts "$host" | awk '{print $1}' | sort -u)
    if [ -z "$ips" ]; then emit dns '' 'Remote-DNS fehlgeschlagen oder Zeitlimit überschritten.'; exit 0; fi ;;
  *) ips=$host ;;
esac
# One address per result, bounded by the local SSH deadline as well as timeout.
for ip in $ips; do
  output=$(timeout "$seconds" nc -n -z -v -w "$seconds" "$ip" "$port" 2>&1); code=$?
  status=network
  if [ "$code" = 0 ]; then status=open
  elif [ "$code" = 124 ]; then status=timeout
  else case "$output" in *refused*) status=refused ;; *timed*out*) status=timeout ;; esac
  fi
  emit "$status" "$ip" 'OpenBSD-netcat TCP-Verbindungsaufbau; keine Dienstanmeldung.'
  [ "$status" = open ] && break
done
exit 0
'''


def parse_probe_output(output):
    results = []
    for line in output.splitlines():
        if not line.startswith(MARKER):
            continue
        payload = line[len(MARKER):]
        if payload.startswith("{"):
            try:
                item = json.loads(payload)
            except (ValueError, TypeError):
                continue
        else:
            parts = payload.split("\t", 2)
            if len(parts) != 3:
                continue
            item = dict(zip(("status", "addresses", "detail"), parts))
        if (not isinstance(item, dict) or item.get("status") not in NEGATIVE | {"open", "tool"}
                or not all(isinstance(item.get(k, ""), str) for k in ("addresses", "detail"))):
            continue
        results.append(item)
    if not results:
        return ProbeResult("error", "Kein gültiges Remote-Prüfergebnis empfangen.")
    statuses = [r["status"] for r in results]
    status = ("open" if "open" in statuses else "tool" if "tool" in statuses else
              "dns" if "dns" in statuses else "refused" if all(s == "refused" for s in statuses)
              else "timeout" if "timeout" in statuses else "network")
    return ProbeResult(status, "\n".join(f"{r.get('addresses', '')}: {r.get('detail', '')}" for r in results),
                       ", ".join(r["addresses"] for r in results if r.get("addresses")))


def probe_target(session, destination, user, tcp_timeout, cancel):
    host, port = target(*destination)
    if type(tcp_timeout) is not int or not 1 <= tcp_timeout <= 30:
        raise ValueError("TCP-Timeout zwischen 1 und 30 Sekunden angeben.")
    if cancel.is_set():
        return ProbeResult("cancelled", "Prüfung nicht begonnen.")
    options = ["-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", "-o", "ConnectionAttempts=1",
               "-o", "StrictHostKeyChecking=yes", "-o", "UpdateHostKeys=no", "-o", "ClearAllForwardings=yes",
               "-o", "ControlMaster=no", "-o", "ControlPath=none", "-o", "ServerAliveInterval=5",
               "-o", "ServerAliveCountMax=1"]
    args = ssh_argv(session, session.username or user, options) + [shlex.join(["sh", "-s", "--", host, str(port), str(tcp_timeout)])]
    started = time.monotonic()
    process = None
    try:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        script = REMOTE_SCRIPT.encode("utf-8")
        while True:
            if cancel.is_set():
                return ProbeResult("cancelled", "Prüfung abgebrochen; keine Aussage zur Erreichbarkeit.")
            if time.monotonic() - started > tcp_timeout + 15:
                return ProbeResult("ssh", "SSH-/Prüfgesamtzeitlimit überschritten; kein vollständiges TCP-Ergebnis.")
            try:
                stdout, _stderr = process.communicate(input=script, timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                script = None
        if cancel.is_set():
            return ProbeResult("cancelled", "Prüfung abgebrochen.")
        if process.returncode == 255:
            return ProbeResult("ssh", "SSH fehlgeschlagen: Benutzer, Schlüssel/Agent, bekannten Hostschlüssel und Verbindung prüfen.")
        if process.returncode:
            return ProbeResult("error", "Remote-Prüfprozess fehlgeschlagen; kein bestätigtes TCP-Ergebnis.")
        result = parse_probe_output(stdout.decode("utf-8", errors="replace"))
        return ProbeResult(result.status, result.detail, result.addresses, datetime.now().astimezone().isoformat(timespec="seconds"))
    except (OSError, ValueError):
        return ProbeResult("ssh", "SSH-Client oder Verbindungsdaten nicht verfügbar.")
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.communicate()


class PortCheckJob:
    """Per-run source concurrency; immutable input and no Tk calls in workers."""
    def __init__(self, sessions, destinations, user, timeout, pairs=None, probe=probe_target, max_parallel=8):
        self.max_parallel = max_parallel
        self.sessions = deepcopy(list(sessions))
        self.destinations = tuple(targets(destinations))
        self.user, self.timeout, self.probe = user, timeout, probe
        self.pairs = set(pairs) if pairs is not None else {(s.key, t) for s in self.sessions for t in self.destinations}
        self.cancel = threading.Event()
        self.events = queue.SimpleQueue()

    def _source(self, session):
        for destination in self.destinations:
            if (session.key, destination) not in self.pairs:
                continue
            if self.cancel.is_set():
                result = ProbeResult("cancelled", "Prüfung nicht begonnen.")
            else:
                self.events.put(("running", session.key, destination, None))
                try:
                    result = self.probe(session, destination, self.user, self.timeout, self.cancel)
                except Exception as error:
                    from .errors import record_failure
                    record_failure(error)
                    result = ProbeResult("error", "Unerwarteter Prüffehler; kein TCP-Ergebnis.")
                if not result.checked_at:
                    result = ProbeResult(result.status, result.detail, result.addresses,
                                         datetime.now().astimezone().isoformat(timespec="seconds"))
            self.events.put(("result", session.key, destination, result))

    def _run(self):
        try:
            from .parallelism import worker_count
            with ThreadPoolExecutor(max_workers=worker_count(len(self.sessions), self.max_parallel)) as executor:
                list(executor.map(self._source, self.sessions))
        finally:
            self.events.put(("done", None, None, None))

    def start(self):
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        return self
