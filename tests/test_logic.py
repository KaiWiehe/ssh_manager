import json
import tkinter as tk
import os
import sys
import tempfile

import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import winreg
from ssh_manager_app.actions_app import (
    close_app,
    export_settings_dialog,
    get_all_folder_names,
    get_ssh_aliases,
    import_settings_dialog,
    show_search_history_menu,
)
from ssh_manager_app.actions_notes import edit_session_note
from ssh_manager_app.dialogs_base import UserDialog, _build_quickselect_buttons, resolve_user_dialog_defaults
from ssh_manager_app.dialogs_move_folder import MoveFolderDialog
from ssh_manager_app.dialogs_session_edit import SessionEditDialog
from ssh_manager_app.dialogs_settings_misc import SettingsView, SshConfigInspectDialog
from ssh_manager_app.dialogs_toast import ToastNotification
from ssh_manager_app.actions_sessions import add_session, delete_folder, delete_session, duplicate_app_session, duplicate_ssh_alias, edit_session, move_session, move_sessions, open_appdata_jsons_in_vscode, rename_folder
from ssh_manager_app.actions_open import inspect_ssh_config, open_in_winscp, open_ssh_config_in_vscode
from ssh_manager_app.actions_remote import connect_sessions, deploy_ssh_key, open_tunnel, open_via_jumphost, quick_connect_session, remove_ssh_key, resolve_single_session_user, resolve_users_for_sessions, run_remote_command
from ssh_manager_app.actions_ui import add_search_history_entry, apply_settings, build_visible_sessions, collapse_all, deselect_all, expand_all, on_search_changed, on_selection_changed, preview_source_visibility, preview_toolbar_visibility, reload_sessions, reset_settings, reset_session_colors, reset_view_state, select_all, show_main_view, show_settings_view
from ssh_manager_app.ui import TOOLBAR_BUTTON_ORDER, layout_toolbar_buttons
from ssh_manager_app.constants import DEFAULT_USER, PALETTE, QUICK_USERS, _APP_PREFIX, _SSH_ALIAS_PREFIX, _SSH_CONFIG_DEFAULT_FOLDER
from ssh_manager_app.core import RegistryReader, _build_jump_ssh_command, _build_ssh_command, _shell_single_quote, _ssh_target, _terminal_profile_flag, _terminal_title_flag, build_wt_command, parse_session_key
from ssh_manager_app.models import AppSettings, Session, SourceVisibilitySettings, color_tag
from ssh_manager_app.tree import _session_values_text
from ssh_manager_app.storage import (
    load_filezilla_config_sessions,
    load_notes,
    load_settings_from_path,
    load_ssh_config_sessions,
    load_ui_state,
    save_notes,
    save_ui_state,
)


def test_build_quickselect_buttons_creates_wrapped_buttons_and_sets_target():
    parent = MagicMock()
    frame = MagicMock()
    target_var = MagicMock()
    button_commands = []
    grid_calls = []

    def fake_button(*_args, **kwargs):
        button_commands.append(kwargs["command"])
        btn = MagicMock()
        btn.grid.side_effect = lambda **grid_kwargs: grid_calls.append(grid_kwargs)
        return btn

    with patch("ssh_manager_app.dialogs_base.ttk.Frame", return_value=frame) as frame_cls, \
         patch("ssh_manager_app.dialogs_base.ttk.Button", side_effect=fake_button):
        result = _build_quickselect_buttons(parent, ["root", "ops", "deploy"], target_var, columns=2, width=10)

    frame_cls.assert_called_once_with(parent)
    frame.columnconfigure.assert_any_call(0, weight=1)
    frame.columnconfigure.assert_any_call(1, weight=1)
    assert result is frame
    assert grid_calls == [
        {"row": 0, "column": 0, "padx": 2, "pady": 2, "sticky": "ew"},
        {"row": 0, "column": 1, "padx": 2, "pady": 2, "sticky": "ew"},
        {"row": 1, "column": 0, "padx": 2, "pady": 2, "sticky": "ew"},
    ]

    button_commands[1]()
    target_var.set.assert_called_once_with("ops")


def test_resolve_user_dialog_defaults_returns_copied_fallbacks():
    quick_users, default_user = resolve_user_dialog_defaults(None, "")

    assert quick_users == QUICK_USERS
    assert quick_users is not QUICK_USERS
    assert default_user == DEFAULT_USER


def test_resolve_user_dialog_defaults_preserves_explicit_values():
    source_quick_users = ["ops", "deploy"]

    quick_users, default_user = resolve_user_dialog_defaults(source_quick_users, "root")

    assert quick_users == source_quick_users
    assert quick_users is not source_quick_users
    assert default_user == "root"


def test_user_dialog_on_ok_rejects_invalid_username():
    dialog = UserDialog.__new__(UserDialog)
    dialog._user_var = MagicMock()
    dialog._user_var.get.return_value = "bad user!"
    dialog.destroy = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.dialogs_base.messagebox.showwarning") as showwarning:
        UserDialog._on_ok(dialog)

    showwarning.assert_called_once_with(
        "Ungültiger Benutzername",
        "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
        parent=dialog,
    )
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_user_dialog_on_ok_accepts_trimmed_username():
    dialog = UserDialog.__new__(UserDialog)
    dialog._user_var = MagicMock()
    dialog._user_var.get.return_value = "  deploy-user  "
    dialog.destroy = MagicMock()
    dialog.result = None

    UserDialog._on_ok(dialog)

    assert dialog.result == "deploy-user"
    dialog.destroy.assert_called_once_with()


def test_user_dialog_center_on_parent_positions_geometry():
    dialog = UserDialog.__new__(UserDialog)
    dialog.update_idletasks = MagicMock()
    dialog.winfo_reqwidth = MagicMock(return_value=200)
    dialog.winfo_reqheight = MagicMock(return_value=100)
    dialog.geometry = MagicMock()
    parent = MagicMock()
    parent.winfo_width.return_value = 800
    parent.winfo_height.return_value = 600
    parent.winfo_x.return_value = 10
    parent.winfo_y.return_value = 20

    UserDialog._center_on_parent(dialog, parent)

    dialog.update_idletasks.assert_called_once_with()
    dialog.geometry.assert_called_once_with("+310+270")


def test_user_dialog_on_ok_keeps_dialog_open_for_empty_username():
    dialog = UserDialog.__new__(UserDialog)
    dialog._user_var = MagicMock()
    dialog._user_var.get.return_value = "   "
    dialog.destroy = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.dialogs_base.messagebox.showwarning") as showwarning:
        UserDialog._on_ok(dialog)

    showwarning.assert_not_called()
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_user_dialog_on_cancel_sets_none_and_destroys():
    dialog = UserDialog.__new__(UserDialog)
    dialog.result = "ops"
    dialog.destroy = MagicMock()

    UserDialog._on_cancel(dialog)

    assert dialog.result is None
    dialog.destroy.assert_called_once_with()


def test_move_folder_dialog_on_ok_rejects_blank_folder_name():
    dialog = MoveFolderDialog.__new__(MoveFolderDialog)
    dialog._folder_var = MagicMock()
    dialog._folder_var.get.return_value = "   "
    dialog.destroy = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.dialogs_move_folder.messagebox.showwarning") as showwarning:
        MoveFolderDialog._on_ok(dialog)

    showwarning.assert_called_once_with(
        "Fehlendes Feld",
        "Bitte einen Ordner eingeben.",
        parent=dialog,
    )
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_move_folder_dialog_on_ok_accepts_trimmed_folder_name():
    dialog = MoveFolderDialog.__new__(MoveFolderDialog)
    dialog._folder_var = MagicMock()
    dialog._folder_var.get.return_value = "  Team/Sub  "
    dialog.destroy = MagicMock()
    dialog.result = None

    MoveFolderDialog._on_ok(dialog)

    assert dialog.result == "Team/Sub"
    dialog.destroy.assert_called_once_with()


def test_jump_host_dialog_on_save_prompts_for_alias_and_stores_result():
    from ssh_manager_app.dialogs_remote import JumpHostDialog

    dialog = JumpHostDialog.__new__(JumpHostDialog)
    dialog._validate = MagicMock(return_value=("jump.example", "jumper", 2200))
    dialog._target_session = Session("target", "prod", [], "prod.example")
    dialog.destroy = MagicMock()
    dialog.save_result = None

    with patch("ssh_manager_app.dialogs_remote.simpledialog.askstring", return_value="  jump-prod  ") as askstring:
        JumpHostDialog._on_save(dialog)

    askstring.assert_called_once_with(
        "SSH-Config speichern",
        "Name für den neuen SSH-Config-Host:",
        parent=dialog,
    )
    assert dialog.save_result == ("jump-prod", "jump.example", 2200, "jumper", "target")
    dialog.destroy.assert_called_once_with()


def test_resolve_jump_host_default_user_prefers_parent_settings_and_falls_back_to_builtin_default():
    from ssh_manager_app.dialogs_remote import _resolve_jump_host_default_user

    parent = MagicMock()
    parent.settings = MagicMock(default_user="ops")
    assert _resolve_jump_host_default_user(parent) == "ops"

    parent.settings.default_user = ""
    assert _resolve_jump_host_default_user(parent) == DEFAULT_USER

    del parent.settings
    assert _resolve_jump_host_default_user(parent) == DEFAULT_USER


def test_jump_host_dialog_validate_rejects_invalid_port_range():
    from ssh_manager_app.dialogs_remote import JumpHostDialog

    dialog = JumpHostDialog.__new__(JumpHostDialog)
    dialog._jump_host_var = MagicMock(); dialog._jump_host_var.get.return_value = "jump.example"
    dialog._jump_user_var = MagicMock(); dialog._jump_user_var.get.return_value = "jumper"
    dialog._jump_port_var = MagicMock(); dialog._jump_port_var.get.return_value = "70000"

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        result = JumpHostDialog._validate(dialog)

    assert result is None
    showwarning.assert_called_once_with(
        "Ungültiger Port",
        "Jumphost-Port muss zwischen 1 und 65535 liegen.",
        parent=dialog,
    )



def test_jump_host_dialog_on_cancel_clears_results_and_destroys():
    from ssh_manager_app.dialogs_remote import JumpHostDialog

    dialog = JumpHostDialog.__new__(JumpHostDialog)
    dialog.result = ("jump.example", "jumper", 22)
    dialog.save_result = ("alias", "jump.example", 22, "jumper", "target")
    dialog.destroy = MagicMock()

    JumpHostDialog._on_cancel(dialog)

    assert dialog.result is None
    assert dialog.save_result is None
    dialog.destroy.assert_called_once_with()



def test_jump_host_dialog_center_on_parent_clamps_size_and_sets_geometry():
    from ssh_manager_app.dialogs_remote import JumpHostDialog

    dialog = JumpHostDialog.__new__(JumpHostDialog)
    dialog.update_idletasks = MagicMock()
    dialog.winfo_reqwidth = MagicMock(return_value=1200)
    dialog.winfo_reqheight = MagicMock(return_value=900)
    dialog.geometry = MagicMock()
    parent = SimpleNamespace(
        winfo_width=lambda: 1000,
        winfo_height=lambda: 800,
        winfo_x=lambda: 10,
        winfo_y=lambda: 20,
    )

    JumpHostDialog._center_on_parent(dialog, parent)

    dialog.geometry.assert_called_once_with("960x760+30+40")



def test_ssh_copy_id_dialog_init_uses_default_quick_users():
    from ssh_manager_app.dialogs_remote import SshCopyIdDialog

    parent = MagicMock()

    with patch("ssh_manager_app.dialogs_remote.tk.Toplevel.__init__", return_value=None), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.title"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.resizable"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.transient"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.grab_set"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.bind"), \
         patch.object(SshCopyIdDialog, "_build"), \
         patch.object(SshCopyIdDialog, "_center_on_parent"):
        dialog = SshCopyIdDialog(parent, quick_users=None, default_user="")

    assert dialog._quick_users == QUICK_USERS
    assert dialog._quick_users is not QUICK_USERS
    assert dialog._default_user == DEFAULT_USER


def test_ssh_remove_key_dialog_init_copies_explicit_quick_users():
    from ssh_manager_app.dialogs_remote import SshRemoveKeyDialog

    parent = MagicMock()
    source_quick_users = ["ops", "deploy"]

    with patch("ssh_manager_app.dialogs_remote.tk.Toplevel.__init__", return_value=None), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.title"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.resizable"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.transient"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.grab_set"), \
         patch("ssh_manager_app.dialogs_remote.tk.Toplevel.bind"), \
         patch.object(SshRemoveKeyDialog, "_build"), \
         patch.object(SshRemoveKeyDialog, "_center_on_parent"):
        dialog = SshRemoveKeyDialog(parent, quick_users=source_quick_users, default_user="root")

    assert dialog._quick_users == source_quick_users
    assert dialog._quick_users is not source_quick_users
    assert dialog._default_user == "root"



