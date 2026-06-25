"""Configurable keyboard shortcuts.

Provides:
- A registry of all named actions (id, label, default shortcut, callback).
- Parsing of user-friendly shortcut strings (e.g. ``Ctrl+P``, ``F2``, ``Delete``)
  into Tk binding sequences (``<Control-p>``).
- Default-merging so newly registered actions automatically appear in user
  config without losing custom bindings.
- Conflict detection between actions.
- Persistence helpers used by ``storage`` to keep the existing settings file
  format intact.

The module is deliberately Tk-free in the parsing/merging logic so it stays
easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable


# ---------------------------------------------------------------------------
# Action catalogue
# ---------------------------------------------------------------------------

#: Ordered list of (action_id, German label, default human-readable shortcut)
DEFAULT_ACTION_ORDER: list[tuple[str, str, str]] = [
    ("open_command_palette", "Befehlspalette öffnen", "Ctrl+P"),
    ("focus_search", "Suche fokussieren", "Ctrl+F"),
    ("new_session", "Neue Verbindung", "Ctrl+N"),
    ("open_settings", "Einstellungen öffnen", "Ctrl+,"),
    ("refresh", "Neu laden", "F5"),
    ("connect", "Verbinden", "Return"),
    ("edit", "Bearbeiten", "F2"),
    ("delete", "Löschen", "Delete"),
    ("select_all", "Alle auswählen", "Ctrl+A"),
    ("deselect_all", "Alle abwählen", "Ctrl+D"),
    ("invert_selection", "Auswahl umkehren", "Ctrl+I"),
    ("toggle_recent_folder", "Ordner 'Zuletzt verwendet' umschalten", "Ctrl+Shift+R"),
    ("import_settings", "Einstellungen importieren", ""),
    ("export_settings", "Einstellungen exportieren", ""),
]


def default_shortcuts() -> dict[str, str]:
    """Return a fresh copy of the default action -> shortcut mapping."""
    return {action_id: default for action_id, _label, default in DEFAULT_ACTION_ORDER}


def action_labels() -> dict[str, str]:
    return {action_id: label for action_id, label, _default in DEFAULT_ACTION_ORDER}


def merge_with_defaults(raw: dict | None) -> dict[str, str]:
    """Merge ``raw`` with the default shortcut table.

    Unknown action ids are dropped, known actions keep the user-provided
    binding (empty string means "unbound").
    Missing actions get their default shortcut, so new releases can extend
    the action list without users losing their config.
    """
    defaults = default_shortcuts()
    if not isinstance(raw, dict):
        return defaults
    merged = dict(defaults)
    for key, value in raw.items():
        if key not in defaults:
            continue
        if value is None:
            merged[key] = ""
            continue
        merged[key] = str(value).strip()
    return merged


# ---------------------------------------------------------------------------
# Shortcut parsing
# ---------------------------------------------------------------------------

_MOD_ALIASES: dict[str, str] = {
    "ctrl": "Control",
    "control": "Control",
    "strg": "Control",
    "shift": "Shift",
    "umschalt": "Shift",
    "alt": "Alt",
    "meta": "Meta",
    "super": "Super",
    "cmd": "Command",
    "command": "Command",
}

_SPECIAL_KEYS: dict[str, str] = {
    "esc": "Escape",
    "escape": "Escape",
    "enter": "Return",
    "return": "Return",
    "space": "space",
    "spacebar": "space",
    "tab": "Tab",
    "backspace": "BackSpace",
    "delete": "Delete",
    "del": "Delete",
    "entf": "Delete",
    "insert": "Insert",
    "ins": "Insert",
    "home": "Home",
    "end": "End",
    "pageup": "Prior",
    "pgup": "Prior",
    "pagedown": "Next",
    "pgdn": "Next",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "minus": "minus",
    "plus": "plus",
    "comma": ",",
    "period": ".",
    ",": "comma",
    ".": "period",
    ";": "semicolon",
    "/": "slash",
    "\\": "backslash",
    "'": "apostrophe",
    "`": "grave",
    "[": "bracketleft",
    "]": "bracketright",
}


@dataclass(frozen=True)
class ParsedShortcut:
    modifiers: tuple[str, ...]
    key: str  # canonical Tk keysym
    display: str  # human readable form (normalised)

    def to_binding(self) -> str:
        """Return a Tk ``<Modifier-key>`` binding string."""
        parts = list(self.modifiers) + [self.key]
        return "<" + "-".join(parts) + ">"

    def to_binding_variants(self) -> list[str]:
        """Return additional bindings to register so e.g. ``Ctrl+a`` also
        catches ``Ctrl+A`` (Tk treats these as distinct keysyms)."""
        bindings = [self.to_binding()]
        if len(self.key) == 1 and self.key.isalpha():
            other = self.key.upper() if self.key.islower() else self.key.lower()
            bindings.append("<" + "-".join(list(self.modifiers) + [other]) + ">")
        return bindings


def parse_shortcut(text: str) -> ParsedShortcut | None:
    """Parse a human-readable shortcut into a ``ParsedShortcut``.

    Returns ``None`` for empty strings or unparseable input.
    """
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    # Allow both "Ctrl+P" and "Ctrl-P".
    tokens = [t for t in raw.replace("-", "+").split("+") if t]
    if not tokens:
        return None

    mods: list[str] = []
    key_token: str | None = None
    for token in tokens[:-1]:
        norm = _MOD_ALIASES.get(token.lower())
        if not norm:
            return None
        if norm not in mods:
            mods.append(norm)
    key_token = tokens[-1]

    # Sort modifiers in a stable order so equivalent shortcuts collide in the
    # conflict detector (Ctrl+Shift+P == Shift+Ctrl+P).
    mod_order = ["Control", "Shift", "Alt", "Meta", "Super", "Command"]
    sorted_mods = tuple(sorted(mods, key=lambda m: mod_order.index(m) if m in mod_order else len(mod_order)))

    key_lower = key_token.lower()
    if key_lower in _SPECIAL_KEYS:
        key = _SPECIAL_KEYS[key_lower]
    elif len(key_token) >= 2 and key_token[0].lower() == "f" and key_token[1:].isdigit():
        n = int(key_token[1:])
        if 1 <= n <= 24:
            key = f"F{n}"
        else:
            return None
    elif len(key_token) == 1:
        # Letter / digit / punctuation. Tk uses lower case keysyms for letters.
        if key_token.isalpha():
            key = key_token.lower()
        else:
            key = key_token
    else:
        # Unknown multi-char key.
        return None

    display = _format_display(sorted_mods, key)
    return ParsedShortcut(modifiers=sorted_mods, key=key, display=display)


def _format_display(mods: tuple[str, ...], key: str) -> str:
    pretty_mods = {
        "Control": "Ctrl",
        "Shift": "Shift",
        "Alt": "Alt",
        "Meta": "Meta",
        "Super": "Super",
        "Command": "Cmd",
    }
    pretty_keys = {
        "Return": "Enter",
        "Escape": "Esc",
        "BackSpace": "Backspace",
        "Prior": "PageUp",
        "Next": "PageDown",
        "space": "Space",
        "comma": ",",
        "period": ".",
        "semicolon": ";",
        "slash": "/",
        "backslash": "\\",
        "apostrophe": "'",
        "grave": "`",
        "bracketleft": "[",
        "bracketright": "]",
    }
    key_disp = pretty_keys.get(key, key)
    if len(key_disp) == 1 and key_disp.isalpha():
        key_disp = key_disp.upper()
    return "+".join(list(pretty_mods.get(m, m) for m in mods) + [key_disp])


def normalize_shortcut(text: str) -> str:
    """Normalise the visible representation. Empty string for unparseable."""
    parsed = parse_shortcut(text)
    return parsed.display if parsed else ""


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------


def find_conflict(action_id: str, candidate: str, mapping: dict[str, str]) -> str | None:
    """Return the action id that already owns ``candidate`` (if any).

    Empty strings or unparseable shortcuts are considered conflict-free.
    """
    parsed = parse_shortcut(candidate)
    if parsed is None:
        return None
    for other_id, other_value in mapping.items():
        if other_id == action_id:
            continue
        other_parsed = parse_shortcut(other_value)
        if other_parsed is None:
            continue
        if other_parsed.modifiers == parsed.modifiers and other_parsed.key == parsed.key:
            return other_id
    return None


def find_all_conflicts(mapping: dict[str, str]) -> list[tuple[str, str, str]]:
    """Return ``(action_a, action_b, normalised_shortcut)`` for each conflict."""
    seen: dict[tuple[tuple[str, ...], str], str] = {}
    conflicts: list[tuple[str, str, str]] = []
    for action_id, value in mapping.items():
        parsed = parse_shortcut(value)
        if parsed is None:
            continue
        key = (parsed.modifiers, parsed.key)
        if key in seen:
            conflicts.append((seen[key], action_id, parsed.display))
        else:
            seen[key] = action_id
    return conflicts


# ---------------------------------------------------------------------------
# Action / Manager
# ---------------------------------------------------------------------------


@dataclass
class ShortcutAction:
    id: str
    label: str
    default: str
    callback: Callable[[], None]
    #: When ``True`` (the default) the shortcut is suppressed while a text
    #: entry has focus (so e.g. ``Ctrl+A`` selects the entry text).
    skip_in_entry: bool = True
    #: When set, the callback only fires if this predicate returns ``True``.
    enabled_when: Callable[[], bool] | None = None


class ShortcutManager:
    """Glues the action registry to a Tk root window.

    Usage:

        manager = ShortcutManager(root)
        manager.register(ShortcutAction("focus_search", ..., callback))
        manager.load_bindings(mapping)
        # later
        manager.apply_bindings(updated_mapping)
    """

    def __init__(self, root) -> None:
        self._root = root
        self._actions: dict[str, ShortcutAction] = {}
        self._active_mapping: dict[str, str] = {}
        self._registered_bindings: dict[str, list[str]] = {}

    # -- registration --------------------------------------------------
    def register(self, action: ShortcutAction) -> None:
        self._actions[action.id] = action

    def actions(self) -> list[ShortcutAction]:
        # Preserve the documented default order, then unknowns.
        ordered_ids = [a for a, _l, _d in DEFAULT_ACTION_ORDER if a in self._actions]
        extras = [a for a in self._actions if a not in ordered_ids]
        return [self._actions[a] for a in ordered_ids + extras]

    def get_action(self, action_id: str) -> ShortcutAction | None:
        return self._actions.get(action_id)

    def current_mapping(self) -> dict[str, str]:
        return dict(self._active_mapping)

    # -- binding -------------------------------------------------------
    def load_bindings(self, mapping: dict[str, str]) -> None:
        self.apply_bindings(merge_with_defaults(mapping))

    def apply_bindings(self, mapping: dict[str, str]) -> None:
        self._unbind_all()
        normalised: dict[str, str] = {}
        for action_id, action in self._actions.items():
            raw = mapping.get(action_id, action.default)
            parsed = parse_shortcut(raw)
            if parsed is None:
                normalised[action_id] = ""
                continue
            normalised[action_id] = parsed.display
            bindings = parsed.to_binding_variants()
            self._registered_bindings[action_id] = bindings
            for binding in bindings:
                self._root.bind_all(binding, self._make_handler(action))
        self._active_mapping = normalised

    def _unbind_all(self) -> None:
        for bindings in self._registered_bindings.values():
            for binding in bindings:
                try:
                    self._root.unbind_all(binding)
                except Exception:
                    pass
        self._registered_bindings.clear()

    def _make_handler(self, action: ShortcutAction):
        def handler(event):
            if action.skip_in_entry and _focus_is_text_entry(event):
                return None
            if action.enabled_when is not None and not action.enabled_when():
                return None
            try:
                action.callback()
            except Exception:
                # Don't let exceptions break the Tk event loop.
                import traceback
                traceback.print_exc()
            return "break"
        return handler


def _focus_is_text_entry(event) -> bool:
    widget = getattr(event, "widget", None)
    focused = None
    try:
        focused = widget.focus_get()  # type: ignore[union-attr]
    except Exception:
        focused = None
    if focused is None:
        return False
    cls = focused.winfo_class() if hasattr(focused, "winfo_class") else ""
    return cls in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}


# ---------------------------------------------------------------------------
# Convenience for callers
# ---------------------------------------------------------------------------


def iter_actions(mapping: dict[str, str]) -> Iterable[tuple[str, str, str]]:
    """Iterate ``(action_id, label, shortcut_display)`` in default order."""
    labels = action_labels()
    for action_id, _label, _default in DEFAULT_ACTION_ORDER:
        yield action_id, labels[action_id], normalize_shortcut(mapping.get(action_id, ""))
