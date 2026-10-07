import pytest

from ssh_manager_app.services import service_command


@pytest.mark.parametrize("unit", ["nginx;reboot", "-bad", "a\nreboot", "$(reboot)", ""])
def test_unit_input_cannot_add_commands(unit):
    with pytest.raises(ValueError):
        service_command("restart", unit)


def test_restart_is_only_the_service_and_checks_active_state():
    command = service_command("restart", "nginx", sudo=True)
    assert command == "sudo systemctl restart -- nginx.service && systemctl is-active -- nginx.service"
    assert "reboot" not in command


def test_logs_are_bounded_and_status_inactive_is_valid_query():
    assert "-n 200 --unit=wildfly.service" in service_command("logs", "wildfly.service", 200)
    with pytest.raises(ValueError):
        service_command("logs", "nginx", 1001)
    assert "status -eq 3" in service_command("status", "nginx")
