"""Command palette dialog and fuzzy matcher.

The palette pops up at the top of the main window (VSCode-style) and shows
sessions, commands, or both depending on the typed input.

Design split:

- :func:`fuzzy_match` / :func:`rank_items` are pure-Python helpers used in
  tests and consumed by the dialog.
- :class:`CommandPaletteItem` is the data structure the dialog renders.
- :class:`CommandPaletteDialog` is the actual Tk popup.
"""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Callable, Iterable, Sequence


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def fuzzy_match(query: str, candidate: str) -> tuple[int, list[int]] | None:
    """Return ``(score, positions)`` when every character of ``query`` appears
    in order inside ``candidate`` (case-insensitive).

    Higher score is better. ``positions`` is the list of matched indices in
    ``candidate`` so callers can highlight matches.
    """
    if not query:
        return (0, [])
    if not candidate:
        return None

    q = query.lower()
    c = candidate.lower()
    positions: list[int] = []
    j = 0
    score = 0
    last_index = -2
    consecutive = 0
    for i, ch in enumerate(c):
        if j >= len(q):
            break
        if ch == q[j]:
            positions.append(i)
            base = 10
            # Bonus for matching at start of string or after a separator.
            if i == 0:
                base += 35
            else:
                prev = c[i - 1]
                if not prev.isalnum() or prev in {" ", "/", "_", "-", "."}:
                    base += 20
            # Consecutive-character bonus.
            if i == last_index + 1:
                consecutive += 1
                base += 15 * consecutive
            else:
                consecutive = 0
            score += base
            last_index = i
            j += 1

    if j != len(q):
        return None
    # Shorter candidates score slightly higher to break ties.
    score += max(0, 30 - len(candidate))
    return score, positions


@dataclass
class CommandPaletteItem:
    id: str
    label: str
    subtitle: str = ""
    kind: str = "action"  # "action" or "session"
    callback: Callable[[], None] | None = None
    #: Used to remember recently-used items across palette opens.
    recent_score: int = 0


