from pathlib import Path
from unittest.mock import patch

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
