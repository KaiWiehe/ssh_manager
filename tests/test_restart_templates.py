from copy import deepcopy
import csv
import io
import json
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ssh_manager_app import storage
from ssh_manager_app.actions_restart import RestartResult, _ssh_args
from ssh_manager_app.actions_restart_templates import monitor_template_restart, probe_unit
from ssh_manager_app.models import Session, default_settings, settings_to_dict
from ssh_manager_app.restart_templates import (RestartScheduler, new_template, resolve_targets,
    service_check, target_fingerprint, validate_library, validate_template)
from ssh_manager_app.result_table import table_text
from ssh_manager_app.ssh_utils import ssh_argv


def session(key="one", **kwargs):
    return Session(key, key, [], key + ".example", source="app", **kwargs)


def template():
    return new_template([session(username="ops"), session("two")])


def test_validation_drafts_and_execution_and_secrets():
    item = template()
    item["sudo_password"] = "secret"
    item["targets"][0]["password"] = "secret"
    checked = validate_template(item)
    assert "secret" not in json.dumps(checked)
    with pytest.raises(ValueError, match="Benutzer fehlt"):
        validate_template(item, runnable=True)
    item["targets"][1]["user"] = "admin"
    assert validate_template(item, runnable=True)["targets"][1]["user"] == "admin"


@pytest.mark.parametrize("unit", ["-evil", "a;reboot", "a\nb", "a b", "$(reboot)"])
def test_invalid_service_never_becomes_command(unit):
    with pytest.raises(ValueError):
        service_check(unit)


@pytest.mark.parametrize("field,value", [("mode", "bad"), ("on_error", "bad"),
    ("max_parallel", 0), ("reboot_timeout", True), ("service_timeout", 3601)])
def test_invalid_execution_options(field, value):
    item = template()
    item[field] = value
    with pytest.raises(ValueError):
        validate_template(item)


def test_duplicate_units_targets_and_names_rejected():
    item = template()
    item["targets"][0]["checks"] = [service_check("nginx"), service_check("nginx", "inactive")]
    with pytest.raises(ValueError):
        validate_template(item)
    item = template()
    item["targets"].append(deepcopy(item["targets"][0]))
    with pytest.raises(ValueError):
        validate_template(item)
    one, two = template(), template()
    with pytest.raises(ValueError):
        validate_library({"schema": 1, "items": [one, two]})


def test_latest_targets_explicit_user_and_alias_are_preserved():
    item = template()
    live = session(username="other", port=2222)
    live.hostname = "new.example"
    resolved = resolve_targets(item, [live, session("two")])
    assert resolved[0][0].hostname == "new.example"
    assert resolved[0][1] == "ops"
    assert resolved[0][0].port == 2222
    before = target_fingerprint(resolved)
    live.port = 3333
    assert target_fingerprint(resolve_targets(item, [live, session("two")])) != before
    with pytest.raises(ValueError, match="fehlt"):
        resolve_targets(item, [])
    with pytest.raises(ValueError, match="eindeutig"):
        resolve_targets(item, [live, live, session("two")])
    alias = Session("one", "test-alias", [], "actual.example", source="ssh_config")
    resolved_alias = resolve_targets(item, [alias, session("two")])[0][0]
    assert _ssh_args(resolved_alias, "ops")[-4:] == ["-l", "ops", "--", "test-alias"]
    assert ssh_argv(resolved_alias, "ops")[-4:] == ["-l", "ops", "--", "test-alias"]
    assert "-l" not in _ssh_args(alias, "ignored")


def test_templates_roundtrip_and_backup_validation(tmp_path, monkeypatch):
    for field, name in (("_STATE_FILE", "ui_state.json"), ("_SETTINGS_FILE", "settings.json"),
                        ("_APP_SESSIONS_FILE", "app_sessions.json"), ("_NOTES_FILE", "notes.json")):
        monkeypatch.setattr(storage, field, tmp_path / name)
    library = {"schema": 1, "items": [template()]}
    storage.save_ui_state(set(), {}, {"restart_templates": library})
    assert storage.load_ui_state()[2]["restart_templates"] == library
    storage.save_settings(default_settings())
    storage.save_app_sessions([])
    storage.save_notes({})
    storage.create_app_backup(tmp_path / "backup.json")
    payload = storage.read_app_backup(tmp_path / "backup.json")
    assert payload["documents"]["ui_state.json"]["toolbar_search_texts"]["restart_templates"] == library
    payload["documents"]["ui_state.json"]["toolbar_search_texts"]["restart_templates"]["schema"] = 99
    with pytest.raises(ValueError):
        storage.validate_app_backup(payload)


def test_current_ui_state_keeps_templates():
    from ssh_manager_app.actions_ui import current_ui_state
    from unittest.mock import MagicMock
    app = SimpleNamespace(_initial_toolbar_search_texts={"restart_templates": {"schema": 1, "items": [template()]}},
                          _search_var=MagicMock(), _search_history=[], _tree=MagicMock())
    assert current_ui_state(app)[2]["restart_templates"] == app._initial_toolbar_search_texts["restart_templates"]


def test_unit_probe_distinguishes_failed_inactive_missing_and_connection():
    def completed(out, code=0):
        return subprocess.CompletedProcess([], code, out, "")
    with patch("ssh_manager_app.actions_restart_templates._run_ssh", side_effect=[
        completed("LoadState=loaded\nActiveState=failed\n"), completed("LoadState=loaded\nActiveState=inactive\n"),
        completed("LoadState=not-found\nActiveState=inactive\n", 1), completed("", 255)]):
        assert probe_unit(session(), "ops", "a.service") == ("state", "failed")
        assert probe_unit(session(), "ops", "a.service") == ("state", "inactive")
        assert probe_unit(session(), "ops", "a.service")[0] == "error"
        assert probe_unit(session(), "ops", "a.service")[0] == "connection"


