"""Window-free console command dispatch."""
from __future__ import annotations

import argparse
import sys

from .version import APP_VERSION


def prompt_user(quick_users):
    from prompt_toolkit.shortcuts import prompt
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.key_binding import KeyBindings
    from .ssh_utils import connection_value
    bindings = KeyBindings()

    @bindings.add("escape", eager=True)
    def cancel(event):
        event.app.exit(exception=KeyboardInterrupt())

    while True:
        user = prompt("SSH-Benutzer (Tab: Vorschläge, Esc/Strg+C: Abbruch): ",
                      completer=WordCompleter(quick_users), key_bindings=bindings)
        try:
            return connection_value(user.strip(), "Benutzer")
        except ValueError:
            print("Bitte einen gültigen Benutzernamen eingeben.")


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
        user = entry.user
        if not entry.session.is_ssh_config_session and not user:
            user = prompt_user(catalog.settings.quick_users)
        result, warning = launch(entry, user)
        if warning:
            print(warning, file=sys.stderr)
        return result
    except (KeyboardInterrupt, EOFError):
        return 130
    except (OSError, ValueError, ImportError) as error:
        from .cli_search import safe_text
        print("sshm: " + safe_text(str(error)), file=sys.stderr)
        return 1
