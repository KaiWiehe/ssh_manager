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
