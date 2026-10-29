"""Per-run controls and real concurrent admission with synthetic probes only."""
from concurrent.futures import ThreadPoolExecutor, Future
from types import SimpleNamespace
from unittest.mock import MagicMock
import socket
import threading

import pytest

from test_restart_templates_ui import app, screenshot
from ssh_manager_app.parallelism import worker_count, ParallelismControl
from ssh_manager_app.models import Session


@pytest.mark.parametrize("total,limit,expected", [(12,8,8), (12,0,12), (150,0,150), (12,25,12), (0,0,1)])
def test_counts_without_hidden_upper_bound(total, limit, expected):
    assert worker_count(total, limit) == expected


def test_control_default_all_and_validation(app):
    control = ParallelismControl(app)
    assert control.get() == 8
    control.value.set("bad")
    with pytest.raises(ValueError):
        control.get()
    control.limited.set(False)
    control.update_state()
    assert control.get() == 0 and str(control.entry.cget("state")) == "disabled"
    control.value.set("256")
    control.limited.set(True)
    control.update_state()
    assert control.get() == 256


def test_diagnosis_dispatches_selected_value_and_restores_controls(app, monkeypatch):
    from ssh_manager_app.diagnosis import ConnectionDiagnosisDialog
    calls = []
    monkeypatch.setattr("ssh_manager_app.diagnosis.diagnose_many", lambda *a: calls.append(a) or [])
    monkeypatch.setattr("ssh_manager_app.diagnosis.run_worker", lambda owner, work, done, fail: done(work()))
    window = ConnectionDiagnosisDialog(app, app._app_sessions)
    window.parallelism.limited.set(False)
    window.start()
    assert calls[0][-1] == 0
    assert str(window.parallelism.check.cget("state")) == "normal"
    screenshot(window, "optional-diagnosis.png")
    window.destroy()


def test_host_menu_choice_reaches_pool_without_changing_dedup(monkeypatch):
    from ssh_manager_app.tree import SessionTree
    counts, submitted = [], []
    class Pool:
        def submit(self, *a, **k):
            submitted.append(a)
            future = Future()
            future.set_result(True)
            return future
        def shutdown(self, **k):
            pass
    def factory(workers=8):
        counts.append(workers)
        return Pool()
    monkeypatch.setattr("ssh_manager_app.tree._create_host_probe_pool", factory)
    monkeypatch.setattr("ssh_manager_app.parallelism.choose_parallelism", lambda *a, **k: 0)
    pairs = [(str(i), Session(str(i), str(i), [], "test.invalid")) for i in range(12)]
    owner = SimpleNamespace(winfo_toplevel=lambda: None, bind=lambda *a, **k: None,
        after=lambda *a: None, _pump_host_checks=lambda: None, _set_item_status=lambda *a: None)
    SessionTree.check_hosts(owner, pairs, prompt=True)
    assert counts == [8, 12] and len(submitted) == 12


@pytest.mark.parametrize("limit,expected", [(8,8), (0,12)])
def test_portcheck_pool_uses_run_choice(monkeypatch, limit, expected):
    import ssh_manager_app.port_checks as pc
    counts = []
    def factory(*, max_workers):
        counts.append(max_workers)
        return ThreadPoolExecutor(max_workers=max_workers)
    monkeypatch.setattr(pc, "ThreadPoolExecutor", factory)
    sessions = [Session(str(i), str(i), [], "test.invalid") for i in range(12)]
    job = pc.PortCheckJob(sessions, [("destination.invalid", 443)], "ops", 3,
        probe=lambda *a: pc.ProbeResult("reachable", "synthetic"), max_parallel=limit)
    job._run()
    assert counts == [expected]


def test_status_button_dispatches_all(app, monkeypatch):
    from ssh_manager_app.dialogs_restart_templates import RestartTemplatesDialog
    calls = []
    monkeypatch.setattr("ssh_manager_app.service_status.run_service_status", lambda *a, **k: calls.append(k))
    window = RestartTemplatesDialog(app, app._app_sessions[:1], status_only=True)
    assert not hasattr(window, "status_parallelism")
    window.check_status()
    assert calls == [{"max_parallel": 0}]
    window.destroy()


def test_certificate_search_choice_is_in_result(app, tmp_path):
    from ssh_manager_app.dialogs_certificate_replace import CertificateReplaceDialog
    certificate = tmp_path / "synthetic.crt"
    certificate.write_text("test only")
    window = CertificateReplaceDialog(app, 12, ["/opt/certificates"], [], lambda _: None)
    window._files = [str(certificate)]
    window.parallelism.limited.set(False)
    window.parallelism.update_state()
    screenshot(window, "optional-certificates.png")
    window._ok()
    assert window.result["max_parallel"] == 0