def test_preflight_failure_never_reboots():
    with patch("ssh_manager_app.actions_restart_templates.probe_unit", return_value=("error", "Dienst nicht vorhanden")), \
         patch("ssh_manager_app.actions_restart_templates.monitor_server_restart") as reboot:
        result = monitor_template_restart(session(), "ops", "", [service_check("missing")], 10, 5,
                                          threading.Event(), lambda *_: None)
    assert result.status == "error"
    assert "kein Neustart" in result.detail
    reboot.assert_not_called()


def test_multiple_services_failed_does_not_satisfy_inactive_but_can_recover():
    checks = [service_check("a"), service_check("b", "inactive")]
    # two preflights, then failed/active, then active/inactive
    values = [("state", "inactive"), ("state", "active"), ("state", "failed"),
              ("state", "failed"), ("state", "active"), ("state", "inactive")]
    reports = []
    with patch("ssh_manager_app.actions_restart_templates.probe_unit", side_effect=values), \
         patch("ssh_manager_app.actions_restart_templates.monitor_server_restart", return_value=RestartResult("online", "Boot-ID geändert")):
        result = monitor_template_restart(session(), "ops", "", checks, 20, 10, threading.Event(),
            lambda *args: reports.append(args), poll_interval=0)
    assert result.status == "online"
    assert "b.service: Soll inactive, Ist inactive" in result.detail
    assert any("Ist failed" in detail for _, detail in reports)


def test_service_deadline_starts_after_reboot_and_reports_every_unit():
    clock = [0]
    def reboot(*args, **kwargs):
        clock[0] = 1000  # service deadline must be relative to this moment
        return RestartResult("online", "Boot-ID geändert")
    def probe(*args, **kwargs):
        clock[0] += 1
        return "state", "failed"
    with patch("ssh_manager_app.actions_restart_templates.probe_unit", side_effect=probe), \
         patch("ssh_manager_app.actions_restart_templates.monitor_server_restart", side_effect=reboot):
        result = monitor_template_restart(session(), "ops", "", [service_check("a"), service_check("b", "inactive")],
            10, 3, threading.Event(), lambda *_: None, monotonic=lambda: clock[0], poll_interval=0)
    assert result.status == "timeout"
    assert "a.service" in result.detail and "b.service" in result.detail
    assert clock[0] >= 1003


def test_scheduler_pause_allows_running_work_but_admits_nothing_until_decision():
    release = threading.Event()
    failed = threading.Event()
    started = []
    def work(target):
        started.append(target)
        if target == 1:
            failed.set()
            return RestartResult("error", "bad")
        release.wait(2)
        return RestartResult("online", "ok")
    scheduler = RestartScheduler([0, 1, 2], 2, "pause", work)
    scheduler.tick()
    assert failed.wait(2)
    # Receiving the result establishes that the worker has set the admission gate.
    scheduler.events.get(timeout=2)
    scheduler.tick()
    assert scheduler.paused and started == [0, 1]
    release.set()
    scheduler.events.get(timeout=2)
    scheduler.tick()
    assert started == [0, 1]
    scheduler.decide(True)
    scheduler.tick()
    scheduler.events.get(timeout=2)
    assert started == [0, 1, 2] and scheduler.done


@pytest.mark.parametrize("policy", ["stop", "continue"])
def test_serial_scheduler_error_policy(policy):
    started = []
    def work(target):
        started.append(target)
        return RestartResult("error" if target == 0 else "online", "result")
    scheduler = RestartScheduler([0, 1], 1, policy, work)
    scheduler.tick()
    assert scheduler.events.get(timeout=2)[0] == 0
    scheduler.tick()
    target, result = scheduler.events.get(timeout=2)
    assert target == 1
    assert result.status == ("not_started" if policy == "stop" else "online")
    assert started == ([0] if policy == "stop" else [0, 1])
    assert scheduler.done


def test_scheduler_multiple_failures_remain_one_pause_and_stop_skips_queue():
    scheduler = RestartScheduler([0, 1, 2], 2, "pause", lambda _: RestartResult("error", "bad"))
    scheduler.tick()
    scheduler.events.get(timeout=2)
    scheduler.events.get(timeout=2)
    assert len(scheduler.failures) == 2 and scheduler.paused
    scheduler.decide(False)
    scheduler.tick()
    assert scheduler.events.get(timeout=2)[1].status == "not_started"
    assert scheduler.done


def test_copy_keeps_complete_multiline_fields():
    details = "Long error " + "x" * 1000 + "\nnginx.service\tfailed"
    text = table_text(["Server", "Details"], [["one", details]])
    rows = list(csv.reader(io.StringIO(text), delimiter="\t"))
    assert rows == [["Server", "Details"], ["one", details]]


def test_template_boot_deadline_rejects_probe_returning_late():
    from ssh_manager_app.actions_restart import monitor_server_restart
    clock = [0]
    reads = iter([(True, "old", ""), (True, "new", ""), (True, "new", "")])
    timeouts = []
    def read(*args, **kwargs):
        value = next(reads)
        if kwargs:
            timeouts.append(kwargs["timeout"])
            clock[0] += .5 if len(timeouts) == 1 else 8
        return value
    with patch("ssh_manager_app.actions_restart._read_boot_id", side_effect=read), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(True, False, "")) as issue:
        result = monitor_server_restart(session(), "ops", "", "", 1, threading.Event(), lambda *_: None,
            evidence_detail=True, monotonic=lambda: clock[0], poll_interval_seconds=0)
    assert result.status == "timeout"
    assert timeouts == [1, .5]
    assert issue.call_args.kwargs["timeout"] == 1
