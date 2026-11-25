from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Timer
import time

import pytest

from ssh_manager_app import mass_restart as mass
from ssh_manager_app.models import Session
from ssh_manager_app.restart_runtime import RestartResult, _ssh_args


def session(key="one", host="one.example.invalid", user="ops"):
    return Session(key, key, [], host, username=user, source="app")


def drive(run):
    deadline = time.monotonic() + 5
    while not run.done and time.monotonic() < deadline:
        run.tick()
        time.sleep(.005)
    assert run.done
    return run.results


def test_strict_flags_are_scoped_to_mass_restart():
    arguments = _ssh_args(session(), "ops", strict=True)
    for option in ("StrictHostKeyChecking=yes", "ForwardAgent=no", "ClearAllForwardings=yes",
                   "ControlMaster=no", "ControlPath=none", "RequestTTY=no"):
        assert arguments[arguments.index(option) - 1] == "-o"
        assert option not in _ssh_args(session(), "ops")


def test_missing_identity_ignores_uuid_banner_and_never_calls_sudo(monkeypatch):
    commands = []

    def respond(_session, _user, command, _cancel, **options):
        assert not options.get("password")
        commands.append(command)
        return subprocess.CompletedProcess([], 1, "dd0d81a2-cba6-45fa-9ad4-0c4d51cee549\n", "")

    monkeypatch.setattr(mass, "mass_ssh", respond)
    result = mass.check_restart_target(session(), "ops", [], "synthetic", Event(), lambda *_: None)
    assert result.status == "error" and "Boot-ID" in result.detail
    assert commands == [mass.IDENTITY_COMMAND]


def test_all_zero_boot_id_is_not_valid(monkeypatch):
    line = f"{mass.IDENTITY_MARKER}:{'1' * 32}:{mass.EMPTY_BOOT_ID}\n"
    monkeypatch.setattr(mass, "mass_ssh", lambda *_args, **_opts: subprocess.CompletedProcess([], 0, line, ""))
    assert mass.read_restart_identity(session(), "ops", Event())[0] == "missing"


def test_untrusted_host_prevents_password_transmission(monkeypatch):
    calls = []

    def respond(_session, _user, command, _cancel, **options):
        calls.append((command, options.get("password")))
        return subprocess.CompletedProcess([], 255, "", "Host key verification failed.")

    monkeypatch.setattr(mass, "mass_ssh", respond)
    result = mass.check_restart_target(session(), "ops", [], "synthetic", Event(), lambda *_: None)
    assert "Hostschlüssel" in result.detail
    assert calls == [(mass.IDENTITY_COMMAND, None)]


