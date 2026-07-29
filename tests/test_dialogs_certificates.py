from types import SimpleNamespace
from unittest.mock import patch

from ssh_manager_app.dialogs_certificates import _sort_remote_entries, _ssh_folder_list_command
from ssh_manager_app.models import Session


def test_remote_folder_listing_uses_ssh_stdin_for_sudo_password_not_arguments():
    session = Session("app__srv", "App", [], "10.0.0.9", port=2222)
    completed = SimpleNamespace(returncode=0, stdout=b"d\t/etc/ssl/certs\nf\t/etc/ssl/old-cert.pem\n", stderr=b"")

    with patch("ssh_manager_app.dialogs_certificates.subprocess.run", return_value=completed) as run:
        folders, error = _ssh_folder_list_command(session, "deploy", "/etc/ssl", "secret")

    assert folders == [("d", "/etc/ssl/certs"), ("f", "/etc/ssl/old-cert.pem")]
    assert error == ""
    command = run.call_args.args[0]
    assert "secret" not in command
    assert command == ["ssh", "-o", "BatchMode=yes", "-p", "2222", "deploy@10.0.0.9", "bash", "-s"]
    remote_script = run.call_args.kwargs["input"].decode("utf-8")
    assert "\r" not in remote_script
    assert "SSH_MANAGER_SUDO_PASSWORD='secret'" in remote_script
    assert "-maxdepth 1" in remote_script
    assert "%y\\t%p" in remote_script


def test_remote_folder_listing_returns_ssh_errors():
    session = Session("app__srv", "App", [], "10.0.0.9")
    completed = SimpleNamespace(returncode=255, stdout=b"", stderr=b"Permission denied")

    with patch("ssh_manager_app.dialogs_certificates.subprocess.run", return_value=completed):
        folders, error = _ssh_folder_list_command(session, "deploy", "/etc", "")

    assert folders == []
    assert error == "Permission denied"


def test_remote_folder_entries_sort_folders_before_files_alphabetically():
    entries = [
        ("f", "/etc/ssl/z-old.pem"),
        ("d", "/etc/ssl/Zebra"),
        ("f", "/etc/ssl/a-cert.pem"),
        ("d", "/etc/ssl/alpha"),
        ("l", "/etc/ssl/current.pem"),
    ]

    assert _sort_remote_entries(entries) == [
        ("d", "/etc/ssl/alpha"),
        ("d", "/etc/ssl/Zebra"),
        ("f", "/etc/ssl/a-cert.pem"),
        ("l", "/etc/ssl/current.pem"),
        ("f", "/etc/ssl/z-old.pem"),
    ]