def test_ssh_copy_id_dialog_on_ok_accepts_valid_input():
    from ssh_manager_app.dialogs_remote import SshCopyIdDialog

    dialog = SshCopyIdDialog.__new__(SshCopyIdDialog)
    dialog._key_var = MagicMock(); dialog._key_var.get.return_value = "id_ed25519.pub"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog.result = None
    dialog.destroy = MagicMock()

    SshCopyIdDialog._on_ok(dialog)

    assert dialog.result == ("id_ed25519.pub", "deploy")
    dialog.destroy.assert_called_once_with()



def test_ssh_copy_id_dialog_on_ok_rejects_invalid_user():
    from ssh_manager_app.dialogs_remote import SshCopyIdDialog

    dialog = SshCopyIdDialog.__new__(SshCopyIdDialog)
    dialog._key_var = MagicMock(); dialog._key_var.get.return_value = "id_ed25519.pub"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "bad user!"
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        SshCopyIdDialog._on_ok(dialog)

    assert dialog.result is None
    showwarning.assert_called_once_with(
        "Ungültiger Benutzername",
        "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
        parent=dialog,
    )
    dialog.destroy.assert_not_called()



def test_ssh_remove_key_dialog_on_ok_requires_key():
    from ssh_manager_app.dialogs_remote import SshRemoveKeyDialog

    dialog = SshRemoveKeyDialog.__new__(SshRemoveKeyDialog)
    dialog._key_var = MagicMock(); dialog._key_var.get.return_value = "   "
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        SshRemoveKeyDialog._on_ok(dialog)

    assert dialog.result is None
    showwarning.assert_called_once_with("Kein Key", "Bitte einen Public Key auswählen.", parent=dialog)
    dialog.destroy.assert_not_called()



def test_ssh_remove_key_dialog_on_cancel_clears_result_and_destroys():
    from ssh_manager_app.dialogs_remote import SshRemoveKeyDialog

    dialog = SshRemoveKeyDialog.__new__(SshRemoveKeyDialog)
    dialog.result = ("id_ed25519.pub", "deploy")
    dialog.destroy = MagicMock()

    SshRemoveKeyDialog._on_cancel(dialog)

    assert dialog.result is None
    dialog.destroy.assert_called_once_with()



def test_remote_command_confirm_dialog_ok_and_cancel_toggle_result():
    from ssh_manager_app.dialogs_remote import RemoteCommandConfirmDialog

    dialog = RemoteCommandConfirmDialog.__new__(RemoteCommandConfirmDialog)
    dialog.result = False
    dialog.destroy = MagicMock()

    RemoteCommandConfirmDialog._on_ok(dialog)

    assert dialog.result is True
    dialog.destroy.assert_called_once_with()

    dialog = RemoteCommandConfirmDialog.__new__(RemoteCommandConfirmDialog)
    dialog.result = True
    dialog.destroy = MagicMock()

    RemoteCommandConfirmDialog._on_cancel(dialog)

    assert dialog.result is False
    dialog.destroy.assert_called_once_with()



def test_ssh_tunnel_dialog_on_ok_accepts_valid_input():
    from ssh_manager_app.dialogs_remote import SshTunnelDialog

    dialog = SshTunnelDialog.__new__(SshTunnelDialog)
    dialog._jumphost_var = MagicMock(); dialog._jumphost_var.get.return_value = "ssh.example"
    dialog._local_port_var = MagicMock(); dialog._local_port_var.get.return_value = "15432"
    dialog._remote_host_var = MagicMock(); dialog._remote_host_var.get.return_value = "db.internal"
    dialog._remote_port_var = MagicMock(); dialog._remote_port_var.get.return_value = "5432"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog._parse_port = MagicMock(side_effect=[15432, 5432])
    dialog.result = None
    dialog.destroy = MagicMock()

    SshTunnelDialog._on_ok(dialog)

    assert dialog.result == ("ssh.example", 15432, "db.internal", 5432, "deploy")
    dialog.destroy.assert_called_once_with()



def test_ssh_tunnel_dialog_on_ok_rejects_invalid_target_host():
    from ssh_manager_app.dialogs_remote import SshTunnelDialog

    dialog = SshTunnelDialog.__new__(SshTunnelDialog)
    dialog._jumphost_var = MagicMock(); dialog._jumphost_var.get.return_value = "ssh.example"
    dialog._local_port_var = MagicMock()
    dialog._remote_host_var = MagicMock(); dialog._remote_host_var.get.return_value = "bad host!"
    dialog._remote_port_var = MagicMock()
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog._parse_port = MagicMock(return_value=15432)
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        SshTunnelDialog._on_ok(dialog)

    assert dialog.result is None
    showwarning.assert_called_once_with(
        "Ungültiger Zielserver",
        "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
        parent=dialog,
    )
    dialog.destroy.assert_not_called()



def test_remote_command_dialog_on_ok_accepts_all_mode():
    from ssh_manager_app.dialogs_remote import RemoteCommandDialog

    dialog = RemoteCommandDialog.__new__(RemoteCommandDialog)
    dialog._command_text = MagicMock(); dialog._command_text.get.return_value = "echo hi\n"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog._user_mode = MagicMock(); dialog._user_mode.get.return_value = "all"
    dialog._close_on_success = MagicMock(); dialog._close_on_success.get.return_value = True
    dialog.result = None
    dialog.destroy = MagicMock()

    RemoteCommandDialog._on_ok(dialog)

    assert dialog.result == ("all", "echo hi", True)
    dialog.destroy.assert_called_once_with()



def test_remote_command_dialog_on_ok_rejects_missing_command():
    from ssh_manager_app.dialogs_remote import RemoteCommandDialog

    dialog = RemoteCommandDialog.__new__(RemoteCommandDialog)
    dialog._command_text = MagicMock(); dialog._command_text.get.return_value = "  \n"
    dialog._user_var = MagicMock()
    dialog._user_mode = MagicMock(); dialog._user_mode.get.return_value = "all"
    dialog._close_on_success = MagicMock()
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        RemoteCommandDialog._on_ok(dialog)

    assert dialog.result is None
    showwarning.assert_called_once_with("Kein Befehl", "Bitte einen Befehl eingeben.", parent=dialog)
    dialog.destroy.assert_not_called()



def test_remote_command_dialog_on_ok_all_mode_rejects_invalid_user():
    from ssh_manager_app.dialogs_remote import RemoteCommandDialog

    dialog = RemoteCommandDialog.__new__(RemoteCommandDialog)
    dialog._command_text = MagicMock(); dialog._command_text.get.return_value = "uptime"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "bad user!"
    dialog._user_mode = MagicMock(); dialog._user_mode.get.return_value = "all"
    dialog._close_on_success = MagicMock()
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        RemoteCommandDialog._on_ok(dialog)

    assert dialog.result is None
    showwarning.assert_called_once_with(
        "Ungültiger Benutzername",
        "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
        parent=dialog,
    )
    dialog.destroy.assert_not_called()



def test_remote_command_dialog_on_cancel_clears_result_and_destroys():
    from ssh_manager_app.dialogs_remote import RemoteCommandDialog

    dialog = RemoteCommandDialog.__new__(RemoteCommandDialog)
    dialog.result = ("all", "uptime", False)
    dialog.destroy = MagicMock()

    RemoteCommandDialog._on_cancel(dialog)

    assert dialog.result is None
    dialog.destroy.assert_called_once_with()



def test_ssh_tunnel_dialog_parse_port_rejects_non_numeric_value():
    from ssh_manager_app.dialogs_remote import SshTunnelDialog

    dialog = SshTunnelDialog.__new__(SshTunnelDialog)
    var = MagicMock(); var.get.return_value = "abc"

    with patch("ssh_manager_app.dialogs_remote.messagebox.showwarning") as showwarning:
        result = SshTunnelDialog._parse_port(dialog, var, "Lokaler Port")

    assert result is None
    showwarning.assert_called_once_with(
        "Ungültiger Port",
        "Lokaler Port muss eine Zahl sein.",
        parent=dialog,
    )



def test_ssh_tunnel_dialog_on_cancel_clears_result_and_destroys():
    from ssh_manager_app.dialogs_remote import SshTunnelDialog

    dialog = SshTunnelDialog.__new__(SshTunnelDialog)
    dialog.result = ("ssh.example", 15432, "db.internal", 5432, "deploy")
    dialog.destroy = MagicMock()

    SshTunnelDialog._on_cancel(dialog)

    assert dialog.result is None
    dialog.destroy.assert_called_once_with()



def test_session_edit_dialog_on_ok_alias_creates_alias_copy_session():
    dialog = SessionEditDialog.__new__(SessionEditDialog)
    dialog._alias_var = MagicMock()
    dialog._alias_var.get.return_value = "prod-alias"
    dialog._alias_folder_var = MagicMock()
    dialog._alias_folder_var.get.return_value = "Prod/Sub"
    dialog._existing_session = None
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_session_edit.uuid.uuid4", return_value="uuid-1"):
        SessionEditDialog._on_ok_alias(dialog)

    assert dialog.result == Session(
        key=_SSH_ALIAS_PREFIX + "uuid-1",
        display_name="prod-alias",
        folder_path=["Prod", "Sub"],
        hostname="prod-alias",
        username="",
        port=22,
        source="ssh_alias",
    )
    dialog.destroy.assert_called_once_with()


def test_session_edit_dialog_on_ok_verbindung_validates_and_builds_session():
    dialog = SessionEditDialog.__new__(SessionEditDialog)
    dialog._name_var = MagicMock(); dialog._name_var.get.return_value = "Srv 1"
    dialog._host_var = MagicMock(); dialog._host_var.get.return_value = "host.example"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog._folder_var = MagicMock(); dialog._folder_var.get.return_value = "Prod/App"
    dialog._port_var = MagicMock(); dialog._port_var.get.return_value = "2222"
    dialog._note_text = MagicMock(); dialog._note_text.get.return_value = " note text \n"
    dialog._existing_session = None
    dialog._duplicate = False
    dialog.result = None
    dialog.note_result = ""
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_session_edit.uuid.uuid4", return_value="uuid-2"):
        SessionEditDialog._on_ok_verbindung(dialog)

    assert dialog.result == Session(
        key=_APP_PREFIX + "uuid-2",
        display_name="Srv 1",
        folder_path=["Prod", "App"],
        hostname="host.example",
        username="deploy",
        port=2222,
        source="app",
    )
    assert dialog.note_result == "note text"
    dialog.destroy.assert_called_once_with()


