from contextlib import redirect_stdout
from copy import deepcopy
import csv
import errno
import io
import json
import queue
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ssh_manager_app import port_checks as pc, storage
from ssh_manager_app.models import Session, default_settings


def session(key="source", **kwargs):
    return Session(key, key, ["folder"], key + ".example", source="app", **kwargs)


@pytest.mark.parametrize("host,port", [("x;reboot", 22), ("$(whoami)", 80), ("-bad", 80),
    ("a b", 80), ("127.0.0.999", 80), ("example.org\n", 0), ("a", True), ("fe80::1%eth0", 80), ("a", 65536)])
def test_invalid_destinations_never_reach_shell(host, port):
    with pytest.raises(ValueError):
        pc.target(host, port)


def test_target_normalization_and_library_whitelist():
    assert pc.target("[2001:db8::1]", "443") == ("2001:db8::1", 443)
    assert pc.targets([["EXAMPLE.org", "443"], ["example.org", 443]]) == [("example.org", 443)]
    value = pc.validate_library({"schema": 1, "items": [{"name": "Web", "targets": [["a.example", 443]], "password": "secret"}]})
    assert "secret" not in json.dumps(value)
    with pytest.raises(ValueError, match="Doppelter"):
        pc.validate_library({"schema": 1, "items": value["items"] * 2})


def run_remote_python(outcomes, *, dns_error=False):
    """Execute the actual shipped remote code against a fake Linux socket API."""
    import socket
    fake_socket = SimpleNamespace(**{key: getattr(socket, key) for key in ("SOCK_STREAM", "gaierror", "timeout")})
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (f"192.0.2.{i+1}", 443)) for i in range(len(outcomes))]
    def getaddrinfo(*_, **__):
        if dns_error:
            raise socket.gaierror()
        return addresses
    fake_socket.getaddrinfo = getaddrinfo
    pending = iter(outcomes)
    class Socket:
        def __init__(self, *_):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def settimeout(self, timeout):
            assert timeout > 0
        def connect(self, endpoint):
            outcome = next(pending)
            if outcome == "refused":
                raise OSError(errno.ECONNREFUSED, "refused")
            if outcome == "timeout":
                raise TimeoutError()
            if outcome == "network":
                raise OSError(errno.ENETUNREACH, "unreachable")
    fake_socket.socket = Socket
    fake_signal = SimpleNamespace(SIGALRM=14, signal=lambda *_: None, alarm=lambda *_: None)
    output = io.StringIO()
    with patch.dict(sys.modules, {"socket": fake_socket, "signal": fake_signal}), \
            patch.object(sys, "argv", ["probe", "example.org", "443", "3"]), redirect_stdout(output):
        try:
            exec(compile(pc.REMOTE_PYTHON, "remote_probe", "exec"), {})
        except SystemExit:
            pass
    return pc.parse_probe_output(output.getvalue())


@pytest.mark.parametrize("outcomes,expected", [(["open"], "open"), (["refused", "open"], "open"),
    (["refused", "refused"], "refused"), (["timeout"], "timeout"), (["network"], "network"),
    (["refused", "network"], "network")])
def test_remote_socket_statuses_and_all_resolved_ips(outcomes, expected):
    result = run_remote_python(outcomes)
    assert result.status == expected
    assert "192.0.2.1" in result.addresses
    if len(outcomes) == 2:
        assert "192.0.2.2" in result.addresses


def test_remote_dns_failure_and_invalid_output_are_not_port_refusal():
    assert run_remote_python([], dns_error=True).status == "dns"
    assert pc.parse_probe_output("login banner\ninvalid").status == "error"
    assert pc.parse_probe_output(pc.MARKER + '{"status": "open", "detail": []}').status == "error"
    assert pc.parse_probe_output(pc.MARKER + 'tool\t\tPython fehlt').status == "tool"


class FakeProcess:
    def __init__(self, output=None, returncode=0, wait=False):
        self.returncode = returncode
        self.output = (output or pc.MARKER + '{"status":"open","detail":"ok","addresses":"192.0.2.1"}').encode()
        self.wait, self.killed, self.inputs = wait, False, []
    def communicate(self, input=None, timeout=None):
        self.inputs.append(input)
        if self.wait and timeout is not None:
            raise subprocess.TimeoutExpired("ssh", timeout)
        return self.output, b"private ssh error"
    def poll(self):
        return None if self.wait and not self.killed else self.returncode
    def kill(self):
        self.killed = True


