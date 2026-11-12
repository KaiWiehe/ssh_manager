import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ssh_manager_app.core import TerminalCommand, TerminalLauncher, TerminalLaunchError, TerminalTabSpec, build_wt_command
from ssh_manager_app.herdr_app import HerdrAppLauncher as Launcher, HerdrAppUnavailableError, HerdrAppBusyError
from ssh_manager_app.models import Session, WindowsTerminalSettings, default_settings
from ssh_manager_app.storage import save_settings, load_settings_from_path
from ssh_manager_app.terminal_ui import run_terminal_ui, launch_built_command_ui

SETTINGS = WindowsTerminalSettings(ssh_open_mode="herdr_app")
SESSION = Session("s", "Name ; Ü", [], "example.org", username="ops", port=2222)


def command():
    return build_wt_command([SESSION], "ignored", terminal_settings=SETTINGS)


@pytest.fixture
def ready():
    with patch.object(Launcher, "_find_program", return_value="app.exe"), \
         patch("ssh_manager_app.core._find_git_bash", return_value="C:/Git/bin/bash.exe"), \
         patch.object(Launcher, "_ready", return_value=[]) as spaces, \
         patch.object(Launcher, "_json", return_value={"space": "sp1", "tab": "tb1", "terminal": "t1"}) as call:
        yield spaces, call


def test_setting_roundtrip(tmp_path):
    settings = default_settings()
    settings.windows_terminal = SETTINGS
    path = tmp_path / "settings.json"
    with patch("ssh_manager_app.storage._SETTINGS_FILE", path):
        save_settings(settings)
    assert load_settings_from_path(path).windows_terminal.ssh_open_mode == "herdr_app"


def test_dispatch_normal_and_built_without_windows_terminal():
    with patch.object(Launcher, "launch_tabs") as launch, patch.object(TerminalLauncher, "_launch_windows_command") as wt:
        TerminalLauncher.launch([SESSION], "ops", terminal_settings=SETTINGS)
        TerminalLauncher.launch_built_command(command(), [SESSION.display_name], SETTINGS)
    assert launch.call_count == 2
    assert launch.call_args.args[0][0].session == SESSION
    wt.assert_not_called()


def test_new_space_first_tab_has_program_no_empty_tab(ready):
    spaces, call = ready
    Launcher.launch_tabs(command().tabs, SETTINGS)
    assert call.call_count == 1
    args = call.call_args.args[1]
    assert args[:2] == ["do", "space.new"]
    payload = json.loads(args[2])
    assert payload["name"] == "SSH Manager"
    assert payload["tab"] == SESSION.display_name
    assert payload["machine"] == ""
    assert payload["argv"][-5:] == ["ssh-manager", "ssh", "-p", "2222", "--", "ops@example.org"][-5:]  # separated arguments
    assert payload["argv"][3] == 'exec "$@"'


def test_existing_local_space_explicit_target(ready):
    spaces, call = ready
    spaces.return_value = [{"name": "SSH Manager", "id": "remote", "machine": "vps"}, {"name": "SSH Manager", "id": "local", "machine": None}]
    Launcher.launch_tabs(command().tabs * 2, SETTINGS)
    assert call.call_count == 2
    for invocation in call.call_args_list:
        args = invocation.args[1]
        assert args[:2] == ["do", "tab.new"]
        assert json.loads(args[2])["space"] == "local"


@pytest.mark.parametrize("spaces", [
    [{"name": "SSH Manager", "id": "one"}, {"name": "SSH Manager", "id": "two"}],
    [{"name": "SSH Manager", "id": None}],
])
def test_ambiguous_or_invalid_target_never_mutates(ready, spaces):
    state, call = ready
    state.return_value = spaces
    with pytest.raises(HerdrAppUnavailableError):
        Launcher.launch_tabs(command().tabs, SETTINGS)
    call.assert_not_called()


def test_partial_and_unknown_starts_never_fallback(ready):
    spaces, call = ready
    call.side_effect = [{"space": "sp1", "tab": "tb1", "terminal": "t1"}, subprocess.TimeoutExpired("redacted", 10)]
    with patch.object(TerminalLauncher, "_launch_windows_command") as wt:
        with pytest.raises(TerminalLaunchError) as error:
            TerminalLauncher.launch_built_command(TerminalCommand(command().tabs * 2), ["A", "B"], SETTINGS)
    assert error.value.started_sessions == [SESSION]
    wt.assert_not_called()
    assert call.call_count == 2


@pytest.mark.parametrize("reply", [{}, {"space": "sp1", "tab": "tb1"}, {"space": 3, "tab": "tb1", "terminal": "t1"}])
def test_invalid_mutation_reply_is_uncertain_not_unavailable(ready, reply):
    spaces, call = ready
    call.return_value = reply
    with pytest.raises(TerminalLaunchError):
        Launcher.launch_tabs(command().tabs, SETTINGS)
    assert call.call_count == 1


def test_script_arguments_remain_separate_and_path_works_for_bash(ready):
    spaces, call = ready
    tab = TerminalTabSpec("script", "unused", SESSION, (r"C:\Git\bin\bash.exe", r"C:\Temp\ä b; c.sh"))
    Launcher.launch_tabs([tab], SETTINGS)
    assert json.loads(call.call_args.args[1][2])["argv"] == [r"C:\Git\bin\bash.exe", "C:/Temp/ä b; c.sh"]


def test_missing_app_no_mutation_or_automatic_fallback():
    with patch.object(Launcher, "_find_program", side_effect=HerdrAppUnavailableError("missing")), patch.object(Launcher, "_json") as call:
        with pytest.raises(HerdrAppUnavailableError):
            Launcher.launch_tabs(command().tabs, SETTINGS)
    call.assert_not_called()