def test_session_edit_dialog_on_ok_verbindung_rejects_invalid_hostname():
    dialog = SessionEditDialog.__new__(SessionEditDialog)
    dialog._name_var = MagicMock(); dialog._name_var.get.return_value = "Srv 1"
    dialog._host_var = MagicMock(); dialog._host_var.get.return_value = "bad host!"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog._folder_var = MagicMock(); dialog._folder_var.get.return_value = "Prod"
    dialog._port_var = MagicMock(); dialog._port_var.get.return_value = "22"
    dialog.destroy = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.dialogs_session_edit.messagebox.showwarning") as showwarning:
        SessionEditDialog._on_ok_verbindung(dialog)

    showwarning.assert_called_once_with(
        "Ungültiger Hostname",
        "Nur Buchstaben, Ziffern, Punkte, Bindestriche, Unterstriche und Doppelpunkte erlaubt.",
        parent=dialog,
    )
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_session_edit_dialog_on_ok_alias_rejects_missing_folder():
    dialog = SessionEditDialog.__new__(SessionEditDialog)
    dialog._alias_var = MagicMock(); dialog._alias_var.get.return_value = "prod-alias"
    dialog._alias_folder_var = MagicMock(); dialog._alias_folder_var.get.return_value = "   "
    dialog.destroy = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.dialogs_session_edit.messagebox.showwarning") as showwarning:
        SessionEditDialog._on_ok_alias(dialog)

    showwarning.assert_called_once_with("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=dialog)
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_session_edit_dialog_on_ok_verbindung_rejects_invalid_port():
    dialog = SessionEditDialog.__new__(SessionEditDialog)
    dialog._name_var = MagicMock(); dialog._name_var.get.return_value = "Srv 1"
    dialog._host_var = MagicMock(); dialog._host_var.get.return_value = "host.example"
    dialog._user_var = MagicMock(); dialog._user_var.get.return_value = "deploy"
    dialog._folder_var = MagicMock(); dialog._folder_var.get.return_value = "Prod"
    dialog._port_var = MagicMock(); dialog._port_var.get.return_value = "70000"
    dialog.destroy = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.dialogs_session_edit.messagebox.showwarning") as showwarning:
        SessionEditDialog._on_ok_verbindung(dialog)

    showwarning.assert_called_once_with("Ungültiger Port", "Port muss eine Zahl zwischen 1 und 65535 sein.", parent=dialog)
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_session_edit_dialog_on_ok_dispatches_by_mode():
    alias_dialog = SessionEditDialog.__new__(SessionEditDialog)
    alias_dialog._mode_var = MagicMock(); alias_dialog._mode_var.get.return_value = "alias"
    alias_dialog._on_ok_alias = MagicMock()
    alias_dialog._on_ok_verbindung = MagicMock()

    SessionEditDialog._on_ok(alias_dialog)

    alias_dialog._on_ok_alias.assert_called_once_with()
    alias_dialog._on_ok_verbindung.assert_not_called()

    app_dialog = SessionEditDialog.__new__(SessionEditDialog)
    app_dialog._mode_var = MagicMock(); app_dialog._mode_var.get.return_value = "verbindung"
    app_dialog._on_ok_alias = MagicMock()
    app_dialog._on_ok_verbindung = MagicMock()

    SessionEditDialog._on_ok(app_dialog)

    app_dialog._on_ok_verbindung.assert_called_once_with()
    app_dialog._on_ok_alias.assert_not_called()


def test_session_edit_dialog_on_cancel_clears_result_and_destroys():
    dialog = SessionEditDialog.__new__(SessionEditDialog)
    dialog.result = Session("s1", "srv1", [], "10.0.0.1")
    dialog.destroy = MagicMock()

    SessionEditDialog._on_cancel(dialog)

    assert dialog.result is None
    dialog.destroy.assert_called_once_with()


def test_move_folder_dialog_on_ok_accepts_trimmed_folder():
    dialog = MoveFolderDialog.__new__(MoveFolderDialog)
    dialog._folder_var = MagicMock(); dialog._folder_var.get.return_value = "  Prod/Sub  "
    dialog.result = None
    dialog.destroy = MagicMock()

    MoveFolderDialog._on_ok(dialog)

    assert dialog.result == "Prod/Sub"
    dialog.destroy.assert_called_once_with()


def test_move_folder_dialog_on_ok_rejects_empty_folder():
    dialog = MoveFolderDialog.__new__(MoveFolderDialog)
    dialog._folder_var = MagicMock(); dialog._folder_var.get.return_value = "   "
    dialog.result = None
    dialog.destroy = MagicMock()

    with patch("ssh_manager_app.dialogs_move_folder.messagebox.showwarning") as showwarning:
        MoveFolderDialog._on_ok(dialog)

    showwarning.assert_called_once_with("Fehlendes Feld", "Bitte einen Ordner eingeben.", parent=dialog)
    assert dialog.result is None
    dialog.destroy.assert_not_called()


def test_move_folder_dialog_on_cancel_clears_result_and_destroys():
    dialog = MoveFolderDialog.__new__(MoveFolderDialog)
    dialog.result = "Prod"
    dialog.destroy = MagicMock()

    MoveFolderDialog._on_cancel(dialog)

    assert dialog.result is None
    dialog.destroy.assert_called_once_with()


def test_move_folder_dialog_center_on_parent_sets_geometry():
    dialog = MoveFolderDialog.__new__(MoveFolderDialog)
    dialog.update_idletasks = MagicMock()
    dialog.winfo_reqwidth = MagicMock(return_value=120)
    dialog.winfo_reqheight = MagicMock(return_value=80)
    dialog.geometry = MagicMock()
    parent = SimpleNamespace(
        winfo_width=lambda: 400,
        winfo_height=lambda: 300,
        winfo_x=lambda: 50,
        winfo_y=lambda: 30,
    )

    MoveFolderDialog._center_on_parent(dialog, parent)

    dialog.geometry.assert_called_once_with("+190+140")


def test_toast_notification_places_itself_and_schedules_destroy():
    toast = ToastNotification.__new__(ToastNotification)
    toast.withdraw = MagicMock()
    toast.overrideredirect = MagicMock()
    toast.attributes = MagicMock()
    toast.update_idletasks = MagicMock()
    toast.winfo_reqwidth = MagicMock(return_value=180)
    toast.winfo_reqheight = MagicMock(return_value=40)
    toast.geometry = MagicMock()
    toast.deiconify = MagicMock()
    toast.after = MagicMock()
    toast.destroy = MagicMock()
    parent = SimpleNamespace(
        update_idletasks=MagicMock(),
        winfo_rootx=lambda: 100,
        winfo_rooty=lambda: 200,
        winfo_width=lambda: 500,
    )

    with patch("ssh_manager_app.dialogs_toast.tk.Toplevel.__init__", return_value=None), \
         patch("ssh_manager_app.dialogs_toast.ttk.Frame") as frame_cls, \
         patch("ssh_manager_app.dialogs_toast.ttk.Label") as label_cls:
        frame = MagicMock()
        frame_cls.return_value = frame
        label = MagicMock()
        label_cls.return_value = label

        ToastNotification.__init__(toast, parent, "Saved", duration_ms=1500)

    toast.withdraw.assert_called_once_with()
    toast.overrideredirect.assert_called_once_with(True)
    toast.attributes.assert_called_once_with("-topmost", True)
    frame_cls.assert_called_once_with(toast, padding=(12, 8), style="Toast.TFrame")
    frame.pack.assert_called_once_with(fill="both", expand=True)
    label_cls.assert_called_once_with(frame, text="Saved", style="Toast.TLabel")
    label.pack.assert_called_once_with()
    parent.update_idletasks.assert_called_once_with()
    toast.geometry.assert_called_once_with("180x40+404+216")
    toast.deiconify.assert_called_once_with()
    toast.after.assert_called_once_with(1500, toast.destroy)


def test_terminal_profile_flag_falls_back_to_git_bash():
    assert _terminal_profile_flag("") == '-p "Git Bash" '
    assert _terminal_profile_flag("  Custom  ") == '-p "Custom" '


def test_terminal_title_flag_supports_name_host_and_user_host_modes():
    session = Session("s1", "prod", [], "10.0.0.1", username="deploy")

    assert _terminal_title_flag(session, "", "name_host") == '--title "prod (10.0.0.1)" '
    assert _terminal_title_flag(session, "ops", "user_host") == '--title "ops@10.0.0.1" '
    assert _terminal_title_flag(session, "", "unknown") == ""


def test_build_ssh_helpers_cover_regular_and_ssh_config_sessions():
    regular = Session("s1", "srv1", [], "10.0.0.1", username="deploy", port=2222, source="app")
    ssh_cfg = Session("s2", "prod-alias", [], "prod-alias", username="root", source="ssh_config")

    assert _build_ssh_command(regular, "ops") == "ssh -p 2222 ops@10.0.0.1"
    assert _build_ssh_command(ssh_cfg, "ignored") == "ssh prod-alias"
    assert _build_jump_ssh_command(regular, "ops", "jump.example", "jumper", 2200) == "ssh -J -p 2200 jumper@jump.example -p 2222 ops@10.0.0.1"
    assert _build_jump_ssh_command(ssh_cfg, "ops", "jump.example") == "ssh -J jump.example prod-alias"


def test_shell_quote_and_ssh_target_helpers_escape_and_format():
    assert _shell_single_quote("it's") == "'it'\"'\"'s'"
    assert _ssh_target("host", " user ", 2222) == "-p 2222 user@host"
    assert _ssh_target("host", "", 22) == "host"


def test_parse_session_key_with_folder():
    folder, name = parse_session_key("Extern/Bundo")
    assert folder == ["Extern"]
    assert name == "Bundo"


def test_parse_session_key_nested():
    folder, name = parse_session_key("Others/Sub/server1")
    assert folder == ["Others", "Sub"]
    assert name == "server1"


def test_parse_session_key_no_folder():
    folder, name = parse_session_key("tool-admin@10.120.67.31")
    assert folder == []
    assert name == "tool-admin@10.120.67.31"


def test_parse_session_key_url_encoded():
    folder, name = parse_session_key("Others/10.120.137.10%20-%20DB")
    assert folder == ["Others"]
    assert name == "10.120.137.10 - DB"


def test_parse_session_key_url_encoded_folder():
    folder, name = parse_session_key("My%20Servers/web-01")
    assert folder == ["My Servers"]
    assert name == "web-01"


def test_build_wt_command_empty_sessions():
    assert build_wt_command([], "tool-admin") == ""


def test_build_wt_command_single_session():
    sessions = [Session("k", "srv1", [], "10.0.0.1")]
    cmd = build_wt_command(sessions, "tool-admin")
    assert cmd == 'wt.exe new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.1'


def test_build_wt_command_multiple_sessions():
    sessions = [
        Session("k1", "srv1", [], "10.0.0.1"),
        Session("k2", "srv2", [], "10.0.0.2"),
    ]
    cmd = build_wt_command(sessions, "tool-admin")
    assert cmd == (
        'wt.exe new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.1'
        ' ; new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.2'
    )


def test_build_wt_command_non_standard_port():
    sessions = [Session("k", "srv", [], "10.0.0.1", port=2222)]
    cmd = build_wt_command(sessions, "dev-sys")
    assert cmd == 'wt.exe new-tab -p "Git Bash" -- ssh -p 2222 dev-sys@10.0.0.1'


def test_build_wt_command_mixed_ports():
    sessions = [
        Session("k1", "s1", [], "10.0.0.1", port=22),
        Session("k2", "s2", [], "10.0.0.2", port=2222),
    ]
    cmd = build_wt_command(sessions, "tool-admin")
    assert cmd == (
        'wt.exe new-tab -p "Git Bash" -- ssh tool-admin@10.0.0.1'
        ' ; new-tab -p "Git Bash" -- ssh -p 2222 tool-admin@10.0.0.2'
    )


def test_registry_reader_loads_sessions():
    session_data = [
        ("Extern/Bundo", "ftp.example.com", 22, "myuser"),
        ("Privat/Plex", "192.168.1.10", 2222, "plex"),
    ]

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        for sname, shost, sport, suser in session_data:
            if path.endswith(sname):
                m._session = (sname, shost, sport, suser)
                break
        else:
            m._session = None
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        if key._session is None:
            raise FileNotFoundError
        _, shost, sport, suser = key._session
        if name == "HostName":
            return (shost, winreg.REG_SZ)
        if name == "PortNumber":
            return (sport, winreg.REG_DWORD)
        if name == "UserName":
            return (suser, winreg.REG_SZ)
        raise FileNotFoundError

    with patch("winreg.OpenKey", side_effect=mock_open_key), \
         patch("winreg.EnumKey", side_effect=mock_enum_key), \
         patch("winreg.QueryValueEx", side_effect=mock_query_value):
        reader = RegistryReader()
        sessions = reader.load_sessions()

    assert len(sessions) == 2
    assert sessions[0].hostname == "ftp.example.com"
    assert sessions[0].display_name == "Bundo"
    assert sessions[0].folder_path == ["Extern"]
    assert sessions[1].hostname == "192.168.1.10"
    assert sessions[1].port == 2222


def test_registry_reader_skips_malicious_hostname():
    session_data = [
        ("Safe/Server", "10.0.0.1", 22, "admin"),
        ("Malicious/Attack", "10.0.0.1 & del /f", 22, "admin"),
        ("Malicious/Pipe", "10.0.0.1 | rm -rf /", 22, "admin"),
        ("Malicious/Semicolon", "10.0.0.1; reboot", 22, "admin"),
    ]

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        for sname, shost, sport, suser in session_data:
            if path.endswith(sname):
                m._session = (sname, shost, sport, suser)
                break
        else:
            m._session = None
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        if key._session is None:
            raise FileNotFoundError
        _, shost, sport, suser = key._session
        if name == "HostName":
            return (shost, winreg.REG_SZ)
        if name == "PortNumber":
            return (sport, winreg.REG_DWORD)
        if name == "UserName":
            return (suser, winreg.REG_SZ)
        raise FileNotFoundError

    with patch("winreg.OpenKey", side_effect=mock_open_key), \
         patch("winreg.EnumKey", side_effect=mock_enum_key), \
         patch("winreg.QueryValueEx", side_effect=mock_query_value):
        reader = RegistryReader()
        sessions = reader.load_sessions()

    assert len(sessions) == 1
    assert sessions[0].hostname == "10.0.0.1"


def test_registry_reader_skips_malicious_username():
    session_data = [
        ("Safe/Server", "10.0.0.2", 22, "valid-user"),
        ("Evil/Server", "10.0.0.3", 22, "user$(id)"),
    ]

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        for sname, shost, sport, suser in session_data:
            if path.endswith(sname):
                m._session = (sname, shost, sport, suser)
                break
        else:
            m._session = None
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        if key._session is None:
            raise FileNotFoundError
        _, shost, sport, suser = key._session
        if name == "HostName":
            return (shost, winreg.REG_SZ)
        if name == "PortNumber":
            return (sport, winreg.REG_DWORD)
        if name == "UserName":
            return (suser, winreg.REG_SZ)
        raise FileNotFoundError

    with patch("winreg.OpenKey", side_effect=mock_open_key), \
         patch("winreg.EnumKey", side_effect=mock_enum_key), \
         patch("winreg.QueryValueEx", side_effect=mock_query_value):
        reader = RegistryReader()
        sessions = reader.load_sessions()

    assert len(sessions) == 1
    assert sessions[0].hostname == "10.0.0.2"


def test_load_ui_state_missing_file_returns_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "nonexistent.json"
        with patch("ssh_manager_app.storage._STATE_FILE", fake_path):
            folders, colors, toolbar_texts = load_ui_state()
    assert folders == set()
    assert colors == {}
    assert toolbar_texts == {}


def test_save_and_load_ui_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "ui_state.json"
        with patch("ssh_manager_app.storage._STATE_FILE", fake_path):
            save_ui_state({"Extern", "Extern/Sub"}, {"Extern/srv": "#c0392b"})
            folders, colors, toolbar_texts = load_ui_state()
    assert folders == {"Extern", "Extern/Sub"}
    assert colors == {"Extern/srv": "#c0392b"}
    assert toolbar_texts == {"search_history": []}


def test_load_ui_state_ignores_unknown_keys():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "ui_state.json"
        fake_path.write_text(json.dumps({"expanded_folders": ["A"], "future_key": 42}), encoding="utf-8")
        with patch("ssh_manager_app.storage._STATE_FILE", fake_path):
            folders, colors, toolbar_texts = load_ui_state()
    assert folders == {"A"}
    assert colors == {}
    assert toolbar_texts == {"search_history": []}


def test_color_tag_strips_hash():
    assert color_tag("#2d8653") == "color_2d8653"


def test_color_tag_without_hash():
    assert color_tag("2d8653") == "color_2d8653"


def test_palette_has_eight_entries():
    assert len(PALETTE) == 8


def test_palette_entries_have_name_and_hex():
    for name, hex_color in PALETTE:
        assert isinstance(name, str) and len(name) > 0
        assert hex_color.startswith("#") and len(hex_color) == 7


def test_session_values_text_joins_hostnames():
    sessions = [
        Session("k1", "App", [], "10.0.0.1"),
        Session("k2", "DB", [], "db.internal"),
    ]

    assert _session_values_text(sessions, "hostname") == "10.0.0.1\ndb.internal"


def test_session_values_text_joins_names_and_skips_empty_values():
    sessions = [
        Session("k1", "App", [], "10.0.0.1"),
        Session("k2", "", [], "10.0.0.2"),
        Session("k3", "DB", [], "10.0.0.3"),
    ]

    assert _session_values_text(sessions, "display_name") == "App\nDB"


def _mock_ssh_config(content: str):
    m = MagicMock()
    m.read_text.return_value = content
    return m


def test_load_ssh_config_sessions_basic():
    config = "Host myserver\n  HostName 10.0.0.5\n  User admin\n  Port 2222\n"
    with patch("ssh_manager_app.storage._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = load_ssh_config_sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert s.display_name == "myserver"
    assert s.hostname == "10.0.0.5"
    assert s.username == "admin"
    assert s.port == 2222
    assert s.source == "ssh_config"
    assert s.folder_path == [_SSH_CONFIG_DEFAULT_FOLDER]


def test_load_ssh_config_sessions_skips_wildcards():
    config = "Host *\n  ServerAliveInterval 60\nHost realhost\n  HostName 1.2.3.4\n"
    with patch("ssh_manager_app.storage._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = load_ssh_config_sessions()
    assert len(sessions) == 1
    assert sessions[0].display_name == "realhost"


def test_load_ssh_config_sessions_skips_multi_pattern():
    config = "Host foo bar\n  HostName 1.2.3.4\nHost single\n  HostName 5.6.7.8\n"
    with patch("ssh_manager_app.storage._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = load_ssh_config_sessions()
    assert len(sessions) == 1
    assert sessions[0].display_name == "single"


def test_load_ssh_config_sessions_missing_file():
    m = MagicMock()
    m.read_text.side_effect = OSError("not found")
    with patch("ssh_manager_app.storage._SSH_CONFIG_FILE", m):
        sessions = load_ssh_config_sessions()
    assert sessions == []


def test_load_ssh_config_sessions_hostname_fallback():
    config = "Host myalias\n"
    with patch("ssh_manager_app.storage._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = load_ssh_config_sessions()
    assert len(sessions) == 1
    assert sessions[0].hostname == "myalias"


def test_build_wt_command_ssh_config_session():
    s = Session("__sshcfg__devbox", "devbox", [_SSH_CONFIG_DEFAULT_FOLDER], "devbox", source="ssh_config")
    cmd = build_wt_command([s], "ignored-user")
    assert cmd == 'wt.exe new-tab -p "Git Bash" -- ssh devbox'


def test_build_wt_command_ssh_alias_session():
    s = Session("__sshalias__abc", "prodbox", ["Prod"], "prodbox", source="ssh_alias")
    cmd = build_wt_command([s], "ignored-user")
    assert cmd == 'wt.exe new-tab -p "Git Bash" -- ssh prodbox'


def test_load_settings_from_path_reads_column_order_and_visibility():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(json.dumps({
            "toolbar": {
                "show_hostname_column": True,
                "show_port_column": False,
                "show_notes_column": True,
                "column_order": ["hostname", "notes", "port"],
            }
        }), encoding="utf-8")
        settings = load_settings_from_path(path)
    assert settings.toolbar.show_hostname_column is True
    assert settings.toolbar.show_port_column is False
    assert settings.toolbar.show_notes_column is True
    assert settings.toolbar.column_order == ["hostname", "notes", "port"]


def test_load_settings_from_path_filters_invalid_column_order_entries():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(json.dumps({
            "toolbar": {
                "column_order": ["foo", "notes", "hostname", "bar"]
            }
        }), encoding="utf-8")
        settings = load_settings_from_path(path)
    assert settings.toolbar.column_order == ["notes", "hostname"]


def test_save_and_load_notes_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "notes.json"
        with patch("ssh_manager_app.storage._NOTES_FILE", fake_path):
            save_notes({"session-1": "Wichtige Notiz", "session-2": "  bleibt  "})
            notes = load_notes()
    assert notes == {"session-1": "Wichtige Notiz", "session-2": "  bleibt  "}


def test_load_notes_ignores_blank_entries():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "notes.json"
        fake_path.write_text(json.dumps({"notes": {"a": "", "b": "   ", "c": "ok"}}), encoding="utf-8")
        with patch("ssh_manager_app.storage._NOTES_FILE", fake_path):
            notes = load_notes()
    assert notes == {"c": "ok"}


def test_load_filezilla_config_sessions_reads_nested_sites():
    xml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<FileZilla3>
  <Servers>
    <Folder Name=\"Kunden\">
      <Server>
        <Name>app-01</Name>
        <Host>10.10.10.10</Host>
        <Port>2222</Port>
        <User>deploy</User>
        <Protocol>1</Protocol>
      </Server>
    </Folder>
    <Server>
      <Name>rootbox</Name>
      <Host>192.168.0.20</Host>
      <Protocol>0</Protocol>
    </Server>
  </Servers>
</FileZilla3>
"""
    with tempfile.TemporaryDirectory() as tmp:
        appdata = Path(tmp)
        fz_dir = appdata / "FileZilla"
        fz_dir.mkdir(parents=True)
        (fz_dir / "sitemanager.xml").write_text(xml, encoding="utf-8")
        with patch.dict("os.environ", {"APPDATA": str(appdata)}):
            sessions = load_filezilla_config_sessions()
    assert len(sessions) == 2
    nested = next(s for s in sessions if s.display_name == "app-01")
    assert nested.hostname == "10.10.10.10"
    assert nested.username == "deploy"
    assert nested.port == 2222
    assert nested.folder_path == ["FileZilla Config", "Kunden"]
    assert nested.source == "filezilla_config"
    root = next(s for s in sessions if s.display_name == "rootbox")
    assert root.port == 22


def test_load_filezilla_config_sessions_skips_non_ssh_protocols():
    xml = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<FileZilla3>
  <Servers>
    <Server>
      <Name>ftp-only</Name>
      <Host>ftp.example.org</Host>
      <Protocol>3</Protocol>
    </Server>
  </Servers>
</FileZilla3>
"""
    with tempfile.TemporaryDirectory() as tmp:
        appdata = Path(tmp)
        fz_dir = appdata / "FileZilla"
        fz_dir.mkdir(parents=True)
        (fz_dir / "sitemanager.xml").write_text(xml, encoding="utf-8")
        with patch.dict("os.environ", {"APPDATA": str(appdata)}):
            sessions = load_filezilla_config_sessions()
    assert sessions == []


def test_get_all_folder_names_returns_sorted_unique_folder_keys():
    app = MagicMock()
    app._sessions = [
        Session("1", "prod-a", ["Prod"], "10.0.0.1"),
        Session("2", "prod-b", ["Prod"], "10.0.0.2"),
        Session("3", "misc", [], "10.0.0.3"),
        Session("4", "dev-a", ["Dev", "API"], "10.0.0.4"),
    ]

    assert get_all_folder_names(app) == ["Dev/API", "Prod"]



def test_get_ssh_aliases_returns_sorted_ssh_config_display_names_only():
    app = MagicMock()
    app._sessions = [
        Session("1", "winscp-box", ["Prod"], "10.0.0.1", source="winscp"),
        Session("2", "db-main", [_SSH_CONFIG_DEFAULT_FOLDER], "db-main", source="ssh_config"),
        Session("3", "app-edge", [_SSH_CONFIG_DEFAULT_FOLDER], "app-edge", source="ssh_config"),
    ]

    assert get_ssh_aliases(app) == ["app-edge", "db-main"]



def test_build_visible_sessions_respects_visibility_and_sorts_ssh_config_folder_first():
    app = MagicMock()
    app.settings = AppSettings(
        source_visibility=SourceVisibilitySettings(
            show_winscp=True,
            show_ssh_config=True,
            show_filezilla_config=False,
            show_app_connections=True,
        )
    )
    app._ssh_config_default_folder = _SSH_CONFIG_DEFAULT_FOLDER
    app._winscp_sessions = [Session("w1", "Zulu", ["Prod"], "10.0.0.10", source="winscp")]
    app._app_sessions = [Session("a1", "Beta", ["App"], "10.0.0.20", source="app")]
    app._ssh_config_sessions = [
        Session("s1", "alpha", [_SSH_CONFIG_DEFAULT_FOLDER], "alpha", source="ssh_config"),
        Session("s2", "gamma", [_SSH_CONFIG_DEFAULT_FOLDER], "gamma", source="ssh_config"),
    ]
    app._filezilla_sessions = [Session("f1", "Hidden", ["FileZilla"], "10.0.0.30", source="filezilla_config")]

    visible = build_visible_sessions(app)

    assert [session.display_name for session in visible] == ["alpha", "gamma", "Beta", "Zulu"]



def test_add_search_history_entry_deduplicates_limits_and_persists():
    app = MagicMock()
    app._search_history = [f"item-{i}" for i in range(10)]

    with patch("ssh_manager_app.actions_ui.persist_ui_state") as persist_mock:
        add_search_history_entry(app, "item-5")
        add_search_history_entry(app, "  fresh-query  ")
        add_search_history_entry(app, "x")

    assert app._search_history == [
        "fresh-query",
        "item-5",
        "item-0",
        "item-1",
        "item-2",
        "item-3",
        "item-4",
        "item-6",
        "item-7",
        "item-8",
    ]
    assert persist_mock.call_count == 2



def test_preview_toolbar_visibility_updates_toolbar_and_tree():
    app = MagicMock()
    app.settings = AppSettings()
    toolbar = app.settings.toolbar
    app._tree = MagicMock()

    preview_toolbar_visibility(app, toolbar)

    assert app.settings.toolbar is toolbar
    app._tree.update_toolbar_settings.assert_called_once_with(toolbar)


def test_preview_source_visibility_rebuilds_sessions_and_persists_state():
    app = MagicMock()
    app.settings = AppSettings()
    source_visibility = app.settings.source_visibility
    app._winscp_sessions = [Session("w1", "winscp", [], "10.0.0.1", source="winscp")]
    app._app_sessions = [Session("a1", "app", [], "10.0.0.2", source="app")]
    app._ssh_config_sessions = [Session("s1", "ssh", [], "10.0.0.3", source="ssh_config")]
    app._filezilla_sessions = [Session("f1", "fz", [], "10.0.0.4", source="filezilla_config")]
    app._tree = MagicMock()
    new_sessions = [Session("x", "visible", [], "10.0.0.5")]

    with patch("ssh_manager_app.actions_ui.build_visible_sessions", return_value=new_sessions) as build_visible, \
         patch("ssh_manager_app.actions_ui.persist_ui_state") as persist_mock:
        preview_source_visibility(app, source_visibility)

    build_visible.assert_called_once_with(app)
    assert app._sessions == new_sessions
    app._tree.refresh.assert_called_once_with(new_sessions)
    persist_mock.assert_called_once_with(app)


def test_reset_settings_restores_defaults_and_reload_settings_view():
    app = MagicMock()
    default_settings = AppSettings()
    app._default_settings_factory.return_value = default_settings
    app._settings_view = MagicMock()

    with patch("ssh_manager_app.actions_ui.apply_settings") as apply_settings:
        reset_settings(app)

    apply_settings.assert_called_once_with(app, default_settings)
    app._settings_view.load_from_app.assert_called_once_with()


def test_reset_session_colors_clears_each_color_and_shows_toast():
    app = MagicMock()
    app._tree.get_session_colors.return_value = {"s1": "#111111", "s2": "#222222"}

    with patch("ssh_manager_app.actions_ui.ToastNotification") as toast:
        reset_session_colors(app)

    app._tree.set_session_color.assert_any_call("s1", None)
    app._tree.set_session_color.assert_any_call("s2", None)
    assert app._tree.set_session_color.call_count == 2
    toast.assert_called_once_with(app, "Farben zurückgesetzt")


def test_reset_view_state_restores_initial_tree_state_and_colors():
    app = MagicMock()
    app._search_var = MagicMock()
    app._sessions = [Session("s1", "srv1", [], "10.0.0.1")]
    app._initial_open_folders = {"Prod"}
    app._initial_session_colors = {"s1": "#123456", "s2": "#654321"}
    app._tree.get_session_colors.return_value = {"s1": "#abcdef", "s3": "#000000"}

    with patch("ssh_manager_app.actions_ui.ToastNotification") as toast:
        reset_view_state(app)

    app._search_var.set.assert_called_once_with("")
    app._tree.populate.assert_called_once_with(app._sessions, open_folders={"Prod"})
    app._tree.set_session_color.assert_any_call("s1", "#123456")
    app._tree.set_session_color.assert_any_call("s2", "#654321")
    app._tree.set_session_color.assert_any_call("s3", None)
    assert app._tree.set_session_color.call_count == 3
    toast.assert_called_once_with(app, "Ansicht auf Startzustand zurückgesetzt")


def test_show_settings_view_switches_from_main_to_settings():
    app = MagicMock()
    app._settings_view = MagicMock()
    app._main_frame = MagicMock()

    show_settings_view(app)

    app._settings_view.load_from_app.assert_called_once_with()
    app._main_frame.grid_remove.assert_called_once_with()
    app._settings_view.grid.assert_called_once_with(row=0, column=0, sticky="nsew")


def test_show_main_view_restores_main_frame_and_layout():
    app = MagicMock()
    app._settings_view = MagicMock()
    app._main_frame = MagicMock()

    with patch("ssh_manager_app.actions_ui.layout_toolbar_buttons") as layout:
        show_main_view(app)

    app._settings_view.grid_remove.assert_called_once_with()
    app._main_frame.grid.assert_called_once_with()
    layout.assert_called_once_with(app)


def test_apply_settings_persists_and_focuses_search():
    app = MagicMock()
    settings = AppSettings()

    with patch("ssh_manager_app.actions_ui.save_settings") as save_settings, \
         patch("ssh_manager_app.actions_ui.layout_toolbar_buttons") as layout, \
         patch("ssh_manager_app.actions_ui.ToastNotification") as toast:
        apply_settings(app, settings)

    assert app.settings is settings
    save_settings.assert_called_once_with(settings)
    layout.assert_called_once_with(app)
    app._search_entry.focus_set.assert_called_once_with()
    toast.assert_called_once_with(app, "Einstellungen gespeichert")


def test_on_selection_changed_updates_connect_button_state():
    app = MagicMock()

    on_selection_changed(app, 3)
    on_selection_changed(app, 0)

    assert app._connect_btn.config.call_args_list[0].kwargs == {"text": "Verbinden (3 ausgewählt)", "state": tk.NORMAL}
    assert app._connect_btn.config.call_args_list[1].kwargs == {"text": "Verbinden", "state": tk.DISABLED}


def test_on_search_changed_filters_persists_and_schedules_history_entry():
    app = MagicMock()
    app._search_var.get.return_value = "  prod  "
    app._search_history_after_id = "after-1"
    app.after.return_value = "after-2"

    with patch("ssh_manager_app.actions_ui.persist_ui_state") as persist_mock:
        on_search_changed(app)

    app._tree.filter.assert_called_once_with("  prod  ")
    persist_mock.assert_called_once_with(app)
    app.after_cancel.assert_called_once_with("after-1")
    app.after.assert_called_once()
    assert app._search_history_after_id == "after-2"


def test_on_search_changed_clears_pending_history_for_short_queries():
    app = MagicMock()
    app._search_var.get.return_value = "x"
    app._search_history_after_id = None

    with patch("ssh_manager_app.actions_ui.persist_ui_state") as persist_mock:
        on_search_changed(app)

    app._tree.filter.assert_called_once_with("x")
    persist_mock.assert_called_once_with(app)
    app.after.assert_not_called()
    assert app._search_history_after_id is None


def test_selection_helpers_delegate_to_tree():
    app = MagicMock()

    select_all(app)
    deselect_all(app)
    expand_all(app)
    collapse_all(app)

    app._tree.set_all_checked.assert_any_call(True)
    app._tree.set_all_checked.assert_any_call(False)
    app._tree.expand_all.assert_called_once_with()
    app._tree.collapse_all.assert_called_once_with()


def test_reload_sessions_rebuilds_and_shows_toast():
    app = MagicMock()

    with patch("ssh_manager_app.actions_ui.rebuild_sessions") as rebuild, \
         patch("ssh_manager_app.actions_ui.ToastNotification") as toast:
        reload_sessions(app)

    rebuild.assert_called_once_with(app, reload_winscp=True)
    toast.assert_called_once_with(app, "Verbindungen neu geladen")


def test_add_session_appends_result_saves_and_rebuilds():
    app = MagicMock()
    app._app_sessions = []
    app._notes = {}
    new_session = Session("s1", "srv1", ["Prod"], "10.0.0.1", source="app")
    dialog = MagicMock()
    dialog.result = new_session
    dialog.note_result = "wichtig"

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=["Prod"]) as get_folders, \
         patch("ssh_manager_app.actions_sessions.get_ssh_aliases", return_value=["alias1"]) as get_aliases, \
         patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_sessions.save_notes") as save_notes, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        add_session(app, folder_preset="Prod")

    get_folders.assert_called_once_with(app)
    get_aliases.assert_called_once_with(app)
    dialog_cls.assert_called_once_with(app, ["Prod"], ssh_aliases=["alias1"], folder_preset="Prod")
    app.wait_window.assert_called_once_with(dialog)
    assert app._app_sessions == [new_session]
    assert app._notes == {"s1": "wichtig"}
    save_notes.assert_called_once_with(app._notes)
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_edit_session_replaces_existing_session_and_updates_note():
    app = MagicMock()
    original = Session("s1", "srv1", ["Prod"], "10.0.0.1", source="app")
    updated = Session("s1", "srv1-new", ["Ops"], "10.0.0.9", source="app")
    app._app_sessions = [original]
    app._notes = {"s1": "alt"}
    dialog = MagicMock()
    dialog.result = updated
    dialog.note_result = "neu"

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=["Prod", "Ops"]), \
         patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_sessions.save_notes") as save_notes, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        edit_session(app, original)

    dialog_cls.assert_called_once_with(app, ["Prod", "Ops"], session=original, note="alt")
    assert app._app_sessions == [updated]
    assert app._notes == {"s1": "neu"}
    save_notes.assert_called_once_with(app._notes)
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_delete_session_removes_confirmed_session_and_rebuilds():
    app = MagicMock()
    keep = Session("s2", "srv2", [], "10.0.0.2", source="app")
    victim = Session("s1", "srv1", [], "10.0.0.1", source="app")
    app._app_sessions = [victim, keep]

    with patch("ssh_manager_app.actions_sessions.messagebox.askyesno", return_value=True) as askyesno, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        delete_session(app, victim)

    askyesno.assert_called_once_with("Verbindung löschen", "Verbindung 'srv1' wirklich löschen?", parent=app)
    assert app._app_sessions == [keep]
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_duplicate_app_session_appends_copy_and_rebuilds():
    app = MagicMock()
    original = Session("s1", "srv1", ["Prod"], "10.0.0.1", source="app")
    duplicate = Session("s2", "srv1 copy", ["Prod"], "10.0.0.1", source="app")
    app._app_sessions = [original]
    dialog = MagicMock()
    dialog.result = duplicate

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=["Prod"]), \
         patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        duplicate_app_session(app, original)

    dialog_cls.assert_called_once_with(app, ["Prod"], session=original, duplicate=True)
    assert app._app_sessions == [original, duplicate]
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_move_session_updates_folder_and_rebuilds():
    app = MagicMock()
    session = Session("s1", "srv1", ["Old"], "10.0.0.1", source="app")
    other = Session("s2", "srv2", ["Keep"], "10.0.0.2", source="app")
    app._app_sessions = [session, other]
    dialog = MagicMock()
    dialog.result = "New/Sub"

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=["Old", "New/Sub"]), \
         patch("ssh_manager_app.actions_sessions.MoveFolderDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        move_session(app, session)

    dialog_cls.assert_called_once_with(app, ["Old", "New/Sub"], "Old")
    assert app._app_sessions[0].folder_path == ["New", "Sub"]
    assert app._app_sessions[1] is other
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_move_sessions_updates_all_selected_sessions():
    app = MagicMock()
    first = Session("s1", "srv1", ["Old"], "10.0.0.1", source="app")
    second = Session("s2", "srv2", ["Old"], "10.0.0.2", source="app")
    untouched = Session("s3", "srv3", ["Keep"], "10.0.0.3", source="app")
    app._app_sessions = [first, second, untouched]
    dialog = MagicMock()
    dialog.result = "Shared/Folder"

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=["Old", "Shared/Folder"]), \
         patch("ssh_manager_app.actions_sessions.MoveFolderDialog", return_value=dialog), \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        move_sessions(app, [first, second])

    assert app._app_sessions[0].folder_path == ["Shared", "Folder"]
    assert app._app_sessions[1].folder_path == ["Shared", "Folder"]
    assert app._app_sessions[2] is untouched
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_delete_folder_removes_matching_sessions_and_rebuilds():
    app = MagicMock()
    first = Session("s1", "srv1", ["Old"], "10.0.0.1", source="app")
    second = Session("s2", "srv2", ["Old"], "10.0.0.2", source="app")
    keep = Session("s3", "srv3", ["Keep"], "10.0.0.3", source="app")
    app._app_sessions = [first, second, keep]

    with patch("ssh_manager_app.actions_sessions.messagebox.askyesno", return_value=True) as askyesno, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        delete_folder(app, [first, second], "Old")

    askyesno.assert_called_once_with("Ordner löschen", "Ordner 'Old' und alle 2 Verbindung(en) darin löschen?", parent=app)
    assert app._app_sessions == [keep]
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_rename_folder_updates_matching_path_segment_and_rebuilds():
    app = MagicMock()
    first = Session("s1", "srv1", ["Root", "Old", "Leaf"], "10.0.0.1", source="app")
    second = Session("s2", "srv2", ["Root", "Old"], "10.0.0.2", source="app")
    keep = Session("s3", "srv3", ["Other", "Old"], "10.0.0.3", source="app")
    app._app_sessions = [first, second, keep]

    with patch("ssh_manager_app.actions_sessions.simpledialog.askstring", return_value=" New ") as askstring, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        rename_folder(app, "Root/Old")

    askstring.assert_called_once_with("Ordner umbenennen", "Neuer Name für 'Old':", initialvalue="Old", parent=app)
    assert app._app_sessions[0].folder_path == ["Root", "New", "Leaf"]
    assert app._app_sessions[1].folder_path == ["Root", "New"]
    assert app._app_sessions[2].folder_path == ["Other", "Old"]
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_duplicate_ssh_alias_creates_app_session_and_rebuilds():
    app = MagicMock()
    app._app_sessions = []
    source = Session("ssh1", "prod-alias", ["SSH config"], "prod-alias", source="ssh_config")
    duplicate = Session("app1", "prod-alias-copy", ["App"], "prod-alias", source="app")
    dialog = MagicMock()
    dialog.result = duplicate

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=["App"]), \
         patch("ssh_manager_app.actions_sessions.get_ssh_aliases", return_value=["prod-alias"]) as get_aliases, \
         patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        duplicate_ssh_alias(app, source)

    get_aliases.assert_called_once_with(app)
    dialog_cls.assert_called_once_with(app, ["App"], ssh_aliases=["prod-alias"], alias_preset="prod-alias")
    assert app._app_sessions == [duplicate]
    save_sessions.assert_called_once_with(app._app_sessions)
    rebuild.assert_called_once_with(app)


