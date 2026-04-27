import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app.core import (
    build_jump_wt_command,
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
    assert "exec bash" in script_text


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
