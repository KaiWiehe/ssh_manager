"""Tests for the command palette fuzzy matcher and mode parsing."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ssh_manager_app.palette import CommandPaletteItem, _parse_query, fuzzy_match, rank_items


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
