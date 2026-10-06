from pathlib import Path
from unittest.mock import patch
import subprocess
import json

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


def test_protected_script_decrypts_in_memory_and_cleans_files(tmp_path):
    from ssh_manager_app.core import _find_git_bash
    from ssh_manager_app.secret_scripts import write_protected_script
    secret = 'secret ä " value'
    script = write_protected_script(tmp_path, "offline_", "printf '%s' " + __import__('shlex').quote(secret) + "\n")
    assert secret not in Path(script).read_text(encoding="utf-8")
    assert secret.encode() not in Path(script).with_suffix(".payload").read_bytes()
    result = subprocess.run([_find_git_bash(), script], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode("utf-8") == secret
    assert not Path(script).exists()
    assert not Path(script).with_suffix(".payload").exists()


def test_failed_terminal_start_cleans_protected_files(tmp_path):
    from ssh_manager_app.core import TerminalCommand, _make_tab
    from ssh_manager_app.secret_scripts import write_protected_script
    script = write_protected_script(tmp_path, "offline_", "echo test\n")
    session = Session("s", "Server", [], "host")
    command = TerminalCommand([_make_tab(session, "ops", ["bash", script], WindowsTerminalSettings())])
    with patch("ssh_manager_app.core.subprocess.Popen", side_effect=OSError("offline")):
        with pytest.raises(OSError):
            TerminalLauncher._launch_windows_command(command)
    assert not Path(script).exists()
    assert not Path(script).with_suffix(".payload").exists()


def test_jump_dialog_really_constructs_and_uses_configured_user():
    import tkinter as tk
    from ssh_manager_app.dialogs_remote import JumpHostDialog
    from ssh_manager_app.models import AppSettings
    root = tk.Tk()
    root.withdraw()
    root.settings = AppSettings(default_user="configured")
    try:
        session = Session("s", "Server", [], "host")
        dialog = JumpHostDialog(root, session, [session])
        assert dialog._jump_user_var.get() == "configured"
        dialog.destroy()
    finally:
        root.destroy()


def test_append_alias_uses_loader_and_preserves_config_backup(tmp_path, monkeypatch):
    import ssh_manager_app.core as core
    import ssh_manager_app.storage as storage
    path = tmp_path / "config"
    original = "Host old\n    HostName old.example\n"
    path.write_text(original)
    monkeypatch.setattr(core, "_SSH_CONFIG_FILE", path)
    monkeypatch.setattr(storage, "_SSH_CONFIG_FILE", path)
    core._append_ssh_config_alias("new", Session("s", "Server", [], "host"), "ops", "jump", "jumper", 2200)
    assert "Host new" in path.read_text()
    assert "ProxyJump jumper@jump:2200" in path.read_text()
    assert path.with_suffix(".bak").read_text() == original
    with pytest.raises(ValueError):
        core._append_ssh_config_alias("old", Session("s", "Server", [], "host"), "ops", "jump")


def test_corrupt_sessions_are_preserved_before_next_save(tmp_path, monkeypatch):
    import ssh_manager_app.storage as storage
    path = tmp_path / "app_sessions.json"
    path.write_bytes(b'{broken')
    monkeypatch.setattr(storage, "_APP_SESSIONS_FILE", path)
    assert storage.load_app_sessions() == []
    backup, = tmp_path.glob("app_sessions.json.corrupt-*")
    storage.save_app_sessions([])
    assert backup.read_bytes() == b'{broken'
    assert storage.take_load_warnings()


def test_failed_atomic_replace_preserves_original(tmp_path):
    from ssh_manager_app.storage import atomic_write_text
    path = tmp_path / "original.json"
    path.write_text("original")
    with patch("ssh_manager_app.storage.os.replace", side_effect=PermissionError("locked")):
        with pytest.raises(PermissionError):
            atomic_write_text(path, "new")
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_interrupted_session_notes_save_recovers_both_files(tmp_path, monkeypatch):
    import ssh_manager_app.storage as storage
    sessions_file, notes_file = tmp_path / "sessions.json", tmp_path / "notes.json"
    monkeypatch.setattr(storage, "_APP_SESSIONS_FILE", sessions_file)
    monkeypatch.setattr(storage, "_NOTES_FILE", notes_file)
    real_write = storage._atomic_write_json
    def write(path, data):
        if path == notes_file:
            raise PermissionError("interrupted")
        real_write(path, data)
    session = Session("__app__s", "Server", [], "host", source="app")
    with patch.object(storage, "_atomic_write_json", side_effect=write):
        with pytest.raises(PermissionError):
            storage.save_sessions_and_notes([session], {session.key: "note"})
    assert (tmp_path / "session-notes-pending.json").exists()
    assert len(storage.load_app_sessions()) == 1
    assert storage.load_notes() == {session.key: "note"}
    assert not (tmp_path / "session-notes-pending.json").exists()


def test_save_ui_state_does_not_mutate_callers_dict(tmp_path, monkeypatch):
    import ssh_manager_app.storage as storage
    monkeypatch.setattr(storage, "_STATE_FILE", tmp_path / "state.json")
    value = {"favorite_sessions": {"s": True}, "recent_sessions": ["s"]}
    original = json.loads(json.dumps(value))
    storage.save_ui_state(set(), {}, value)
    assert value == original


def test_settings_preview_leaves_saved_nested_state_unchanged():
    from copy import deepcopy
    from unittest.mock import MagicMock
    from ssh_manager_app.models import AppSettings, ToolbarSettings
    from ssh_manager_app.actions_ui import preview_toolbar_visibility
    app = MagicMock()
    app.settings = AppSettings()
    app._persisted_settings = deepcopy(app.settings)
    original = deepcopy(app._persisted_settings)
    with patch("ssh_manager_app.actions_ui.layout_toolbar_buttons"):
        preview_toolbar_visibility(app, ToolbarSettings(show_add_connection=False))
    assert not app.settings.toolbar.show_add_connection
    assert app._persisted_settings == original
    app.settings.toolbar.column_order.append("changed-draft")
    assert app._persisted_settings.toolbar.column_order == original.toolbar.column_order


def test_real_settings_cancel_restores_saved_toolbar(tmp_path, monkeypatch):
    from copy import deepcopy
    import ssh_manager_app.storage as storage
    import ssh_manager_app.constants as constants
    from ssh_manager import SSHManagerApp
    from ssh_manager_app.core import RegistryReader
    from ssh_manager_app.actions_ui import preview_toolbar_visibility, show_settings_view
    from ssh_manager_app.models import ToolbarSettings
    for name in ("_SETTINGS_FILE", "_STATE_FILE", "_APP_SESSIONS_FILE", "_NOTES_FILE", "_SSH_CONFIG_FILE"):
        monkeypatch.setattr(storage, name, tmp_path / (name + ".json"))
    monkeypatch.setattr(constants, "_STATE_FILE", tmp_path / "state.json")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(RegistryReader, "load_sessions", lambda self: [])
    storage.take_load_warnings()
    monkeypatch.setattr("tkinter.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("tkinter.messagebox.showerror", lambda *a, **k: None)
    app = SSHManagerApp()
    app.withdraw()
    try:
        saved = deepcopy(app._persisted_settings)
        show_settings_view(app)
        preview_toolbar_visibility(app, ToolbarSettings(show_add_connection=False))
        app._settings_view._cancel_and_show_main_view()
        assert app.settings == saved
        assert app.settings is not app._persisted_settings
    finally:
        app.destroy()


def test_old_heredoc_marker_cannot_escape_to_local_shell(tmp_path):
    from ssh_manager_app.core import _find_git_bash, build_remote_command_wt_command
    captured = {}
    local_marker = tmp_path / "unexpected-local-file"
    remote_command = "__REMOTE_CMD__\nprintf hacked > " + __import__('shlex').quote(str(local_marker).replace("\\", "/"))
    with patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda prefix, content: captured.update(content=content) or "offline.sh"):
        build_remote_command_wt_command([(Session("s", "Server", [], "host"), "ops", remote_command)], close_on_success=True)
    output = tmp_path / "ssh-input"
    script = tmp_path / "offline.sh"
    script.write_text("ssh() { cat > " + __import__('shlex').quote(str(output).replace("\\", "/")) + "; }\n" + captured["content"], encoding="utf-8")
    result = subprocess.run([_find_git_bash(), str(script)], capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not local_marker.exists()
    assert output.read_text() == remote_command + "\n"


def test_invalid_runbook_interpreter_never_creates_script():
    from ssh_manager_app.core import build_remote_script_wt_command
    with patch("ssh_manager_app.core._write_temp_bash_script") as write:
        with pytest.raises(ValueError):
            build_remote_script_wt_command([(Session("s", "Server", [], "host"), "ops", {"mode": "remote_script", "interpreter": "bash; local-command"})], close_on_success=True)
    write.assert_not_called()


def test_local_script_has_unique_private_upload_directory():
    from ssh_manager_app.core import build_remote_script_wt_command
    captured = []
    with patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda prefix, content: captured.append(content) or "offline.sh"):
        for _ in range(2):
            build_remote_script_wt_command([(Session("s", "Server", [], "host", port=2222), "ops", {"mode": "local_script", "local_path": "script.py", "interpreter": "python3"})], close_on_success=True)
    assert captured[0] != captured[1]
    assert "mkdir -m 700" in captured[0]
    assert "scp -P 2222 --" in captured[0]
    assert "$(date" not in captured[0]
    assert "rm -rf --" in captured[0]