def test_find_app_outside_path(tmp_path, monkeypatch):
    target = tmp_path / "Programs/herdr-app/herdr-app.exe"
    target.parent.mkdir(parents=True)
    target.touch()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with patch("ssh_manager_app.herdr_app.shutil.which", return_value=None):
        assert Launcher._find_program("herdr-app", "herdr-app") == str(target)


def test_closed_app_opened_once_then_polled():
    with patch.object(Launcher, "_spaces", side_effect=[RuntimeError(), [], []]), patch("ssh_manager_app.herdr_app.subprocess.Popen") as start:
        assert Launcher._ready("app.exe") == []
    start.assert_called_once()


def test_running_app_is_not_restarted():
    with patch.object(Launcher, "_spaces", return_value=[]), patch("ssh_manager_app.herdr_app.subprocess.Popen") as start:
        assert Launcher._ready("app.exe") == []
    start.assert_not_called()


def test_competing_launch_rejected_without_mutation(ready):
    Launcher._lock.acquire()
    try:
        with pytest.raises(HerdrAppBusyError):
            Launcher.launch_tabs(command().tabs, SETTINGS)
    finally:
        Launcher._lock.release()
    ready[1].assert_not_called()


def test_ui_schedules_work_snapshot_and_updates_recent_after_success():
    app, work, success, error = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    settings = WindowsTerminalSettings(ssh_open_mode="herdr_app")
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker:
        run_terminal_ui(app, work, settings, success, error, resources=["s"])
        work.assert_not_called()
        success.assert_not_called()
        settings.ssh_open_mode = "windows_terminal"
        worker.call_args.args[1]()
        assert work.call_args.args[0].ssh_open_mode == "herdr_app"
        worker.call_args.args[2](None)
    success.assert_called_once_with(None)
    assert not app.__dict__["_pending_terminal_targets"]


def test_ui_overlapping_targets_rejected_before_worker():
    app = MagicMock()
    app.__dict__["_pending_terminal_targets"] = {"s"}
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker:
        run_terminal_ui(app, MagicMock(), SETTINGS, MagicMock(), MagicMock(), resources=["s"])
    worker.assert_not_called()


@pytest.mark.parametrize("allow", [True, False])
def test_fallback_only_on_explicit_confirmation(allow):
    app, work, success, error, cleanup = [MagicMock() for _ in range(5)]
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker, patch("ssh_manager_app.terminal_ui.messagebox.askyesno", return_value=allow), patch("ssh_manager_app.terminal_ui.owner_alive", return_value=True):
        run_terminal_ui(app, work, SETTINGS, success, error, cleanup=cleanup)
        worker.call_args.args[3](HerdrAppUnavailableError("missing"))
    if allow:
        assert work.call_args.args[0].ssh_open_mode == "windows_terminal"
        success.assert_called_once()
    else:
        work.assert_not_called()
        cleanup.assert_called_once()


def test_partial_error_no_fallback_job_not_launched():
    app, job = MagicMock(), MagicMock()
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker, patch("ssh_manager_app.terminal_ui.messagebox.showerror"), patch("ssh_manager_app.terminal_ui.messagebox.askyesno") as ask:
        launch_built_command_ui(app, command(), ["A"], SETTINGS, job)
        worker.call_args.args[3](TerminalLaunchError("uncertain"))
    job.launched.assert_not_called()
    job.uncertain_launch.assert_called_once()
    ask.assert_not_called()


def test_json_errors_do_not_echo_secrets():
    with patch("ssh_manager_app.herdr_app.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "SECRET")):
        with pytest.raises(RuntimeError) as error:
            Launcher._json("app", ["do", "tab.new"])
    assert "SECRET" not in str(error.value)


def test_reservation_held_through_nonmodal_fallback_and_mode_change():
    app, work, success, error = [MagicMock() for _ in range(4)]
    second_work, second_error = MagicMock(), MagicMock()
    def dialog(*args, **kwargs):
        assert app.__dict__["_pending_terminal_targets"] == {"s"}
        run_terminal_ui(app, second_work, WindowsTerminalSettings(), MagicMock(), second_error, resources=["s"])
        return True
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker, patch("ssh_manager_app.terminal_ui.messagebox.askyesno", side_effect=dialog), patch("ssh_manager_app.terminal_ui.owner_alive", return_value=True):
        run_terminal_ui(app, work, SETTINGS, success, error, resources=["s"])
        worker.call_args.args[3](HerdrAppUnavailableError("missing"))
    second_work.assert_not_called()
    assert isinstance(second_error.call_args.args[0], HerdrAppBusyError)
    assert work.call_count == 1
    assert not app.__dict__["_pending_terminal_targets"]


def test_busy_cleans_unstarted_script_and_finishes_job():
    app, job = MagicMock(), MagicMock()
    cmd = command()
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker, patch("ssh_manager_app.terminal_ui.messagebox.showerror"), patch.object(cmd, "cleanup") as cleanup:
        launch_built_command_ui(app, cmd, ["A"], SETTINGS, job)
        worker.call_args.args[3](HerdrAppBusyError("busy"))
    cleanup.assert_called_once()
    job.not_started.assert_called_once()
    job.launched.assert_not_called()


def test_overlap_finishes_already_prepared_job():
    app, job = MagicMock(), MagicMock()
    app.__dict__["_pending_terminal_targets"] = {SESSION.key}
    cmd = command()
    with patch("ssh_manager_app.terminal_ui.run_worker") as worker, patch("ssh_manager_app.terminal_ui.messagebox.showerror"), patch.object(cmd, "cleanup") as cleanup:
        launch_built_command_ui(app, cmd, ["A"], SETTINGS, job)
    worker.assert_not_called()
    cleanup.assert_called_once()
    job.not_started.assert_called_once()
