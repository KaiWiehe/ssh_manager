import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app.core import (
    HerdrLauncher,
    HerdrUnavailableError,
    TerminalLaunchError,
    TerminalLauncher,
    TerminalTabSpec,
    TerminalCommand,
    build_wt_command,
    _find_git_bash,
    build_jump_wt_command,
    build_certificate_deploy_wt_command,
    build_certificate_replace_wt_command,
    build_remote_command_wt_command,
    build_ssh_tunnel_command,
)
from ssh_manager_app.models import Session, WindowsTerminalSettings


def _herdr_tab_response(workspace_id: str, tab_id: str, pane_id: str, include_workspace: bool = False) -> dict:
    result = {
        "tab": {"tab_id": tab_id, "workspace_id": workspace_id},
        "root_pane": {"pane_id": pane_id},
    }
    if include_workspace:
        result["workspace"] = {"workspace_id": workspace_id}
    return {"result": result}


def test_terminal_launcher_uses_windows_terminal_by_default():
    session = Session("s1", "Server", [], "10.0.0.1")
    with patch("ssh_manager_app.core.build_wt_command", return_value=build_wt_command([session], "ops")) as build, \
         patch("ssh_manager_app.core.subprocess.Popen") as popen:
        TerminalLauncher.launch([session], "ops", {"s1": "#123456"})

    build.assert_called_once()
    popen.assert_called_once_with(build_wt_command([session], "ops").argv, shell=False)


def test_terminal_launcher_falls_back_to_windows_terminal_before_first_herdr_tab():
    session = Session("s1", "Server", [], "10.0.0.1")
    settings = WindowsTerminalSettings(ssh_open_mode="herdr")
    with patch.object(HerdrLauncher, "launch", side_effect=HerdrUnavailableError("nicht erreichbar")), \
         patch("ssh_manager_app.core.build_wt_command", return_value=build_wt_command([session], "ops")), \
         patch("ssh_manager_app.core.subprocess.Popen") as popen:
        TerminalLauncher.launch([session], "ops", terminal_settings=settings)

    popen.assert_called_once_with(build_wt_command([session], "ops").argv, shell=False)


def test_terminal_launcher_does_not_fallback_after_partial_herdr_start():
    session = Session("s1", "Server", [], "10.0.0.1")
    settings = WindowsTerminalSettings(ssh_open_mode="herdr")
    error = TerminalLaunchError("teilweise", [session])
    with patch.object(HerdrLauncher, "launch", side_effect=error), \
         patch("ssh_manager_app.core.subprocess.Popen") as popen:
        with pytest.raises(TerminalLaunchError) as raised:
            TerminalLauncher.launch([session], "ops", terminal_settings=settings)

    assert raised.value.started_sessions == [session]
    popen.assert_not_called()


def test_terminal_launcher_extracts_multiple_herdr_tabs_from_windows_terminal_command():
    sessions = [Session("s1", "One ; -- ", [], "one.example"), Session("s2", "Two", [], "two.example")]
    command = build_wt_command(sessions, "ops")
    tabs = TerminalLauncher._tabs_from_windows_command(command, ["One", "Two"])
    assert [tab.command for tab in tabs] == ["ssh -- ops@one.example", "ssh -- ops@two.example"]
    assert [tab.label for tab in tabs] == ["One", "Two"]


def test_terminal_launcher_uses_herdr_for_built_commands_when_selected():
    settings = WindowsTerminalSettings(ssh_open_mode="herdr")
    command = build_wt_command([Session("s1", "Server", [], "server.example")], "ops")

    with patch.object(HerdrLauncher, "launch_tabs") as launch_tabs, \
         patch.object(TerminalLauncher, "_launch_windows_command") as launch_windows:
        TerminalLauncher.launch_built_command(command, ["Server"], settings)

    launch_tabs.assert_called_once_with(
        command.tabs,
        settings,
    )
    launch_windows.assert_not_called()