def test_sudo_preflight_and_reboot_guard_use_same_command(monkeypatch):
    original = mass.RestartIdentity("a" * 32, "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(mass, "read_restart_identity", lambda *_: ("identity", original))
    observed = []

    def respond(_session, _user, command, _cancel, **options):
        observed.append((command, options["password"]))
        output = options["ready"] + "\n" + command.rsplit(" ", 1)[-1] + "\n" if len(observed) == 1 else ""
        return subprocess.CompletedProcess([], 0 if len(observed) == 1 else mass.IDENTITY_CHANGED, output, "")

    monkeypatch.setattr(mass, "mass_ssh", respond)
    cancel = Event()
    target = session()
    preflight = mass.check_restart_target(target, "ops", [], "secret", cancel, lambda *_: None)
    assert preflight.identity == original
    result = mass.run_prepared_restart(target, "ops", [], lambda: "secret", original, 10, 10,
                                       cancel, lambda *_: None)
    assert result.status == "error" and "Kein Neustart ausgelöst" in result.detail
    assert "sudo -S -p '' -l -- reboot && printf" in observed[0][0]
    assert "sudo -S -p '' -- reboot && printf" in observed[1][0]
    assert all(original.boot_id in command and original.machine_id in command for command, _password in observed)
    assert all(password == "secret" and "secret" not in command for command, password in observed)


@pytest.mark.parametrize("password", ["", "synthetic"])
def test_sudo_list_requires_proof_of_execution_even_when_ssh_exits_zero(monkeypatch, password):
    identity = mass.RestartIdentity("a", "boot")
    monkeypatch.setattr(mass, "read_restart_identity", lambda *_: ("identity", identity))

    def ssh(_session, _user, _command, _cancel, **options):
        return subprocess.CompletedProcess([], 0, options["ready"] + "\n", "")

    monkeypatch.setattr(mass, "mass_ssh", ssh)
    result = mass.check_restart_target(session(), "ops", [], password, Event(), lambda *_: None)
    assert result.status == "error" and "sudo-Berechtigung" in result.detail


def test_effective_machine_id_blocks_direct_and_alias_duplicates(monkeypatch):
    direct = session()
    alias = Session("alias", "alias", [], "other.example.invalid", source="ssh_alias")
    identity = mass.RestartIdentity("a", "original")
    monkeypatch.setattr(mass, "check_restart_target", lambda *_: mass.RestartPreflight("online", "OK", identity=identity))
    monkeypatch.setattr(mass, "run_prepared_restart", lambda *_: pytest.fail("Duplicate reached reboot phase"))
    plan = {"mode": "parallel", "max_parallel": 2, "on_error": "continue"}
    run = mass.MassRestartRun(plan, [(direct, "ops", []), (alias, "admin", [])], ["", ""], Event())
    results = drive(run)
    assert all("Doppelte Zielidentität" in result.detail for result in results.values())


def test_duplicate_diagnostic_preserves_other_preflight_errors(monkeypatch):
    identity = mass.RestartIdentity("a", "original")

    def check(target, *_):
        if target.key == "other":
            return RestartResult("error", "anderer Fehler")
        return mass.RestartPreflight("error" if target.key == "two" else "online",
                                     "fehlender Dienst", identity=identity)

    monkeypatch.setattr(mass, "check_restart_target", check)
    goals = [(session(key, f"{key}.example.invalid"), "ops", []) for key in ("one", "two", "other")]
    run = mass.MassRestartRun({"mode": "serial", "on_error": "continue"}, goals, ["a", "b", "c"], Event())
    results = drive(run)
    assert "Doppelte Zielidentität" in results[0].detail and "Doppelte Zielidentität" in results[1].detail
    assert "fehlender Dienst" in results[1].detail and results[2].detail == "anderer Fehler"
    assert not run.passwords


def test_duplicate_machine_and_boot_conflicts_both_appear(monkeypatch):
    identities = {"one": mass.RestartIdentity("a", "x"), "two": mass.RestartIdentity("b", "y"),
                  "three": mass.RestartIdentity("a", "y")}
    monkeypatch.setattr(mass, "check_restart_target", lambda target, *_:
        mass.RestartPreflight("online", "passed", identity=identities[target.key]))
    goals = [(session(key, f"{key}.example.invalid"), "ops", []) for key in identities]
    run = mass.MassRestartRun({"mode": "serial", "on_error": "continue"}, goals, [""] * 3, Event())
    results = drive(run)
    assert "Eintrag 1 und 3" in results[0].detail
    assert "Eintrag 2 und 3" in results[1].detail
    assert "Eintrag 1 und 3" in results[2].detail and "Eintrag 2 und 3" in results[2].detail


def test_preflight_lock_blocks_overlap_even_before_units_and_sudo(tmp_path, monkeypatch):
    identity = mass.RestartIdentity("a", "new-boot")
    monkeypatch.setattr(mass, "restart_lock_directory", lambda: tmp_path)
    monkeypatch.setattr(mass, "read_restart_identity", lambda *_: ("identity", identity))
    monkeypatch.setattr(mass, "mass_ssh", lambda *_args, **_opts: pytest.fail("Conflicting target reached sudo"))
    run = mass.MassRestartRun({"mode": "serial", "on_error": "continue"},
                              [(session(), "ops", [])], ["secret"], Event())
    with ExitStack() as first:
        mass._lock_restart_identity(first, tmp_path, identity)
        assert "Zielsperre" in drive(run)[0].detail
    assert not run.passwords


def test_local_duplicate_is_rejected_regardless_of_username():
    goals = [(session(), "ops", []), (session("two", "ONE.EXAMPLE.INVALID."), "other", [])]
    with pytest.raises(ValueError, match="Eintrag 1 .*und 2"):
        mass.duplicate_restart_targets(goals)


def test_target_lock_blocks_a_second_process_and_releases_after_close(tmp_path):
    code = """from contextlib import ExitStack
from pathlib import Path
import sys
from ssh_manager_app.mass_restart import _lock_restart_identity, RestartIdentity

with ExitStack() as stack:
    try:
        _lock_restart_identity(stack, Path(sys.argv[1]), RestartIdentity('system', 'boot'))
    except OSError:
        sys.exit(3)
"""
    args = [sys.executable, "-c", code, str(tmp_path)]
    with ExitStack() as stack:
        mass._lock_restart_identity(stack, tmp_path, mass.RestartIdentity("system", "different-boot"))
        assert subprocess.run(args, cwd=Path(__file__).resolve().parents[1], timeout=10).returncode == 3
    assert subprocess.run(args, cwd=Path(__file__).resolve().parents[1], timeout=10).returncode == 0


def test_cancel_reaps_owned_local_ssh_process(monkeypatch):
    popen = subprocess.Popen
    processes = []
    timer = None
    cancel = Event()

    def launch(*args, **kwargs):
        nonlocal timer
        process = popen(*args, **kwargs)
        processes.append(process)
        timer = Timer(.1, cancel.set)
        timer.start()
        return process

    monkeypatch.setattr(mass, "_ssh_args", lambda *args, **kwargs: [sys.executable, "-c", "import time; time.sleep(10)"])
    monkeypatch.setattr(mass.subprocess, "Popen", launch)
    with pytest.raises(mass.RestartCancelled):
        mass.mass_ssh(session(), "ops", "unused", cancel, timeout=5, password="*" * 4096, ready="expected-marker")
    timer.join(timeout=1)
    assert len(processes) == 1 and processes[0].poll() is not None


def test_ssh_sends_password_only_after_readiness_marker(tmp_path, monkeypatch):
    observed = tmp_path / "stdin.txt"
    child = "import sys,pathlib; print(sys.argv[2],flush=True); pathlib.Path(sys.argv[1]).write_text(sys.stdin.readline(),encoding='utf-8')"
    cancel = Event()
    monkeypatch.setattr(mass, "_ssh_args", lambda *_args, **_opts: [sys.executable, "-u", "-c", child, str(observed), "wrong"])
    with pytest.raises(subprocess.TimeoutExpired):
        mass.mass_ssh(session(), "ops", "unused", cancel, timeout=.5, password="secret", ready="correct")
    assert not observed.exists()
    monkeypatch.setattr(mass, "_ssh_args", lambda *_args, **_opts: [sys.executable, "-u", "-c", child, str(observed), "correct"])
    result = mass.mass_ssh(session(), "ops", "unused", cancel, timeout=5, password="secret", ready="correct")
    assert result.returncode == 0 and observed.read_text(encoding="utf-8") == "secret\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows process-tree regression")
