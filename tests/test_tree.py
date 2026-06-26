"""Regression tests for ``SessionTree`` helpers that don't need a real Tk root.

We exercise the methods as unbound functions against a lightweight fake ``self``
so the tests stay headless-friendly.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app import Session
from ssh_manager_app.tree import SessionTree


def _make_fake_tree(session: Session, *, item_id: str = "I001") -> MagicMock:
    """Build a stand-in for ``SessionTree`` good enough for ``set_session_color``."""
    fake = MagicMock(spec_set=[
        "_session_colors",
        "_item_to_session",
        "_tv",
        "_on_ui_state_changed",
        "_notify_ui_state_changed",
        "TAG_SESSION",
    ])
    fake._session_colors = {}
    fake._item_to_session = {item_id: session}
    fake._tv = MagicMock()
    fake._on_ui_state_changed = None
    fake._notify_ui_state_changed = MagicMock()
    fake.TAG_SESSION = SessionTree.TAG_SESSION
    return fake


def _session(key: str = "host:user") -> Session:
    return Session(key=key, display_name="Host", folder_path=[], hostname="host")


def test_set_session_color_with_hex_does_not_raise_unbound_local():
    """Regression: ``set_session_color`` previously shadowed the imported
    ``color_tag`` helper with a local variable, causing ``UnboundLocalError``.
    """
    session = _session()
    fake = _make_fake_tree(session)

    # Must not raise UnboundLocalError.
    SessionTree.set_session_color(fake, session.key, "#ff8800")

    assert fake._session_colors[session.key] == "#ff8800"
    # The tree row should have been updated with a tag tuple including a color tag.
    fake._tv.item.assert_called_once()
    _args, kwargs = fake._tv.item.call_args
    tags = kwargs.get("tags")
    assert tags is not None
    assert SessionTree.TAG_SESSION in tags
    # There must be a second tag (the generated color tag); its exact value comes
    # from the ``color_tag`` helper in models.
    assert len(tags) == 2
    assert tags[1]  # truthy color tag string
    fake._notify_ui_state_changed.assert_called_once()


def test_set_session_color_clearing_removes_color_and_skips_color_tag():
    session = _session()
    fake = _make_fake_tree(session)
    fake._session_colors[session.key] = "#abcdef"

    SessionTree.set_session_color(fake, session.key, None)

    assert session.key not in fake._session_colors
    _args, kwargs = fake._tv.item.call_args
    tags = kwargs.get("tags")
    # Only the base session tag, no color tag appended.
    assert tags == (SessionTree.TAG_SESSION,)
    fake._notify_ui_state_changed.assert_called_once()


def _make_open_state_tree() -> SessionTree:
    tree = object.__new__(SessionTree)
    tree._open_folders = set()
    tree._item_to_folder_key = {"folder-iid": "Prod/API"}
    tree._active_filter_query = ""
    tree._suppress_open_state_events = 0
    tree._on_ui_state_changed = MagicMock()
    tree._tv = MagicMock()
    return tree


def test_tree_open_event_updates_cached_folder_state():
    tree = _make_open_state_tree()
    event = MagicMock()
    event.widget.focus.return_value = "folder-iid"

    SessionTree._on_tree_folder_open_changed(tree, event, True)

    assert tree.get_open_folders() == {"Prod/API"}
    tree._on_ui_state_changed.assert_called_once()


def test_tree_close_event_updates_cached_folder_state():
    tree = _make_open_state_tree()
    tree._open_folders = {"Prod/API"}
    event = MagicMock()
    event.widget.focus.return_value = "folder-iid"

    SessionTree._on_tree_folder_open_changed(tree, event, False)

    assert tree.get_open_folders() == set()
    tree._on_ui_state_changed.assert_called_once()


def test_tree_open_events_are_ignored_during_search():
    tree = _make_open_state_tree()
    tree._active_filter_query = "prod"
    event = MagicMock()
    event.widget.focus.return_value = "folder-iid"

    SessionTree._on_tree_folder_open_changed(tree, event, True)

    assert tree.get_open_folders() == set()
    tree._on_ui_state_changed.assert_not_called()


def test_tree_open_events_are_ignored_during_programmatic_rebuild():
    tree = _make_open_state_tree()
    tree._suppress_open_state_events = 1
    event = MagicMock()
    event.widget.focus.return_value = "folder-iid"

    SessionTree._on_tree_folder_open_changed(tree, event, True)

    assert tree.get_open_folders() == set()
    tree._on_ui_state_changed.assert_not_called()


def test_filter_uses_temporary_open_state_for_active_search():
    session = Session("s1", "db-prod", ["Prod", "DB"], "db.example.com")
    tree = object.__new__(SessionTree)
    tree._sessions = [session]
    tree._active_filter_query = ""
    tree._pre_search_open_folders = None
    tree._open_folders = {"Prod"}
    tree._checked = {}
    tree._item_to_session = {}
    tree.populate = MagicMock()
    tree._notify_count = MagicMock()

    SessionTree.filter(tree, "db")

    assert tree._pre_search_open_folders == {"Prod"}
    tree.populate.assert_called_once_with(
        [session],
        open_folders={"Prod", "Prod/DB"},
        update_open_state=False,
    )
    assert tree.get_open_folders() == {"Prod"}
