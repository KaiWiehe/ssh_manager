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
