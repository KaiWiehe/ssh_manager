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


def test_registry_reader_loads_sessions(monkeypatch):
    """RegistryReader liest Sessions korrekt aus gemockter Registry."""
    session_data = [
        ("Extern/Bundo", "ftp.example.com", 22, "myuser"),
        ("Privat/Plex", "192.168.1.10", 2222, "plex"),
    ]

    call_count = {"n": 0}

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        idx = min(call_count["n"] // 2, len(session_data) - 1)
        call_count["n"] += 1
        s = session_data[idx]
        if name == "HostName":
            return (s[1], winreg.REG_SZ)
        if name == "PortNumber":
            return (s[2], winreg.REG_DWORD)
        if name == "UserName":
            return (s[3], winreg.REG_SZ)
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


def test_registry_reader_skips_malicious_hostname(monkeypatch):
    """RegistryReader überspringt Sessions mit gefährlichem Hostname."""
    session_data = [
        ("Safe/Server", "10.0.0.1", 22, "admin"),
        ("Malicious/Attack", "10.0.0.1 & del /f", 22, "admin"),
        ("Malicious/Pipe", "10.0.0.1 | rm -rf /", 22, "admin"),
        ("Malicious/Semicolon", "10.0.0.1; reboot", 22, "admin"),
    ]

    call_count = {"n": 0}

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        idx = min(call_count["n"] // 3, len(session_data) - 1)
        call_count["n"] += 1
        s = session_data[idx]
        if name == "HostName":
            return (s[1], winreg.REG_SZ)
        if name == "PortNumber":
            return (s[2], winreg.REG_DWORD)
        if name == "UserName":
            return (s[3], winreg.REG_SZ)
        raise FileNotFoundError

    with patch("winreg.OpenKey", side_effect=mock_open_key), \
         patch("winreg.EnumKey", side_effect=mock_enum_key), \
         patch("winreg.QueryValueEx", side_effect=mock_query_value):
        reader = RegistryReader()
        sessions = reader.load_sessions()

    # Only the safe session should survive validation
    assert len(sessions) == 1
    assert sessions[0].hostname == "10.0.0.1"


def test_registry_reader_skips_malicious_username(monkeypatch):
    """RegistryReader überspringt Sessions mit gefährlichem Username."""
    session_data = [
        ("Safe/Server", "10.0.0.2", 22, "valid-user"),
        ("Evil/Server", "10.0.0.3", 22, "user$(id)"),
    ]

    call_count = {"n": 0}

    def mock_open_key(base, path, *a, **kw):
        m = MagicMock()
        m.__enter__ = lambda s: s
        m.__exit__ = MagicMock(return_value=False)
        return m

    def mock_enum_key(key, i):
        names = [s[0] for s in session_data]
        if i < len(names):
            return names[i]
        raise OSError

    def mock_query_value(key, name):
        idx = min(call_count["n"] // 3, len(session_data) - 1)
        call_count["n"] += 1
        s = session_data[idx]
        if name == "HostName":
            return (s[1], winreg.REG_SZ)
        if name == "PortNumber":
            return (s[2], winreg.REG_DWORD)
        if name == "UserName":
            return (s[3], winreg.REG_SZ)
        raise FileNotFoundError

    with patch("winreg.OpenKey", side_effect=mock_open_key), \
         patch("winreg.EnumKey", side_effect=mock_enum_key), \
         patch("winreg.QueryValueEx", side_effect=mock_query_value):
        reader = RegistryReader()
        sessions = reader.load_sessions()

    assert len(sessions) == 1
    assert sessions[0].hostname == "10.0.0.2"