def test_ssh_arguments_keep_alias_user_and_no_prompts():
    fake = FakeProcess()
    alias = Session("alias", "my-alias", [], "actual", source="ssh_config")
    with patch.object(pc.subprocess, "Popen", return_value=fake) as popen:
        result = pc.probe_target(alias, ("2001:db8::1", 443), "ignored", 3, threading.Event())
    args = popen.call_args.args[0]
    assert args[-3:] == ["--", "my-alias", "sh -s -- 2001:db8::1 443 3"]
    assert "BatchMode=yes" in args and "StrictHostKeyChecking=yes" in args
    assert "-l" not in args
    assert popen.call_args.kwargs.get("shell", False) is False
    assert fake.inputs[0] == pc.REMOTE_SCRIPT.encode()
    assert result.status == "open" and result.checked_at
    alias.ssh_user_override = "explicit"
    with patch.object(pc.subprocess, "Popen", return_value=FakeProcess()) as popen:
        pc.probe_target(alias, ("192.0.2.1", 443), "ignored", 3, threading.Event())
    assert popen.call_args.args[0][-5:-1] == ["-l", "explicit", "--", "my-alias"]


def test_ssh_failure_is_not_negative_tcp_result_and_never_exposes_stderr():
    with patch.object(pc.subprocess, "Popen", return_value=FakeProcess(returncode=255)):
        result = pc.probe_target(session(username="ops"), ("a.example", 443), "fallback", 3, threading.Event())
    assert result.status == "ssh" and result.status not in pc.NEGATIVE
    assert "private" not in result.detail


def test_cancel_and_deadline_kill_and_reap_process():
    cancel = threading.Event()
    fake = FakeProcess(wait=True)
    clock = iter([0, 0, 99])
    with patch.object(pc.subprocess, "Popen", return_value=fake), patch.object(pc.time, "monotonic", side_effect=lambda: next(clock)):
        result = pc.probe_target(session(), ("a", 443), "ops", 3, cancel)
    assert result.status == "ssh" and fake.killed
    assert fake.inputs[0] == pc.REMOTE_SCRIPT.encode()
    fake = FakeProcess(wait=True)
    def communicate(input=None, timeout=None):
        if timeout is not None:
            cancel.set()
            raise subprocess.TimeoutExpired("ssh", timeout)
        return b"", b""
    fake.communicate = communicate
    with patch.object(pc.subprocess, "Popen", return_value=fake):
        result = pc.probe_target(session(), ("a", 443), "ops", 3, cancel)
    assert result.status == "cancelled" and fake.killed


def test_destination_picker_uses_effective_alias_hostname_without_port():
    alias = Session("key", "myalias", [], "stale", source="ssh_alias", port=22)
    with patch.object(pc.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="hostname actual.example\nport 2222\n")):
        assert pc.resolve_destination(alias) == "actual.example"


def collect(job):
    events = []
    while True:
        event = job.events.get(timeout=5)
        events.append(event)
        if event[0] == "done":
            return events


def test_source_pool_limits_parallelism_and_uses_run_snapshot():
    lock = threading.Lock()
    active, peak, calls = [0], [0], []
    sources = [session(str(i)) for i in range(20)]
    def probe(source, target, user, timeout, cancel):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
            calls.append((source.key, source.hostname, target))
        time.sleep(.01)
        with lock:
            active[0] -= 1
        return pc.ProbeResult("open", "ok")
    job = pc.PortCheckJob(sources, [("a", 443), ("b", 5432)], "ops", 3, probe=probe)
    sources[0].hostname = "changed"
    events = collect(job.start())
    assert 1 < peak[0] <= 8
    assert len(calls) == 40 and len([e for e in events if e[0] == "result"]) == 40
    assert all(c[1] != "changed" for c in calls)


