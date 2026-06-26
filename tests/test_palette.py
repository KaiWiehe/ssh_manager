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
    DEFAULT_PALETTE_WIDTH,
    MIN_PALETTE_WIDTH,
    _PaletteTooltip,
    _parse_query,
    clamp_palette_width,
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


def _make_fake_dialog(*, on_width_changed=None, current_width=DEFAULT_PALETTE_WIDTH):
    """Build a stand-in for ``CommandPaletteDialog`` good enough for the
    teardown-related methods. We treat the unbound methods on the class as
    plain functions and pass our fake as ``self``.
    """
    fake = MagicMock()
    fake._closing = False
    fake._master = MagicMock()
    fake._tooltip = None
    fake._focus_check_id = None
    fake._resize_drag = None
    fake._on_width_changed = on_width_changed
    fake._current_width = current_width
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
    # We now unbind both <FocusOut> and <Unmap>.
    unbound_events = [c.args[0] for c in fake.unbind.call_args_list]
    assert "<FocusOut>" in unbound_events
    assert "<Unmap>" in unbound_events
    fake.grab_release.assert_called_once()
    fake._master.focus_set.assert_called_once()
    fake.destroy.assert_called_once()
    # Order matters: unbind(s) -> grab_release -> master focus -> destroy.
    assert fake._mock_order == [
        "unbind",
        "unbind",
        "grab_release",
        "master_focus_set",
        "destroy",
    ]


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
    assert fake._mock_order == [
        "unbind",
        "unbind",
        "grab_release",
        "master_focus_set",
        "destroy",
    ]
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


# ---------------------------------------------------------------------------
# OS-level focus-out / app switch handling
# ---------------------------------------------------------------------------


def test_focus_out_schedules_deferred_check():
    """``<FocusOut>`` must not close synchronously - a Tk-internal popup
    (combobox dropdown, native dialog) briefly steals focus and we'd close
    too aggressively. Instead we schedule a deferred ``_check_focus_lost``.
    """
    fake = _make_fake_dialog()
    fake._focus_check_id = None
    fake.after.return_value = "after#1"

    CommandPaletteDialog._on_focus_out(fake, MagicMock())

    fake.after.assert_called_once()
    delay = fake.after.call_args.args[0]
    assert 0 < delay <= 200, "deferred check delay should be short"
    assert fake._focus_check_id == "after#1"
    # And we did NOT close synchronously.
    fake.destroy.assert_not_called()


def test_focus_out_skips_when_check_already_scheduled():
    fake = _make_fake_dialog()
    fake._focus_check_id = "already-pending"

    CommandPaletteDialog._on_focus_out(fake, MagicMock())

    fake.after.assert_not_called()


def test_focus_out_skips_during_resize_drag():
    """While the user drags an edge handle, focus briefly shifts. Don't close."""
    fake = _make_fake_dialog()
    fake._resize_drag = {"side": "right", "start_x_root": 0, "start_width": 720}

    CommandPaletteDialog._on_focus_out(fake, MagicMock())

    fake.after.assert_not_called()
    fake.destroy.assert_not_called()


def test_check_focus_lost_closes_when_no_widget_owns_focus():
    """``focus_displayof()`` returning ``None`` means no widget in our Tk
    application owns focus -> user switched to another OS-level window."""
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    fake.focus_displayof.return_value = None

    CommandPaletteDialog._check_focus_lost(fake)

    fake.destroy.assert_called_once()


def test_check_focus_lost_keeps_open_for_internal_focus():
    """When focus moved to the popup itself (or a child), stay open."""
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    # ``str(self)`` on a MagicMock is something like ``"<MagicMock id=...>"``
    # which is fine for the prefix check as long as focus_displayof returns
    # the same path.
    fake.__str__ = lambda self: ".palette"
    child = MagicMock()
    child.__str__ = lambda self: ".palette.entry"
    fake.focus_displayof.return_value = child

    CommandPaletteDialog._check_focus_lost(fake)

    fake.destroy.assert_not_called()


def test_check_focus_lost_closes_when_other_toplevel_focused():
    """If focus jumped to a sibling widget (e.g. main window), close."""
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    fake.__str__ = lambda self: ".palette"
    other = MagicMock()
    other.__str__ = lambda self: ".main.tree"
    fake.focus_displayof.return_value = other

    CommandPaletteDialog._check_focus_lost(fake)

    fake.destroy.assert_called_once()


def test_unmap_event_closes_popup():
    """Unmap on the toplevel (minimize / desktop switch) should close."""
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    event = MagicMock()
    event.widget = fake

    CommandPaletteDialog._on_unmap(fake, event)

    fake.destroy.assert_called_once()


def test_unmap_event_skipped_when_closing():
    fake = _make_fake_dialog()
    fake._closing = True

    CommandPaletteDialog._on_unmap(fake, MagicMock())

    fake.destroy.assert_not_called()


