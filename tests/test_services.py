import pytest
import subprocess
from unittest.mock import patch

from ssh_manager_app.services import service_command, SERVICE_NOT_FOUND


@pytest.mark.parametrize("unit", ["nginx;reboot", "-bad", "a\nreboot", "$(reboot)", ""])
def test_unit_input_cannot_add_commands(unit):
    with pytest.raises(ValueError):
        service_command("restart", unit)


def test_restart_is_only_the_service_and_checks_active_state():
    command = service_command("restart", "nginx", sudo=True)
    assert command.endswith("sudo systemctl restart -- nginx.service && systemctl is-active -- nginx.service")
    assert "sudo systemctl show --property=LoadState --value -- nginx.service" in command
    assert "reboot" not in command


def test_logs_are_bounded_and_status_inactive_is_valid_query():
    assert "-n 200 --unit=wildfly.service" in service_command("logs", "wildfly.service", 200)
    with pytest.raises(ValueError):
        service_command("logs", "nginx", 1001)
    assert "status -eq 3" in service_command("status", "nginx")


@pytest.mark.parametrize("action", ["status", "logs", "restart"])
@pytest.mark.parametrize("load_state, expected", [("loaded", 0), ("not-found", SERVICE_NOT_FOUND), ("error", 5)])
def test_local_bash_checks_missing_service_before_action(tmp_path, action, load_state, expected):
    from ssh_manager_app.core import _find_git_bash
    script = tmp_path / "service.sh"
    fake = f'''systemctl() {{
      if [ "$1" = show ]; then
        if [ '{load_state}' = error ]; then return 5; fi
        printf '%s\\n' '{load_state}'; return 0
      fi
      printf '%s\\n' ACTION_STARTED
      if [ "$1" = status ]; then return 3; fi
      return 0
    }}
    journalctl() {{ printf '%s\\n' ACTION_STARTED; }}
    '''
    script.write_text(fake + service_command(action, "nginx") + "\n", encoding="utf-8", newline="\n")
    result = subprocess.run([_find_git_bash(), str(script)], capture_output=True, text=True, timeout=10)
    assert result.returncode == expected
    assert ("ACTION_STARTED" in result.stdout) == (load_state == "loaded")
    assert ("Dienst wurde nicht gefunden" in result.stdout) == (load_state == "not-found")


def test_service_terminal_receipt_reports_missing_unit_per_host(tmp_path):
    from ssh_manager_app import core
    from ssh_manager_app.models import Session
    from ssh_manager_app.operation_results import OperationJob, track_results
    import shlex
    sessions = [Session("a", "Alpha", [], "a.invalid", "ops"), Session("b", "Beta", [], "b.invalid", "ops")]
    job = OperationJob(sessions, "Dienste", directory=tmp_path, exit_labels={SERVICE_NOT_FOUND: "Dienst wurde nicht gefunden"})
    captured, fake_paths = [], []
    for state in ("loaded", "not-found"):
        remote = tmp_path / f"{state}.sh"
        remote.write_text(f"systemctl() {{ if [ \"$1\" = show ]; then echo {state}; fi; return 0; }}\n" + service_command("status", "nginx"), encoding="utf-8", newline="\n")
        fake_paths.append("bash " + shlex.quote(remote.as_posix()))
    with track_results(job), patch.object(core, "_build_ssh_command", side_effect=fake_paths), patch.object(core, "_write_temp_bash_script", side_effect=lambda prefix, content: captured.append(content) or "dummy.sh"):
        core.build_remote_command_wt_command([(session, "ops", service_command("status", "nginx")) for session in sessions], close_on_success=True)
    for i, content in enumerate(captured):
        local = tmp_path / f"local-{i}.sh"
        local.write_text(content, encoding="utf-8", newline="\n")
        subprocess.run([core._find_git_bash(), str(local)], input="\n", text=True, capture_output=True, timeout=10)
    assert job.poll()["a"] == ("success", "Exit-Code 0")
    assert job.poll()["b"] == ("failed", "Dienst wurde nicht gefunden")
    assert job.failed_sessions() == [sessions[1]]
