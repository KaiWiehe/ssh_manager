from copy import deepcopy
import json
from pathlib import Path

import pytest

from ssh_manager_app import storage
from ssh_manager_app.models import Session, default_settings


@pytest.fixture
def stores(tmp_path, monkeypatch):
    for name, filename in (("_STATE_FILE", "ui_state.json"), ("_NOTES_FILE", "notes.json"),
                           ("_SETTINGS_FILE", "settings.json"), ("_APP_SESSIONS_FILE", "app_sessions.json")):
        monkeypatch.setattr(storage, name, tmp_path / filename)
    storage.save_settings(default_settings())
    storage.save_app_sessions([Session("__app__one", "Test", ["Lab"], "test.invalid", "ops", source="app")])
    storage.save_notes({"__app__one": "Notiz"})
    storage.save_ui_state({"Lab"}, {"__app__one": "#123456"}, {"remote_command_favorites": [{"mode": "command", "command": "uptime"}]})
    return tmp_path


def test_backup_restore_roundtrip_and_safety_copy(stores):
    backup = stores / "backup.json"
    storage.create_app_backup(backup)
    payload = storage.read_app_backup(backup)
    assert set(payload["documents"]) == {"settings.json", "app_sessions.json", "notes.json", "ui_state.json"}
    storage.save_notes({"__app__one": "Geändert"})
    safety = storage.restore_app_backup(payload)
    assert storage.load_notes() == {"__app__one": "Notiz"}
    assert storage.read_app_backup(safety)["documents"]["notes.json"]["notes"]["__app__one"] == "Geändert"
    assert storage.load_app_sessions()[0].display_name == "Test"
    assert storage.load_ui_state()[2]["remote_command_favorites"][0]["command"] == "uptime"


def test_restore_failure_recovers_whole_transaction(stores, monkeypatch):
    backup = stores / "backup.json"
    storage.create_app_backup(backup)
    payload = storage.read_app_backup(backup)
    payload["documents"]["notes.json"]["notes"]["__app__one"] = "Wiederhergestellt"
    write = storage._atomic_write_json
    def fail(path, value):
        if path == storage._NOTES_FILE:
            raise OSError("simulated failure")
        write(path, value)
    monkeypatch.setattr(storage, "_atomic_write_json", fail)
    with pytest.raises(OSError):
        storage.restore_app_backup(payload)
    assert (stores / "app-restore-pending.json").exists()
    monkeypatch.setattr(storage, "_atomic_write_json", write)
    assert storage.load_notes()["__app__one"] == "Wiederhergestellt"
    assert not (stores / "app-restore-pending.json").exists()


@pytest.mark.parametrize("bad", ["paths", "source", "port", "duplicate"])
def test_invalid_backup_rejected_before_any_write(stores, bad):
    backup = stores / "backup.json"
    storage.create_app_backup(backup)
    payload = deepcopy(storage.read_app_backup(backup))
    if bad == "paths":
        payload["documents"]["../../config"] = {}
    elif bad == "source":
        payload["documents"]["app_sessions.json"]["sessions"][0]["source"] = "winscp"
    elif bad == "port":
        payload["documents"]["app_sessions.json"]["sessions"][0]["port"] = 999999
    else:
        payload["documents"]["app_sessions.json"]["sessions"] *= 2
    before = storage._NOTES_FILE.read_bytes()
    with pytest.raises(ValueError):
        storage.restore_app_backup(payload)
    assert storage._NOTES_FILE.read_bytes() == before
    assert not (stores / "app-restore-pending.json").exists()


def test_backup_cannot_replace_live_store(stores):
    with pytest.raises(ValueError):
        storage.create_app_backup(storage._STATE_FILE)
