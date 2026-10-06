from pathlib import Path
from unittest.mock import patch
import subprocess

import pytest

from ssh_manager_app.core import TerminalLauncher, build_wt_command
from ssh_manager_app.models import Session, WindowsTerminalSettings
from ssh_manager_app.ssh_utils import connection_value


@pytest.mark.parametrize("value", ["-oProxyCommand=calc", "host\n", "host;calc", "$(calc)", 'x" & calc & "'])
def test_connection_identifiers_cannot_be_commands_or_options(value):
    with pytest.raises(ValueError):
        connection_value(value)


def test_terminal_preserves_names_profiles_and_herdr_tab_boundaries():
    name = 'Produktion ä " & | % ; -- Test'
    profile = 'Bash ä " & | % ; Test'
    session = Session("s", name, [], "host")
    command = build_wt_command([session, session], "ops", {"s": "bad;new-tab"}, WindowsTerminalSettings(profile_name=profile, title_mode="name"))
    assert command.argv.count(";") == 1
    assert name.replace(";", r"\;") in command.argv
    assert profile.replace(";", r"\;") in command.argv
    assert "--tabColor" not in command.argv
    assert len(TerminalLauncher._tabs_from_windows_command(command, [name, name])) == 2
    with patch("ssh_manager_app.core.subprocess.Popen") as start:
        TerminalLauncher.launch_built_command(command, [name, name])
    start.assert_called_once_with(command.argv, shell=False)


def test_launcher_refuses_raw_shell_command():
    with patch("ssh_manager_app.core.subprocess.Popen") as start:
        with pytest.raises(ValueError):
            TerminalLauncher._launch_windows_command("wt.exe & calc")
    start.assert_not_called()


@pytest.mark.parametrize("key", ["../id.pub", "a\nb.pub", "id", "C:\\key.pub"])
def test_key_actions_reject_non_public_or_outside_filenames(key):
    from ssh_manager_app.core import build_ssh_remove_key_command
    with pytest.raises(ValueError):
        build_ssh_remove_key_command([Session("s", "Server", [], "host")], key, "ops")


def test_key_removal_handles_last_key_and_preserves_file_mode():
    from ssh_manager_app.core import _find_git_bash, _remove_key_remote_script
    script = '''
HOME=$(mktemp -d)
trap 'rm -rf "$HOME"' EXIT
mkdir "$HOME/.ssh"
printf '%s\\n' 'ssh-ed25519 last-key' > "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
before=$(stat -c %a "$HOME/.ssh/authorized_keys")
printf '%s\\n' 'ssh-ed25519 last-key' | bash -c ''' + __import__('shlex').quote(_remove_key_remote_script()) + '''
[ $? -eq 0 ] || exit 5
[ ! -s "$HOME/.ssh/authorized_keys" ] || exit 6
[ "$(stat -c %a "$HOME/.ssh/authorized_keys")" = "$before" ] || exit 7
'''
    result = subprocess.run([_find_git_bash()], input=script, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