def test_cancel_terminates_windows_proxy_child(tmp_path, monkeypatch):
    import ctypes
    from ctypes import wintypes

    pid_file = tmp_path / "pid.txt"
    child = ("import pathlib,subprocess,sys,time; "
             "proxy=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); "
             "pathlib.Path(sys.argv[1]).write_text(str(proxy.pid)); time.sleep(20)")
    monkeypatch.setattr(mass, "_ssh_args", lambda *_args, **_opts: [sys.executable, "-c", child, str(pid_file)])
    cancel = Event()

    def stop_after_spawn():
        deadline = time.monotonic() + 4
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        cancel.set()

    timer = Timer(.05, stop_after_spawn)
    timer.start()
    try:
        with pytest.raises(mass.RestartCancelled):
            mass.mass_ssh(session(), "ops", "unused", cancel, timeout=6)
    finally:
        timer.join(timeout=5)
    pid = int(pid_file.read_text())
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    process = kernel.OpenProcess(0x00100001, False, pid)  # SYNCHRONIZE | PROCESS_TERMINATE
    if process:
        try:
            assert kernel.WaitForSingleObject(process, 2000) == 0
        finally:
            kernel.TerminateProcess(process, 1)  # Clean up the synthetic process if the check fails.
            kernel.CloseHandle(process)
