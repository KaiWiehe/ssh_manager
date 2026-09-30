"""Increment or validate the SSH Manager application version."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "ssh_manager_app" / "version.py"
WINDOWS_VERSION_FILE = ROOT / "packaging" / "ssh_manager_version_info.txt"
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")


def _read_app_version() -> str:
    source = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION = "(\d+\.\d+\.\d+)"$', source, re.MULTILINE)
    if match is None:
        raise SystemExit(f"APP_VERSION fehlt oder ist ungültig: {VERSION_FILE}")
    return match.group(1)


def _windows_versions() -> set[str]:
    source = WINDOWS_VERSION_FILE.read_text(encoding="utf-8")
    string_versions = set(re.findall(r"StringStruct\('(?:File|Product)Version', '(\d+\.\d+\.\d+)'\)", source))
    tuple_versions = {
        ".".join(match[:3])
        for match in re.findall(r"(?:filevers|prodvers)=\((\d+), (\d+), (\d+), 0\)", source)
    }
    return string_versions | tuple_versions


def _check(version: str) -> None:
    windows_versions = _windows_versions()
    if windows_versions != {version}:
        rendered = ", ".join(sorted(windows_versions)) or "keine gültige Version"
        raise SystemExit(
            "Versions-Metadaten sind nicht synchron: "
            f"App={version}, Windows={rendered}"
        )


def _write_version(old_version: str, new_version: str) -> None:
    major, minor, patch = new_version.split(".")

    app_source = VERSION_FILE.read_text(encoding="utf-8")
    app_source = app_source.replace(
        f'APP_VERSION = "{old_version}"',
        f'APP_VERSION = "{new_version}"',
        1,
    )
    VERSION_FILE.write_text(app_source, encoding="utf-8")

    windows_source = WINDOWS_VERSION_FILE.read_text(encoding="utf-8")
    windows_source = re.sub(
        r"(filevers|prodvers)=\(\d+, \d+, \d+, 0\)",
        rf"\1=({major}, {minor}, {patch}, 0)",
        windows_source,
    )
    windows_source = re.sub(
        r"(StringStruct\('(?:File|Product)Version', ')\d+\.\d+\.\d+('\))",
        rf"\g<1>{new_version}\2",
        windows_source,
    )
    WINDOWS_VERSION_FILE.write_text(windows_source, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Versionen nur prüfen")
    parser.add_argument("--set", dest="requested_version", help="Version explizit auf MAJOR.MINOR.PATCH setzen")
    args = parser.parse_args()

    current_version = _read_app_version()
    if args.check:
        if args.requested_version:
            parser.error("--check und --set können nicht kombiniert werden")
        _check(current_version)
        print(f"Version {current_version} ist synchron.")
        return

    if args.requested_version:
        if SEMVER_PATTERN.fullmatch(args.requested_version) is None:
            parser.error("--set erwartet MAJOR.MINOR.PATCH, zum Beispiel 1.2.3")
        new_version = args.requested_version
    else:
        major, minor, patch = map(int, current_version.split("."))
        new_version = f"{major}.{minor}.{patch + 1}"

    if new_version == current_version:
        raise SystemExit(f"Version ist bereits {current_version}.")

    _write_version(current_version, new_version)
    _check(new_version)
    print(f"Version erhöht: {current_version} -> {new_version}")


if __name__ == "__main__":
    main()