def test_no_rate_or_64_cap_in_unlimited_port_scan(monkeypatch):
    from ssh_manager_app.port_scan import scan_address
    barrier = threading.Barrier(70)
    def probe(*a):
        barrier.wait(5)  # Would fail if even one of the 70 tasks were still queued behind a cap64.
        return "refused"
    monkeypatch.setattr("ssh_manager_app.port_scan.probe_port", probe)
    address = (socket.AF_INET, socket.SOCK_STREAM, 6, ("127.0.0.1", 0))
    done, total, counts = scan_address(address, threading.Event(), lambda *a: None,
        ports=range(1,71), workers=0, rate=0)
    assert done == total == counts["refused"] == 70


def test_dns_timeout_does_not_exceed_selected_socket_limit(monkeypatch):
    from ssh_manager_app.dns_lookup import _resolve_with_socket, socket_lookup_executor
    release = threading.Event()
    lock = threading.Lock()
    active, maximum = 0, 0
    def socket_lookup(*a):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        release.wait(3)
        with lock:
            active -= 1
        return []
    monkeypatch.setattr("ssh_manager_app.dns_lookup._socket_lookup", socket_lookup)
    with ThreadPoolExecutor(max_workers=4) as socket_pool:
        def request(i):
            token = socket_lookup_executor.set(socket_pool)
            try:
                with pytest.raises(socket.timeout):
                    _resolve_with_socket("test.invalid", "forward", .02)
            finally:
                socket_lookup_executor.reset(token)
        try:
            with ThreadPoolExecutor(max_workers=4) as callers:
                list(callers.map(request, range(12)))
            assert maximum == 4
        finally:
            release.set()


@pytest.mark.parametrize("limit,expected", [(4,4), (0,12)])
def test_dns_batch_has_no_hidden_four_pool(monkeypatch, limit, expected):
    import ssh_manager_app.actions_dns as dns
    from ssh_manager_app.dns_lookup import DnsLookupResult
    counts, output = [], []
    def pool(*, max_workers, thread_name_prefix):
        counts.append(max_workers)
        return ThreadPoolExecutor(max_workers=max_workers)
    monkeypatch.setattr(dns, "ThreadPoolExecutor", pool)
    monkeypatch.setattr(dns, "DnsLookupProgressDialog", lambda *a: SimpleNamespace(cancelled=False))
    monkeypatch.setattr(dns, "resolve_dns_value", lambda value, **k: DnsLookupResult(value, "forward", ["127.0.0.1"], "synthetic", "ok"))
    monkeypatch.setattr(dns, "_show_dns_lookup_results", lambda app, progress, results: output.extend(results))
    monkeypatch.setattr(dns, "run_worker", lambda owner, work, done, fail: done(work()))
    dns._resolve_values_async(None, [(f"h{i}.invalid", "auto", str(i)) for i in range(12)], max_parallel=limit)
    assert counts == [expected, expected] and len(output) == 12


def test_fullscan_all_ips_and_ports_dispatches_zero_limits(app, monkeypatch):
    from ssh_manager_app.port_scan import FullPortScanDialog
    barrier = threading.Barrier(2)
    calls = []
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, (ip, 0)) for ip in ("192.0.2.1", "192.0.2.2")]
    monkeypatch.setattr("ssh_manager_app.port_scan.scan_addresses", lambda *a: addresses)
    def scan(address, cancel, report, **kwargs):
        calls.append(kwargs)
        barrier.wait(3)
        return 1, 1, dict(open=0, refused=1, timeout=0, error=0)
    monkeypatch.setattr("ssh_manager_app.port_scan.scan_address", scan)
    window = FullPortScanDialog(app, app._app_sessions[:1])
    window.parallelism.check.invoke()
    window.target_parallelism.check.invoke()
    window.rate_check.invoke()
    screenshot(window, "optional-fullscan.png")
    window.start()
    def poll():
        if window.running:
            app.after(20, poll)
        else:
            app.quit()
    app.after(20, poll)
    watchdog = app.after(5000, app.quit)
    app.mainloop()
    app.after_cancel(watchdog)
    assert not window.running and len(calls) == 2
    assert all(c["rate"] == c["workers"] == 0 for c in calls)
    window.destroy()