def test_terminal_launcher_falls_back_for_built_command_before_first_herdr_tab():
    settings = WindowsTerminalSettings(ssh_open_mode="herdr")
    command = build_wt_command([Session("s1", "Server", [], "server.example")], "ops")

    with patch.object(HerdrLauncher, "launch_tabs", side_effect=HerdrUnavailableError("nicht erreichbar")), \
         patch.object(TerminalLauncher, "_launch_windows_command") as launch_windows:
        TerminalLauncher.launch_built_command(command, ["Server"], settings)

    launch_windows.assert_called_once_with(command)


def test_terminal_launcher_does_not_fallback_built_command_after_partial_herdr_start():
    settings = WindowsTerminalSettings(ssh_open_mode="herdr")
    command = build_wt_command([Session("s1", "Server", [], "server.example")], "ops")

    with patch.object(HerdrLauncher, "launch_tabs", side_effect=TerminalLaunchError("teilweise")), \
         patch.object(TerminalLauncher, "_launch_windows_command") as launch_windows:
        with pytest.raises(TerminalLaunchError):
            TerminalLauncher.launch_built_command(command, ["Server"], settings)

    launch_windows.assert_not_called()


def test_herdr_launcher_reuses_existing_workspace_and_does_not_open_outer_tab_for_visible_client():
    sessions = [
        Session("s1", "Server 1", [], "10.0.0.1"),
        Session("s2", "Server 2", [], "10.0.0.2", username="deploy"),
    ]
    settings = WindowsTerminalSettings(ssh_open_mode="herdr")
    tab_number = 0
    json_calls = []
    command_calls = []

    def run_json(_executable, args, timeout=5.0):
        nonlocal tab_number
        json_calls.append(args)
        if args[:2] == ["tab", "create"]:
            tab_number += 1
            return _herdr_tab_response("w7", f"w7:t{tab_number}", f"w7:p{tab_number}")
        return {"result": {}}

    def run_command(_executable, args, timeout=5.0):
        command_calls.append(args)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch("ssh_manager_app.core.shutil.which", return_value=r"C:\Tools\herdr.exe"), \
         patch.object(HerdrLauncher, "_ensure_server"), \
         patch.object(HerdrLauncher, "_find_workspace", return_value="w7"), \
         patch.object(HerdrLauncher, "_run_json", side_effect=run_json), \
         patch.object(HerdrLauncher, "_run", side_effect=run_command), \
         patch.object(HerdrLauncher, "_best_effort"), \
         patch.object(HerdrLauncher, "_has_visible_client", return_value=True), \
         patch("ssh_manager_app.core.subprocess.Popen") as popen:
        HerdrLauncher.launch(sessions, "ops", settings)

    assert [call for call in json_calls if call[:2] == ["tab", "create"]] == [
        ["tab", "create", "--workspace", "w7", "--label", "Server 1", "--no-focus"],
        ["tab", "create", "--workspace", "w7", "--label", "Server 2", "--no-focus"],
    ]
    assert [call for call in command_calls if call[:2] == ["pane", "run"]] == [
        ["pane", "run", "w7:p1", "ssh -- ops@10.0.0.1"],
        ["pane", "run", "w7:p2", "ssh -- deploy@10.0.0.2"],
    ]
    popen.assert_not_called()