def test_open_appdata_jsons_in_vscode_uses_popen_shell():
    app = MagicMock()
    appdata_dir = MagicMock()
    appdata_dir.__str__.return_value = "/tmp/appdata"

    with patch("ssh_manager_app.actions_sessions._APPDATA_DIR", appdata_dir):
        open_appdata_jsons_in_vscode(app)

    appdata_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
    app._popen_shell.assert_called_once_with('code "/tmp/appdata"')


def test_add_session_returns_early_on_cancel():
    app = MagicMock()
    app._app_sessions = []
    app._notes = {}
    dialog = MagicMock()
    dialog.result = None
    dialog.note_result = None

    with patch("ssh_manager_app.actions_sessions.get_all_folder_names", return_value=[]), \
         patch("ssh_manager_app.actions_sessions.get_ssh_aliases", return_value=[]), \
         patch("ssh_manager_app.actions_sessions.SessionEditDialog", return_value=dialog), \
         patch("ssh_manager_app.actions_sessions.save_notes") as save_notes, \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        add_session(app)

    assert app._app_sessions == []
    assert app._notes == {}
    save_notes.assert_not_called()
    save_sessions.assert_not_called()
    rebuild.assert_not_called()


def test_delete_session_returns_early_when_not_confirmed():
    app = MagicMock()
    session = Session("s1", "srv1", [], "10.0.0.1", source="app")
    app._app_sessions = [session]

    with patch("ssh_manager_app.actions_sessions.messagebox.askyesno", return_value=False), \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        delete_session(app, session)

    assert app._app_sessions == [session]
    save_sessions.assert_not_called()
    rebuild.assert_not_called()


