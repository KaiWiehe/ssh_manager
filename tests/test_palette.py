"""Tests for the command palette fuzzy matcher and mode parsing."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock

import tkinter as tk

from ssh_manager_app.palette import (
    CommandPaletteDialog,
    CommandPaletteItem,
    _parse_query,
    fuzzy_match,
    rank_items,
)


# ---------------------------------------------------------------------------
# fuzzy_match
# ---------------------------------------------------------------------------


def test_fuzzy_match_simple():
    result = fuzzy_match("ssh", "Open SSH")
    assert result is not None
    score, positions = result
    assert score > 0
    # Returns the indices where the matched characters live.
    assert all(0 <= p < len("Open SSH") for p in positions)


def test_fuzzy_match_initials_pattern():
    result = fuzzy_match("stsv", "Start Server")
    assert result is not None


def test_fuzzy_match_out_of_order_returns_none():
    assert fuzzy_match("baz", "abz") is None


def test_fuzzy_match_empty_query_returns_zero_score():
    result = fuzzy_match("", "anything")
    assert result == (0, [])


def test_fuzzy_match_case_insensitive():
    assert fuzzy_match("CTRL", "ctrl+p") is not None


def test_fuzzy_match_prefix_scores_higher_than_middle():
    head = fuzzy_match("ser", "server")
    middle = fuzzy_match("ser", "edit serial")
    assert head is not None and middle is not None
    head_score, _ = head
    middle_score, _ = middle
    assert head_score > middle_score


def test_fuzzy_match_consecutive_better_than_split():
    cons = fuzzy_match("conn", "connect")
    split = fuzzy_match("conn", "c o n n")
    assert cons is not None and split is not None
    cs, _ = cons
    ss, _ = split
    assert cs > ss


# ---------------------------------------------------------------------------
# rank_items
# ---------------------------------------------------------------------------


def _make_items(*names: str, kind: str = "action") -> list[CommandPaletteItem]:
    return [CommandPaletteItem(id=f"id:{n}", label=n, kind=kind) for n in names]


def test_rank_items_filters_non_matches():
    items = _make_items("Verbinden", "Bearbeiten", "Löschen", "Refresh")
    results = rank_items("brb", items)
    labels = [item.label for item, _ in results]
    assert "Bearbeiten" in labels
    # 'brb' should not match unrelated items.
    assert "Refresh" not in labels


def test_rank_items_orders_by_score():
    items = _make_items("Start Server", "Storage Sweep", "Verbinden")
    results = rank_items("stsv", items)
    assert results, "Expected at least one match"
    # "Start Server" has the cleaner initials sequence than "Storage Sweep".
    top_label = results[0][0].label
    assert top_label == "Start Server"


def test_rank_items_empty_query_uses_recent_score():
    items = [
        CommandPaletteItem("a", "Alpha", recent_score=0),
        CommandPaletteItem("b", "Bravo", recent_score=100),
        CommandPaletteItem("c", "Charlie", recent_score=50),
    ]
    results = rank_items("", items)
    labels = [item.label for item, _ in results]
    assert labels[0] == "Bravo"
    assert labels[1] == "Charlie"
    assert labels[2] == "Alpha"


def test_rank_items_respects_limit():
    items = _make_items(*[f"Item {i}" for i in range(200)])
    results = rank_items("item", items, limit=25)
    assert len(results) == 25


def test_rank_items_matches_subtitle_fallback():
    items = [CommandPaletteItem("a", "Beta", subtitle="ssh user@example.com")]
    results = rank_items("ssh", items)
    assert results, "Subtitle should be considered as fallback"


# ---------------------------------------------------------------------------
# Mode parsing
# ---------------------------------------------------------------------------


def test_parse_query_default_mode():
    assert _parse_query("hello") == ("hello", "all")


def test_parse_query_actions_mode():
    assert _parse_query(">refresh") == ("refresh", "actions")
    assert _parse_query("  >  edit ") == ("edit ", "actions")


def test_parse_query_empty():
    assert _parse_query("") == ("", "all")
    assert _parse_query(">") == ("", "actions")


# ---------------------------------------------------------------------------
# Mixed-mode behaviour
# ---------------------------------------------------------------------------


def test_actions_mode_excludes_sessions_via_separate_pool():
    """Simulate the dialog's mode behaviour by calling rank_items only on
    actions when the user typed '>' prefix."""
    sessions = _make_items("server-prod", "server-dev", kind="session")
    actions = _make_items("Refresh", "Settings", kind="action")
    query, mode = _parse_query(">set")
    pool = actions if mode == "actions" else (sessions + actions)
    results = rank_items(query, pool)
    labels = [item.label for item, _ in results]
    assert "Settings" in labels
    assert "server-prod" not in labels


def test_default_mode_mixes_sessions_and_actions():
    sessions = _make_items("server-prod", kind="session")
    actions = _make_items("Refresh", kind="action")
    query, mode = _parse_query("r")
    pool = actions if mode == "actions" else (sessions + actions)
    results = rank_items(query, pool)
    kinds = {item.kind for item, _ in results}
    # Both kinds should appear because pool was mixed.
    assert kinds == {"session", "action"}


# ---------------------------------------------------------------------------
# Dialog teardown / grab release (regression for "UI frozen after Strg+P")
# ---------------------------------------------------------------------------


def _make_fake_dialog():
    """Build a stand-in for ``CommandPaletteDialog`` good enough for the
    teardown-related methods. We treat the unbound methods on the class as
    plain functions and pass our fake as ``self``.
    """
    fake = MagicMock()
    fake._closing = False
    fake._master = MagicMock()
    # We want to observe the call order across these methods.
    fake._mock_order = []

    def _record(name):
        def _inner(*args, **kwargs):
            fake._mock_order.append(name)
        return _inner

    fake.unbind.side_effect = _record("unbind")
    fake.grab_release.side_effect = _record("grab_release")
    fake._master.focus_set.side_effect = _record("master_focus_set")
    fake.destroy.side_effect = _record("destroy")
    return fake


def test_close_releases_grab_restores_focus_then_destroys():
    """``_close`` must release the Tk grab and hand focus back to the main
    window BEFORE destroying the popup, otherwise the main window stays
    frozen for a few seconds after running a palette action."""
    fake = _make_fake_dialog()

    CommandPaletteDialog._close(fake)

    assert fake._closing is True
    fake.unbind.assert_called_once_with("<FocusOut>")
    fake.grab_release.assert_called_once()
    fake._master.focus_set.assert_called_once()
    fake.destroy.assert_called_once()
    # Order matters: unbind -> grab_release -> master focus -> destroy.
    assert fake._mock_order == ["unbind", "grab_release", "master_focus_set", "destroy"]


def test_close_is_idempotent():
    fake = _make_fake_dialog()
    CommandPaletteDialog._close(fake)
    CommandPaletteDialog._close(fake)
    # Only the first invocation should reach destroy()/grab_release().
    assert fake.destroy.call_count == 1
    assert fake.grab_release.call_count == 1


def test_close_still_releases_grab_when_destroy_raises():
    fake = _make_fake_dialog()
    fake.destroy.side_effect = tk.TclError("boom")
    # Must not propagate; grab_release must still have happened.
    CommandPaletteDialog._close(fake)
    fake.grab_release.assert_called_once()
    fake._master.focus_set.assert_called_once()


def _wire_real_close(fake):
    """Bind the real ``_close`` to the fake so ``_execute_selected`` triggers
    the actual teardown logic instead of a MagicMock no-op."""
    fake._close.side_effect = lambda: CommandPaletteDialog._close(fake)


def test_execute_selected_closes_popup_before_running_callback():
    """Regression: previously the dialog called ``self.destroy()`` and then ran
    the action inline. With the leftover grab still being torn down by Tk this
    could freeze input on the main window. The fix closes the popup first and
    schedules the callback via ``after_idle`` so Tk fully releases the grab
    before the action runs."""
    callback = MagicMock()
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    fake._listbox = MagicMock()
    fake._listbox.curselection.return_value = (0,)
    fake._ranked = [(CommandPaletteItem(id="x", label="Alles auswählen", callback=callback), [])]

    # ``after_idle`` should be invoked with the callback wrapper.
    scheduled = []
    fake._master.after_idle.side_effect = lambda fn: scheduled.append(fn)

    result = CommandPaletteDialog._execute_selected(fake)

    assert result == "break"
    # Popup teardown happened before scheduling the action.
    fake.destroy.assert_called_once()
    fake._master.focus_set.assert_called_once()
    fake.grab_release.assert_called_once()
    # _close ran before after_idle was used to schedule the action.
    assert fake._mock_order == ["unbind", "grab_release", "master_focus_set", "destroy"]
    # The callback was NOT invoked synchronously; it's deferred.
    callback.assert_not_called()
    assert len(scheduled) == 1
    # Running the scheduled wrapper invokes the user callback.
    scheduled[0]()
    callback.assert_called_once()


def test_execute_selected_swallows_callback_exception():
    bad = MagicMock(side_effect=RuntimeError("kaboom"))
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    fake._listbox = MagicMock()
    fake._listbox.curselection.return_value = (0,)
    fake._ranked = [(CommandPaletteItem(id="x", label="x", callback=bad), [])]
    scheduled = []
    fake._master.after_idle.side_effect = lambda fn: scheduled.append(fn)

    CommandPaletteDialog._execute_selected(fake)
    # Running the deferred wrapper must not propagate the exception.
    scheduled[0]()
    bad.assert_called_once()


def test_focus_out_no_ops_when_closing_in_progress():
    """If the programmatic close path already started, a stray FocusOut event
    must not trigger a second ``_close``/``destroy`` cycle."""
    fake = _make_fake_dialog()
    fake._closing = True

    CommandPaletteDialog._on_focus_out(fake, MagicMock())

    fake.destroy.assert_not_called()
    fake.grab_release.assert_not_called()
