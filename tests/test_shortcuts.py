"""Tests for the configurable keyboard shortcuts framework."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app.shortcuts import (
    DEFAULT_ACTION_ORDER,
    default_shortcuts,
    find_all_conflicts,
    find_conflict,
    merge_with_defaults,
    normalize_shortcut,
    parse_shortcut,
)
from ssh_manager_app.models import default_settings
from ssh_manager_app.storage import load_settings_from_path, save_settings


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_simple_ctrl_letter():
    parsed = parse_shortcut("Ctrl+P")
    assert parsed is not None
    assert parsed.modifiers == ("Control",)
    assert parsed.key == "p"
    assert parsed.display == "Ctrl+P"


def test_parse_ctrl_dash_syntax():
    parsed = parse_shortcut("Ctrl-A")
    assert parsed is not None
    assert parsed.modifiers == ("Control",)
    assert parsed.key == "a"


def test_parse_function_key():
    parsed = parse_shortcut("F5")
    assert parsed is not None
    assert parsed.modifiers == ()
    assert parsed.key == "F5"
    assert parsed.display == "F5"


def test_parse_special_key():
    parsed = parse_shortcut("Delete")
    assert parsed is not None
    assert parsed.key == "Delete"


def test_parse_german_alias_strg():
    parsed = parse_shortcut("Strg+P")
    assert parsed is not None
    assert parsed.modifiers == ("Control",)


def test_parse_returns_none_for_empty_string():
    assert parse_shortcut("") is None
    assert parse_shortcut("   ") is None


def test_parse_returns_none_for_unknown_modifier():
    assert parse_shortcut("Hyper+A") is None


def test_parse_modifier_order_is_canonical():
    a = parse_shortcut("Ctrl+Shift+P")
    b = parse_shortcut("Shift+Ctrl+P")
    assert a is not None and b is not None
    assert a.modifiers == b.modifiers
    assert a.to_binding() == b.to_binding()


def test_to_binding_format():
    parsed = parse_shortcut("Ctrl+P")
    assert parsed.to_binding() == "<Control-p>"


def test_to_binding_variants_letter_case():
    parsed = parse_shortcut("Ctrl+P")
    variants = parsed.to_binding_variants()
    assert "<Control-p>" in variants
    assert "<Control-P>" in variants


def test_normalize_shortcut_canonicalises():
    assert normalize_shortcut("ctrl+a") == "Ctrl+A"
    assert normalize_shortcut("STRG+F") == "Ctrl+F"
    assert normalize_shortcut("garbage") == ""


def test_parse_comma_key():
    parsed = parse_shortcut("Ctrl+,")
    assert parsed is not None
    assert parsed.modifiers == ("Control",)
    assert parsed.key == "comma"


# ---------------------------------------------------------------------------
# Default merge
# ---------------------------------------------------------------------------


def test_default_shortcuts_contains_known_actions():
    defaults = default_shortcuts()
    assert "open_command_palette" in defaults
    assert defaults["open_command_palette"] == "Ctrl+P"
    assert defaults["edit"] == "F2"
    assert defaults["delete"] == "Delete"


def test_merge_with_defaults_fills_missing_actions():
    user_value = {"focus_search": "F3"}
    merged = merge_with_defaults(user_value)
    assert merged["focus_search"] == "F3"
    # Default still present for actions not provided by the user.
    assert merged["open_command_palette"] == "Ctrl+P"
    assert merged["edit"] == "F2"


def test_merge_with_defaults_drops_unknown_actions():
    merged = merge_with_defaults({"bogus_action": "Ctrl+Q"})
    assert "bogus_action" not in merged
    # All defaults survive intact.
    assert merged == default_shortcuts()


def test_merge_with_defaults_handles_empty_or_none():
    assert merge_with_defaults(None) == default_shortcuts()
    assert merge_with_defaults({}) == default_shortcuts()
    merged = merge_with_defaults({"edit": None})
    assert merged["edit"] == ""


def test_merge_with_defaults_keeps_user_unbind_choice():
    merged = merge_with_defaults({"refresh": ""})
    assert merged["refresh"] == ""
    # Other defaults remain set.
    assert merged["edit"] == "F2"


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def test_find_conflict_returns_none_when_unique():
    mapping = {"focus_search": "Ctrl+F", "edit": "F2"}
    assert find_conflict("new_session", "Ctrl+N", mapping) is None


def test_find_conflict_detects_duplicate():
    mapping = {"focus_search": "Ctrl+F", "edit": "Ctrl+F"}
    other = find_conflict("focus_search", "Ctrl+F", {"edit": "Ctrl+F"})
    assert other == "edit"


def test_find_conflict_ignores_same_action():
    mapping = {"focus_search": "Ctrl+F"}
    # Setting Ctrl+F on focus_search again is not a conflict with itself.
    assert find_conflict("focus_search", "Ctrl+F", mapping) is None


def test_find_conflict_ignores_unbound():
    assert find_conflict("focus_search", "", {"edit": "F2"}) is None


def test_find_conflict_modifier_order_independent():
    other = find_conflict("a", "Ctrl+Shift+P", {"b": "Shift+Ctrl+P"})
    assert other == "b"


def test_find_all_conflicts_lists_duplicates():
    mapping = {"a": "Ctrl+P", "b": "Ctrl+P", "c": "F2"}
    conflicts = find_all_conflicts(mapping)
    assert len(conflicts) == 1
    a, b, label = conflicts[0]
    assert {a, b} == {"a", "b"}
    assert label == "Ctrl+P"


# ---------------------------------------------------------------------------
# Persistence roundtrip
# ---------------------------------------------------------------------------


def test_settings_persistence_roundtrip_preserves_shortcuts():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        settings = default_settings()
        settings.keyboard_shortcuts["focus_search"] = "Ctrl+Shift+F"
        settings.keyboard_shortcuts["refresh"] = ""

        with patch("ssh_manager_app.storage._SETTINGS_FILE", settings_file):
            save_settings(settings)

        loaded = load_settings_from_path(settings_file)

    assert loaded.keyboard_shortcuts["focus_search"] == "Ctrl+Shift+F"
    assert loaded.keyboard_shortcuts["refresh"] == ""
    # Untouched defaults survive.
    assert loaded.keyboard_shortcuts["edit"] == "F2"


def test_load_settings_fills_missing_shortcuts_block():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        # Write a settings file without the shortcuts block at all.
        settings_file.write_text(json.dumps({"quick_users": ["alice"], "default_user": "alice"}), encoding="utf-8")

        loaded = load_settings_from_path(settings_file)

    assert loaded.keyboard_shortcuts == default_shortcuts()


def test_load_settings_with_partial_shortcuts_merges_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        settings_file = Path(tmp) / "settings.json"
        settings_file.write_text(
            json.dumps({
                "quick_users": ["alice"],
                "default_user": "alice",
                "keyboard_shortcuts": {"refresh": "F6"},
            }),
            encoding="utf-8",
        )

        loaded = load_settings_from_path(settings_file)

    assert loaded.keyboard_shortcuts["refresh"] == "F6"
    # Other defaults remain.
    assert loaded.keyboard_shortcuts["edit"] == "F2"
    assert loaded.keyboard_shortcuts["open_command_palette"] == "Ctrl+P"


def test_action_order_is_stable():
    ids = [a for a, _l, _d in DEFAULT_ACTION_ORDER]
    # Spot-check that key actions exist exactly once.
    for action in ("open_command_palette", "edit", "delete", "select_all"):
        assert ids.count(action) == 1


# ---------------------------------------------------------------------------
# ShortcutManager (with a fake Tk root)
# ---------------------------------------------------------------------------


class _FakeRoot:
    def __init__(self) -> None:
        self.bound: dict[str, object] = {}
        self.unbound: list[str] = []

    def bind_all(self, sequence: str, handler):
        self.bound[sequence] = handler

    def unbind_all(self, sequence: str):
        self.unbound.append(sequence)
        self.bound.pop(sequence, None)


def test_shortcut_manager_registers_bindings():
    from ssh_manager_app.shortcuts import ShortcutAction, ShortcutManager

    root = _FakeRoot()
    manager = ShortcutManager(root)
    calls: list[str] = []
    manager.register(ShortcutAction("focus_search", "Suche", "Ctrl+F", lambda: calls.append("focus")))
    manager.load_bindings({"focus_search": "Ctrl+F"})
    assert "<Control-f>" in root.bound
    # Letter case variant also registered.
    assert "<Control-F>" in root.bound


def test_shortcut_manager_reapply_removes_old_bindings():
    from ssh_manager_app.shortcuts import ShortcutAction, ShortcutManager

    root = _FakeRoot()
    manager = ShortcutManager(root)
    manager.register(ShortcutAction("focus_search", "Suche", "Ctrl+F", lambda: None))
    manager.load_bindings({"focus_search": "Ctrl+F"})
    assert "<Control-f>" in root.bound
    manager.apply_bindings({"focus_search": "F3"})
    # Old binding removed, new one in place.
    assert "<Control-f>" not in root.bound
    assert "<F3>" in root.bound


def test_shortcut_manager_unbound_skips_registration():
    from ssh_manager_app.shortcuts import ShortcutAction, ShortcutManager

    root = _FakeRoot()
    manager = ShortcutManager(root)
    manager.register(ShortcutAction("focus_search", "Suche", "Ctrl+F", lambda: None))
    manager.load_bindings({"focus_search": ""})
    # Nothing bound because the user removed the shortcut.
    assert root.bound == {}
    assert manager.current_mapping()["focus_search"] == ""
