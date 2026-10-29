import subprocess
import threading
from unittest.mock import patch

import pytest

from ssh_manager_app.actions_restart import _issue_reboot, monitor_server_restart, RestartResult
from ssh_manager_app.actions_restart_templates import monitor_template_restart, probe_unit
from ssh_manager_app.models import Session
from ssh_manager_app.remote_browser import list_services
from ssh_manager_app.service_status import check_unit
from ssh_manager_app.ssh_failures import SSH_AUTHENTICATION_HELP, SshQueryError, ssh_authentication_failed


def session():
    return Session("one", "one", [], "host.example", source="app")


def denied():
    return subprocess.CompletedProcess([], 255, "", "ops@host: Permission denied (publickey,password).")


@pytest.mark.parametrize("message", ["Permission denied (publickey).", "Authentication failed.",
    "Received disconnect: Too many authentication failures", "sign_and_send_pubkey: signing failed: agent refused operation"])
def test_known_ssh_authentication_failures(message):
    assert ssh_authentication_failed(255, message)


@pytest.mark.parametrize("code,message", [(1, "cat: Permission denied (file)"),
    (255, "Connection timed out"), (255, "Host key verification failed."),
    (1, "sudo: a password is required")])
def test_remote_permissions_sudo_and_network_are_not_ssh_authentication(code, message):
    assert not ssh_authentication_failed(code, message)


def test_service_browser_returns_actionable_safe_authentication_error():
    with patch("ssh_manager_app.remote_browser.subprocess.run", return_value=denied()):
        with pytest.raises(SshQueryError) as error:
            list_services(session(), "ops")
    assert str(error.value) == SSH_AUTHENTICATION_HELP
    assert "ops@host" not in str(error.value)


def test_mass_service_status_reports_key_help_instead_of_timeout():
    with patch("ssh_manager_app.actions_restart_templates._run_ssh", return_value=denied()):
        assert probe_unit(session(), "ops", "a.service") == ("error", SSH_AUTHENTICATION_HELP)
        result = check_unit(session(), "ops", {"unit": "a.service", "expected": "active"})
    assert result.outcome == "Fehler" and result.detail == SSH_AUTHENTICATION_HELP
    assert result.actual == "nicht geprüft"


def test_authentication_failure_issuing_reboot_is_definitive():
    with patch("ssh_manager_app.actions_restart._run_ssh", return_value=denied()):
        assert _issue_reboot(session(), "ops", "sudo-secret") == (False, False, SSH_AUTHENTICATION_HELP)


def test_restart_authentication_preflight_never_reboots():
    with patch("ssh_manager_app.actions_restart._run_ssh", return_value=denied()), \
         patch("ssh_manager_app.actions_restart._issue_reboot") as reboot:
        result = monitor_server_restart(session(), "ops", "", "", 30, threading.Event(), lambda *_: None)
    assert result == RestartResult("error", SSH_AUTHENTICATION_HELP)
    reboot.assert_not_called()


def test_restart_stops_when_authentication_is_rejected_after_reboot():
    with patch("ssh_manager_app.actions_restart._read_boot_id", side_effect=[
        (True, "old", ""), (False, None, SSH_AUTHENTICATION_HELP)]), \
         patch("ssh_manager_app.actions_restart._issue_reboot", return_value=(True, False, "")):
        result = monitor_server_restart(session(), "ops", "", "", 30, threading.Event(), lambda *_: None)
    assert result == RestartResult("error", SSH_AUTHENTICATION_HELP)


def test_template_service_monitor_stops_on_authentication_failure_after_reboot():
    with patch("ssh_manager_app.actions_restart_templates.probe_unit", side_effect=[
        ("state", "active"), ("error", SSH_AUTHENTICATION_HELP)]), \
         patch("ssh_manager_app.actions_restart_templates.monitor_server_restart", return_value=RestartResult("online", "Boot-ID geändert")):
        result = monitor_template_restart(session(), "ops", "", [{"unit": "a.service", "expected": "active"}],
            30, 30, threading.Event(), lambda *_: None)
    assert result.status == "error" and SSH_AUTHENTICATION_HELP in result.detail