def test_unmap_event_from_child_widget_does_not_close_popup():
    """Typing the first query hides the placeholder label via grid_remove(),
    which emits an Unmap event for that child widget. The palette must stay
    open and only close when the Toplevel itself is unmapped.
    """
    fake = _make_fake_dialog()
    _wire_real_close(fake)
    event = MagicMock()
    event.widget = MagicMock()

    CommandPaletteDialog._on_unmap(fake, event)

    fake.destroy.assert_not_called()


# ---------------------------------------------------------------------------
# Width clamping / persistence
# ---------------------------------------------------------------------------


def test_clamp_palette_width_enforces_min():
    assert clamp_palette_width(100) == MIN_PALETTE_WIDTH
    assert clamp_palette_width(MIN_PALETTE_WIDTH) == MIN_PALETTE_WIDTH


def test_clamp_palette_width_enforces_max_when_master_known():
    # 90% of 1000 = 900 -> input of 2000 clamps to 900.
    assert clamp_palette_width(2000, master_width=1000) == 900


def test_clamp_palette_width_no_master_only_lower_bound():
    assert clamp_palette_width(5000, master_width=None) == 5000


def test_clamp_palette_width_handles_garbage():
    # ``None`` / strings fall back to DEFAULT, then clamp.
    assert clamp_palette_width("nope") == DEFAULT_PALETTE_WIDTH
    assert clamp_palette_width(None) == DEFAULT_PALETTE_WIDTH


def test_close_persists_width_via_callback():
    """On close the dialog calls ``on_width_changed`` exactly once with the
    current width so settings get written without spamming on every resize.
    """
    saved = []
    fake = _make_fake_dialog(on_width_changed=saved.append, current_width=614)

    CommandPaletteDialog._close(fake)

    assert saved == [614]


def test_close_swallows_persistence_errors():
    """Settings persistence must not break the close path."""
    def explode(_w):
        raise RuntimeError("disk full")
    fake = _make_fake_dialog(on_width_changed=explode)

    # Must not raise.
    CommandPaletteDialog._close(fake)
    fake.destroy.assert_called_once()


def test_close_skips_persistence_when_no_callback():
    fake = _make_fake_dialog(on_width_changed=None)
    # Should not throw.
    CommandPaletteDialog._close(fake)
    fake.destroy.assert_called_once()


# ---------------------------------------------------------------------------
# Resize drag logic
# ---------------------------------------------------------------------------


def test_begin_resize_records_drag_state():
    fake = _make_fake_dialog(current_width=700)
    fake.winfo_width.return_value = 700
    fake._tooltip = MagicMock()
    event = MagicMock(x_root=500)

    CommandPaletteDialog._begin_resize(fake, event, "right")

    assert fake._resize_drag == {
        "side": "right",
        "start_x_root": 500,
        "start_width": 700,
    }
    # Tooltip is hidden when a resize starts.
    fake._tooltip.hide.assert_called_once()


def test_do_resize_right_side_grows_with_positive_delta():
    fake = _make_fake_dialog(current_width=700)
    fake._resize_drag = {"side": "right", "start_x_root": 500, "start_width": 700}
    fake._master.winfo_width.return_value = 2000
    fake._master.winfo_rootx.return_value = 100
    fake._master.winfo_rooty.return_value = 50
    fake.winfo_height.return_value = 420
    event = MagicMock(x_root=560)  # +60px

    CommandPaletteDialog._do_resize(fake, event)

    assert fake._current_width == 760
    fake.geometry.assert_called_once()
    geom = fake.geometry.call_args.args[0]
    assert geom.startswith("760x420+")


def test_do_resize_left_side_grows_with_negative_delta():
    fake = _make_fake_dialog(current_width=700)
    fake._resize_drag = {"side": "left", "start_x_root": 500, "start_width": 700}
    fake._master.winfo_width.return_value = 2000
    fake._master.winfo_rootx.return_value = 100
    fake._master.winfo_rooty.return_value = 50
    fake.winfo_height.return_value = 420
    event = MagicMock(x_root=440)  # -60px on x_root, but left side grows.

    CommandPaletteDialog._do_resize(fake, event)

    assert fake._current_width == 760


def test_do_resize_clamps_to_min():
    fake = _make_fake_dialog(current_width=700)
    fake._resize_drag = {"side": "right", "start_x_root": 500, "start_width": 700}
    fake._master.winfo_width.return_value = 2000
    fake._master.winfo_rootx.return_value = 100
    fake._master.winfo_rooty.return_value = 50
    fake.winfo_height.return_value = 420
    event = MagicMock(x_root=0)  # huge negative delta

    CommandPaletteDialog._do_resize(fake, event)

    assert fake._current_width == MIN_PALETTE_WIDTH