def test_rename_folder_returns_early_when_name_unchanged():
    app = MagicMock()
    session = Session("s1", "srv1", ["Root", "Old"], "10.0.0.1", source="app")
    app._app_sessions = [session]

    with patch("ssh_manager_app.actions_sessions.simpledialog.askstring", return_value="Old"), \
         patch("ssh_manager_app.actions_sessions.save_app_sessions") as save_sessions, \
         patch("ssh_manager_app.actions_sessions.rebuild_sessions") as rebuild:
        rename_folder(app, "Root/Old")

    assert app._app_sessions[0].folder_path == ["Root", "Old"]
    save_sessions.assert_not_called()
    rebuild.assert_not_called()


def test_open_appdata_jsons_in_vscode_shows_error_on_oserror():
    app = MagicMock()
    appdata_dir = MagicMock()
    appdata_dir.__str__.return_value = "/tmp/appdata"
    app._popen_shell.side_effect = OSError("boom")

    with patch("ssh_manager_app.actions_sessions._APPDATA_DIR", appdata_dir), \
         patch("ssh_manager_app.actions_sessions.messagebox.showerror") as showerror:
        open_appdata_jsons_in_vscode(app)

    showerror.assert_called_once_with("VS Code nicht gefunden", "Fehler beim Öffnen:\nboom")


