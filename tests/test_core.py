import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app.core import (
    build_jump_wt_command,
    build_certificate_deploy_wt_command,
    build_certificate_replace_wt_command,
    build_remote_command_wt_command,
    build_ssh_tunnel_command,
)
from ssh_manager_app.models import Session, WindowsTerminalSettings


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

    assert cmd == (
        'wt.exe new-tab --tabColor "#112233" --title "deploy@10.0.0.5" '
        '-p "Git Bash" -- ssh -J -p 2200 jumper@jump.example.com -p 2222 deploy@10.0.0.5'
    )


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

    assert cmd.startswith('wt.exe new-tab --tabColor "#abcdef" --title "App" -p "Git Bash" -- ')
    assert 'bash.exe' in cmd
    assert captured["prefix"] == "remote_cmd_"
    script_text = captured["content"]
    assert "ssh deploy@10.0.0.9 -t <<'__REMOTE_CMD__'" in script_text
    assert "uptime" in script_text
    assert "exec ssh deploy@10.0.0.9" in script_text


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
    assert "unset SSH_MANAGER_SUDO_PASSWORD; rm -f \"$0\"; exec ssh deploy@10.0.0.9" in captured["content"]


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

    assert command.startswith("wt.exe new-tab")
    script = captured["content"]
    assert script.count("scp ") == 2
    assert "SSH_MANAGER_SUDO_PASSWORD='secret'" in script
    assert "sudo cp -f --" in script
    assert "target_dirs=('/etc/wildfly/certs')" in script
    assert "'server.crt'" in script
    assert "'server.key'" in script
    assert "sudo systemctl restart wildfly.service" in script
    assert script.index("scp ") < script.index("sudo cp -f --") < script.index("sudo systemctl restart wildfly.service")


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
    assert script.index("Prüfe, ob vorhandene Dateien überschrieben würden") < script.index("sudo cp -f --")
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

    assert "exec ssh deploy@10.0.0.9" in build_content(False)
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

    assert cmd[:4] == ["wt.exe", "new-tab", "-p", "My Bash"]
    assert cmd[4:6] == ["--", r"C:\\Git\\bin\\bash.exe"]
    assert captured["prefix"] == "ssh_tunnel_"
    script_text = captured["content"]
    assert "ssh -N -L 15432:db.internal:5432 deploy@jump.example.com" in script_text
