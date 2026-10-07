import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ssh_manager_app.runbook_parameters import validate_definitions, validate_values, prepare_parameter_spec


def test_shell_metacharacters_are_data_not_substituted_code():
    from ssh_manager_app.core import _find_git_bash
    spec = {"mode": "command", "command": 'printf "%s" "$RUNBOOK_VALUE"', "parameters": [{"name": "VALUE", "type": "text"}]}
    value = "hello'; printf INJECTED; # $(printf INJECTED)\nnext line"
    prepared = prepare_parameter_spec(spec, {"VALUE": value})
    result = subprocess.run([_find_git_bash(), "-c", prepared["command"]], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout == value
    assert spec["command"] == 'printf "%s" "$RUNBOOK_VALUE"'


@pytest.mark.parametrize("parameter,value", [({"name": "PORT", "type": "port"}, "65536"),
    ({"name": "NUMBER", "type": "integer"}, "1;id"), ({"name": "PATH", "type": "path"}, "relative"),
    ({"name": "SERVICE", "type": "choice", "choices": ["web", "db"]}, "other")])
def test_typed_values_reject_invalid_input(parameter, value):
    with pytest.raises(ValueError):
        validate_values([parameter], {parameter["name"]: value})


def test_secret_defaults_and_duplicate_or_shell_variable_names_rejected():
    for parameters in ([{"name": "TOKEN", "secret": True, "default": "password"}],
                       [{"name": "A"}, {"name": "A"}], [{"name": "A;id"}]):
        with pytest.raises(ValueError):
            validate_definitions(parameters)


def test_secret_command_only_occurs_in_protected_body_not_terminal_header():
    from ssh_manager_app.core import build_remote_command_wt_command
    from ssh_manager_app.models import Session
    spec = {"mode": "command", "command": 'test -n "$RUNBOOK_TOKEN"', "parameters": [{"name": "TOKEN", "secret": True}]}
    values = {"TOKEN": "private-dummy-token"}
    actual = prepare_parameter_spec(spec, values)
    display = prepare_parameter_spec(spec, values, redact=True)
    scripts = []
    with patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda prefix, text: scripts.append(text) or "test.sh"):
        build_remote_command_wt_command([(Session("x", "Test", [], "test.invalid"), "ops", actual["command"])], close_on_success=True, display_command=display["command"])
    assert scripts[0].count("private-dummy-token") == 1
    assert "<verborgen>" in scripts[0]
    assert "private-dummy-token" not in display["command"]


def test_runtime_values_never_enter_history_or_favorites():
    import json
    from ssh_manager_app.actions_remote import run_remote_command
    from ssh_manager_app.models import Session, default_settings
    session = Session("x", "Test", [], "test.invalid", "ops")
    spec = {"mode": "command", "command": 'test -n "$RUNBOOK_TOKEN"', "parameters": [{"name": "TOKEN", "secret": True}]}
    app = SimpleNamespace(settings=default_settings(), _initial_toolbar_search_texts={},
                          _tree=SimpleNamespace(get_session_colors=lambda: {}), wait_window=lambda _: None)
    dialog = SimpleNamespace(result=("all", spec, True, False, ""), _favorites=[])
    inputs = SimpleNamespace(result={"TOKEN": "private-dummy-token"})
    confirm = SimpleNamespace(result=True)
    with patch("ssh_manager_app.actions_remote.RemoteCommandDialog", return_value=dialog), \
         patch("ssh_manager_app.runbook_parameters.RunbookParametersDialog", return_value=inputs), \
         patch("ssh_manager_app.actions_remote.RemoteCommandConfirmDialog", return_value=confirm) as preview, \
         patch("ssh_manager_app.actions_remote.build_remote_command_wt_command", return_value="terminal") as build, \
         patch("ssh_manager_app.actions_remote.TerminalLauncher.launch_built_command"):
        run_remote_command(app, [session])
    assert "private-dummy-token" in build.call_args.args[0][0][2]
    assert "private-dummy-token" not in preview.call_args.args[1]
    assert "private-dummy-token" not in json.dumps(app._initial_toolbar_search_texts)
    assert inputs.result is None