def rank_items(query: str, items: Sequence[CommandPaletteItem], *, limit: int = 50) -> list[tuple[CommandPaletteItem, list[int]]]:
    """Filter and rank ``items`` against ``query``.

    Returns ``[(item, label_positions), ...]`` sorted by best match first.
    When ``query`` is empty, items are ordered by ``recent_score`` (desc)
    then by label.
    """
    if not query:
        ordered = sorted(items, key=lambda it: (-it.recent_score, it.label.lower()))
        return [(item, []) for item in ordered[:limit]]

    scored: list[tuple[int, int, CommandPaletteItem, list[int]]] = []
    # tie-breaker uses the original index so ordering is stable.
    for index, item in enumerate(items):
        result = fuzzy_match(query, item.label)
        if result is None:
            # Try subtitle as fallback with a small penalty.
            sub_result = fuzzy_match(query, item.subtitle) if item.subtitle else None
            if sub_result is None:
                continue
            score, _positions = sub_result
            score -= 5
            positions: list[int] = []
        else:
            score, positions = result
        score += item.recent_score
        scored.append((-score, index, item, positions))

    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return [(item, positions) for _score, _idx, item, positions in scored[:limit]]


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class CommandPaletteDialog(tk.Toplevel):
    """Popup window that shows sessions and actions in a quick-open list."""

    PLACEHOLDER = "Tippen um zu suchen \u00b7 '>' f\u00fcr Befehle \u00b7 Enter zum Ausf\u00fchren \u00b7 Esc zum Schlie\u00dfen"

    def __init__(self, master, sessions: Sequence[CommandPaletteItem], actions: Sequence[CommandPaletteItem]):
        super().__init__(master)
        self._master = master
        self._sessions = list(sessions)
        self._actions = list(actions)
        self._ranked: list[tuple[CommandPaletteItem, list[int]]] = []

        self.withdraw()
        self.overrideredirect(True)
        self.transient(master)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass

        self._build()
        self._position()
        self.deiconify()
        try:
            self.grab_set()
        except tk.TclError:
            pass
        self._entry.focus_set()
        self._render(self._current_query())

    # ------------------------------------------------------------ build
    def _build(self) -> None:
        self.configure(background="#1f1f1f")
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        self._query_var = tk.StringVar(value="")
        self._entry = ttk.Entry(frame, textvariable=self._query_var, font=("Segoe UI", 12))
        self._entry.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 6))
        self._query_var.trace_add("write", lambda *_: self._on_query_changed())

        self._placeholder_label = ttk.Label(
            frame,
            text=self.PLACEHOLDER,
            foreground="#888888",
        )
        self._placeholder_label.grid(row=2, column=0, sticky="ew", padx=2, pady=(6, 0))

        list_wrap = ttk.Frame(frame)
        list_wrap.grid(row=1, column=0, sticky="nsew")
        list_wrap.columnconfigure(0, weight=1)
        list_wrap.rowconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            list_wrap,
            activestyle="dotbox",
            font=("Segoe UI", 11),
            height=12,
            borderwidth=0,
            highlightthickness=0,
            selectmode="browse",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)

        self._listbox.bind("<Return>", lambda _e: self._execute_selected())
        self._listbox.bind("<Double-Button-1>", lambda _e: self._execute_selected())
        self._entry.bind("<Return>", lambda _e: self._execute_selected())
        self._entry.bind("<Escape>", lambda _e: self.destroy())
        self._listbox.bind("<Escape>", lambda _e: self.destroy())
        self._entry.bind("<Down>", self._move_selection_down)
        self._entry.bind("<Up>", self._move_selection_up)
        self._listbox.bind("<Up>", self._move_selection_up)
        self._listbox.bind("<Down>", self._move_selection_down)

        self.bind("<FocusOut>", self._on_focus_out)

    def _position(self) -> None:
        self.update_idletasks()
        master = self._master
        try:
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
        except tk.TclError:
            mx, my, mw = 0, 0, 800
        target_w = max(540, min(mw - 80, 720))
        x = mx + (mw - target_w) // 2
        y = my + 60
        self.geometry(f"{target_w}x420+{x}+{y}")

    def _on_focus_out(self, event):
        # Skip when a child of the dialog took focus.
        focused = self.focus_get()
        if focused is None:
            self.destroy()
            return
        try:
            if str(focused).startswith(str(self)):
                return
        except Exception:
            pass
        self.destroy()

    # --------------------------------------------------------- rendering
    def _current_query(self) -> str:
        return self._query_var.get()

    def _on_query_changed(self) -> None:
        self._render(self._current_query())

    def _render(self, raw_query: str) -> None:
        query, mode = _parse_query(raw_query)
        if mode == "actions":
            pool = self._actions
        else:
            pool = list(self._sessions) + list(self._actions)
        ranked = rank_items(query, pool)
        self._ranked = ranked

        self._listbox.delete(0, "end")
        for item, _positions in ranked:
            marker = "\u26a1" if item.kind == "action" else "\u2192"
            line = f"  {marker}  {item.label}"
            if item.subtitle:
                line += f"   \u2014 {item.subtitle}"
            self._listbox.insert("end", line)
        if ranked:
            self._listbox.selection_set(0)
            self._listbox.activate(0)
        # Placeholder visibility.
        if raw_query.strip():
            self._placeholder_label.grid_remove()
        else:
            self._placeholder_label.grid()

    # ------------------------------------------------------ interaction
    def _move_selection_down(self, _event=None):
        if not self._ranked:
            return "break"
        cur = self._listbox.curselection()
        idx = (cur[0] + 1) if cur else 0
        idx = min(idx, len(self._ranked) - 1)
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.activate(idx)
        self._listbox.see(idx)
        return "break"

    def _move_selection_up(self, _event=None):
        if not self._ranked:
            return "break"
        cur = self._listbox.curselection()
        idx = (cur[0] - 1) if cur else 0
        idx = max(idx, 0)
        self._listbox.selection_clear(0, "end")
        self._listbox.selection_set(idx)
        self._listbox.activate(idx)
        self._listbox.see(idx)
        return "break"

    def _execute_selected(self):
        if not self._ranked:
            return "break"
        cur = self._listbox.curselection()
        idx = cur[0] if cur else 0
        item, _ = self._ranked[idx]
        self.destroy()
        if item.callback is not None:
            try:
                item.callback()
            except Exception:
                import traceback
                traceback.print_exc()
        return "break"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_query(raw: str) -> tuple[str, str]:
    """Return ``(actual_query, mode)``.

    ``mode`` is one of ``"all"`` or ``"actions"`` depending on the prefix.
    """
    text = (raw or "").lstrip()
    if text.startswith(">"):
        return text[1:].lstrip(), "actions"
    return text, "all"
