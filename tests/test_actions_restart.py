from __future__ import annotations

import subprocess
import threading
from unittest.mock import MagicMock, patch

from ssh_manager_app.actions_restart import (
    RestartResult,
    _issue_reboot,
    _read_boot_id,
    _run_ssh,
    _service_load_state,
    _ssh_args,
    monitor_server_restart,
    restart_servers,
)
from ssh_manager_app.models import AppSettings, Session


def _session(*, source: str = "app", port: int = 22) -> Session:
    return Session("s1", "Server 1", ["Prod"], "server.example", username="ops", port=port, source=source)


def _clock(*values: float):
    iterator = iter(values)
    return lambda: next(iterator)


def test_ssh_args_support_direct_host_port_and_ssh_config_alias():
    direct = _session(port=2222)
    alias = Session("alias", "prod-alias", [], "10.0.0.8", source="ssh_config")

    direct_args = _ssh_args(direct, "deploy", connect_timeout=7)
    alias_args = _ssh_args(alias, "ignored", connect_timeout=7)

    assert direct_args[-4:] == ["-p", "2222", "--", "deploy@server.example"]
    assert "ConnectTimeout=7" in direct_args
    assert alias_args[-1] == "prod-alias"
    assert "10.0.0.8" not in alias_args
    assert "ignored" not in alias_args


def test_issue_reboot_sends_password_only_via_stdin():
    completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    with patch("ssh_manager_app.actions_restart._run_ssh", return_value=completed) as run:
        result = _issue_reboot(_session(), "ops", "super-secret")

    assert result == (True, False, "")
    args, kwargs = run.call_args
    assert args[2] == "sudo -S -p '' reboot"
    assert "super-secret" not in repr(args)
    assert kwargs["input_text"] == "super-secret\n"


def test_issue_reboot_without_password_uses_noninteractive_sudo():
    completed = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    with patch("ssh_manager_app.actions_restart._run_ssh", return_value=completed) as run:
        _issue_reboot(_session(), "ops", "")

    assert run.call_args.args[2] == "sudo -n -p '' reboot"
    assert run.call_args.kwargs["input_text"] is None


def test_run_ssh_uses_argument_list_without_shell_and_keeps_stdin_separate():
    completed = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
    with patch("ssh_manager_app.actions_restart.subprocess.run", return_value=completed) as run:
        result = _run_ssh(_session(port=2222), "ops", "true", input_text="stdin-secret", timeout=9)

    assert result is completed
    command = run.call_args.args[0]
    assert command[-5:] == ["-p", "2222", "--", "ops@server.example", "true"]
    assert "stdin-secret" not in repr(command)
    assert run.call_args.kwargs["input"] == "stdin-secret"
    assert "shell" not in run.call_args.kwargs


def test_service_name_is_shell_quoted_for_remote_check():
    completed = subprocess.CompletedProcess([], 0, stdout="loaded\n", stderr="")
    with patch("ssh_manager_app.actions_restart._run_ssh", return_value=completed) as run:
        connected, state, error = _service_load_state(_session(), "ops", "safe.service; reboot")

    assert (connected, state, error) == (True, "loaded", "")
    assert run.call_args.args[2].endswith("'safe.service; reboot'")


def test_read_boot_id_ignores_shell_banner_and_parses_linux_uuid():
    boot_id = "12345678-1234-1234-1234-123456789abc"
    completed = subprocess.CompletedProcess(
        [],
        0,
        stdout=f"Long shell banner that is not a boot id\n__SSH_MANAGER_CONNECTED__\n{boot_id}\n",
        stderr="",
    )
    with patch("ssh_manager_app.actions_restart._run_ssh", return_value=completed):
        result = _read_boot_id(_session(), "ops")

    assert result == (True, boot_id, "")


def test_monitor_restart_observes_ssh_down_then_stable_return():
    reports = []
    reads = [
        (True, "old-boot-id-0001", ""),
        (False, None, "offline"),
        (True, "new-boot-id-0002", ""),
        (True, "new-boot-id-0002", ""),
    ]
    with patch("ssh_manager_app.actions_restart._read_boot_id", side_effect=reads), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(True, False, "")):
        result = monitor_server_restart(
            _session(), "ops", "secret", "", 300, threading.Event(),
            lambda state, detail: reports.append((state, detail)),
            poll_interval_seconds=0,
            monotonic=_clock(0, 1, 2, 3),
        )

    assert result == RestartResult("online", "Neustart bestätigt; SSH ist wieder erreichbar")
    assert [state for state, _detail in reports] == ["preflight", "restarting", "waiting_ssh", "waiting_ssh"]


