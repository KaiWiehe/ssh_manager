"""In-place terminal view for a running standalone restart plan."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager, ExitStack
import ctypes
from ctypes import wintypes
import os
import shutil
import sys
import time
import unicodedata


RESTART_STATUS = {
    "pending": ("Wartet", 90), "preflight": ("Vorprüfung", 36),
    "restarting": ("Neustart", 93), "waiting_down": ("Neustart", 93),
    "waiting_ssh": ("SSH / Boot-ID", 93), "waiting_service": ("Dienste prüfen", 36),
    "online": ("Erfolgreich", 92), "error": ("Fehler", 91), "timeout": ("Timeout", 91),
    "stopped": ("Abgebrochen", 33), "not_started": ("Nicht gestartet", 90),
}
RESTART_FINISHED = {"online", "error", "timeout", "stopped", "not_started"}


def restart_live_terminal():
    return (sys.stdin.isatty() and sys.stdout.isatty()
            and os.environ.get("TERM", "").lower() != "dumb")


def _restart_cell_width(char):
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def restart_terminal_cell(value, width, *, pad=False):
    plain = " ".join("".join(char if char.isprintable() or char.isspace() else "?" for char in value).split())
    cells = sum(_restart_cell_width(char) for char in plain)
    if cells > width:
        chars, cells = [], 0
        for char in plain:
            size = _restart_cell_width(char)
            if cells + size >= width:
                break
            chars.append(char)
            cells += size
        plain = "".join(chars) + "…" if width else ""
        cells += bool(width)
    return plain + (" " * (width - cells) if pad else "")


def _restart_windows_console(stack):
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel.GetConsoleMode.restype = wintypes.BOOL
    kernel.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.SetConsoleMode.restype = wintypes.BOOL

    def enable(stream, flags):
        handle = msvcrt.get_osfhandle(stream.fileno())
        previous = wintypes.DWORD()
        if not kernel.GetConsoleMode(handle, ctypes.byref(previous)):
            raise OSError("Konsolenmodus nicht verfügbar")
        if not kernel.SetConsoleMode(handle, previous.value | flags):
            raise OSError("Konsolenmodus konnte nicht gesetzt werden")
        stack.callback(kernel.SetConsoleMode, handle, previous.value)

    enable(sys.stdout, 0x0001 | 0x0004)  # Processed output and VT escape sequences.
    enable(sys.stdin, 0x0001)  # Keep console Ctrl+C processing active.

    def keys():
        result = []
        for _ in range(32):
            if not msvcrt.kbhit():
                break
            key = msvcrt.getwch()
            if key in ("\0", "\xe0"):
                msvcrt.getwch()  # Discard the second byte of an extended key.
            else:
                result.append(key)
        return "".join(result)

    return keys


def _restart_posix_console(stack):
    import select
    import termios
    import tty

    descriptor = sys.stdin.fileno()
    try:
        previous = termios.tcgetattr(descriptor)
        stack.callback(termios.tcsetattr, descriptor, termios.TCSANOW, previous)
        tty.setcbreak(descriptor, termios.TCSANOW)
    except termios.error as error:
        raise OSError("Terminaleingabe konnte nicht eingerichtet werden") from error

    def keys():
        if not select.select([descriptor], [], [], 0)[0]:
            return ""
        data = os.read(descriptor, 32)
        return data.decode("ascii", errors="replace") if data else "\x04"

    return keys


@contextmanager
def restart_terminal_view(plan, targets, *, enabled):
    if not enabled:
        yield None
        return
    with ExitStack() as stack:
        try:
            keys = _restart_windows_console(stack) if os.name == "nt" else _restart_posix_console(stack)
        except (OSError, ValueError):
            stack.close()
            yield None
            return
        view = RestartTerminalView(plan, targets, sys.stdout, keys, use_color=not os.environ.get("NO_COLOR"))
        stack.callback(view.restore)
        view.start()
        yield view


class RestartTerminalView:
    def __init__(self, plan, targets, stream, read_keys, *, use_color):
        self.plan, self.targets, self.stream = plan, targets, stream
        self.read_keys, self.use_color = read_keys, use_color
        self.states = [(None, "pending", "")] * len(targets)
        self.page = 0
        self.page_count = 1
        self.confirm = ""
        self.pause_failures = ()
        self.pause_input_ready = False
        self.frame = None
        self.active = False
        self.started = time.monotonic()

    def write(self, text):
        if self.stream.encoding:
            text = text.encode(self.stream.encoding, errors="replace").decode(self.stream.encoding)
        self.stream.write(text)
        self.stream.flush()

    def start(self):
        self.active = True
        self.write("\x1b[?1049h\x1b[?25l\x1b[2J")

    def restore(self):
        if self.active:
            self.active = False
            self.write("\x1b[0m\x1b[?25h\x1b[?1049l")

    def update(self, timestamp, index, state, detail):
        self.states[index] = timestamp, state, detail

    def _paint(self, text, code):
        return f"\x1b[{code}m{text}\x1b[0m" if self.use_color else text

    def _table(self, indexes, width, *, final=False):
        padding = 2
        status_width = min(16, max(1, width // 3))
        server_width = min(38, max(5, int(width * .35)))
        padding = min(padding, max(0, width - status_width - 1))
        remaining = width - server_width - status_width - padding * 2
        show_detail = remaining >= 12
        show_time = remaining >= 30
        if show_time:
            remaining -= 8 + padding
        if not show_detail:
            server_width = max(0, width - status_width - padding)
        gap = " " * padding

        def row(server, status, timestamp, detail):
            left = restart_terminal_cell(server, server_width, pad=True)
            columns = [left, status]
            if show_time:
                columns.append(restart_terminal_cell(timestamp, 8, pad=True))
            if show_detail:
                columns.append(restart_terminal_cell(detail, remaining))
            return gap.join(columns)

        yield row("Server", restart_terminal_cell("Status", status_width, pad=True), "Seit", "Letzte Meldung")
        for index in indexes:
            timestamp, state, detail = self.states[index]
            status, color = RESTART_STATUS.get(state, (state, 0))
            since = f"{timestamp:%H:%M:%S}" if timestamp else "—"
            if state == "online":
                detail = "Boot-ID geändert · Dienste OK" if self.targets[index].checks else "Boot-ID geändert · SSH wieder online"
            elif final:
                detail = ""  # Full diagnoses follow the final table.
            yield row(f"{index + 1}. {self.targets[index].label}",
                      self._paint(restart_terminal_cell(status, status_width, pad=True), color), since, detail)

    def _summary(self):
        counts = Counter(state for _, state, _detail in self.states)
        finished = sum(counts[state] for state in RESTART_FINISHED)
        errors = counts["error"] + counts["timeout"]
        summary = f"{finished}/{len(self.targets)} abgeschlossen · {counts['online']} erfolgreich · {errors} Fehler"
        if counts["stopped"] or counts["not_started"]:
            summary += f" · {counts['stopped'] + counts['not_started']} gestoppt/ausgelassen"
        return summary

    def draw(self, *, failures=(), interrupted=False):
        columns, rows = shutil.get_terminal_size((100, 24))
        width, rows = max(1, columns - 1), max(1, rows)
        elapsed = int(time.monotonic() - self.started)
        footer = []
        controls = "Strg+C abbrechen"
        if interrupted:
            controls = "Abbruch angefordert · laufende SSH-Aufrufe werden beendet"
        elif failures:
            index, result = failures[-1]
            if rows >= 10:
                footer.append(f"{self.targets[index].label}: {result.detail}")
            choice = " [j]" if self.confirm == "j" and tuple(failures) == self.pause_failures else ""
            controls = f"J+Enter weiter · Enter stoppt{choice}"
        title = "Fehlerpause" if failures else "Massen-Neustart"
        title = restart_terminal_cell(f"{title} · {self.plan['name']}", width)
        lead = []
        if rows >= 6:
            lead = [self._paint(title, 1),
                    restart_terminal_cell(f"{self._summary()} · {elapsed // 60:02}:{elapsed % 60:02}", width), ""]
        # Leave room for the table heading, controls and pagination line.
        per_page = max(1, rows - len(lead) - len(footer) - 3)
        self.page_count = (len(self.targets) + per_page - 1) // per_page
        self.page = min(self.page, self.page_count - 1)
        start = self.page * per_page
        if self.page_count > 1 and rows >= 4:
            footer.append(f"Seite {self.page + 1}/{self.page_count} · P zurück · N weiter")
        footer.append(controls)
        table = list(self._table(range(start, min(start + per_page, len(self.targets))), width))
        lines = [*lead, *table[:max(0, rows - len(lead) - len(footer))],
                 *(restart_terminal_cell(line, width) for line in footer)]
        frame = "".join(f"\x1b[{index};1H{line}\x1b[K" for index, line in enumerate(lines, 1)) + "\x1b[J"
        if frame != self.frame:
            self.write(frame)
            self.frame = frame

    def read_decision(self, *, failures=()):
        keys = self.read_keys().lower()
        if "\x03" in keys:
            raise KeyboardInterrupt
        failures = tuple(failures)
        if failures != self.pause_failures:
            self.pause_failures = failures
            self.confirm = ""
            self.pause_input_ready = False
        if failures and not self.pause_input_ready:
            # Discard queued keystrokes until the new prompt has an empty input queue.
            self.pause_input_ready = not keys
            return False if "\x04" in keys else None
        for key in keys:
            if key == "p":
                self.page = max(0, self.page - 1)
                self.confirm = ""
            elif key == "n":
                self.page = min(self.page_count - 1, self.page + 1)
                self.confirm = ""
            elif failures and key in ("\r", "\n", "\x04"):
                decision = self.confirm == "j" and key != "\x04"
                self.confirm = ""
                self.pause_input_ready = False
                return decision
            elif failures:
                if key in ("\b", "\x7f"):
                    self.confirm = self.confirm[:-1]
                else:
                    self.confirm = "j" if key == "j" and not self.confirm else "?"
        return None

    def show_result(self, results):
        self.restore()
        width = max(1, shutil.get_terminal_size((100, 24)).columns - 1)
        lines = ["", f"Ergebnis · {self._summary()}", *self._table(range(len(self.targets)), width, final=True)]
        details_by_targets = {}
        for index, result in sorted(results.items()):
            checks = self.targets[index].checks
            details = result.detail.splitlines()
            if result.status == "online" and not any("wildfly" in check for check in checks):
                details = details[-len(checks):] if checks and result.includes_service_states else []
            if not result.includes_service_states:
                details.extend(f"{check['unit']}: Soll {check['expected']}, Ist nicht geprüft" for check in checks)
            if details:
                details_by_targets.setdefault(tuple(details), []).append(str(index + 1))
        if details_by_targets:
            lines.extend(("", "Details je Zielnummer"))
            for details, targets in details_by_targets.items():
                description = " · ".join(restart_terminal_cell(line, 10000) for line in details)
                lines.append(f"  {', '.join(targets)}  {description}")
        self.write("\n".join(lines) + "\n")
