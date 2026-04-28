import json
import tkinter as tk
import os
import sys
import tempfile
from pathlib import Path
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
from ssh_manager_app.actions_remote import connect_sessions, deploy_ssh_key, open_tunnel, open_via_jumphost, quick_connect_session, remove_ssh_key, resolve_single_session_user, resolve_users_for_sessions, run_remote_command
from ssh_manager_app.actions_ui import add_search_history_entry, build_visible_sessions
from ssh_manager_app.ui import TOOLBAR_BUTTON_ORDER, layout_toolbar_buttons
from ssh_manager_app.constants import PALETTE, _SSH_CONFIG_DEFAULT_FOLDER
from ssh_manager_app.core import RegistryReader, build_wt_command, parse_session_key
from ssh_manager_app.models import AppSettings, Session, SourceVisibilitySettings, color_tag
from ssh_manager_app.storage import (
    load_filezilla_config_sessions,
    load_notes,
    load_settings_from_path,
    load_ssh_config_sessions,
    load_ui_state,
    save_notes,
    save_ui_state,
)


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
    from ssh_manager_app.dialogs_user import UserDialog as UserDialogImpl

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