def test_herdr_launcher_reuses_initial_workspace_pane_and_attaches_once_when_headless():
    session = Session("s1", "Production", [], "prod.example", username="root")
    settings = WindowsTerminalSettings(profile_name="Custom Bash", ssh_open_mode="herdr")
    json_calls = []
    command_calls = []

    def run_json(_executable, args, timeout=5.0):
        json_calls.append(args)
        if args[:2] == ["workspace", "create"]:
            return _herdr_tab_response("w8", "w8:t1", "w8:p1", include_workspace=True)
        return {"result": {}}

    def run_command(_executable, args, timeout=5.0):
        command_calls.append(args)
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.dict(os.environ, {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1", "UNRELATED": "keep"}), \
         patch("ssh_manager_app.core.shutil.which", return_value=r"C:\Tools\herdr.exe"), \
         patch.object(HerdrLauncher, "_ensure_server"), \
         patch.object(HerdrLauncher, "_find_workspace", return_value=None), \
         patch.object(HerdrLauncher, "_run_json", side_effect=run_json), \
         patch.object(HerdrLauncher, "_run", side_effect=run_command), \
         patch.object(HerdrLauncher, "_best_effort") as best_effort, \
         patch.object(HerdrLauncher, "_has_visible_client", return_value=False), \
         patch("ssh_manager_app.core.subprocess.Popen") as popen:
        HerdrLauncher.launch([session], "ignored", settings)

    assert [call for call in json_calls if call[:2] == ["workspace", "create"]] == [
        ["workspace", "create", "--label", "SSH Manager", "--no-focus"],
    ]
    assert [call for call in json_calls if call[:2] == ["tab", "create"]] == []
    assert ["pane", "run", "w8:p1", "ssh -- root@prod.example"] in command_calls
    best_effort.assert_any_call(r"C:\Tools\herdr.exe", ["tab", "rename", "w8:t1", "Production"])
    attach_args, attach_kwargs = popen.call_args
    assert attach_args[0] == [
        "wt.exe", "new-tab", "--reloadEnvironment", "-p", "Custom Bash", "--", r"C:\Tools\herdr.exe",
    ]
    assert attach_kwargs["env"]["UNRELATED"] == "keep"
    assert not any(key.upper().startswith("HERDR_") for key in attach_kwargs["env"])


def test_find_git_bash_uses_per_user_install_when_git_is_not_on_path(tmp_path):
    bash = tmp_path / "Programs" / "Git" / "bin" / "bash.exe"
    bash.parent.mkdir(parents=True)
    bash.touch()

    with patch("ssh_manager_app.core.shutil.which", return_value=None), \
         patch.dict(os.environ, {"LOCALAPPDATA": str(tmp_path)}):
        assert _find_git_bash() == str(bash)


def test_build_jump_wt_command_with_port_and_title_mode():
    session = Session("app__srv", "Prod DB", ["DB"], "10.0.0.5", port=2222)
    settings = WindowsTerminalSettings(profile_name="Git Bash", use_tab_color=True, title_mode="user_host")

    cmd = build_jump_wt_command(
        session,
        target_user="deploy",
        jump_host="jump.example.com",
        jump_user="jumper",
        jump_port=2200,
        session_color="#112233",
        terminal_settings=settings,
    )

    assert cmd.argv == ["wt.exe", "new-tab", "--tabColor", "#112233", "--title", "deploy@10.0.0.5", "-p", "Git Bash", "--", "ssh", "-J", "jumper@jump.example.com:2200", "-p", "2222", "--", "deploy@10.0.0.5"]


def test_build_remote_command_wt_command_creates_temp_script_and_uses_git_bash():
    session = Session("app__srv", "App", ["Team"], "10.0.0.9")
    settings = WindowsTerminalSettings(profile_name="Git Bash", use_tab_color=True, title_mode="name")

    captured = {}

    def fake_write_temp_script(prefix, content):
        captured["prefix"] = prefix
        captured["content"] = content
        return "/tmp/fake-remote.sh"

    with patch("ssh_manager_app.core._find_git_bash", return_value=r"C:\\Git\\bin\\bash.exe"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=fake_write_temp_script):
        cmd = build_remote_command_wt_command(
            [(session, "deploy", "uptime")],
            close_on_success=False,
            session_colors={session.key: "#abcdef"},
            terminal_settings=settings,
        )

    assert cmd.argv[:9] == ["wt.exe", "new-tab", "--tabColor", "#abcdef", "--title", "App", "-p", "Git Bash", "--"]
    assert cmd.argv[-2].endswith('bash.exe')
    assert captured["prefix"] == "remote_cmd_"
    script_text = captured["content"]
    assert "ssh -- deploy@10.0.0.9 -t <<'__SSH_MANAGER_" in script_text
    assert "uptime" in script_text
    assert "exec ssh -- deploy@10.0.0.9" in script_text


def test_build_remote_command_wt_command_passes_optional_sudo_password_without_command_args():
    session = Session("app__srv", "App", [], "10.0.0.9")
    captured = {}

    with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda _prefix, content: captured.setdefault("content", content) or "/tmp/run.sh"):
        build_remote_command_wt_command(
            [(session, "deploy", "sudo systemctl status wildfly.service")],
            close_on_success=False,
            sudo_password="secret'value",
        )

    assert "SSH_MANAGER_SUDO_PASSWORD='secret'\"'\"'value'" in captured["content"]
    assert "command sudo -S -p '' \"$@\"" in captured["content"]
    assert "trap 'unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"' EXIT" in captured["content"]
    assert "unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"; exec ssh -- deploy@10.0.0.9" in captured["content"]


def test_build_certificate_deploy_wt_command_uploads_all_files_then_installs_and_runs_post_command():
    session = Session("app__srv", "App", [], "10.0.0.9")
    captured = {}

    def fake_write_temp_script(_prefix, content):
        captured["content"] = content
        return "/tmp/cert-deploy.sh"

    with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=fake_write_temp_script):
        command = build_certificate_deploy_wt_command(
            [(session, "deploy", {
                "files": [r"C:\\certs\\server.crt", r"C:\\certs\\server.key"],
                "target_dir": "/etc/wildfly/certs",
                "overwrite": True,
                "sudo_password": "secret",
                "post_command": "sudo systemctl restart wildfly.service",
            })],
        )

    assert command.argv[:2] == ["wt.exe", "new-tab"]
    script = captured["content"]
    assert script.count("scp ") == 2
    assert "SSH_MANAGER_SUDO_PASSWORD='secret'" in script
    assert "sudo cp --" in script
    assert "install_certificate" in script
    assert "target_dirs=('/etc/wildfly/certs')" in script
    assert "'server.crt'" in script
    assert "'server.key'" in script
    assert "sudo systemctl restart wildfly.service" in script
    assert script.index("scp ") < script.index("if ! install_certificate") < script.index("sudo systemctl restart wildfly.service")


