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


class _NavigationTreeview:
    def __init__(self) -> None:
        self.children = {
            "": ["folder", "root-session"],
            "folder": ["child-session", "subfolder"],
            "subfolder": ["grandchild-session"],
        }
        self.parents = {
            "folder": "",
            "root-session": "",
            "child-session": "folder",
            "subfolder": "folder",
            "grandchild-session": "subfolder",
        }
        self.open = {"folder": True, "subfolder": False}
        self.focus_id = "folder"
        self.selected: tuple[str, ...] = ()
        self.seen: list[str] = []

    def focus(self, item_id=None):
        if item_id is not None:
            self.focus_id = item_id
        return self.focus_id

    def selection_set(self, item_id):
        self.selected = (item_id,)

    def see(self, item_id):
        self.seen.append(item_id)

    def get_children(self, item_id=""):
        return tuple(self.children.get(item_id, ()))

    def parent(self, item_id):
        return self.parents.get(item_id, "")

    def next(self, item_id):
        siblings = self.children.get(self.parent(item_id), [])
        index = siblings.index(item_id)
        return siblings[index + 1] if index + 1 < len(siblings) else ""

    def prev(self, item_id):
        siblings = self.children.get(self.parent(item_id), [])
        index = siblings.index(item_id)
        return siblings[index - 1] if index else ""

    def item(self, item_id, option=None, **kwargs):
        if "open" in kwargs:
            self.open[item_id] = kwargs["open"]
        if option == "open":
            return self.open.get(item_id, False)
        return {}

    def bbox(self, _item_id):
        return (10, 40, 300, 22)

    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 200


def _make_navigation_tree() -> SessionTree:
    tree = object.__new__(SessionTree)
    tree._tv = _NavigationTreeview()
    tree._item_to_folder_key = {"folder": "Prod", "subfolder": "Prod/API"}
    tree._item_to_session = {
        "root-session": Session("root", "Root", [], "root.example"),
        "child-session": Session("child", "Child", ["Prod"], "child.example"),
        "grandchild-session": Session("grandchild", "Grandchild", ["Prod", "API"], "grandchild.example"),
    }
    tree._checked = {item_id: False for item_id in tree._item_to_session}
    tree._open_folders = {"Prod"}
    tree._active_filter_query = ""
    tree._suppress_open_state_events = 0
    tree._on_ui_state_changed = MagicMock()
    tree._on_selection_changed = MagicMock()
    tree._on_quick_connect = MagicMock()
    tree._img_checked = "checked"
    tree._img_unchecked = "unchecked"
    return tree


def test_visible_navigation_walks_expanded_rows_and_skips_collapsed_children():
    tree = _make_navigation_tree()

    assert tree._next_visible_item("folder") == "child-session"
    assert tree._next_visible_item("subfolder") == "root-session"
    assert tree._previous_visible_item("root-session") == "subfolder"

    tree._tv.open["subfolder"] = True
    assert tree._previous_visible_item("root-session") == "grandchild-session"


def test_right_opens_folder_then_moves_to_first_child_and_persists_state():
    tree = _make_navigation_tree()
    tree._tv.open["folder"] = False
    tree._open_folders.clear()

    assert tree._on_key_right(MagicMock()) == "break"
    assert tree._tv.open["folder"] is True
    assert tree.get_open_folders() == {"Prod"}
    tree._on_ui_state_changed.assert_called_once_with()

    tree._on_key_right(MagicMock())
    assert tree._tv.focus_id == "child-session"
    assert tree._tv.selected == ("child-session",)


def test_left_closes_open_folder_or_moves_to_parent():
    tree = _make_navigation_tree()

    tree._on_key_left(MagicMock())
    assert tree._tv.open["folder"] is False
    assert tree.get_open_folders() == set()

    tree._tv.focus_id = "child-session"
    tree._on_key_left(MagicMock())
    assert tree._tv.focus_id == "folder"


def test_enter_toggles_folder_and_quick_connects_only_focused_session():
    tree = _make_navigation_tree()

    tree.activate_focused()
    assert tree._tv.open["folder"] is False
    tree._on_quick_connect.assert_not_called()

    tree._tv.focus_id = "child-session"
    tree.activate_focused()
    tree._on_quick_connect.assert_called_once_with(tree._item_to_session["child-session"])


def test_space_toggles_session_and_entire_folder_with_mixed_state():
    tree = _make_navigation_tree()
    tree._tv.focus_id = "child-session"

    assert tree._on_key_space(MagicMock()) == "break"
    assert tree._checked["child-session"] is True

    tree._tv.focus_id = "folder"
    tree._on_key_space(MagicMock())
    assert tree._checked["child-session"] is True
    assert tree._checked["grandchild-session"] is True
    assert tree._checked["root-session"] is False
    tree._on_key_space(MagicMock())
    assert tree._checked["child-session"] is False
    assert tree._checked["grandchild-session"] is False
    assert tree._checked["root-session"] is False


def test_focus_restore_uses_stable_identity_and_falls_back_when_hidden():
    tree = _make_navigation_tree()

    tree._restore_focus_identity(("session", "child", "Prod"))
    assert tree._tv.focus_id == "child-session"

    tree._tv.open["folder"] = False
    tree._restore_focus_identity(("session", "child", "Prod"))
    assert tree._tv.focus_id == "folder"


def test_keyboard_context_menu_routes_to_focused_row_coordinates():
    tree = _make_navigation_tree()
    tree._show_folder_menu = MagicMock()
    tree._show_session_menu = MagicMock()

    assert tree._on_key_context_menu(MagicMock()) == "break"
    tree._show_folder_menu.assert_called_once_with("folder", x_root=210, y_root=262)

    tree._tv.focus_id = "child-session"
    tree._on_key_context_menu(MagicMock())
    tree._show_session_menu.assert_called_once_with("child-session", x_root=210, y_root=262)


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
