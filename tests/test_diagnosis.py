from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import socket

from ssh_manager_app.diagnosis import diagnose_session, diagnose_many
from ssh_manager_app.models import Session


def target(source="app"):
    return Session("id", "host", [], "host.test", "ops", source=source)


def test_open_port_does_not_claim_authentication_or_need_local_ssh():
    with patch("ssh_manager_app.diagnosis.shutil.which", return_value=None), patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 22))]), patch("socket.socket"):
        checks = diagnose_session(target())
    assert checks[0][1] == "fehlt"
    assert checks[-2][1] == "erfolgreich"
    assert checks[-1][1] == "nicht geprüft"


def test_alias_proxy_skips_direct_tcp_but_tests_actual_login():
    config = SimpleNamespace(returncode=0, stdout="hostname internal.test\nport 2222\nproxyjump gateway\n")
    login = SimpleNamespace(returncode=255)
    with patch("ssh_manager_app.diagnosis.shutil.which", return_value="ssh.exe"), patch("socket.getaddrinfo", side_effect=socket.gaierror), patch("socket.socket") as tcp, patch("subprocess.run", side_effect=[config, login]) as run:
        checks = diagnose_session(target("ssh_config"), authenticate=True)
    tcp.assert_not_called()
    assert next(check for check in checks if check[0] == "TCP zum Ziel")[1] == "nicht geprüft"
    assert checks[-1][1] == "fehlgeschlagen"
    argv = run.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in argv
    assert "UpdateHostKeys=no" in argv
    assert "ClearAllForwardings=yes" in argv
    assert argv[-1] == "true"
    assert "--" in argv


def test_no_dns_means_no_tcp_no_unrequested_login():
    with patch("ssh_manager_app.diagnosis.shutil.which", return_value="ssh"), patch("socket.getaddrinfo", side_effect=socket.gaierror), patch("socket.socket") as tcp, patch("subprocess.run") as run:
        checks = diagnose_session(target())
    tcp.assert_not_called()
    run.assert_not_called()
    assert checks[1][1] == "fehlgeschlagen"


def test_parallel_checks_cap_worker_count_and_keep_effective_user():
    with patch("ssh_manager_app.diagnosis.ThreadPoolExecutor") as executor, patch("ssh_manager_app.diagnosis.diagnose_session", return_value=[]) as diagnose:
        executor.return_value.__enter__.return_value.map.side_effect = lambda fn, items: map(fn, items)
        assert diagnose_many([target()], "fallback", False)[0][0].key == "id"
    executor.assert_called_once_with(max_workers=8)
    diagnose.assert_called_once_with(target(), "ops", authenticate=False)
