"""Command palette dialog and fuzzy matcher.

The palette pops up at the top of the main window (VSCode-style) and shows
sessions, commands, or both depending on the typed input.

Design split:

- :func:`fuzzy_match` / :func:`rank_items` are pure-Python helpers used in
  tests and consumed by the dialog.
- :class:`CommandPaletteItem` is the data structure the dialog renders.
- :class:`CommandPaletteDialog` is the actual Tk popup.
- :class:`_PaletteTooltip` is a tiny tooltip helper used to show the full
  label + subtitle when the user hovers a list entry whose text is wider
  than the visible row.
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
# Width-persistence helpers
# ---------------------------------------------------------------------------


#: Constraints for the user-adjustable palette width.
MIN_PALETTE_WIDTH = 400
DEFAULT_PALETTE_WIDTH = 720


def clamp_palette_width(width: int, master_width: int | None = None) -> int:
    """Clamp ``width`` to ``[MIN_PALETTE_WIDTH, 0.9 * master_width]``.

    ``master_width`` may be ``None`` (or a too-small value) when the master
    window has not been fully laid out yet; in that case only the lower bound
    is enforced.
    """
    try:
        value = int(width)
    except (TypeError, ValueError):
        value = DEFAULT_PALETTE_WIDTH
    if value < MIN_PALETTE_WIDTH:
        value = MIN_PALETTE_WIDTH
    if master_width and master_width > MIN_PALETTE_WIDTH:
        upper = max(MIN_PALETTE_WIDTH, int(master_width * 0.9))
        if value > upper:
            value = upper
    return value


# ---------------------------------------------------------------------------
# Tooltip helper
# ---------------------------------------------------------------------------


class _PaletteTooltip:
    """Borderless Toplevel that shows the full label + subtitle of a row.

    The tooltip is created lazily and tracks the *currently hovered* index so
    repeated hover events on the same row are no-ops. Mouse leave or palette
    close calls :meth:`hide`.
    """

    DELAY_MS = 500

    def __init__(self, master: tk.Misc):
        self._master = master
        self._toplevel: tk.Toplevel | None = None
        self._after_id: str | None = None
        self._current_index: int | None = None

    def schedule(self, index: int, text: str, x: int, y: int) -> None:
        """Schedule showing the tooltip for ``index`` after a short delay.

        Calling :meth:`schedule` with a new ``index`` cancels any pending
        timer for a previous row.
        """
        if self._current_index == index and self._toplevel is not None:
            # Already visible for this row.
            return
        self.hide()
        self._current_index = index
        try:
            self._after_id = self._master.after(
                self.DELAY_MS,
                lambda idx=index, t=text, xx=x, yy=y: self._show(idx, t, xx, yy),
            )
        except tk.TclError:
            self._after_id = None

    def hide(self) -> None:
        """Cancel any pending show and destroy the tooltip if visible."""
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._toplevel is not None:
            try:
                self._toplevel.destroy()
            except tk.TclError:
                pass
            self._toplevel = None
        self._current_index = None

    def _show(self, index: int, text: str, x: int, y: int) -> None:
        # Race-guard: schedule() may have been called again with a different
        # index between the timer firing and Tk dispatching us.
        if self._current_index != index:
            return
        self._after_id = None
        try:
            tip = tk.Toplevel(self._master)
        except tk.TclError:
            self._toplevel = None
            return
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            tip,
            text=text,
            justify="left",
            background="#fff8dc",
            foreground="#1f1f1f",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=6,
            wraplength=520,
        )
        label.pack()
        tip.geometry(f"+{x + 14}+{y + 18}")
        self._toplevel = tip


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class CommandPaletteDialog(tk.Toplevel):
    """Popup window that shows sessions and actions in a quick-open list."""

    PLACEHOLDER = "Tippen um zu suchen \u00b7 '>' f\u00fcr Befehle \u00b7 Enter zum Ausf\u00fchren \u00b7 Esc zum Schlie\u00dfen"

    #: Width of the invisible resize-handle strip on each side of the popup.
    _RESIZE_HANDLE_PX = 4

    def __init__(
        self,
        master,
        sessions: Sequence[CommandPaletteItem],
        actions: Sequence[CommandPaletteItem],
        *,
        initial_width: int | None = None,
        on_width_changed: Callable[[int], None] | None = None,
    ):
        super().__init__(master)
        self._master = master
        self._sessions = list(sessions)
        self._actions = list(actions)
        self._ranked: list[tuple[CommandPaletteItem, list[int]]] = []
        # True once the popup has begun tearing itself down; guards against the
        # ``<FocusOut>`` handler racing with the programmatic close path.
        self._closing = False
        # Width persistence: ``_on_width_changed`` is called exactly once at
        # close time with the final width so we don't spam the settings file
        # on every resize event.
        self._on_width_changed = on_width_changed
        self._current_width = clamp_palette_width(
            initial_width if initial_width is not None else DEFAULT_PALETTE_WIDTH
        )
        # Bookkeeping for manual edge-drag resize.
        self._resize_drag: dict | None = None
        # Tooltip helper - lazy created in :meth:`_build`.
        self._tooltip: _PaletteTooltip | None = None
        # Deferred OS-level focus-out check.
        self._focus_check_id: str | None = None

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

        # Outer container hosts left/right resize handles + the actual content
        # frame in the middle.
        outer = tk.Frame(self, background="#1f1f1f", bd=0, highlightthickness=0)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(0, weight=1)

        self._left_handle = tk.Frame(
            outer,
            width=self._RESIZE_HANDLE_PX,
            background="#1f1f1f",
            cursor="sb_h_double_arrow",
        )
        self._left_handle.grid(row=0, column=0, sticky="ns")
        self._right_handle = tk.Frame(
            outer,
            width=self._RESIZE_HANDLE_PX,
            background="#1f1f1f",
            cursor="sb_h_double_arrow",
        )
        self._right_handle.grid(row=0, column=2, sticky="ns")
        for handle, side in ((self._left_handle, "left"), (self._right_handle, "right")):
            handle.bind("<ButtonPress-1>", lambda e, s=side: self._begin_resize(e, s))
            handle.bind("<B1-Motion>", self._do_resize)
            handle.bind("<ButtonRelease-1>", self._end_resize)

        frame = ttk.Frame(outer, padding=10)
        frame.grid(row=0, column=1, sticky="nsew")
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
        self._entry.bind("<Escape>", lambda _e: self._close())
        self._listbox.bind("<Escape>", lambda _e: self._close())
        self._entry.bind("<Down>", self._move_selection_down)
        self._entry.bind("<Up>", self._move_selection_up)
        self._listbox.bind("<Up>", self._move_selection_up)
        self._listbox.bind("<Down>", self._move_selection_down)

        # Tooltip wiring - attach motion/leave handlers on the listbox.
        self._tooltip = _PaletteTooltip(self)
        self._listbox.bind("<Motion>", self._on_list_motion)
        self._listbox.bind("<Leave>", lambda _e: self._tooltip and self._tooltip.hide())
        # Hide the tooltip whenever the listbox is scrolled or clicked.
        self._listbox.bind("<MouseWheel>", lambda _e: self._tooltip and self._tooltip.hide(), add="+")
        self._listbox.bind("<Button-4>", lambda _e: self._tooltip and self._tooltip.hide(), add="+")
        self._listbox.bind("<Button-5>", lambda _e: self._tooltip and self._tooltip.hide(), add="+")
        self._listbox.bind("<ButtonPress>", lambda _e: self._tooltip and self._tooltip.hide(), add="+")

        # Focus / app-switch handling. ``<FocusOut>`` on the entry/listbox
        # fires whenever Tk moves focus internally OR when the whole app loses
        # focus to another OS-level window. The deferred check via
        # ``focus_displayof()`` lets us distinguish those cases: when focus
        # genuinely left the application we close, but a transient internal
        # transfer (entry -> listbox, popup, etc.) is ignored.
        self.bind("<FocusOut>", self._on_focus_out)
        # ``<Unmap>`` fires when the OS hides our window (e.g. user switched
        # to another desktop or minimized the parent). Treat it as "close".
        self.bind("<Unmap>", self._on_unmap)

    def _position(self) -> None:
        self.update_idletasks()
        master = self._master
        try:
            mx = master.winfo_rootx()
            my = master.winfo_rooty()
            mw = master.winfo_width()
        except tk.TclError:
            mx, my, mw = 0, 0, 800
        target_w = clamp_palette_width(self._current_width, mw if mw > 1 else None)
        self._current_width = target_w
        x = mx + (mw - target_w) // 2
        y = my + 60
        self.geometry(f"{target_w}x420+{x}+{y}")

    # ------------------------------------------------------ focus / close
    def _on_focus_out(self, event):
        # If we're already in the middle of closing programmatically (Enter
        # picked an action), bail out so we don't race with that teardown and
        # leave a stale grab/focus on the main window.
        if self._closing:
            return
        # The drag-to-resize path also briefly disturbs focus.
        if self._resize_drag is not None:
            return
        # Defer the decision: when a Tk-internal popup steals focus (e.g.
        # combobox dropdown, native dialog), ``focus_displayof()`` will still
        # return a widget. Only treat ``None`` after a short tick as an
        # OS-level focus-out worth closing for.
        if self._focus_check_id is not None:
            return
        try:
            self._focus_check_id = self.after(60, self._check_focus_lost)
        except tk.TclError:
            self._focus_check_id = None

    def _check_focus_lost(self) -> None:
        self._focus_check_id = None
        if self._closing:
            return
        if self._resize_drag is not None:
            return
        try:
            owner = self.focus_displayof()
        except tk.TclError:
            owner = None
        if owner is None:
            # Nothing in this Tk application owns the focus anymore -> the
            # user switched to another OS-level window. Close.
            self._close()
            return
        # ``focus_displayof()`` returns a widget. Keep the popup open if it's
        # us (or one of our descendants). Otherwise the main window or some
        # other Toplevel grabbed focus -> close.
        try:
            owner_path = str(owner)
            self_path = str(self)
        except Exception:
            return
        if owner_path == self_path or owner_path.startswith(self_path + "."):
            return
        # Submenu / native dialog spawned by us would normally remain a
        # descendant; if it isn't, treat it as a real app switch.
        self._close()

    def _on_unmap(self, _event=None):
        if self._closing:
            return
        # The Toplevel bind tag can also see child-widget Unmap events. Typing
        # the first query hides the placeholder label via grid_remove(); that
        # must not close the whole palette.
        if _event is not None and getattr(_event, "widget", self) is not self:
            return
        self._close()

    def _close(self) -> None:
        """Tear the popup down: release grab, restore focus, then destroy.

        Safe to call multiple times. Guarantees the Tk grab is released even
        if ``destroy`` itself throws, otherwise the main window stays frozen.
        """
        if self._closing:
            return
        self._closing = True
        # Drop the FocusOut binding first so the grab/focus dance during
        # teardown can't fire a recursive ``_close``.
        try:
            self.unbind("<FocusOut>")
        except tk.TclError:
            pass
        try:
            self.unbind("<Unmap>")
        except tk.TclError:
            pass
        # Cancel any pending deferred focus check.
        if self._focus_check_id is not None:
            try:
                self.after_cancel(self._focus_check_id)
            except tk.TclError:
                pass
            self._focus_check_id = None
        # Tear down tooltip before destroying ourselves so it can't outlive
        # the parent and leak a stray Toplevel.
        if self._tooltip is not None:
            try:
                self._tooltip.hide()
            except tk.TclError:
                pass
        # Persist width once on close (not on every resize event).
        if self._on_width_changed is not None:
            try:
                self._on_width_changed(int(self._current_width))
            except Exception:
                # Settings persistence must never break the close path.
                pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        # Hand focus back to the main window before destroying ourselves so
        # the OS/Tk doesn't get confused about where keyboard input should go.
        try:
            self._master.focus_set()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    # --------------------------------------------------------- resizing
    def _begin_resize(self, event, side: str) -> None:
        try:
            current_w = self.winfo_width()
        except tk.TclError:
            current_w = self._current_width
        self._resize_drag = {
            "side": side,
            "start_x_root": event.x_root,
            "start_width": current_w,
        }
        # Hide tooltip while resizing.
        if self._tooltip is not None:
            self._tooltip.hide()

    def _do_resize(self, event) -> None:
        drag = self._resize_drag
        if not drag:
            return
        delta = event.x_root - drag["start_x_root"]
        if drag["side"] == "left":
            # Dragging the left edge to the left grows the popup.
            delta = -delta
        new_width = drag["start_width"] + delta
        try:
            master_w = self._master.winfo_width()
        except tk.TclError:
            master_w = None
        new_width = clamp_palette_width(new_width, master_w)
        if new_width == self._current_width:
            return
        self._current_width = new_width
        try:
            mx = self._master.winfo_rootx()
            mw = self._master.winfo_width()
            my = self._master.winfo_rooty()
        except tk.TclError:
            mx, mw, my = 0, new_width, 0
        x = mx + (mw - new_width) // 2
        y = my + 60
        # Keep current height so resize stays width-only.
        try:
            current_h = self.winfo_height()
        except tk.TclError:
            current_h = 420
        self.geometry(f"{new_width}x{current_h}+{x}+{y}")

    def _end_resize(self, _event=None) -> None:
        self._resize_drag = None

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

        # Hide any visible tooltip - the list contents just changed.
        if self._tooltip is not None:
            self._tooltip.hide()

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

    # ----------------------------------------------------------- tooltip
    def _on_list_motion(self, event) -> None:
        if self._tooltip is None or not self._ranked:
            return
        try:
            index = self._listbox.nearest(event.y)
        except tk.TclError:
            return
        if index < 0 or index >= len(self._ranked):
            self._tooltip.hide()
            return
        # Sanity check: only show when the pointer is actually over a row.
        try:
            bbox = self._listbox.bbox(index)
        except tk.TclError:
            bbox = None
        if bbox is None:
            self._tooltip.hide()
            return
        y0 = bbox[1]
        y1 = y0 + bbox[3]
        if event.y < y0 or event.y > y1:
            self._tooltip.hide()
            return

        item, _ = self._ranked[index]
        parts = [item.label]
        if item.subtitle:
            parts.append(item.subtitle)
        text = "\n".join(parts)
        self._tooltip.schedule(index, text, event.x_root, event.y_root)

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
        callback = item.callback
        # Close the popup FIRST (release grab + restore focus + destroy) so the
        # main window can receive input immediately. Schedule the action via
        # ``after_idle`` on the master so Tk has fully processed the teardown
        # before the callback runs; otherwise a callback that opens another
        # modal can collide with the dying grab and freeze the UI for a few
        # seconds.
        self._close()
        if callback is not None:
            def _run_callback():
                try:
                    callback()
                except Exception:
                    import traceback
                    traceback.print_exc()

            try:
                self._master.after_idle(_run_callback)
            except tk.TclError:
                # Master is gone; run inline as a last resort.
                _run_callback()
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
