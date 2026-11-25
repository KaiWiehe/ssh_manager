from datetime import datetime
from io import StringIO
import os
import re
from threading import Event
from types import SimpleNamespace

import pytest

from ssh_manager_app import restart_terminal
from ssh_manager_app.mass_restart import MassRestartRun
from ssh_manager_app.restart_runtime import RestartResult, RestartScheduler
from ssh_manager_app.restart_terminal import RestartTerminalView


def make_view(monkeypatch, *, size=(110, 24), count=5, keys=(), color=True):
    monkeypatch.setattr(restart_terminal.shutil, "get_terminal_size", lambda _: os.terminal_size(size))
    targets = [SimpleNamespace(label=f"Server {index:02}", checks=[{"unit": "app.service", "expected": "active"}])
               for index in range(1, count + 1)]
    stream = StringIO()
    read_keys = iter(keys)
    return RestartTerminalView({"name": "Wartung"}, targets, stream, lambda: next(read_keys, ""), use_color=color)


def test_latest_status_replaces_the_previous_frame_and_final_table_stays_in_history(monkeypatch):
    view = make_view(monkeypatch)
    moment = datetime(2026, 11, 25, 9, 42, 16)
    view.start()
    view.update(moment, 0, "preflight", "Vorprüfung gestartet")
    view.draw()
    assert "Vorprüfung gestartet" in view.frame
    view.update(moment, 0, "waiting_ssh", "SSH wieder erreichbar")
    view.update(moment, 1, "error", "Berechtigung fehlt")
    view.draw()
    assert "Vorprüfung gestartet" not in view.frame
    assert "SSH wieder erreichbar" in view.frame and "09:42:16" in view.frame
    assert view.frame.count("1. Server 01") == 1
    assert "\x1b[93mSSH / Boot-ID" in view.frame and "\x1b[91mFehler" in view.frame
    view.update(moment, 0, "online", "Dienstprüfung abgeschlossen")
    view.update(moment, 2, "not_started", "Neustart wurde nicht ausgelöst")
    view.show_result({
        0: RestartResult("online", "Boot-ID geändert\nDienstprüfung abgeschlossen\napp.service: Soll active, Ist active",
                         includes_service_states=True),
        1: RestartResult("error", "Berechtigung fehlt\nFehlerdiagnose"),
        2: RestartResult("not_started", "Neustart wurde nicht ausgelöst"),
    })
    output = view.stream.getvalue().split("\x1b[?1049l", 1)[1]
    assert "\x1b[92mErfolgreich" in output and "Boot-ID geändert · Dienste OK" in output
    assert "3/5 abgeschlossen · 1 erfolgreich · 1 Fehler" in output
    assert output.count("Fehlerdiagnose") == 1
    assert "app.service: Soll active, Ist active" in output
    assert "Neustart wurde nicht ausgelöst" in output and "Ist nicht geprüft" in output


def test_live_table_pages_and_keeps_rows_inside_a_small_terminal(monkeypatch):
    view = make_view(monkeypatch, count=30, size=(38, 10), keys=["n", "p"], color=False)
    view.draw()
    assert "Seite 1/8" in view.frame and "5. Server 05" not in view.frame
    view.read_decision()
    view.draw()
    assert "Seite 2/8" in view.frame and "5. Server 05" in view.frame
    assert "1. Server 01" not in view.frame and "\x1b[90m" not in view.frame
    assert max(int(row) for row in re.findall(r"\x1b\[(\d+);1H", view.frame)) <= 10
    view.read_decision()
    view.draw()
    assert "Seite 1/8" in view.frame
    assert restart_terminal.restart_terminal_cell("界界X\x1b", 4) == "界…"
    assert restart_terminal.restart_terminal_cell("X\r\nY\x1b", 4) == "X Y?"


@pytest.mark.parametrize(("answer", "expected"), [("j\r", True), ("\r", False), ("\x04", False)])
def test_failure_decision_requires_fresh_input_after_the_prompt(monkeypatch, answer, expected):
    view = make_view(monkeypatch, size=(38, 10), keys=["j\r", "j\r", "", answer, "j\r", "", "j\r"])
    failures = [(0, RestartResult("error", "Prüfung fehlgeschlagen"))]
    view.draw(failures=failures)
    assert "Fehlerpause" in view.frame
    assert "J+Enter weiter · Enter stoppt" in view.frame
    assert view.read_decision(failures=failures) is None
    assert view.read_decision(failures=failures) is None
    assert view.read_decision(failures=failures) is None
    assert view.read_decision(failures=failures) is expected
    next_failures = [(1, RestartResult("timeout", "Nächste Fehlerpause"))]
    view.draw(failures=next_failures)
    assert view.read_decision(failures=next_failures) is None
    assert view.read_decision(failures=next_failures) is None
    assert view.read_decision(failures=next_failures) is True


def test_a_new_scheduler_failure_invalidates_the_displayed_continuation():
    run = MassRestartRun.__new__(MassRestartRun)
    run.cancel = Event()
    run.phase = "restart"
    run.scheduler = RestartScheduler([2], 2, "pause", None)
    run.scheduler.active = 2
    run.scheduler._complete(0, RestartResult("error", "Erster Server"))
    visible_failures = run.pause_failures()
    run.scheduler._complete(1, RestartResult("timeout", "Zweiter Server"))
    run.continue_after_failures(visible_failures)
    assert run.scheduler.paused and len(run.pause_failures()) == 2
    run.continue_after_failures(run.pause_failures())
    assert not run.scheduler.paused


def test_live_context_restores_console_on_failure_and_respects_no_color(monkeypatch):
    stream = StringIO()
    restored = []

    def console(stack):
        stack.callback(lambda: restored.append(True))
        return lambda: ""

    monkeypatch.setattr(restart_terminal, "_restart_windows_console", console)
    monkeypatch.setattr(restart_terminal, "_restart_posix_console", console)
    monkeypatch.setattr(restart_terminal.sys, "stdout", stream)
    monkeypatch.setenv("NO_COLOR", "1")
    with pytest.raises(RuntimeError), restart_terminal.restart_terminal_view({}, [], enabled=True) as view:
        assert not view.use_color
        raise RuntimeError("test")
    assert "\x1b[?1049h" in stream.getvalue() and "\x1b[?1049l" in stream.getvalue()
    assert restored == [True]