def test_build_certificate_deploy_wt_command_blocks_existing_files_without_overwrite():
    session = Session("app__srv", "App", [], "10.0.0.9")
    captured = {}

    with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda _prefix, content: captured.update(content=content) or "/tmp/cert-deploy.sh"):
        build_certificate_deploy_wt_command(
            [(session, "deploy", {
                "files": [r"C:\\certs\\server.crt"],
                "target_dir": "/etc/wildfly/certs",
                "overwrite": False,
                "sudo_password": "",
                "post_command": "sudo systemctl restart wildfly.service",
            })],
        )

    script = captured["content"]
    assert "AUSGELASSEN: Zieldatei existiert bereits" in script
    assert "Es wurde keine Datei dieses Hosts ersetzt und kein Nach-Befehl ausgeführt." in script


def test_build_certificate_deploy_wt_command_copies_to_every_target_directory_after_precheck():
    session = Session("app__srv", "App", [], "10.0.0.9")
    captured = {}

    with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda _prefix, content: captured.update(content=content) or "/tmp/cert-deploy.sh"):
        build_certificate_deploy_wt_command(
            [(session, "deploy", {
                "files": [r"C:\\certs\\server.crt"],
                "target_dirs": ["/opt/wildfly-a/certs", "/opt/wildfly-b/certs"],
                "overwrite": False,
            })],
        )

    script = captured["content"]
    assert "target_dirs=('/opt/wildfly-a/certs' '/opt/wildfly-b/certs')" in script
    assert script.index("Prüfe, ob vorhandene Dateien überschrieben würden") < script.index("if ! install_certificate")
    assert "Erfolgreich übertragen: 1 Datei(en) in 2 Zielordner" in script