def test_edit_session_note_saves_note_and_refreshes_ui():
    app = MagicMock()
    app._notes = {}
    app._sessions = [Session("s1", "srv1", [], "10.0.0.1")]
    app._tree = MagicMock()
    app.winfo_width.return_value = 800
    app.winfo_height.return_value = 600
    app.winfo_x.return_value = 10
    app.winfo_y.return_value = 20
    session = app._sessions[0]

    dialog = MagicMock()
    dialog.winfo_reqwidth.return_value = 200
    dialog.winfo_reqheight.return_value = 100

    text_widget = MagicMock()
    text_widget.get.return_value = " neue notiz "

    button_commands = {}

    def fake_button(*_args, **kwargs):
        if "text" in kwargs and "command" in kwargs:
            button_commands[kwargs["text"]] = kwargs["command"]
        btn = MagicMock()
        btn.pack.return_value = None
        return btn

    def fake_wait_window(_dialog):
        button_commands["OK"]()

    app.wait_window.side_effect = fake_wait_window

    with patch("ssh_manager_app.actions_notes.tk.Toplevel", return_value=dialog), \
         patch("ssh_manager_app.actions_notes.ttk.Frame", return_value=MagicMock()), \
         patch("ssh_manager_app.actions_notes.ttk.Label", return_value=MagicMock()), \
         patch("ssh_manager_app.actions_notes.ttk.Button", side_effect=fake_button), \
         patch("ssh_manager_app.actions_notes.tk.Text", return_value=text_widget), \
         patch("ssh_manager_app.actions_notes.save_notes") as save_notes, \
         patch("ssh_manager_app.actions_notes.persist_ui_state") as persist_ui_state, \
         patch("ssh_manager_app.actions_notes.ToastNotification") as toast:
        edit_session_note(app, session)

    assert app._notes == {"s1": "neue notiz"}
    save_notes.assert_called_once_with(app._notes)
    app._tree.refresh.assert_called_once_with(app._sessions)
    persist_ui_state.assert_called_once_with(app)
    toast.assert_called_once_with(app, "Notiz gespeichert")


def test_edit_session_note_cancel_keeps_existing_notes():
    app = MagicMock()
    app._notes = {"s1": "alt"}
    app._sessions = [Session("s1", "srv1", [], "10.0.0.1")]
    app._tree = MagicMock()
    app.winfo_width.return_value = 800
    app.winfo_height.return_value = 600
    app.winfo_x.return_value = 10
    app.winfo_y.return_value = 20
    session = app._sessions[0]

    dialog = MagicMock()
    dialog.winfo_reqwidth.return_value = 200
    dialog.winfo_reqheight.return_value = 100

    text_widget = MagicMock()
    text_widget.get.return_value = "wird nicht gespeichert"

    button_commands = {}

    def fake_button(*_args, **kwargs):
        if "text" in kwargs and "command" in kwargs:
            button_commands[kwargs["text"]] = kwargs["command"]
        btn = MagicMock()
        btn.pack.return_value = None
        return btn

    def fake_wait_window(_dialog):
        button_commands["Abbrechen"]()

    app.wait_window.side_effect = fake_wait_window

    with patch("ssh_manager_app.actions_notes.tk.Toplevel", return_value=dialog), \
         patch("ssh_manager_app.actions_notes.ttk.Frame", return_value=MagicMock()), \
         patch("ssh_manager_app.actions_notes.ttk.Label", return_value=MagicMock()), \
         patch("ssh_manager_app.actions_notes.ttk.Button", side_effect=fake_button), \
         patch("ssh_manager_app.actions_notes.tk.Text", return_value=text_widget), \
         patch("ssh_manager_app.actions_notes.save_notes") as save_notes, \
         patch("ssh_manager_app.actions_notes.persist_ui_state") as persist_ui_state, \
         patch("ssh_manager_app.actions_notes.ToastNotification") as toast:
        edit_session_note(app, session)

    assert app._notes == {"s1": "alt"}
    save_notes.assert_not_called()
    app._tree.refresh.assert_not_called()
    persist_ui_state.assert_not_called()
    toast.assert_not_called()


def test_inspect_ssh_config_opens_dialog_for_session_alias():
    app = MagicMock()
    session = Session("s1", "prod-alias", [], "prod-alias", source="ssh_config")

    with patch("ssh_manager_app.actions_open.SshConfigInspectDialog") as dialog_cls:
        inspect_ssh_config(app, session)

    dialog_cls.assert_called_once_with(app, "prod-alias")


def test_open_ssh_config_in_vscode_launches_code_with_shell():
    app = MagicMock()

    with patch("ssh_manager_app.actions_open.subprocess.Popen") as popen:
        open_ssh_config_in_vscode(app)

    popen.assert_called_once()
    args, kwargs = popen.call_args
    assert args[0].startswith('code "')
    assert kwargs == {"shell": True}


def test_open_in_winscp_opens_all_selected_sessions():
    app = MagicMock()
    sessions = [
        Session("s1", "srv1", ["Prod"], "10.0.0.1"),
        Session("s2", "srv2", ["Prod", "Db"], "10.0.0.2"),
    ]

    with patch("ssh_manager_app.actions_open._find_winscp", return_value="C:/Program Files/WinSCP/WinSCP.exe"), \
         patch("ssh_manager_app.actions_open.subprocess.Popen") as popen:
        open_in_winscp(app, sessions)

    assert popen.call_count == 2
    assert popen.call_args_list[0].args[0] == ["C:/Program Files/WinSCP/WinSCP.exe", "Prod/srv1"]
    assert popen.call_args_list[1].args[0] == ["C:/Program Files/WinSCP/WinSCP.exe", "Prod/Db/srv2"]


def test_open_ssh_config_in_vscode_shows_error_on_oserror():
    app = MagicMock()

    with patch("ssh_manager_app.actions_open.subprocess.Popen", side_effect=OSError("boom")), \
         patch("ssh_manager_app.actions_open.messagebox.showerror") as showerror:
        open_ssh_config_in_vscode(app)

    showerror.assert_called_once_with("VS Code nicht gefunden", "Fehler beim Öffnen:\nboom", parent=app)


def test_open_in_winscp_shows_error_when_winscp_missing():
    app = MagicMock()
    sessions = [Session("s1", "srv1", [], "10.0.0.1")]

    with patch("ssh_manager_app.actions_open._find_winscp", return_value=""), \
         patch("ssh_manager_app.actions_open.messagebox.showerror") as showerror:
        open_in_winscp(app, sessions)

    showerror.assert_called_once_with(
        "WinSCP nicht gefunden",
        "WinSCP.exe wurde nicht gefunden.\nBitte WinSCP installieren oder zum PATH hinzufügen.",
        parent=app,
    )


def test_open_in_winscp_shows_error_on_launch_failure():
    app = MagicMock()
    sessions = [Session("s1", "srv1", ["Prod"], "10.0.0.1")]

    with patch("ssh_manager_app.actions_open._find_winscp", return_value="C:/Program Files/WinSCP/WinSCP.exe"), \
         patch("ssh_manager_app.actions_open.subprocess.Popen", side_effect=OSError("broken")), \
         patch("ssh_manager_app.actions_open.messagebox.showerror") as showerror:
        open_in_winscp(app, sessions)

    showerror.assert_called_once_with("Fehler", "Fehler beim Starten von WinSCP:\nbroken", parent=app)


def test_ssh_manager_app_stays_thin_bootstrap_shell():
    from ssh_manager import SSHManagerApp

    method_names = [
        name
        for name, value in SSHManagerApp.__dict__.items()
        if callable(value) and getattr(value, "__module__", None) == "ssh_manager"
    ]

    assert method_names == ["__init__"]


def test_dialog_exports_use_split_modules():
    from ssh_manager_app.dialogs import (
        JumpHostDialog,
        MoveFolderDialog,
        RemoteCommandConfirmDialog,
        RemoteCommandDialog,
        SessionEditDialog,
        SettingsView,
        SshConfigInspectDialog,
        SshCopyIdDialog,
        SshRemoveKeyDialog,
        SshTunnelDialog,
        ToastNotification,
        UserDialog,
    )
    from ssh_manager_app.dialogs_move_folder import MoveFolderDialog as MoveFolderDialogImpl
    from ssh_manager_app.dialogs_remote import (
        JumpHostDialog as JumpHostDialogImpl,
        RemoteCommandConfirmDialog as RemoteCommandConfirmDialogImpl,
        RemoteCommandDialog as RemoteCommandDialogImpl,
        SshCopyIdDialog as SshCopyIdDialogImpl,
        SshRemoveKeyDialog as SshRemoveKeyDialogImpl,
        SshTunnelDialog as SshTunnelDialogImpl,
    )
    from ssh_manager_app.dialogs_session_edit import SessionEditDialog as SessionEditDialogImpl
    from ssh_manager_app.dialogs_settings_misc import SettingsView as SettingsViewImpl
    from ssh_manager_app.dialogs_settings_misc import SshConfigInspectDialog as SshConfigInspectDialogImpl
    from ssh_manager_app.dialogs_toast import ToastNotification as ToastNotificationImpl
    from ssh_manager_app.dialogs_base import UserDialog as UserDialogImpl

    assert JumpHostDialog is JumpHostDialogImpl
    assert MoveFolderDialog is MoveFolderDialogImpl
    assert RemoteCommandConfirmDialog is RemoteCommandConfirmDialogImpl
    assert RemoteCommandDialog is RemoteCommandDialogImpl
    assert SessionEditDialog is SessionEditDialogImpl
    assert SettingsView is SettingsViewImpl
    assert SshConfigInspectDialog is SshConfigInspectDialogImpl
    assert SshCopyIdDialog is SshCopyIdDialogImpl
    assert SshRemoveKeyDialog is SshRemoveKeyDialogImpl
    assert SshTunnelDialog is SshTunnelDialogImpl
    assert ToastNotification is ToastNotificationImpl
    assert UserDialog is UserDialogImpl

def test_main_modules_import_cleanly():
    import importlib

    ui_module = importlib.import_module("ssh_manager_app.ui")
    main_module = importlib.import_module("ssh_manager")

    assert hasattr(ui_module, "build_main_ui")
    assert hasattr(main_module, "SSHManagerApp")


def test_layout_toolbar_buttons_places_only_enabled_buttons_in_order():
    app = MagicMock()
    app.settings = AppSettings()
    app.settings.toolbar.show_select_all = True
    app.settings.toolbar.show_deselect_all = False
    app.settings.toolbar.show_expand_all = True
    app.settings.toolbar.show_collapse_all = False
    app.settings.toolbar.show_add_connection = True
    app.settings.toolbar.show_reload = True
    app.settings.toolbar.show_open_tunnel = False
    app.settings.toolbar.show_check_hosts = True

    app._toolbar_buttons = {key: MagicMock() for key in TOOLBAR_BUTTON_ORDER}

    layout_toolbar_buttons(app)

    for button in app._toolbar_buttons.values():
        button.grid_forget.assert_called_once()

    assert app._toolbar_buttons["show_select_all"].grid.call_args.kwargs == {"row": 0, "column": 2, "padx": (2, 2)}
    app._toolbar_buttons["show_deselect_all"].grid.assert_not_called()
    assert app._toolbar_buttons["show_expand_all"].grid.call_args.kwargs == {"row": 0, "column": 3, "padx": (2, 2)}
    app._toolbar_buttons["show_collapse_all"].grid.assert_not_called()
    assert app._toolbar_buttons["show_add_connection"].grid.call_args.kwargs == {"row": 0, "column": 4, "padx": (8, 2)}
    assert app._toolbar_buttons["show_reload"].grid.call_args.kwargs == {"row": 0, "column": 5, "padx": (2, 2)}
    app._toolbar_buttons["show_open_tunnel"].grid.assert_not_called()
    assert app._toolbar_buttons["show_check_hosts"].grid.call_args.kwargs == {"row": 0, "column": 6, "padx": (2, 0)}


