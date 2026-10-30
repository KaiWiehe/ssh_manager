"""Window-free console command dispatch."""
from __future__ import annotations

import argparse
import sys

from .version import APP_VERSION


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sshm", description="SSH Manager: Baumsuche und SSH im aktuellen Terminal.")
    parser.add_argument("query", nargs="*", help="Optionaler Startsuchtext")
    parser.add_argument("--version", action="version", version=f"SSH Manager CLI {APP_VERSION}")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("sshm benötigt ein interaktives Terminal. In PowerShell oder Git Bash aufrufen.", file=sys.stderr)
        return 2
    try:
        from .session_catalog import load_catalog
        from .cli_ui import SessionPicker
        from .cli_launch import launch

        catalog = load_catalog()
        if not catalog.entries:
            from .source_status import STATUS_LABELS
            for source, status in catalog.statuses.items():
                print(f"{source}: {STATUS_LABELS.get(status['state'], status['state'])}", file=sys.stderr)
            print("Keine nutzbaren Verbindungen vorhanden. Quellen im SSH Manager prüfen.", file=sys.stderr)
            return 1
        picker = SessionPicker(catalog, " ".join(args.query))
        entry = picker.run()
        if entry is None:
            return 130
        result, warning = launch(entry, picker.chosen_user)
        if warning:
            print(warning, file=sys.stderr)
        return result
    except (KeyboardInterrupt, EOFError):
        return 130
    except (OSError, ValueError, ImportError) as error:
        from .cli_search import safe_text
        print("sshm: " + safe_text(str(error)), file=sys.stderr)
        return 1
