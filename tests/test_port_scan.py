import errno
import socket
import threading
import time
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ssh_manager_app.models import Session
from ssh_manager_app.port_scan import scan_address, scan_addresses, probe_port, FullPortScanDialog


ADDRESS = (socket.AF_INET, socket.SOCK_STREAM, 6, ("127.0.0.1", 0))


@pytest.mark.parametrize("code, result", [(0, "open"), (errno.ECONNREFUSED, "refused"), (10061, "refused"), (errno.ETIMEDOUT, "timeout"), (10060, "timeout"), (errno.ENETUNREACH, "error")])
def test_tcp_result_classification_and_close_without_sending(code, result):
    with patch("ssh_manager_app.port_scan.socket.socket") as constructor:
        connection = constructor.return_value.__enter__.return_value
        connection.connect_ex.return_value = code
        assert probe_port(ADDRESS, 443, 1) == result
    connection.connect_ex.assert_called_once_with(("127.0.0.1", 443))
    connection.send.assert_not_called()
    connection.recv.assert_not_called()
    constructor.return_value.__exit__.assert_called_once()


def test_scan_live_local_listener_only():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert probe_port(ADDRESS, listener.getsockname()[1], 1) == "open"


def test_scan_covers_requested_ports_and_separates_outcomes():
    events = []
    with patch("ssh_manager_app.port_scan.probe_port", side_effect=["open", "refused", "timeout", "error"]) as probe:
        done, total, counts = scan_address(ADDRESS, threading.Event(), lambda *event: events.append(event), ports=range(1, 5), rate=100, workers=1)
    assert (done, total, counts) == (4, 4, dict(open=1, refused=1, timeout=1, error=1))
    assert [call.args[1] for call in probe.call_args_list] == [1, 2, 3, 4]
    assert ("open", 1) in events
    assert events[-1] == ("progress", (done, total, counts))


def test_rate_limit_no_burst_and_bounded_parallelism():
    lock = threading.Lock()
    starts, active, maximum = [], 0, 0

    def probe(*_args):
        nonlocal active, maximum
        with lock:
            starts.append(time.monotonic())
            active += 1
            maximum = max(maximum, active)
        time.sleep(.08)
        with lock:
            active -= 1
        return "refused"

    with patch("ssh_manager_app.port_scan.probe_port", side_effect=probe):
        scan_address(ADDRESS, threading.Event(), lambda *_: None, ports=range(1, 7), rate=50, workers=2)
    assert maximum <= 2
    assert starts[-1] - starts[0] >= .1


def test_cancel_keeps_partial_verified_open_results_and_stops_new_starts():
    cancel = threading.Event()
    events = []

    def report(kind, value):
        events.append((kind, value))
        if kind == "open":
            cancel.set()

    with patch("ssh_manager_app.port_scan.probe_port", return_value="open") as probe:
        done, total, counts = scan_address(ADDRESS, cancel, report, ports=range(1, 65536), rate=100, workers=1)
    assert done == counts["open"] == 1 and total == 65535
    assert probe.call_count == 1
    assert ("open", 1) in events


def test_scan_all_65535_ports_is_default_without_materializing_or_starting_them():
    cancel = threading.Event()
    cancel.set()
    with patch("ssh_manager_app.port_scan.probe_port") as probe:
        done, total, counts = scan_address(ADDRESS, cancel, lambda *_: None)
    assert done == 0 and total == 65535
    probe.assert_not_called()


def test_alias_dns_uses_resolved_host_and_deduplicates_all_ips():
    session = Session("a", "prod", [], "alias.invalid", source="ssh_config")
    config = SimpleNamespace(returncode=0, stdout="hostname real.invalid\nproxyjump gateway\n")
    one = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 0))
    two = (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 0, 0, 0))
    with patch("ssh_manager_app.port_scan.subprocess.run", return_value=config) as run, patch("socket.getaddrinfo", return_value=[one, one, two]) as dns:
        addresses = scan_addresses(session, "ops")
    assert len(addresses) == 2
    dns.assert_called_once_with("real.invalid", 0, type=socket.SOCK_STREAM)
    assert run.call_args.args[0] == ["ssh", "-G", "--", "prod"]


@pytest.fixture
def root():
    root = tk.Tk()
    root.geometry("1200x900")
    yield root
    root.destroy()


def test_dialog_does_not_scan_on_open_and_consumes_partial_events_in_main_thread(root):
    sessions = [Session("a", "Alpha", [], "server.invalid", "ops")]
    with patch("ssh_manager_app.port_scan.threading.Thread") as thread:
        dialog = FullPortScanDialog(root, sessions)
    thread.assert_not_called()
    dialog.running = True
    dialog.events.put(("open", ("Alpha", "192.0.2.1", 443)))
    dialog.events.put(("progress", ("Alpha", "192.0.2.1", (1, 65535, dict(open=1, timeout=0, error=0)))))
    dialog.events.put(("finished", "Abgebrochen – Teilergebnis"))
    dialog.poll()
    assert len(dialog.output.get_children()) == 1
    assert "Teilergebnis" in dialog.status.get()
    assert not dialog.running
    dialog.close()
    assert dialog.cancel_event.is_set()


def test_dialog_launches_explicitly_and_closing_cancels_worker(root):
    dialog = FullPortScanDialog(root, [Session("a", "Alpha", [], "server.invalid")])
    with patch("ssh_manager_app.port_scan.threading.Thread") as thread:
        dialog.start()
    thread.assert_called_once()
    assert dialog.running
    assert str(dialog.start_button.cget("state")) == "disabled"
    dialog.stop()
    assert dialog.cancel_event.is_set()
    dialog.close()
    assert dialog.timer is None


def test_controller_scans_all_ips_serially_and_marks_unresolved_host_incomplete(root):
    sessions = [Session("a", "Alpha", [], "a.invalid"), Session("b", "Beta", [], "b.invalid")]
    dialog = FullPortScanDialog(root, sessions)
    with patch("ssh_manager_app.port_scan.threading.Thread") as thread:
        dialog.start()
    second = (socket.AF_INET6, socket.SOCK_STREAM, 6, ("::1", 0, 0, 0))

    def fake_scan(address, cancel, report, **_kwargs):
        report("open", 443)
        return 65535, 65535, dict(open=1, refused=65534, timeout=0, error=0)

    with patch("ssh_manager_app.port_scan.scan_addresses", side_effect=[[ADDRESS, second], OSError()]), patch("ssh_manager_app.port_scan.scan_address", side_effect=fake_scan) as scan:
        thread.call_args.kwargs["target"]()
    dialog.after_cancel(dialog.timer)
    dialog.poll()
    assert [call.args[0] for call in scan.call_args_list] == [ADDRESS, second]
    assert len(dialog.output.get_children()) == 2
    assert "unvollständig" in dialog.status.get()
    assert "Beta: Auflösung fehlgeschlagen" in dialog.details.get("1.0", "end")
    dialog.close()


@pytest.mark.parametrize("rate, timeout", [("101", "1"), ("0", "1"), ("50", "nan"), ("50", "0"), ("x", "1")])
def test_invalid_limits_do_not_start_any_network_work(root, rate, timeout):
    dialog = FullPortScanDialog(root, [])
    dialog.rate.set(rate)
    dialog.timeout.set(timeout)
    with patch("ssh_manager_app.port_scan.threading.Thread") as thread, patch("ssh_manager_app.port_scan.messagebox.showwarning") as warning:
        dialog.start()
    thread.assert_not_called()
    warning.assert_called_once()
    assert not dialog.running
    dialog.close()
