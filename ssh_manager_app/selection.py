"""Target policy shared by keyboard and palette actions."""
from __future__ import annotations


def single_action_target(tree):
    """One checked host wins; without checks use the focused connection.

    A multi-host selection must never silently choose a different single host.
    Context menus explicitly label their own row and keep using that row.
    """
    selected = tree.get_selected_sessions()
    if len(selected) == 1:
        return selected[0]
    if selected:
        return None
    return tree.get_single_context_session()
