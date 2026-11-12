"""Native Herdr desktop integration (separate from the legacy Herdr TUI)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


class HerdrAppUnavailableError(RuntimeError):
    """No terminal creation has been attempted; an explicit fallback is safe."""


class HerdrAppBusyError(RuntimeError):
    """No creation attempted; another native launch owns the resource."""


class HerdrAppLauncher:
    SPACE_NAME = "SSH Manager"
    _lock = threading.Lock()

    @staticmethod
    def _find_program(name, folder):
        found = shutil.which(name)
        if found:
            return found
        local = os.environ.get("LOCALAPPDATA")
        if local:
            path = Path(local) / "Programs" / folder / (name + ".exe")
            if path.is_file():
                return str(path)
        raise HerdrAppUnavailableError(f"{name} wurde nicht gefunden. Bitte Herdr App installieren.")

    @staticmethod
    def _json(executable, args):
        result = subprocess.run(
            [executable, *args], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        # Never expose stderr: it can contain program arguments or secrets.
        if result.returncode:
            raise RuntimeError("Herdr App hat den Aufruf abgelehnt.")
        data = json.loads(result.stdout)
        if not isinstance(data, dict) or "error" in data:
            raise ValueError("Ungültige Antwort der Herdr App.")
        return data

    @classmethod
    def _spaces(cls, executable):
        data = cls._json(executable, ["ls"])
        spaces = data.get("spaces")
        if not isinstance(spaces, list) or any(not isinstance(s, dict) for s in spaces):
            raise ValueError("Ungültige Bereichsliste der Herdr App.")
        return spaces

    @classmethod
    def _ready(cls, executable):
        try:
            return cls._spaces(executable)
        except RuntimeError:
            # Only a failed read can cause a window launch. Never repeat a mutation.
            subprocess.Popen([executable], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                return cls._spaces(executable)
            except RuntimeError:
                time.sleep(0.1)
        raise HerdrAppUnavailableError("Herdr App ist noch nicht bereit. Bitte öffnen und erneut versuchen.")

    @staticmethod
    def _id(data, key):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Herdr App hat keine gültigen Ziel-IDs geliefert.")
        return value

    @classmethod
    def launch_tabs(cls, tabs, settings):
        from .core import TerminalCommand, TerminalLaunchError, _find_git_bash
        if not tabs:
            return
        # Reject competing launches rather than queueing a second copy of a click.
        if not cls._lock.acquire(blocking=False):
            raise HerdrAppBusyError("Ein Herdr-App-Start läuft bereits. Bitte dessen Ergebnis abwarten.")
        started = []
        try:
            try:
                executable = cls._find_program("herdr-app", "herdr-app")
                cls._find_program("hc", "herdr-core")
                bash = _find_git_bash()
                if bash == "bash":
                    raise HerdrAppUnavailableError("Git Bash wurde nicht gefunden. Bitte Git für Windows installieren.")
                prepared = []
                for tab in tabs:
                    if not tab.argv:
                        raise ValueError("Terminal-Start benötigt strukturierte Argumente.")
                    argv = list(tab.argv)
                    if argv[0].lower().endswith(("bash.exe", "bash")):
                        if len(argv) > 1:
                            argv[1] = argv[1].replace("\\", "/")
                    else:
                        argv = [bash, "--login", "-c", 'exec "$@"', "ssh-manager", *argv]
                    prepared.append((tab, argv))
                spaces = cls._ready(executable)
                matches = [s for s in spaces if s.get("name") == cls.SPACE_NAME and not s.get("machine")]
                if len(matches) > 1:
                    raise ValueError("Mehrere lokale Herdr-Bereiche heißen SSH Manager. Bitte eindeutig benennen.")
                space = cls._id(matches[0], "id") if matches else None
            except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                raise HerdrAppUnavailableError(str(exc) if isinstance(exc, (HerdrAppUnavailableError, ValueError))
                                               else "Herdr App konnte nicht vorbereitet werden.") from exc

            for index, (tab, argv) in enumerate(prepared):
                try:
                    payload = {"name": tab.label, "argv": argv}
                    if space is None:
                        payload.update(name=cls.SPACE_NAME, tab=tab.label, machine="", folder=str(Path.home()))
                        reply = cls._json(executable, ["do", "space.new", json.dumps(payload, ensure_ascii=False)])
                        space = cls._id(reply, "space")
                    else:
                        payload.update(space=space, folder=str(Path.home()))
                        reply = cls._json(executable, ["do", "tab.new", json.dumps(payload, ensure_ascii=False)])
                    cls._id(reply, "tab")
                    cls._id(reply, "terminal")
                    if tab.session is not None:
                        started.append(tab.session)
                except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
                    # The current request may have committed despite a timeout.
                    # Only subsequent, never-attempted scripts can be removed.
                    TerminalCommand([spec for spec, _ in prepared[index + 1:]]).cleanup()
                    raise TerminalLaunchError(
                        f"Herdr-App-Start unvollständig oder unklar ({len(started)} bestätigte Starts). "
                        "Bitte Tabs prüfen; kein automatischer Zweitstart.", started_sessions=started,
                    ) from exc
        finally:
            cls._lock.release()
