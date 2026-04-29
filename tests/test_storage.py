import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app.constants import _SSH_ALIAS_PREFIX, _SSH_CONFIG_PREFIX
from ssh_manager_app.models import default_settings
from ssh_manager_app.storage import (
    load_app_sessions,
    load_filezilla_config_sessions,
    load_notes,
    load_settings,
    load_settings_from_path,
    load_ssh_config_sessions,
    load_ui_state,
    save_app_sessions,
    save_notes,
    save_settings,
    save_ui_state,
)


def test_load_settings_returns_defaults_on_invalid_json():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        settings_file.write_text("{kaputt", encoding="utf-8")
        with patch("ssh_manager_app.storage._SETTINGS_FILE", settings_file):
            settings = load_settings()

    defaults = default_settings()
    assert settings == defaults


def test_save_settings_writes_nested_settings_payload():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        settings = default_settings()
        settings.quick_users = ["alice", "bob"]
        settings.default_user = "alice"
        settings.toolbar.show_notes_column = False
        settings.windows_terminal.profile_name = "PowerShell"
        settings.source_visibility.show_filezilla_config = True

        with patch("ssh_manager_app.storage._SETTINGS_FILE", settings_file):
            save_settings(settings)

        raw = json.loads(settings_file.read_text(encoding="utf-8"))

    assert raw["quick_users"] == ["alice", "bob"]
    assert raw["default_user"] == "alice"
    assert raw["toolbar"]["show_notes_column"] is False
    assert raw["windows_terminal"]["profile_name"] == "PowerShell"
    assert raw["source_visibility"]["show_filezilla_config"] is True


def test_load_settings_from_path_invalid_quick_users_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(json.dumps({"quick_users": "not-a-list"}), encoding="utf-8")

        settings = load_settings_from_path(path)

    defaults = default_settings()
    assert settings.quick_users == defaults.quick_users
    assert settings.default_user == defaults.default_user


def test_load_settings_from_path_non_object_root_falls_back_to_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

        settings = load_settings_from_path(path)

    assert settings == default_settings()


def test_load_settings_from_path_ignores_non_object_nested_sections():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "toolbar": 7,
                    "windows_terminal": "broken",
                    "source_visibility": ["bad"],
                }
            ),
            encoding="utf-8",
        )

        settings = load_settings_from_path(path)

    defaults = default_settings()
    assert settings.toolbar == defaults.toolbar
    assert settings.windows_terminal == defaults.windows_terminal
    assert settings.source_visibility == defaults.source_visibility


def test_load_settings_from_path_normalizes_default_user_and_timeout():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "quick_users": [" alice ", "", "bob"],
                    "default_user": "carol",
                    "host_check_timeout_seconds": "0",
                    "startup_expand_mode": "invalid",
                }
            ),
            encoding="utf-8",
        )

        settings = load_settings_from_path(path)

    assert settings.quick_users == ["carol", "alice", "bob"]
    assert settings.default_user == "carol"
    assert settings.host_check_timeout_seconds == 1
    assert settings.startup_expand_mode == default_settings().startup_expand_mode


def test_load_settings_from_path_filters_invalid_column_order_entries():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "settings.json"
        path.write_text(
            json.dumps({"toolbar": {"column_order": ["notes", "bogus", "port", "hostname"]}}),
            encoding="utf-8",
        )

        settings = load_settings_from_path(path)

    assert settings.toolbar.column_order == ["notes", "port", "hostname"]


def test_save_and_load_ui_state_roundtrip_with_search_history():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "ui_state.json"
        with patch("ssh_manager_app.storage._STATE_FILE", state_file):
            save_ui_state(
                {"Extern", "Extern/Sub"},
                {"Extern/srv": "#c0392b"},
                {"search_history": [" alpha ", "", "beta"]},
            )
            folders, colors, toolbar_texts = load_ui_state()

    assert folders == {"Extern", "Extern/Sub"}
    assert colors == {"Extern/srv": "#c0392b"}
    assert toolbar_texts["search_history"] == ["alpha", "beta"]


