from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import socket
import pytest

from ssh_manager_app.diagnosis import diagnose_session, diagnose_many, parse_ports
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


@pytest.mark.parametrize("value", ["0", "65536", "80-1", "1-65535", "abc", "80; rm", "-22"])
def test_invalid_or_unbounded_scan_is_rejected(value):
    with pytest.raises(ValueError):
        parse_ports(value)


def test_ports_accept_list_and_small_ranges_without_duplicates():
    assert parse_ports("80,443; 8000-8002 80") == (80, 443, 8000, 8001, 8002)
    assert parse_ports("") == ()


def test_extra_ports_reach_actual_requested_ipv6_port_and_skip_duplicate_ssh():
    session = target()
    session.hostname = "::1"
    address = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 22, 0, 0))
    with patch("socket.getaddrinfo", return_value=[address]), patch("socket.socket") as tcp:
        checks = diagnose_session(session, ports=(22, 443))
    connects = tcp.return_value.__enter__.return_value.connect.call_args_list
    assert [call.args[0] for call in connects] == [("::1", 22, 0, 0), ("::1", 443, 0, 0)]
    assert checks[1][1] == "nicht nötig"
    assert next(check for check in checks if check[0] == "TCP-Port 443")[1] == "erfolgreich"


def test_explicit_extra_ports_are_direct_even_with_ssh_proxy():
    config = SimpleNamespace(returncode=0, stdout="hostname internal.test\nport 2222\nproxyjump gateway\n")
    address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 2222))
    with patch("ssh_manager_app.diagnosis.shutil.which", return_value="ssh"), patch("subprocess.run", return_value=config), patch("socket.getaddrinfo", return_value=[address]), patch("socket.socket") as tcp:
        checks = diagnose_session(target("ssh_config"), ports=(443,))
    tcp.return_value.__enter__.return_value.connect.assert_called_once_with(("127.0.0.1", 443))
    assert "ohne SSH-Proxy" in next(check for check in checks if check[0] == "TCP-Port 443")[2]