def test_export_and_import_settings_dialog_delegate_only_when_view_exists():
    app = MagicMock()
    app._settings_view = None

    export_settings_dialog(app)
    import_settings_dialog(app)

    app = MagicMock()
    app._settings_view = MagicMock()

    export_settings_dialog(app)
    import_settings_dialog(app)

    app._settings_view._export_settings.assert_called_once_with()
    app._settings_view._import_settings.assert_called_once_with()


def test_settings_view_export_settings_writes_json_and_shows_toast():
    view = SettingsView.__new__(SettingsView)
    view._app = MagicMock()
    settings = AppSettings()
    view._collect_settings = MagicMock(return_value=settings)

    path_mock = MagicMock()
    with patch("ssh_manager_app.dialogs_settings_misc.filedialog.asksaveasfilename", return_value="/tmp/settings.json"), \
         patch("ssh_manager_app.dialogs_settings_misc.Path", return_value=path_mock), \
         patch("ssh_manager_app.dialogs_settings_misc.ToastNotification") as toast:
        SettingsView._export_settings(view)

    view._collect_settings.assert_called_once_with()
    path_mock.write_text.assert_called_once()
    written_json = path_mock.write_text.call_args.args[0]
    assert '"default_user": "tool-admin"' in written_json
    assert path_mock.write_text.call_args.kwargs == {"encoding": "utf-8"}
    toast.assert_called_once_with(view._app, "Einstellungen exportiert")



def test_settings_view_export_settings_shows_error_on_write_failure():
    view = SettingsView.__new__(SettingsView)
    view._app = MagicMock()
    view._collect_settings = MagicMock(return_value=AppSettings())
    path_mock = MagicMock()
    path_mock.write_text.side_effect = OSError("disk full")

    with patch("ssh_manager_app.dialogs_settings_misc.filedialog.asksaveasfilename", return_value="/tmp/settings.json"), \
         patch("ssh_manager_app.dialogs_settings_misc.Path", return_value=path_mock), \
         patch("ssh_manager_app.dialogs_settings_misc.messagebox.showerror") as showerror:
        SettingsView._export_settings(view)

    showerror.assert_called_once_with("Export fehlgeschlagen", "Datei konnte nicht gespeichert werden:\ndisk full", parent=view)



def test_settings_view_import_settings_applies_loaded_settings_and_reloads_view():
    view = SettingsView.__new__(SettingsView)
    view._app = MagicMock()
    view.load_from_app = MagicMock()
    settings = AppSettings(default_user="alice")

    with patch("ssh_manager_app.dialogs_settings_misc.filedialog.askopenfilename", return_value="/tmp/settings.json"), \
         patch("ssh_manager_app.dialogs_settings_misc.load_settings_from_path", return_value=settings) as load_settings, \
         patch("ssh_manager_app.actions_ui.apply_settings") as apply_settings, \
         patch("ssh_manager_app.dialogs_settings_misc.ToastNotification") as toast:
        SettingsView._import_settings(view)

    load_settings.assert_called_once()
    apply_settings.assert_called_once_with(view._app, settings)
    view.load_from_app.assert_called_once_with()
    toast.assert_called_once_with(view._app, "Einstellungen importiert")



def test_settings_view_import_settings_shows_error_on_invalid_file():
    view = SettingsView.__new__(SettingsView)
    view._app = MagicMock()
    view.load_from_app = MagicMock()

    with patch("ssh_manager_app.dialogs_settings_misc.filedialog.askopenfilename", return_value="/tmp/settings.json"), \
         patch("ssh_manager_app.dialogs_settings_misc.load_settings_from_path", side_effect=ValueError("kaputt")), \
         patch("ssh_manager_app.dialogs_settings_misc.messagebox.showerror") as showerror:
        SettingsView._import_settings(view)

    showerror.assert_called_once_with("Import fehlgeschlagen", "Datei konnte nicht gelesen werden:\nkaputt", parent=view)
    view.load_from_app.assert_not_called()



def test_settings_view_collect_settings_normalizes_values():
    view = SettingsView.__new__(SettingsView)
    view.STARTUP_LABELS = SettingsView.STARTUP_LABELS
    view.TITLE_MODE_LABELS = SettingsView.TITLE_MODE_LABELS
    view._quick_users_text = MagicMock()
    view._quick_users_text.get.return_value = " alice\n\n bob \n"
    view._default_user_var = MagicMock()
    view._default_user_var.get.return_value = "charlie"
    view._host_timeout_var = MagicMock()
    view._host_timeout_var.get.return_value = "0"
    view._startup_expand_var = MagicMock()
    view._startup_expand_var.get.return_value = SettingsView.STARTUP_LABELS["expanded"]
    view._profile_name_var = MagicMock()
    view._profile_name_var.get.return_value = "  "
    view._use_tab_color_var = MagicMock()
    view._use_tab_color_var.get.return_value = True
    view._title_mode_var = MagicMock()
    view._title_mode_var.get.return_value = SettingsView.TITLE_MODE_LABELS["name_host"]
    view._collect_toolbar_settings = MagicMock(return_value=AppSettings().toolbar)
    view._collect_source_visibility_settings = MagicMock(return_value=AppSettings().source_visibility)

    settings = SettingsView._collect_settings(view)

    assert settings.quick_users == ["alice", "bob"]
    assert settings.default_user == "alice"
    assert settings.host_check_timeout_seconds == 1
    assert settings.startup_expand_mode == "expanded"
    assert settings.windows_terminal.profile_name == "Git Bash"
    assert settings.windows_terminal.use_tab_color is True
    assert settings.windows_terminal.title_mode == "name_host"


def test_settings_view_collect_settings_rejects_missing_quick_users():
    view = SettingsView.__new__(SettingsView)
    view._quick_users_text = MagicMock()
    view._quick_users_text.get.return_value = "\n  \n"

    with pytest.raises(ValueError, match="Mindestens ein Quick-User"):
        SettingsView._collect_settings(view)


def test_settings_view_move_column_order_reorders_and_triggers_preview():
    view = SettingsView.__new__(SettingsView)
    listbox = MagicMock()
    listbox.curselection.return_value = (1,)
    listbox.size.return_value = 3
    listbox.get.return_value = "Hostname"
    view._column_order_list = listbox
    view._on_toolbar_changed = MagicMock()

    SettingsView._move_column_order(view, -1)

    listbox.delete.assert_called_once_with(1)
    listbox.insert.assert_called_once_with(0, "Hostname")
    listbox.selection_set.assert_called_once_with(0)
    view._on_toolbar_changed.assert_called_once_with()


def test_settings_view_show_section_raises_selected_frame_and_updates_nav_labels():
    view = SettingsView.__new__(SettingsView)
    general_frame = MagicMock()
    toolbar_frame = MagicMock()
    view._section_frames = {"general": general_frame, "toolbar": toolbar_frame}
    general_button = MagicMock()
    toolbar_button = MagicMock()
    view._nav_buttons = {"general": general_button, "toolbar": toolbar_button}

    SettingsView._show_section(view, "toolbar")

    assert view._active_section == "toolbar"
    toolbar_frame.tkraise.assert_called_once_with()
    general_frame.tkraise.assert_not_called()
    general_button.configure.assert_called_once_with(text="  Allgemein")
    toolbar_button.configure.assert_called_once_with(text="▸ Toolbar")