def test_job_cancel_preserves_unstarted_and_retry_only_requested_pairs():
    calls = []
    def probe(source, destination, user, timeout, cancel):
        calls.append(destination)
        cancel.set()
        return pc.ProbeResult("refused", "no")
    job = pc.PortCheckJob([session()], [("a", 443), ("b", 443)], "ops", 3, probe=probe)
    events = collect(job.start())
    assert calls == [("a", 443)]
    assert [e[3].status for e in events if e[0] == "result"] == ["refused", "cancelled"]
    calls.clear()
    pairs = {("source", ("b", 443))}
    job = pc.PortCheckJob([session()], [("a", 443), ("b", 443)], "ops", 3, pairs=pairs, probe=probe)
    collect(job.start())
    assert calls == [("b", 443)]


def test_template_persistence_roundtrip_and_backup_validation(tmp_path, monkeypatch):
    for field, name in (("_STATE_FILE", "ui_state.json"), ("_SETTINGS_FILE", "settings.json"),
                        ("_APP_SESSIONS_FILE", "app_sessions.json"), ("_NOTES_FILE", "notes.json")):
        monkeypatch.setattr(storage, field, tmp_path / name)
    library = {"schema": 1, "items": [{"name": "Web", "targets": [["192.0.2.1", 443]]}]}
    storage.save_ui_state({"folder"}, {}, {pc.STATE_KEY: library})
    assert storage.load_ui_state()[2][pc.STATE_KEY] == library
    storage.save_settings(default_settings())
    storage.save_app_sessions([])
    storage.save_notes({})
    storage.create_app_backup(tmp_path / "backup.json")
    backup = storage.read_app_backup(tmp_path / "backup.json")
    assert backup["documents"]["ui_state.json"]["toolbar_search_texts"][pc.STATE_KEY] == library
    bad = deepcopy(backup)
    bad["documents"]["ui_state.json"]["toolbar_search_texts"][pc.STATE_KEY]["items"][0]["targets"][0][1] = 0
    with pytest.raises(ValueError):
        storage.validate_app_backup(bad)


@pytest.mark.parametrize("outcome,expected", [("open", "open"), ("refused", "refused"),
                                          ("timeout", "timeout"), ("unknown", "network")])
def test_real_bash_netcat_fallback_and_remote_dns(outcome, expected):
    from ssh_manager_app.core import _find_git_bash
    # Run the actual shipped shell script. All network utilities are shell fakes;
    # command detection hides Python so the netcat fallback is exercised on Windows.
    prefix = r'''
command() {
  if [ "$1" = -v ] && [ "$2" = python3 ]; then return 1; fi
  builtin command "$@"
}
getent() { printf '192.0.2.10 STREAM\n192.0.2.20 STREAM\n'; }
timeout() { shift; "$@"; }
nc() {
  if [ "$1" = -h ]; then echo 'OpenBSD netcat'; return 1; fi
  case "$*" in '-n -z -v -w 3 192.0.2.'*) ;; *) return 9 ;; esac
  case "$OUTCOME" in
    open) return 0 ;;
    refused) echo 'Connection refused' >&2; return 1 ;;
    timeout) return 124 ;;
    *) echo 'Unknown error' >&2; return 2 ;;
  esac
}
'''
    script = f"OUTCOME={outcome}\n" + prefix + pc.REMOTE_SCRIPT
    completed = subprocess.run([_find_git_bash(), "-s", "--", "service.example", "443", "3"],
                               input=script, text=True, capture_output=True, timeout=8)
    assert completed.returncode == 0, completed.stderr
    result = pc.parse_probe_output(completed.stdout)
    assert result.status == expected
    assert "192.0.2.10" in result.addresses
    if outcome != "open":
        assert "192.0.2.20" in result.addresses


def test_current_state_preserves_template_library_and_action_requires_checks():
    from ssh_manager_app.actions_ui import current_ui_state
    from ssh_manager_app.action_availability import action_disabled_reason
    from unittest.mock import MagicMock
    library = {"schema": 1, "items": [{"name": "Web", "targets": [["a.example", 443]]}]}
    app = SimpleNamespace(_initial_toolbar_search_texts={pc.STATE_KEY: library},
                          _search_var=MagicMock(), _search_history=[], _tree=MagicMock())
    assert current_ui_state(app)[2][pc.STATE_KEY] == library
    app._tree.get_selected_sessions.return_value = []
    assert action_disabled_reason(app, "Portfreigabe prüfen…")
    app._tree.get_selected_sessions.return_value = [session()]
    assert action_disabled_reason(app, "Portfreigabe prüfen…") == ""