def test_build_certificate_deploy_wt_command_keeps_bash_open_by_default_and_can_close_tab():
    session = Session("app__srv", "App", [], "10.0.0.9")

    def build_content(close_on_success):
        captured = {}
        with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
             patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda _prefix, content: captured.update(content=content) or "/tmp/cert-deploy.sh"):
            build_certificate_deploy_wt_command(
                [(session, "deploy", {
                    "files": [r"C:\\certs\\server.crt"],
                    "target_dir": "/etc/wildfly/certs",
                    "overwrite": False,
                    "close_on_success": close_on_success,
                })],
            )
        return captured["content"]

    assert "exec ssh -- deploy@10.0.0.9" in build_content(False)
    assert "exec bash" not in build_content(False)
    assert "  exit 0" in build_content(True)


def test_build_certificate_replace_preserves_target_metadata_and_runs_post_command():
    session = Session("app__srv", "App", [], "10.0.0.9")
    captured = {}
    with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda _prefix, content: captured.update(content=content) or "/tmp/replace.sh"):
        build_certificate_replace_wt_command(
            [(session, "deploy", {"files": [r"C:\\certs\\keystore.jks"], "matches": [("keystore.jks", "/opt/wildfly-a/keystore.jks")], "post_command": "sudo systemctl restart wildfly.service"})],
        )
    script = captured["content"]
    assert "sudo stat -c '%u:%g:%a'" in script
    assert "sudo chown \"$owner:$group\"" in script
    assert "sudo chmod \"$mode\"" in script
    assert "sudo systemctl restart wildfly.service" in script


def test_build_certificate_replace_uploads_only_files_with_matches_and_forces_tty():
    session = Session("app__srv", "App", [], "10.0.0.9")
    captured = {}
    with patch("ssh_manager_app.core._find_git_bash", return_value="bash"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda _prefix, content: captured.update(content=content) or "/tmp/replace.sh"):
        build_certificate_replace_wt_command(
            [(session, "deploy", {"files": [r"C:\\certs\\needed.jks", r"C:\\certs\\unused.p12"], "matches": [("needed.jks", "/opt/wildfly/needed.jks")]})],
        )
    script = captured["content"]
    assert "needed.jks" in script
    assert "unused.p12" not in script
    assert "ssh -- deploy@10.0.0.9 <<'__SSH_MANAGER_" in script
    assert "rm -rf -- /tmp/ssh-manager-replace-" in script


def test_build_ssh_tunnel_command_returns_expected_wt_args():
    settings = WindowsTerminalSettings(profile_name="My Bash", use_tab_color=False, title_mode="default")

    captured = {}

    def fake_write_temp_script(prefix, content):
        captured["prefix"] = prefix
        captured["content"] = content
        return "/tmp/fake-tunnel.sh"

    with patch("ssh_manager_app.core._find_git_bash", return_value=r"C:\\Git\\bin\\bash.exe"), \
         patch("ssh_manager_app.core._write_temp_bash_script", side_effect=fake_write_temp_script):
        cmd = build_ssh_tunnel_command(
            ssh_server="jump.example.com",
            local_port=15432,
            remote_host="db.internal",
            remote_port=5432,
            user="deploy",
            terminal_settings=settings,
        )

    assert cmd.argv[:4] == ["wt.exe", "new-tab", "-p", "My Bash"]
    assert cmd.argv[4:6] == ["--", r"C:\\Git\\bin\\bash.exe"]
    assert captured["prefix"] == "ssh_tunnel_"
    script_text = captured["content"]
    assert "ssh -N -L 15432:db.internal:5432 -- deploy@jump.example.com" in script_text