def test_do_resize_noop_without_active_drag():
    fake = _make_fake_dialog(current_width=700)
    fake._resize_drag = None
    CommandPaletteDialog._do_resize(fake, MagicMock(x_root=999))
    assert fake._current_width == 700
    fake.geometry.assert_not_called()


def test_end_resize_clears_drag_state():
    fake = _make_fake_dialog()
    fake._resize_drag = {"side": "right", "start_x_root": 0, "start_width": 700}
    CommandPaletteDialog._end_resize(fake, MagicMock())
    assert fake._resize_drag is None


# ---------------------------------------------------------------------------
# Tooltip helper
# ---------------------------------------------------------------------------


def test_tooltip_schedule_calls_master_after_with_delay():
    master = MagicMock()
    master.after.return_value = "after#42"
    tip = _PaletteTooltip(master)

    tip.schedule(3, "hello\nsubtitle", x=100, y=200)

    master.after.assert_called_once()
    assert master.after.call_args.args[0] == _PaletteTooltip.DELAY_MS
    assert tip._after_id == "after#42"
    assert tip._current_index == 3


def test_tooltip_schedule_same_index_when_visible_is_noop():
    master = MagicMock()
    master.after.return_value = "after#1"
    tip = _PaletteTooltip(master)
    tip._current_index = 3
    tip._toplevel = MagicMock()  # simulate already visible

    tip.schedule(3, "text", x=0, y=0)

    master.after.assert_not_called()


def test_tooltip_schedule_different_index_cancels_previous_timer():
    master = MagicMock()
    master.after.side_effect = ["after#1", "after#2"]
    tip = _PaletteTooltip(master)

    tip.schedule(1, "a", x=0, y=0)
    tip.schedule(2, "b", x=0, y=0)

    master.after_cancel.assert_called_once_with("after#1")
    assert tip._current_index == 2


def test_tooltip_hide_cancels_pending_timer():
    master = MagicMock()
    master.after.return_value = "after#1"
    tip = _PaletteTooltip(master)
    tip.schedule(0, "x", x=0, y=0)

    tip.hide()

    master.after_cancel.assert_called_once_with("after#1")
    assert tip._after_id is None
    assert tip._current_index is None


def test_tooltip_show_skips_when_index_changed():
    """If schedule() was called again before the timer fired, the stale show
    must NOT create a Toplevel."""
    master = MagicMock()
    tip = _PaletteTooltip(master)
    tip._current_index = 5  # newer schedule
    tip._show(index=3, text="stale", x=0, y=0)
    assert tip._toplevel is None


# ---------------------------------------------------------------------------
# Listbox motion -> tooltip wiring
# ---------------------------------------------------------------------------


def test_on_list_motion_schedules_tooltip_with_label_and_subtitle():
    fake = _make_fake_dialog()
    item = CommandPaletteItem(id="x", label="very long connection name", subtitle="user@host")
    fake._ranked = [(item, [])]
    fake._tooltip = MagicMock()
    fake._listbox = MagicMock()
    fake._listbox.nearest.return_value = 0
    fake._listbox.bbox.return_value = (0, 10, 200, 20)  # row spans y=10..30
    event = MagicMock(y=20, x_root=500, y_root=300)

    CommandPaletteDialog._on_list_motion(fake, event)

    fake._tooltip.schedule.assert_called_once()
    args, kwargs = fake._tooltip.schedule.call_args
    # schedule(index, text, x_root, y_root) positional.
    assert args[0] == 0
    text = args[1]
    assert "very long connection name" in text
    assert "user@host" in text


def test_on_list_motion_hides_when_outside_row_bbox():
    fake = _make_fake_dialog()
    item = CommandPaletteItem(id="x", label="a", subtitle="")
    fake._ranked = [(item, [])]
    fake._tooltip = MagicMock()
    fake._listbox = MagicMock()
    fake._listbox.nearest.return_value = 0
    fake._listbox.bbox.return_value = (0, 10, 200, 20)
    # y below the row bbox
    event = MagicMock(y=100, x_root=0, y_root=0)

    CommandPaletteDialog._on_list_motion(fake, event)

    fake._tooltip.hide.assert_called_once()
    fake._tooltip.schedule.assert_not_called()


def test_on_list_motion_noop_when_no_items():
    fake = _make_fake_dialog()
    fake._ranked = []
    fake._tooltip = MagicMock()
    CommandPaletteDialog._on_list_motion(fake, MagicMock(y=0, x_root=0, y_root=0))
    fake._tooltip.schedule.assert_not_called()
    fake._tooltip.hide.assert_not_called()


def test_render_hides_tooltip():
    """When the visible list changes, any visible tooltip must disappear."""
    fake = _make_fake_dialog()
    fake._sessions = []
    fake._actions = []
    fake._listbox = MagicMock()
    fake._placeholder_label = MagicMock()
    fake._tooltip = MagicMock()

    CommandPaletteDialog._render(fake, "")

    fake._tooltip.hide.assert_called_once()

