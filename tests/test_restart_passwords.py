"""Credential persistence and admission tests; no actual SSH connections."""
from copy import deepcopy
import json
import os

import pytest

from ssh_manager_app.restart_passwords import seal, unseal, validate_sealed, passwords_for_run
from ssh_manager_app.restart_templates import new_template, resolve_targets, validate_template
from ssh_manager_app.models import Session


@pytest.mark.skipif(os.name != "nt", reason="Real Windows DPAPI required")
def test_dpapi_roundtrip_unicode_exact_spaces_and_no_cleartext():
    secret = "  sönder • password ' $ ;  "
    stored = seal(secret)
    assert secret not in stored
    assert unseal(stored) == secret
    assert seal(secret, stored) == stored
    assert seal("changed", stored) != stored
    assert seal("", stored) == ""


@pytest.mark.parametrize("value", ["plaintext", "dpapi-user-v1:", "dpapi-user-v1:!!!", 123, None])
def test_invalid_payloads_rejected_without_echoing(value):
    with pytest.raises(ValueError, match="Ungültiges verschlüsseltes") as error:
        validate_sealed(value)
    assert "plaintext" not in str(error.value)


@pytest.mark.parametrize("value", ["line\nbreak", "line\rbreak", "null\x00byte", "x" * 4097])
def test_sudo_stdin_injection_and_oversized_passwords_rejected(value):
    with pytest.raises(ValueError):
        seal(value)


@pytest.mark.skipif(os.name != "nt", reason="Real Windows DPAPI required")
def test_saved_credentials_validate_and_resolve_by_id_after_reorder():
    sessions = [Session(key, key, [], key + ".example", "admin", source="app") for key in ("one", "two", "three")]
    item = new_template(sessions)
    item["password_per_connection"] = True
    item["password_protected"] = seal("common")
    for target, password in zip(item["targets"], ("exception", "common", "")):
        target["password_protected"] = seal(password)
    item = validate_template(json.loads(json.dumps(item)))
    assert "exception" not in json.dumps(item)
    targets = resolve_targets(item, sessions)[::-1]
    assert passwords_for_run(item, targets, "ignored") == {"three": "", "two": "common", "one": "exception"}
    item["password_per_connection"] = False
    assert set(passwords_for_run(item, targets, "temporary").values()) == {"temporary"}


def test_unreadable_credentials_block_before_progress_or_reboot(monkeypatch):
    from ssh_manager_app import actions_restart_templates as actions
    sessions = [Session("one", "one", [], "one.example", "admin", source="app")]
    item = new_template(sessions)
    item["password_per_connection"] = True
    item["targets"][0]["password_protected"] = "dpapi-user-v1:YWJj"
    def forbidden(*args, **kwargs):
        pytest.fail("Must fail before any progress dialog or SSH work")
    monkeypatch.setattr(actions, "ServerRestartProgressDialog", forbidden)
    monkeypatch.setattr(actions, "monitor_template_restart", forbidden)
    with pytest.raises(ValueError, match="Windows-Konto"):
        actions.run_template(None, item, resolve_targets(item, sessions), "")
    assert validate_template(deepcopy(item)) == item  # Backups need no decryption.


@pytest.mark.skipif(os.name != "nt", reason="Real Windows DPAPI required")
def test_encrypted_credentials_survive_real_storage_and_backup(tmp_path, monkeypatch):
    from ssh_manager_app import storage
    from ssh_manager_app.models import default_settings
    for field, name in (("_STATE_FILE", "ui_state.json"), ("_SETTINGS_FILE", "settings.json"),
                        ("_APP_SESSIONS_FILE", "app_sessions.json"), ("_NOTES_FILE", "notes.json")):
        monkeypatch.setattr(storage, field, tmp_path / name)
    item = new_template([Session("one", "one", [], "one.example", "admin", source="app")])
    item.update(password_per_connection=True, password_protected=seal("shared-private"))
    item["targets"][0]["password_protected"] = seal("exception-private")
    library = {"schema": 1, "items": [item]}
    storage.save_ui_state(set(), {}, {"restart_templates": library})
    assert storage.load_ui_state()[2]["restart_templates"] == library
    storage.save_settings(default_settings())
    storage.save_app_sessions([])
    storage.save_notes({})
    backup = tmp_path / "backup.json"
    storage.create_app_backup(backup)
    assert "shared-private" not in backup.read_text(encoding="utf-8")
    assert "exception-private" not in backup.read_text(encoding="utf-8")
    restored = storage.read_app_backup(backup)["documents"]["ui_state.json"]["toolbar_search_texts"]["restart_templates"]
    assert restored == library
    assert unseal(restored["items"][0]["targets"][0]["password_protected"]) == "exception-private"
