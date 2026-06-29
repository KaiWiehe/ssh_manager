from __future__ import annotations

import ipaddress
import base64
import json
import re
import socket
import subprocess
from dataclasses import dataclass


DNS_LOOKUP_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class DnsLookupResult:
    query: str
    mode: str
    results: list[str]
    resolver: str
    status: str
    error: str = ""
    connection_name: str = ""


def detect_lookup_mode(value: str) -> str:
    """Return ``reverse`` for IP addresses and ``forward`` for host names."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Leere Eingabe")
    try:
        ipaddress.ip_address(cleaned)
        return "reverse"
    except ValueError:
        return "forward"


def normalize_lookup_mode(value: str, mode: str = "auto") -> str:
    requested = (mode or "auto").strip().lower()
    if requested == "auto":
        return detect_lookup_mode(value)
    if requested not in {"forward", "reverse"}:
        raise ValueError(f"Unbekannter DNS-Lookup-Modus: {mode}")
    return requested


def resolve_dns_value(value: str, mode: str = "auto", timeout: int = DNS_LOOKUP_TIMEOUT_SECONDS) -> DnsLookupResult:
    query = value.strip()
    if not query:
        return DnsLookupResult(query=value, mode="auto", results=[], resolver="-", status="error", error="Leere Eingabe")
    lookup_mode = normalize_lookup_mode(query, mode)

    errors: list[str] = []
    for resolver_name, resolver in (
        ("Resolve-DnsName", _resolve_with_powershell),
        ("nslookup", _resolve_with_nslookup),
        ("Python socket", _resolve_with_socket),
    ):
        try:
            results = resolver(query, lookup_mode, timeout)
        except Exception as exc:
            errors.append(f"{resolver_name}: {exc}")
            continue
        if results:
            return DnsLookupResult(query=query, mode=lookup_mode, results=_dedupe(results), resolver=resolver_name, status="ok")
        errors.append(f"{resolver_name}: keine Treffer")

    error = "; ".join(errors[-2:]) if errors else "Keine Treffer"
    return DnsLookupResult(query=query, mode=lookup_mode, results=[], resolver="-", status="not_found", error=error)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip().rstrip(".")
        if not cleaned or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        result.append(cleaned)
    return result


def _run_command(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout, shell=False)


def _resolve_with_powershell(query: str, mode: str, timeout: int) -> list[str]:
    name_assignment = f"$name={_powershell_single_quote(query)};\n"
    if mode == "reverse":
        command = (
            name_assignment +
            "Resolve-DnsName -Name $name -Type PTR -ErrorAction Stop | "
            "Select-Object NameHost,IPAddress,Name,Type | ConvertTo-Json -Compress"
        )
    else:
        command = (
            name_assignment +
            "$items=@(); "
            "$items += Resolve-DnsName -Name $name -Type A -ErrorAction SilentlyContinue; "
            "$items += Resolve-DnsName -Name $name -Type AAAA -ErrorAction SilentlyContinue; "
            "$items | Select-Object NameHost,IPAddress,Name,Type | ConvertTo-Json -Compress"
        )
    encoded_command = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    result = _run_command(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_command],
        timeout,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "PowerShell fehlgeschlagen").strip())
    return parse_resolve_dns_name_json(result.stdout, mode)


def _powershell_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def parse_resolve_dns_name_json(output: str, mode: str) -> list[str]:
    text = output.strip()
    if not text:
        return []
    data = json.loads(text)
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = [item for item in data if isinstance(item, dict)]
    else:
        return []

    values: list[str] = []
    key = "NameHost" if mode == "reverse" else "IPAddress"
    for item in items:
        value = item.get(key)
        if value:
            values.append(str(value))
    return _dedupe(values)


def _resolve_with_nslookup(query: str, mode: str, timeout: int) -> list[str]:
    if mode == "reverse":
        commands = [["nslookup", "-type=PTR", query]]
    else:
        commands = [["nslookup", "-type=A", query], ["nslookup", "-type=AAAA", query]]

    outputs: list[str] = []
    errors: list[str] = []
    for command in commands:
        result = _run_command(command, timeout)
        if result.returncode == 0:
            outputs.append(result.stdout)
        else:
            errors.append((result.stderr or result.stdout or "nslookup fehlgeschlagen").strip())
    parsed = parse_nslookup_output("\n".join(outputs), mode)
    if parsed:
        return parsed
    if errors and not outputs:
        raise RuntimeError("; ".join(errors))
    return []


_IP_TOKEN_RE = re.compile(r"(?<![\w:.])(?:\d{1,3}(?:\.\d{1,3}){3}|[0-9a-fA-F:]{2,})(?![\w:.])")


def parse_nslookup_output(output: str, mode: str) -> list[str]:
    values: list[str] = []
    lines = output.splitlines()
    answer_started = False
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower()
        if "non-authoritative" in lowered or "nicht autoris" in lowered or lowered.startswith("name:"):
            answer_started = True
        if mode == "reverse":
            if " name = " in f" {lowered} ":
                values.append(line.split("=", 1)[1].strip())
            elif lowered.startswith("name:") and not lowered.startswith("server:"):
                values.append(line.split(":", 1)[1].strip())
            continue
        if not answer_started:
            continue
        for match in _IP_TOKEN_RE.findall(line):
            try:
                values.append(str(ipaddress.ip_address(match)))
            except ValueError:
                continue
    return _dedupe(values)


def _resolve_with_socket(query: str, mode: str, timeout: int) -> list[str]:
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        if mode == "reverse":
            host, aliases, _addresses = socket.gethostbyaddr(query)
            return _dedupe([host] + list(aliases))
        infos = socket.getaddrinfo(query, None, type=socket.SOCK_STREAM)
        addresses = [info[4][0] for info in infos if info and len(info) >= 5]
        return _dedupe(addresses)
    finally:
        socket.setdefaulttimeout(previous_timeout)
