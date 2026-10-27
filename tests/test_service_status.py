"""Read-only status and unbounded restart admission, using synthetic hosts only."""
from copy import deepcopy
import subprocess
import threading

import pytest

from test_restart_templates_ui import app, screenshot
from ssh_manager_app.models import Session
from ssh_manager_app.restart_templates import new_template, validate_template, resolve_targets, execution_policy
from ssh_manager_app.dialogs_restart_templates import RestartTemplatesDialog
from ssh_manager_app.service_status import check_unit, run_service_status


@pytest.mark.parametrize("actual,expected,outcome", [("active", "active", "Soll erfüllt"),
    ("inactive", "inactive", "Soll erfüllt"), ("failed", "inactive", "Abweichung"),
    ("activating", "active", "Abweichung")])
def test_status_only_runs_systemctl_show(monkeypatch, actual, expected, outcome):
    commands = []
    def ssh(session, user, command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess([], 0, f"LoadState=loaded\nActiveState={actual}\n", "")
    monkeypatch.setattr("ssh_manager_app.actions_restart_templates._run_ssh", ssh)
    result = check_unit(Session("one", "one", [], "one.example"), "admin", {"unit": "a.service", "expected": expected})
    assert result.actual == actual and result.outcome == outcome
    assert commands == ["systemctl show --property=LoadState --property=ActiveState -- a.service"]


@pytest.mark.parametrize("stdout,code,actual", [("", 255, "nicht geprüft"),
    ("LoadState=not-found\nActiveState=inactive\n", 1, "nicht vorhanden"), ("invalid", 0, "nicht geprüft")])
def test_missing_and_ssh_errors_are_not_inactive(monkeypatch, stdout, code, actual):
    monkeypatch.setattr("ssh_manager_app.actions_restart_templates._run_ssh",
        lambda *a, **k: subprocess.CompletedProcess([], code, stdout, ""))
    result = check_unit(Session("one", "one", [], "one.example"), "admin", {"unit": "a.service", "expected": "inactive"})
    assert result.actual == actual and result.outcome == "Fehler"


def finish_window(app, window):
    def is_done():
        return window.finished if hasattr(window, "finished") else window._finished
    def finish():
        if is_done():
            app.quit()
        else:
            app.after(20, finish)
    app.after(20, finish)
    watchdog = app.after(5000, app.quit)
    app.mainloop()
    app.after_cancel(watchdog)
    assert is_done()


def test_all_parallel_mode_disables_irrelevant_fields_and_roundtrips(app):
    window = RestartTemplatesDialog(app, app._app_sessions)
    window.options["max_parallel"].set("2")
    window.options["on_error"].set("weitere stoppen")
    window.options["mode"].set("Alle parallel durchstarten")
    assert str(window.option_widgets["max_parallel"].cget("state")) == "disabled"
    assert str(window.option_widgets["on_error"].cget("state")) == "disabled"
    item = validate_template(window.collect())
    assert item["mode"] == "all_parallel" and execution_policy(item) == (3, "continue")
    assert window.save()
    assert app._initial_toolbar_search_texts["restart_templates"]["items"][0]["mode"] == "all_parallel"
    screenshot(window, "restart-all-parallel.png")
    window.load(item)
    window.options["mode"].set("parallel")
    assert str(window.option_widgets["max_parallel"].cget("state")) == "normal"
    assert str(window.option_widgets["on_error"].cget("state")) == "readonly"
    assert window.options["max_parallel"].get() == "2"
    assert window.options["on_error"].get() == "weitere stoppen"
    window.destroy()


def test_two_managers_merge_changes_to_the_shared_library(app):
    restart = RestartTemplatesDialog(app, app._app_sessions[:1])
    status = RestartTemplatesDialog(app, app._app_sessions[:1], status_only=True)
    restart.name.set("Restart A")
    status.name.set("Status B")
    assert restart.save() and status.save()
    assert {i["name"] for i in app._initial_toolbar_search_texts["restart_templates"]["items"]} == {"Restart A", "Status B"}
    restart.destroy()
    status.destroy()


def test_changed_shared_template_blocks_stale_status_and_reload_reads_latest(app, monkeypatch):
    item = new_template(app._app_sessions[:1])
    app._initial_toolbar_search_texts["restart_templates"] = {"schema": 1, "items": [item]}
    status = RestartTemplatesDialog(app, [], status_only=True)
    status.load(item)
    changed = deepcopy(item)
    changed["targets"][0]["checks"] = [{"unit": "new.service", "expected": "active"}]
    app._initial_toolbar_search_texts["restart_templates"]["items"][0] = changed
    errors = []
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.messagebox.showerror", lambda *a, **k: errors.append(a))
    monkeypatch.setattr("ssh_manager_app.service_status.run_service_status", lambda *a: pytest.fail("Stale template must not run"))
    status.check_status()
    assert errors and "anderen Fenster" in errors[0][1]
    assert app._initial_toolbar_search_texts["restart_templates"]["items"][0] == changed
    monkeypatch.setattr(status, "discard_ok", lambda: True)
    status.list.selection_set(item["id"])
    status.open_selected()
    assert status.template == changed
    status.destroy()


def test_all_parallel_admits_every_host_despite_first_failure(app, monkeypatch):
    from ssh_manager_app.actions_restart import RestartResult
    from ssh_manager_app.actions_restart_templates import run_template
    item = new_template(app._app_sessions)
    item.update(mode="all_parallel", max_parallel=1, on_error="stop")
    for target in item["targets"]:
        target["user"] = "admin"
    seen = []
    monkeypatch.setattr("ssh_manager_app.actions_restart_templates.monitor_template_restart",
        lambda session, *a, **k: (seen.append(session.key), RestartResult("error", "synthetic failure"))[1])
    progress = run_template(app, validate_template(item), resolve_targets(item, app._app_sessions), "")
    finish_window(app, progress)
    assert set(seen) == {"one", "two", "three"}
    assert set(progress._states.values()) == {"error"}
    progress.destroy()


def test_status_results_each_service_no_checks_and_copy(app, monkeypatch):
    item = new_template(app._app_sessions)
    for target in item["targets"]:
        target["user"] = "admin"
    item["targets"][0]["checks"] = [{"unit": "a.service", "expected": "active"}, {"unit": "b.service", "expected": "inactive"}]
    item["targets"][1]["checks"] = [{"unit": "c.service", "expected": "active"}]
    calls = []
    def probe(session, user, unit):
        calls.append((session.key, unit))
        return "state", {"a.service": "active", "b.service": "failed", "c.service": "inactive"}[unit]
    monkeypatch.setattr("ssh_manager_app.service_status.probe_unit", probe)
    monkeypatch.setattr("ssh_manager_app.actions_restart._issue_reboot", lambda *a, **k: pytest.fail("Reboot forbidden"))
    window = run_service_status(app, "Shared template", resolve_targets(item, app._app_sessions))
    assert not str(window.transient()) and app.grab_current() is None
    finish_window(app, window)
    assert len(window.full_rows) == 4 and len(calls) == 3
    rows = list(window.full_rows.values())
    assert [row[4] for row in rows] == ["active", "failed", "inactive", "—"]
    assert rows[-1][-1] == "Keine Dienste hinterlegt"
    window.table_tools.copy("errors")
    copied = window.clipboard_get()
    assert "b.service" in copied and "c.service" in copied and "a.service" not in copied
    screenshot(window, "service-status-results.png")
    window.close()


def test_status_manager_reuses_templates_without_password_decryption(app, monkeypatch):
    item = new_template(app._app_sessions[:1])
    item.update(password_per_connection=True, password_protected="dpapi-user-v1:YWJj")
    item["targets"][0]["password_protected"] = "dpapi-user-v1:YWJj"
    app._initial_toolbar_search_texts["restart_templates"] = {"schema": 1, "items": [item]}
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.unseal", lambda *a: pytest.fail("Status must not decrypt sudo secrets"))
    window = RestartTemplatesDialog(app, [], status_only=True)
    window.load(item)
    called = []
    monkeypatch.setattr("ssh_manager_app.service_status.run_service_status", lambda *a, **k: called.append(a))
    window.check_status()
    assert len(called) == 1 and called[0][1] == item["name"]
    assert window.template["targets"][0]["password_protected"] == item["targets"][0]["password_protected"]
    assert all(not field.winfo_ismapped() for field in window.password_widgets)
    assert not window.option_widgets["mode"].winfo_ismapped()
    screenshot(window, "service-status-manager.png")
    window.destroy()


def test_all_parallel_has_no_128_host_limit():
    sessions = [Session(str(i), str(i), [], f"host{i}.invalid", "admin", source="app") for i in range(130)]
    item = new_template(sessions)
    item.update(mode="all_parallel", max_parallel=1, on_error="pause")
    assert execution_policy(validate_template(item)) == (130, "continue")


def test_cancel_limits_workers_to_eight_and_skips_waiting_hosts(app, monkeypatch):
    sessions = [Session(str(i), str(i), [], f"host{i}.invalid", "admin", source="app") for i in range(12)]
    checks = [{"unit": "a.service", "expected": "active"}, {"unit": "b.service", "expected": "active"}]
    release = threading.Event()
    started = []
    lock = threading.Lock()
    def probe(session, *args):
        with lock:
            started.append(session.key)
        release.wait(3)
        return "state", "active"
    monkeypatch.setattr("ssh_manager_app.service_status.probe_unit", probe)
    window = run_service_status(app, "Cancel", [(s, "admin", deepcopy(checks)) for s in sessions])
    def cancel():
        window.stop_checks()
        release.set()
    app.after(50, cancel)
    finish_window(app, window)
    assert 1 <= len(started) <= 8
    assert "Nicht geprüft" in window.outcomes.values()
    assert len(window.outcomes) == 24
    window.close()
