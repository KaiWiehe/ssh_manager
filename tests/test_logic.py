# tests/test_logic.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager import Session, parse_session_key


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


from ssh_manager import build_wt_command


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


from unittest.mock import patch, MagicMock
import winreg
from ssh_manager import RegistryReader


def test_registry_reader_loads_sessions():
    """RegistryReader liest Sessions korrekt aus gemockter Registry."""
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
    """RegistryReader überspringt Sessions mit gefährlichem Hostname."""
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

    # Only the safe session should survive validation
    assert len(sessions) == 1
    assert sessions[0].hostname == "10.0.0.1"


def test_registry_reader_skips_malicious_username():
    """RegistryReader überspringt Sessions mit gefährlichem Username."""
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


import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from ssh_manager import _color_tag, PALETTE, _load_ui_state, _save_ui_state


def test_load_ui_state_missing_file_returns_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "nonexistent.json"
        with patch("ssh_manager._STATE_FILE", fake_path):
            folders, colors = _load_ui_state()
    assert folders == set()
    assert colors == {}


def test_save_and_load_ui_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "ui_state.json"
        with patch("ssh_manager._STATE_FILE", fake_path):
            _save_ui_state({"Extern", "Extern/Sub"}, {"Extern/srv": "#c0392b"})
            folders, colors = _load_ui_state()
    assert folders == {"Extern", "Extern/Sub"}
    assert colors == {"Extern/srv": "#c0392b"}


def test_load_ui_state_ignores_unknown_keys():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "ui_state.json"
        fake_path.write_text(json.dumps({"expanded_folders": ["A"], "future_key": 42}))
        with patch("ssh_manager._STATE_FILE", fake_path):
            folders, colors = _load_ui_state()
    assert folders == {"A"}
    assert colors == {}


from ssh_manager import _color_tag, PALETTE


def test_color_tag_strips_hash():
    assert _color_tag("#2d8653") == "color_2d8653"


def test_color_tag_without_hash():
    assert _color_tag("2d8653") == "color_2d8653"


def test_palette_has_eight_entries():
    assert len(PALETTE) == 8


def test_palette_entries_have_name_and_hex():
    for name, hex_color in PALETTE:
        assert isinstance(name, str) and len(name) > 0
        assert hex_color.startswith("#") and len(hex_color) == 7


from ssh_manager import _load_ssh_config_sessions, _SSH_CONFIG_DEFAULT_FOLDER
from unittest.mock import patch, MagicMock


def _mock_ssh_config(content: str):
    """Erstellt einen Mock für _SSH_CONFIG_FILE mit gegebenem Inhalt."""
    m = MagicMock()
    m.read_text.return_value = content
    return m


def test_load_ssh_config_sessions_basic():
    config = "Host myserver\n  HostName 10.0.0.5\n  User admin\n  Port 2222\n"
    with patch("ssh_manager._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = _load_ssh_config_sessions()
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
    with patch("ssh_manager._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = _load_ssh_config_sessions()
    assert len(sessions) == 1
    assert sessions[0].display_name == "realhost"


def test_load_ssh_config_sessions_skips_multi_pattern():
    config = "Host foo bar\n  HostName 1.2.3.4\nHost single\n  HostName 5.6.7.8\n"
    with patch("ssh_manager._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = _load_ssh_config_sessions()
    assert len(sessions) == 1
    assert sessions[0].display_name == "single"


def test_load_ssh_config_sessions_missing_file():
    m = MagicMock()
    m.read_text.side_effect = OSError("not found")
    with patch("ssh_manager._SSH_CONFIG_FILE", m):
        sessions = _load_ssh_config_sessions()
    assert sessions == []


def test_load_ssh_config_sessions_hostname_fallback():
    config = "Host myalias\n"
    with patch("ssh_manager._SSH_CONFIG_FILE", _mock_ssh_config(config)):
        sessions = _load_ssh_config_sessions()
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


from ssh_manager import (
    _default_settings,
    _load_settings_from_path,
    _save_notes,
    _load_notes,
    _load_filezilla_config_sessions,
    ToolbarSettings,
)


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
        settings = _load_settings_from_path(path)
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
        settings = _load_settings_from_path(path)
    assert settings.toolbar.column_order == ["notes", "hostname"]


def test_default_column_order_matches_ui_expectation():
    settings = _default_settings()
    assert settings.toolbar.column_order == ["notes", "hostname", "port"]


def test_save_and_load_notes_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "notes.json"
        with patch("ssh_manager._NOTES_FILE", fake_path):
            _save_notes({"session-1": "Wichtige Notiz", "session-2": "  bleibt  "})
            notes = _load_notes()
    assert notes == {"session-1": "Wichtige Notiz", "session-2": "  bleibt  "}


def test_load_notes_ignores_blank_entries():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "notes.json"
        fake_path.write_text(json.dumps({"notes": {"a": "", "b": "   ", "c": "ok"}}), encoding="utf-8")
        with patch("ssh_manager._NOTES_FILE", fake_path):
            notes = _load_notes()
    assert notes == {"c": "ok"}


def test_load_filezilla_config_sessions_reads_nested_sites():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<FileZilla3>
  <Servers>
    <Folder Name="Kunden">
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
            sessions = _load_filezilla_config_sessions()
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
    xml = """<?xml version="1.0" encoding="UTF-8"?>
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
            sessions = _load_filezilla_config_sessions()
    assert sessions == []