def test_monitor_restart_accepts_changed_boot_id_when_short_outage_was_missed():
    reads = [
        (True, "old-boot-id-0001", ""),
        (True, "new-boot-id-0002", ""),
        (True, "new-boot-id-0002", ""),
    ]
    with patch("ssh_manager_app.actions_restart._read_boot_id", side_effect=reads), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(True, False, "")):
        result = monitor_server_restart(
            _session(), "ops", "", "", 300, threading.Event(), MagicMock(),
            poll_interval_seconds=0,
            monotonic=_clock(0, 1, 2),
        )

    assert result.status == "online"


def test_monitor_restart_waits_until_optional_service_is_active():
    reports = []
    reads = [
        (True, "old-boot-id-0001", ""),
        (False, None, "offline"),
        (True, "new-boot-id-0002", ""),
        (True, "new-boot-id-0002", ""),
        (True, "new-boot-id-0002", ""),
    ]
    with patch("ssh_manager_app.actions_restart._read_boot_id", side_effect=reads), \
         patch("ssh_manager_app.actions_restart._service_load_state", return_value=(True, "loaded", "")), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(True, False, "")), \
         patch("ssh_manager_app.actions_restart._service_active", side_effect=[(True, False, "activating"), (True, True, "active")]):
        result = monitor_server_restart(
            _session(), "ops", "secret", "wildfly.service", 300, threading.Event(),
            lambda state, detail: reports.append((state, detail)),
            poll_interval_seconds=0,
            monotonic=_clock(0, 1, 2, 3, 4),
        )

    assert result == RestartResult("online", "SSH und wildfly.service sind verfügbar")
    assert ("waiting_service", "wildfly.service: activating") in reports


def test_monitor_restart_rejects_unknown_service_before_reboot():
    with patch("ssh_manager_app.actions_restart._read_boot_id", return_value=(True, "old", "")), \
         patch("ssh_manager_app.actions_restart._service_load_state", return_value=(True, "not-found", "systemd-Unit 'missing.service' ist nicht vorhanden.")), \
         patch("ssh_manager_app.actions_restart._issue_reboot") as issue:
        result = monitor_server_restart(
            _session(), "ops", "secret", "missing.service", 300, threading.Event(), MagicMock(),
        )

    assert result.status == "error"
    assert "nicht vorhanden" in result.detail
    issue.assert_not_called()


def test_monitor_restart_reports_sudo_failure_without_polling():
    with patch("ssh_manager_app.actions_restart._read_boot_id", return_value=(True, "old", "")), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(False, False, "Sorry, try again.")):
        result = monitor_server_restart(
            _session(), "ops", "wrong", "", 300, threading.Event(), MagicMock(),
        )

    assert result == RestartResult("error", "Sorry, try again.")


def test_monitor_restart_times_out_when_ssh_does_not_return():
    reads = [(True, "old", ""), (False, None, "offline")]
    with patch("ssh_manager_app.actions_restart._read_boot_id", side_effect=reads), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(True, False, "")):
        result = monitor_server_restart(
            _session(), "ops", "", "", 300, threading.Event(), MagicMock(),
            poll_interval_seconds=0,
            monotonic=_clock(0, 1, 301),
        )

    assert result == RestartResult("timeout", "SSH wurde innerhalb der Wartezeit nicht wieder erreichbar")


def test_monitor_restart_can_be_stopped_before_reboot_is_issued():
    cancel_event = threading.Event()
    cancel_event.set()
    with patch("ssh_manager_app.actions_restart._read_boot_id", return_value=(True, "old", "")), \
         patch("ssh_manager_app.actions_restart._issue_reboot") as issue:
        result = monitor_server_restart(
            _session(), "ops", "", "", 300, cancel_event, MagicMock(),
        )

    assert result == RestartResult("stopped", "Neustart wurde noch nicht ausgelöst")
    issue.assert_not_called()


def test_restart_servers_warns_when_selection_has_no_runnable_host():
    app = MagicMock()
    app.settings = AppSettings()
    with patch("ssh_manager_app.actions_restart.messagebox.showwarning") as warning, \
         patch("ssh_manager_app.actions_restart.ServerRestartDialog") as dialog:
        restart_servers(app, [Session("empty", "Ordner", [], "")])

    warning.assert_called_once_with("Keine Hosts", "Keine ausführbaren Hosts ausgewählt.", parent=app)
    dialog.assert_not_called()