def test_load_ui_state_preserves_other_toolbar_texts_and_normalizes_mixed_history_entries():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "ui_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "expanded_folders": ["Extern"],
                    "session_colors": {"Extern/srv": "#c0392b"},
                    "toolbar_search_texts": {
                        "main": "  prod  ",
                        "last_remote_command": "uptime",
                        "search_history": [" alpha ", 42, "", None, "beta"],
                    },
                }
            ),
            encoding="utf-8",
        )

        with patch("ssh_manager_app.storage._STATE_FILE", state_file):
            folders, colors, toolbar_texts = load_ui_state()

    assert folders == {"Extern"}
    assert colors == {"Extern/srv": "#c0392b"}
    assert toolbar_texts == {
        "main": "  prod  ",
        "last_remote_command": "uptime",
        "search_history": ["alpha", "42", "None", "beta"],
    }


def test_load_ui_state_returns_defaults_when_toolbar_search_texts_payload_is_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        state_file = Path(tmp) / "ui_state.json"
        state_file.write_text(
            json.dumps(
                {
                    "expanded_folders": ["Extern"],
                    "session_colors": {"Extern/srv": "#c0392b"},
                    "toolbar_search_texts": 7,
                }
            ),
            encoding="utf-8",
        )

        with patch("ssh_manager_app.storage._STATE_FILE", state_file):
            folders, colors, toolbar_texts = load_ui_state()

    assert folders == set()
    assert colors == {}
    assert toolbar_texts == {}


def test_save_and_load_notes_roundtrip_filters_blank_values():
    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.json"
        with patch("ssh_manager_app.storage._NOTES_FILE", notes_file):
            save_notes({"a": "hello", "b": ""})
            notes = load_notes()

    assert notes == {"a": "hello"}


def test_load_notes_returns_empty_dict_for_non_object_root_payload():
    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "notes.json"
        notes_file.write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")

        with patch("ssh_manager_app.storage._NOTES_FILE", notes_file):
            notes = load_notes()

    assert notes == {}


def test_save_and_load_app_sessions_roundtrip_for_app_and_alias_sources():
    with tempfile.TemporaryDirectory() as tmp:
        sessions_file = Path(tmp) / "app_sessions.json"
        with patch("ssh_manager_app.storage._APP_SESSIONS_FILE", sessions_file):
            from ssh_manager_app.models import Session

            sessions = [
                Session(
                    key=f"__app__server-1",
                    display_name="Server 1",
                    folder_path=["Team"],
                    hostname="10.0.0.1",
                    username="alice",
                    port=22,
                    source="app",
                ),
                Session(
                    key=f"{_SSH_ALIAS_PREFIX}jump-prod",
                    display_name="jump-prod",
                    folder_path=["Aliases"],
                    hostname="10.0.0.2",
                    username="bob",
                    port=2222,
                    source="ssh_alias",
                ),
            ]
            save_app_sessions(sessions)
            loaded = load_app_sessions()

    assert [s.key for s in loaded] == ["__app__server-1", f"{_SSH_ALIAS_PREFIX}jump-prod"]
    assert loaded[0].folder_path == ["Team"]
    assert loaded[1].port == 2222



def test_load_app_sessions_skips_malformed_entries_and_keeps_valid_ones():
    with tempfile.TemporaryDirectory() as tmp:
        sessions_file = Path(tmp) / "app_sessions.json"
        sessions_file.write_text(
            json.dumps(
                {
                    "sessions": [
                        {"id": "server-1", "name": "Server 1", "hostname": "10.0.0.1", "source": "app"},
                        "not-a-dict",
                        {"id": "broken", "name": "Broken"},
                    ]
                }
            ),
            encoding="utf-8",
        )

        with patch("ssh_manager_app.storage._APP_SESSIONS_FILE", sessions_file):
            sessions = load_app_sessions()

    assert [s.key for s in sessions] == ["__app__server-1"]
    assert sessions[0].hostname == "10.0.0.1"