def test_ssh_config_inspect_dialog_build_uses_stdout_and_disables_text():
    dialog = SshConfigInspectDialog.__new__(SshConfigInspectDialog)
    dialog.columnconfigure = MagicMock()
    dialog.rowconfigure = MagicMock()

    txt = MagicMock()
    vsb = MagicMock()
    hsb = MagicMock()
    txt_frame = MagicMock()
    btn_frame = MagicMock()
    close_button = MagicMock()

    with patch("ssh_manager_app.dialogs_settings_misc.ttk.Frame", side_effect=[txt_frame, btn_frame]) as frame_cls, \
         patch("ssh_manager_app.dialogs_settings_misc.tk.Text", return_value=txt) as text_cls, \
         patch("ssh_manager_app.dialogs_settings_misc.ttk.Scrollbar", side_effect=[vsb, hsb]) as scrollbar_cls, \
         patch("ssh_manager_app.dialogs_settings_misc.ttk.Button", return_value=close_button) as button_cls, \
         patch("ssh_manager_app.dialogs_settings_misc.subprocess.run", return_value=SimpleNamespace(stdout="host x\n", stderr="")) as run:
        SshConfigInspectDialog._build(dialog, "prod")

    run.assert_called_once_with(["ssh", "-G", "prod"], capture_output=True, text=True, timeout=5)
    text_cls.assert_called_once_with(txt_frame, wrap="none", font=("Consolas", 9))
    txt.insert.assert_called_once_with("1.0", "host x\n")
    txt.configure.assert_any_call(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    txt.configure.assert_any_call(state="disabled")
    button_cls.assert_called_once_with(btn_frame, text="Schließen", command=dialog.destroy, width=12)
    close_button.pack.assert_called_once_with()


def test_ssh_config_inspect_dialog_build_shows_exception_text():
    dialog = SshConfigInspectDialog.__new__(SshConfigInspectDialog)
    dialog.columnconfigure = MagicMock()
    dialog.rowconfigure = MagicMock()
    txt = MagicMock()

    with patch("ssh_manager_app.dialogs_settings_misc.ttk.Frame", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_settings_misc.tk.Text", return_value=txt), \
         patch("ssh_manager_app.dialogs_settings_misc.ttk.Scrollbar", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_settings_misc.ttk.Button", return_value=MagicMock()), \
         patch("ssh_manager_app.dialogs_settings_misc.subprocess.run", side_effect=RuntimeError("boom")):
        SshConfigInspectDialog._build(dialog, "prod")

    txt.insert.assert_called_once_with("1.0", "Fehler: boom")
    txt.configure.assert_any_call(state="disabled")


def test_ssh_config_inspect_dialog_build_falls_back_to_stderr_when_stdout_is_empty():
    dialog = SshConfigInspectDialog.__new__(SshConfigInspectDialog)
    dialog.columnconfigure = MagicMock()
    dialog.rowconfigure = MagicMock()
    txt = MagicMock()

    with patch("ssh_manager_app.dialogs_settings_misc.ttk.Frame", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_settings_misc.tk.Text", return_value=txt), \
         patch("ssh_manager_app.dialogs_settings_misc.ttk.Scrollbar", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_settings_misc.ttk.Button", return_value=MagicMock()), \
         patch("ssh_manager_app.dialogs_settings_misc.subprocess.run", return_value=SimpleNamespace(stdout="", stderr="warning")):
        SshConfigInspectDialog._build(dialog, "prod")

    txt.insert.assert_called_once_with("1.0", "warning")
    txt.configure.assert_any_call(state="disabled")


def test_ssh_config_inspect_dialog_center_on_parent_sets_geometry():
    dialog = SshConfigInspectDialog.__new__(SshConfigInspectDialog)
    dialog.update_idletasks = MagicMock()
    dialog.winfo_reqwidth = MagicMock(return_value=300)
    dialog.winfo_reqheight = MagicMock(return_value=200)
    dialog.geometry = MagicMock()
    parent = SimpleNamespace(
        winfo_width=lambda: 800,
        winfo_height=lambda: 600,
        winfo_x=lambda: 50,
        winfo_y=lambda: 40,
    )

    SshConfigInspectDialog._center_on_parent(dialog, parent)

    dialog.geometry.assert_called_once_with("+300+240")


def test_close_app_persists_state_before_destroy():
    app = MagicMock()

    with patch("ssh_manager_app.actions_app.persist_ui_state") as persist_mock:
        close_app(app)

    persist_mock.assert_called_once_with(app)
    app.destroy.assert_called_once_with()


def test_show_search_history_menu_builds_entries_and_popup_for_history():
    app = MagicMock()
    app._search_history = ["alpha", "beta"]
    app._search_history_btn.winfo_rootx.return_value = 100
    app._search_history_btn.winfo_rooty.return_value = 50
    app._search_history_btn.winfo_height.return_value = 20

    menu = MagicMock()
    with patch("ssh_manager_app.actions_app.tk.Menu", return_value=menu):
        show_search_history_menu(app)

    labels = [call.kwargs.get("label") for call in menu.add_command.call_args_list]
    assert labels == ["alpha", "beta", "Verlauf leeren"]
    menu.add_separator.assert_called_once_with()
    menu.tk_popup.assert_called_once_with(100, 70)


def test_show_search_history_menu_shows_placeholder_when_empty():
    app = MagicMock()
    app._search_history = []
    app._search_history_btn.winfo_rootx.return_value = 5
    app._search_history_btn.winfo_rooty.return_value = 7
    app._search_history_btn.winfo_height.return_value = 11

    menu = MagicMock()
    with patch("ssh_manager_app.actions_app.tk.Menu", return_value=menu):
        show_search_history_menu(app)

    menu.add_command.assert_called_once_with(label="Kein Suchverlauf", state=tk.DISABLED)
    menu.add_separator.assert_not_called()
    menu.tk_popup.assert_called_once_with(5, 18)


def test_show_search_history_menu_item_callback_applies_selected_entry():
    app = MagicMock()
    app._search_history = ["alpha", "beta"]
    app._search_history_btn.winfo_rootx.return_value = 0
    app._search_history_btn.winfo_rooty.return_value = 0
    app._search_history_btn.winfo_height.return_value = 0

    menu = MagicMock()
    with patch("ssh_manager_app.actions_app.tk.Menu", return_value=menu), \
         patch("ssh_manager_app.actions_app.apply_search_history_entry") as apply_entry:
        show_search_history_menu(app)
        first_command = menu.add_command.call_args_list[0].kwargs["command"]
        first_command()

    apply_entry.assert_called_once_with(app, "alpha")


def test_show_search_history_menu_clear_callback_clears_history():
    app = MagicMock()
    app._search_history = ["alpha"]
    app._search_history_btn.winfo_rootx.return_value = 0
    app._search_history_btn.winfo_rooty.return_value = 0
    app._search_history_btn.winfo_height.return_value = 0

    menu = MagicMock()
    with patch("ssh_manager_app.actions_app.tk.Menu", return_value=menu), \
         patch("ssh_manager_app.actions_app.clear_search_history") as clear_history:
        show_search_history_menu(app)
        clear_command = menu.add_command.call_args_list[-1].kwargs["command"]
        clear_command()

    clear_history.assert_called_once_with(app)


def test_connect_sessions_uses_app_settings_directly():
    app = MagicMock()
    app.settings = AppSettings(quick_users=["alice", "bob"], default_user="alice")
    app._tree.get_session_colors.return_value = {"s1": "#123456"}
    session = Session("s1", "srv1", [], "10.0.0.1")

    dialog = MagicMock()
    dialog.result = "bob"

    with patch("ssh_manager_app.actions_remote.UserDialog", return_value=dialog) as dialog_cls:
        connect_sessions(app, [session])

    dialog_cls.assert_called_once_with(app, quick_users=["alice", "bob"], default_user="alice")
    app.wait_window.assert_called_once_with(dialog)
    app._terminal_launcher.launch.assert_called_once_with(
        [session],
        "bob",
        {"s1": "#123456"},
        terminal_settings=app.settings.windows_terminal,
    )


def test_open_tunnel_uses_app_settings_directly():
    app = MagicMock()
    app.settings = AppSettings(quick_users=["root", "deploy"], default_user="deploy")
    app.settings.windows_terminal.profile_name = "Custom Bash"

    dialog = MagicMock()
    dialog.result = ("jump.example", 9000, "db.internal", 5432, "deploy")

    with patch("ssh_manager_app.actions_remote.SshTunnelDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_remote.build_ssh_tunnel_command", return_value="wt cmd") as build_cmd, \
         patch("ssh_manager_app.actions_remote.subprocess.Popen") as popen:
        open_tunnel(app)

    dialog_cls.assert_called_once_with(
        app,
        session=None,
        quick_users=["root", "deploy"],
        default_user="deploy",
    )
    build_cmd.assert_called_once_with(
        "jump.example",
        9000,
        "db.internal",
        5432,
        "deploy",
        terminal_settings=app.settings.windows_terminal,
    )
    popen.assert_called_once_with("wt cmd")


def test_quick_connect_session_uses_terminal_settings_from_app_settings():
    app = MagicMock()
    app.settings = AppSettings(default_user="kai")
    app._tree.get_session_colors.return_value = {"s1": "#abcdef"}
    session = Session("s1", "srv1", [], "10.0.0.1")

    with patch("ssh_manager_app.actions_remote.resolve_single_session_user", return_value="root"):
        quick_connect_session(app, session)

    app._terminal_launcher.launch.assert_called_once_with(
        [session],
        "root",
        {"s1": "#abcdef"},
        terminal_settings=app.settings.windows_terminal,
    )


def test_deploy_ssh_key_uses_app_settings_directly():
    app = MagicMock()
    app.settings = AppSettings(quick_users=["root", "ops"], default_user="ops")
    sessions = [Session("s1", "srv1", [], "10.0.0.1")]

    dialog = MagicMock()
    dialog.result = ("id_ed25519.pub", "ops")

    with patch("ssh_manager_app.actions_remote.SshCopyIdDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_remote.build_ssh_copy_id_command", return_value="copy-cmd") as build_cmd, \
         patch("ssh_manager_app.actions_remote.subprocess.Popen") as popen:
        deploy_ssh_key(app, sessions)

    dialog_cls.assert_called_once_with(app, target_count=1, quick_users=["root", "ops"], default_user="ops")
    build_cmd.assert_called_once_with(sessions, "id_ed25519.pub", "ops", terminal_settings=app.settings.windows_terminal)
    popen.assert_called_once_with("copy-cmd", shell=True)


def test_remove_ssh_key_uses_app_settings_directly():
    app = MagicMock()
    app.settings = AppSettings(quick_users=["root", "ops"], default_user="ops")
    sessions = [Session("s1", "srv1", [], "10.0.0.1")]

    dialog = MagicMock()
    dialog.result = ("id_ed25519.pub", "ops")

    with patch("ssh_manager_app.actions_remote.SshRemoveKeyDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_remote.build_ssh_remove_key_command", return_value="remove-cmd") as build_cmd, \
         patch("ssh_manager_app.actions_remote.subprocess.Popen") as popen:
        remove_ssh_key(app, sessions)

    dialog_cls.assert_called_once_with(app, target_count=1, quick_users=["root", "ops"], default_user="ops")
    build_cmd.assert_called_once_with(sessions, "id_ed25519.pub", "ops", terminal_settings=app.settings.windows_terminal)
    popen.assert_called_once_with("remove-cmd", shell=True)


def test_run_remote_command_uses_app_settings_directly():
    app = MagicMock()
    app.settings = AppSettings(quick_users=["root", "ops"], default_user="ops")
    app._initial_toolbar_search_texts = {"last_remote_command": "uptime"}
    app._tree.get_session_colors.return_value = {"s1": "#123456"}
    sessions = [Session("s1", "srv1", [], "10.0.0.1")]

    dialog = MagicMock()
    dialog.result = ("all", "whoami", True)
    confirm = MagicMock()
    confirm.result = True

    with patch("ssh_manager_app.actions_remote.RemoteCommandDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_remote.resolve_users_for_sessions", return_value=[(sessions[0], "ops")]) as resolve_users, \
         patch("ssh_manager_app.actions_remote.RemoteCommandConfirmDialog", return_value=confirm) as confirm_cls, \
         patch("ssh_manager_app.actions_remote.build_remote_command_wt_command", return_value="remote-cmd") as build_cmd, \
         patch("ssh_manager_app.actions_remote.subprocess.Popen") as popen:
        run_remote_command(app, sessions)

    dialog_cls.assert_called_once_with(
        app,
        target_count=1,
        last_command="uptime",
        quick_users=["root", "ops"],
        default_user="ops",
    )
    resolve_users.assert_called_once_with(app, sessions, "all")
    confirm_cls.assert_called_once_with(app, "whoami", [(sessions[0], "ops")], True)
    build_cmd.assert_called_once_with(
        [(sessions[0], "ops", "whoami")],
        close_on_success=True,
        session_colors={"s1": "#123456"},
        terminal_settings=app.settings.windows_terminal,
    )
    popen.assert_called_once_with("remote-cmd", shell=True)


def test_open_via_jumphost_uses_terminal_settings_from_app_settings():
    app = MagicMock()
    app.settings = AppSettings(default_user="ops")
    app._sessions = []
    app._tree.get_open_folders.return_value = {"Prod"}
    app._tree.get_session_colors.return_value = {"s1": "#654321"}
    session = Session("s1", "srv1", ["Prod"], "10.0.0.1")

    dialog = MagicMock()
    dialog.save_result = None
    dialog.result = ("jump.example", "jumper", 2222)

    with patch("ssh_manager_app.actions_remote.JumpHostDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_remote.resolve_single_session_user", return_value="ops") as resolve_user, \
         patch("ssh_manager_app.actions_remote.build_jump_wt_command", return_value="jump-cmd") as build_cmd, \
         patch("ssh_manager_app.actions_remote.subprocess.Popen") as popen:
        open_via_jumphost(app, session)

    dialog_cls.assert_called_once_with(app, session, app._sessions, open_folders_getter=app._tree.get_open_folders)
    resolve_user.assert_called_once_with(app, session, title="Benutzername für srv1")
    build_cmd.assert_called_once_with(
        session,
        "ops",
        "jump.example",
        "jumper",
        2222,
        "#654321",
        terminal_settings=app.settings.windows_terminal,
    )
    popen.assert_called_once_with("jump-cmd", shell=True)


def test_open_via_jumphost_save_result_rebuilds_sessions_and_shows_toast():
    app = MagicMock()
    app.settings = AppSettings(default_user="ops")
    app._sessions = []
    app._tree.get_open_folders.return_value = {"Prod"}
    session = Session("s1", "srv1", ["Prod"], "10.0.0.1")

    dialog = MagicMock()
    dialog.save_result = ("alias-prod", "jump.example", 2222, "jumper", "target-key")
    dialog.result = None

    with patch("ssh_manager_app.actions_remote.JumpHostDialog", return_value=dialog), \
         patch("ssh_manager_app.actions_remote.resolve_single_session_user", return_value="ops") as resolve_user, \
         patch("ssh_manager_app.actions_remote._append_ssh_config_alias") as append_alias, \
         patch("ssh_manager_app.actions_remote.rebuild_sessions") as rebuild_sessions, \
         patch("ssh_manager_app.actions_remote.ToastNotification") as toast:
        open_via_jumphost(app, session)

    resolve_user.assert_called_once_with(app, session, title="Benutzername für srv1")
    append_alias.assert_called_once_with("alias-prod", session, "ops", "jump.example", "jumper", 2222)
    rebuild_sessions.assert_called_once_with(app, reload_winscp=True)
    toast.assert_called_once_with(app, "SSH-Config 'alias-prod' gespeichert")


def test_resolve_single_session_user_returns_ssh_config_username_without_dialog():
    app = MagicMock()
    app.settings = AppSettings(quick_users=["root"], default_user="root")
    session = Session("s1", "alias1", [], "alias1", username="deploy", source="ssh_config")

    result = resolve_single_session_user(app, session)

    assert result == "deploy"
    app.wait_window.assert_not_called()


def test_resolve_users_for_sessions_all_mode_uses_shared_user_for_missing_hosts():
    app = MagicMock()
    ssh_cfg = Session("s1", "cfg", [], "cfg", username="deploy", source="ssh_config")
    regular = Session("s2", "srv2", [], "10.0.0.2")
    dialog = MagicMock()
    dialog.result = "ops"

    with patch("ssh_manager_app.actions_remote.UserDialog", return_value=dialog) as dialog_cls:
        result = resolve_users_for_sessions(app, [ssh_cfg, regular], "all")

    dialog_cls.assert_called_once_with(app, title="Benutzername für alle Hosts")
    app.wait_window.assert_called_once_with(dialog)
    assert result == [(ssh_cfg, "deploy"), (regular, "ops")]


def test_resolve_users_for_sessions_per_host_mode_returns_none_on_cancel():
    app = MagicMock()
    regular = Session("s2", "srv2", [], "10.0.0.2")
    dialog = MagicMock()
    dialog.result = None

    with patch("ssh_manager_app.actions_remote.UserDialog", return_value=dialog) as dialog_cls:
        result = resolve_users_for_sessions(app, [regular], "per_host")

    dialog_cls.assert_called_once_with(app, title="Benutzername für srv2")
    app.wait_window.assert_called_once_with(dialog)
    assert result is None


def test_resolve_users_for_sessions_all_mode_skips_dialog_when_all_users_known():
    app = MagicMock()
    sessions = [
        Session("s1", "cfg1", [], "cfg1", username="deploy", source="ssh_config"),
        Session("s2", "cfg2", [], "cfg2", username="root", source="ssh_config"),
    ]

    with patch("ssh_manager_app.actions_remote.UserDialog") as dialog_cls:
        result = resolve_users_for_sessions(app, sessions, "all")

    dialog_cls.assert_not_called()
    app.wait_window.assert_not_called()
    assert result == [(sessions[0], "deploy"), (sessions[1], "root")]


def test_resolve_users_for_sessions_all_mode_warns_when_no_user_can_be_resolved():
    app = MagicMock()
    session = Session("s1", "srv1", [], "10.0.0.1")
    dialog = MagicMock()
    dialog.result = ""

    with patch("ssh_manager_app.actions_remote.UserDialog", return_value=dialog), \
         patch("ssh_manager_app.actions_remote.messagebox.showwarning") as showwarning:
        result = resolve_users_for_sessions(app, [session], "all")

    assert result is None
    showwarning.assert_called_once_with(
        "Fehlender Benutzer",
        "Für 'srv1' konnte kein Benutzer bestimmt werden.",
        parent=app,
    )
