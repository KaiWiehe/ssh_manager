from types import SimpleNamespace
from unittest.mock import patch

from ssh_manager_app.dialogs_certificates import _ssh_folder_list_command
from ssh_manager_app.models import Session


def test_remote_folder_listing_uses_ssh_stdin_for_sudo_password_not_arguments():
    session = Session("app__srv", "App", [], "10.0.0.9", port=2222)
    completed = SimpleNamespace(returncode=0, stdout="/etc/ssl/certs\n/etc/ssl/private\n", stderr="")

    with patch("ssh_manager_app.dialogs_certificates.subprocess.run", return_value=completed) as run:
        folders, error = _ssh_folder_list_command(session, "deploy", "/etc/ssl", "secret")

    assert folders == ["/etc/ssl/certs", "/etc/ssl/private"]
    assert error == ""
    command = run.call_args.args[0]
    assert "secret" not in command
    assert command == ["ssh", "-o", "BatchMode=yes", "-p", "2222", "deploy@10.0.0.9", "bash", "-s"]
    remote_script = run.call_args.kwargs["input"]
    assert "SSH_MANAGER_SUDO_PASSWORD='secret'" in remote_script
    assert "-maxdepth 1" in remote_script


def test_remote_folder_listing_returns_ssh_errors():
    session = Session("app__srv", "App", [], "10.0.0.9")
    completed = SimpleNamespace(returncode=255, stdout="", stderr="Permission denied")

    with patch("ssh_manager_app.dialogs_certificates.subprocess.run", return_value=completed):
        folders, error = _ssh_folder_list_command(session, "deploy", "/etc", "")

    assert folders == []
    assert error == "Permission denied"