def test_save_app_sessions_skips_unsupported_sources():
    with tempfile.TemporaryDirectory() as tmp:
        sessions_file = Path(tmp) / "app_sessions.json"
        with patch("ssh_manager_app.storage._APP_SESSIONS_FILE", sessions_file):
            from ssh_manager_app.models import Session

            save_app_sessions(
                [
                    Session(
                        key="__app__server-1",
                        display_name="Server 1",
                        folder_path=["Team"],
                        hostname="10.0.0.1",
                        source="app",
                    ),
                    Session(
                        key="__winscp__legacy-1",
                        display_name="Legacy",
                        folder_path=["Legacy"],
                        hostname="10.0.0.2",
                        source="winscp",
                    ),
                ]
            )
            loaded = load_app_sessions()

    assert [s.key for s in loaded] == ["__app__server-1"]


def test_load_filezilla_config_sessions_parses_nested_folders_and_ignores_unsupported_protocols():
    with tempfile.TemporaryDirectory() as tmp:
        appdata = Path(tmp)
        filezilla_dir = appdata / "FileZilla"
        filezilla_dir.mkdir(parents=True)
        xml_file = filezilla_dir / "sitemanager.xml"
        xml_file.write_text(
            """
<FileZilla3>
  <Servers>
    <Folder Name="RootFolder">
      <Server>
        <Name>Prod</Name>
        <Host>prod.example.com</Host>
        <Port>2222</Port>
        <User>deploy</User>
        <Protocol>1</Protocol>
      </Server>
      <Server>
        <Name>Ignored</Name>
        <Host>ignored.example.com</Host>
        <Protocol>3</Protocol>
      </Server>
    </Folder>
  </Servers>
</FileZilla3>
""".strip(),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"APPDATA": str(appdata)}):
            sessions = load_filezilla_config_sessions()

    assert len(sessions) == 1
    session = sessions[0]
    assert session.display_name == "Prod"
    assert session.folder_path == ["FileZilla Config", "RootFolder"]
    assert session.hostname == "prod.example.com"
    assert session.port == 2222
    assert session.username == "deploy"


def test_load_filezilla_config_sessions_supports_lowercase_dir_and_defaults_missing_metadata():
    with tempfile.TemporaryDirectory() as tmp:
        appdata = Path(tmp)
        filezilla_dir = appdata / "filezilla"
        filezilla_dir.mkdir(parents=True)
        xml_file = filezilla_dir / "sitemanager.xml"
        xml_file.write_text(
            """
<FileZilla3>
  <Servers>
    <Folder>
      <Server>
        <Host>fallback.example.com</Host>
        <Port>not-a-port</Port>
        <Protocol>0</Protocol>
      </Server>
    </Folder>
  </Servers>
</FileZilla3>
""".strip(),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"APPDATA": str(appdata)}):
            sessions = load_filezilla_config_sessions()

    assert len(sessions) == 1
    session = sessions[0]
    assert session.display_name == "fallback.example.com"
    assert session.folder_path == ["FileZilla Config", "Ordner"]
    assert session.hostname == "fallback.example.com"
    assert session.port == 22
    assert session.username == ""


def test_load_ssh_config_sessions_skips_wildcards_and_parses_fields():
    with tempfile.TemporaryDirectory() as tmp:
        ssh_config = Path(tmp) / "config"
        ssh_config.write_text(
            """
Host prod
  HostName prod.example.com
  User deploy
  Port 2200

Host *
  User ignored

Host staging
  HostName stage.example.com
""".strip(),
            encoding="utf-8",
        )
        with patch("ssh_manager_app.storage._SSH_CONFIG_FILE", ssh_config):
            sessions = load_ssh_config_sessions()

    assert [s.key for s in sessions] == [f"{_SSH_CONFIG_PREFIX}prod", f"{_SSH_CONFIG_PREFIX}staging"]
    assert sessions[0].hostname == "prod.example.com"
    assert sessions[0].username == "deploy"
    assert sessions[0].port == 2200
    assert sessions[1].hostname == "stage.example.com"
