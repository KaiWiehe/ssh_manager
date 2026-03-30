# Session-Farbmarkierung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sessions im Treeview können per Rechtsklick eine von 8 Pastellfarben (foreground) zugewiesen bekommen; die Farbe wird persistent in `ui_state.json` gespeichert.

**Architecture:** PALETTE-Konstante + `_color_tag()` Hilfsfunktion zentral definiert; `SessionTree` verwaltet `_session_colors` dict und registriert Treeview-Tags; `_load_ui_state`/`_save_ui_state` werden auf ein gemeinsames Dict umgestellt; `SSHManagerApp._on_close()` übergibt beide State-Teile.

**Tech Stack:** Python 3.8+, tkinter/ttk, json

---

## Dateien

| Datei | Änderung |
|-------|----------|
| `ssh_manager.py` | Alle Änderungen (Konstanten, State-Funktionen, SessionTree, App) |
| `tests/test_logic.py` | Neue Tests für `_color_tag`, `_load_ui_state`, `_save_ui_state` |

---

## Task 1: PALETTE-Konstante und `_color_tag()` Hilfsfunktion

**Files:**
- Modify: `ssh_manager.py` (~Zeile 26, nach `WINDOW_MIN_SIZE`)
- Test: `tests/test_logic.py`

- [ ] **Schritt 1: Failing-Test schreiben**

In `tests/test_logic.py` am Ende ergänzen:

```python
from ssh_manager import _color_tag, PALETTE


def test_color_tag_strips_hash():
    assert _color_tag("#2d8653") == "color_2d8653"


def test_color_tag_without_hash():
    assert _color_tag("2d8653") == "color_2d8653"


def test_palette_has_eight_entries():
    assert len(PALETTE) == 8


def test_palette_entries_have_name_and_hex():
    for name, hex_color in PALETTE:
        assert isinstance(name, str) and len(name) > 0
        assert hex_color.startswith("#") and len(hex_color) == 7
```

- [ ] **Schritt 2: Test ausführen – muss fehlschlagen**

```
pytest tests/test_logic.py::test_color_tag_strips_hash -v
```
Erwartet: `ImportError: cannot import name '_color_tag'`

- [ ] **Schritt 3: PALETTE + `_color_tag` implementieren**

In `ssh_manager.py` nach `WINDOW_MIN_SIZE = (600, 450)` einfügen:

```python
PALETTE: list[tuple[str, str]] = [
    ("Grün (Test)",  "#2d8653"),
    ("Rot (Live)",   "#c0392b"),
    ("Blau",         "#2980b9"),
    ("Orange",       "#d35400"),
    ("Lila",         "#8e44ad"),
    ("Türkis",       "#16a085"),
    ("Grau",         "#7f8c8d"),
    ("Gelb",         "#b7950b"),
]


def _color_tag(hex_color: str) -> str:
    """Tag-Name für eine Hex-Farbe, z.B. '#2d8653' → 'color_2d8653'."""
    return f"color_{hex_color.lstrip('#')}"
```

- [ ] **Schritt 4: Tests ausführen – alle grün**

```
pytest tests/test_logic.py -v
```
Erwartet: alle bisherigen + 4 neue Tests grün.

- [ ] **Schritt 5: Committen**

```bash
git add ssh_manager.py tests/test_logic.py
git commit -m "feat: add PALETTE constant and _color_tag helper"
```

---

## Task 2: `_load_ui_state` / `_save_ui_state` auf gemeinsames Dict umstellen

**Files:**
- Modify: `ssh_manager.py` (Funktionen `_load_ui_state`, `_save_ui_state`, Aufruf in `SSHManagerApp.__init__`)
- Test: `tests/test_logic.py`

- [ ] **Schritt 1: Failing-Tests schreiben**

In `tests/test_logic.py` ergänzen:

```python
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from ssh_manager import _load_ui_state, _save_ui_state


def test_load_ui_state_missing_file_returns_defaults():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "nonexistent.json"
        with patch("ssh_manager._STATE_FILE", fake_path):
            folders, colors = _load_ui_state()
    assert folders == set()
    assert colors == {}


def test_save_and_load_ui_state_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "ui_state.json"
        with patch("ssh_manager._STATE_FILE", fake_path):
            _save_ui_state({"Extern", "Extern/Sub"}, {"Extern/srv": "#c0392b"})
            folders, colors = _load_ui_state()
    assert folders == {"Extern", "Extern/Sub"}
    assert colors == {"Extern/srv": "#c0392b"}


def test_load_ui_state_ignores_unknown_keys():
    with tempfile.TemporaryDirectory() as tmp:
        fake_path = Path(tmp) / "ui_state.json"
        fake_path.write_text(json.dumps({"expanded_folders": ["A"], "future_key": 42}))
        with patch("ssh_manager._STATE_FILE", fake_path):
            folders, colors = _load_ui_state()
    assert folders == {"A"}
    assert colors == {}
```

- [ ] **Schritt 2: Tests ausführen – müssen fehlschlagen**

```
pytest tests/test_logic.py::test_load_ui_state_missing_file_returns_defaults -v
```
Erwartet: `ValueError: too many values to unpack` oder TypeError (aktuelle Funktion gibt `set` zurück, kein Tuple).

- [ ] **Schritt 3: `_load_ui_state` und `_save_ui_state` anpassen**

In `ssh_manager.py` die beiden Funktionen ersetzen:

```python
def _load_ui_state() -> tuple[set[str], dict[str, str]]:
    """Lädt UI-Zustand aus JSON. Gibt leere Defaults zurück wenn nicht vorhanden."""
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("expanded_folders", [])), dict(data.get("session_colors", {}))
    except (OSError, json.JSONDecodeError, ValueError):
        return set(), {}


def _save_ui_state(expanded_folders: set[str], session_colors: dict[str, str]) -> None:
    """Speichert UI-Zustand als JSON in %APPDATA%\\SSH-Manager\\."""
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(
        json.dumps(
            {"expanded_folders": sorted(expanded_folders), "session_colors": session_colors},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
```

- [ ] **Schritt 4: Aufrufstellen in `SSHManagerApp.__init__` anpassen**

Die Zeile `self._initial_open_folders = _load_ui_state()` ersetzen:

```python
self._initial_open_folders, self._initial_session_colors = _load_ui_state()
```

- [ ] **Schritt 5: `_on_close` anpassen**

```python
def _on_close(self) -> None:
    _save_ui_state(self._tree.get_open_folders(), self._tree.get_session_colors())
    self.destroy()
```

- [ ] **Schritt 6: Tests ausführen – alle grün**

```
pytest tests/test_logic.py -v
```
Erwartet: alle Tests grün (13 alte + 7 neue).

- [ ] **Schritt 7: Committen**

```bash
git add ssh_manager.py tests/test_logic.py
git commit -m "feat: extend ui_state with session_colors"
```

---

## Task 3: SessionTree – `_session_colors`, Tag-Registrierung, `populate()` anpassen

**Files:**
- Modify: `ssh_manager.py` (Klasse `SessionTree`)

- [ ] **Schritt 1: `__init__` erweitern**

`SessionTree.__init__` Signatur und Body anpassen. Das `initial_session_colors`-Parameter und `self._session_colors` Dict hinzufügen:

```python
def __init__(
    self,
    parent: tk.Widget,
    sessions: list[Session],
    img_unchecked: tk.PhotoImage,
    img_checked: tk.PhotoImage,
    on_selection_changed,  # Callable[[int], None]
    initial_open_folders: set[str] | None = None,
    initial_session_colors: dict[str, str] | None = None,
):
    super().__init__(parent)
    self._sessions = sessions
    self._img_unchecked = img_unchecked
    self._img_checked = img_checked
    self._on_selection_changed = on_selection_changed

    self._item_to_session: dict[str, Session] = {}
    self._checked: dict[str, bool] = {}
    self._item_to_folder_key: dict[str, str] = {}
    self._session_colors: dict[str, str] = dict(initial_session_colors or {})

    self._build()
    self.populate(sessions, open_folders=initial_open_folders or set())
```

- [ ] **Schritt 2: `_configure_color_tags()` Methode hinzufügen und in `_build()` aufrufen**

Die neue Methode nach `_build()` definieren:

```python
def _configure_color_tags(self) -> None:
    """Registriert für jede Palettenfarbe einen Treeview-Tag."""
    for _, hex_color in PALETTE:
        self._tv.tag_configure(_color_tag(hex_color), foreground=hex_color)
```

Am Ende von `_build()`, nach dem `self._tv.bind`-Block, einfügen:

```python
self._configure_color_tags()
```

- [ ] **Schritt 3: `get_session_colors()` Methode hinzufügen**

Nach `get_open_folders()` einfügen:

```python
def get_session_colors(self) -> dict[str, str]:
    """Gibt eine Kopie des aktuellen session_key → hex Mappings zurück."""
    return dict(self._session_colors)
```

- [ ] **Schritt 4: `set_session_color()` Methode hinzufügen**

Nach `get_session_colors()` einfügen:

```python
def set_session_color(self, session_key: str, hex_color: str | None) -> None:
    """Setzt oder entfernt die Textfarbe einer Session sofort im Tree."""
    if hex_color:
        self._session_colors[session_key] = hex_color
    else:
        self._session_colors.pop(session_key, None)
    for item_id, session in self._item_to_session.items():
        if session.key == session_key:
            color_tag = _color_tag(hex_color) if hex_color else None
            tags = (self.TAG_SESSION,) + ((color_tag,) if color_tag else ())
            self._tv.item(item_id, tags=tags)
            break
```

- [ ] **Schritt 5: `populate()` – Farb-Tag beim Session-Insert anwenden**

Im Session-Insert-Block von `populate()` die `tags`-Zeile anpassen. Vorher:

```python
item_id = self._tv.insert(
    parent_id, "end",
    image=self._img_unchecked,
    text=f"  {session.display_name}",
    values=(session.hostname, port_str),
    tags=(self.TAG_SESSION,),
)
```

Nachher:

```python
_ctag = _color_tag(self._session_colors[session.key]) if session.key in self._session_colors else None
_tags = (self.TAG_SESSION,) + ((_ctag,) if _ctag else ())
item_id = self._tv.insert(
    parent_id, "end",
    image=self._img_unchecked,
    text=f"  {session.display_name}",
    values=(session.hostname, port_str),
    tags=_tags,
)
```

- [ ] **Schritt 6: Tests ausführen**

```
pytest tests/test_logic.py -v
```
Erwartet: alle 20 Tests grün.

- [ ] **Schritt 7: Committen**

```bash
git add ssh_manager.py
git commit -m "feat: SessionTree stores and applies session colors"
```

---

## Task 4: Rechtsklick-Kontextmenü für Sessions

**Files:**
- Modify: `ssh_manager.py` (Methode `_on_right_click` in `SessionTree`)

- [ ] **Schritt 1: `_on_right_click` aufteilen**

Die bestehende Methode `_on_right_click` ersetzen durch drei Methoden:

```python
def _on_right_click(self, event: tk.Event) -> None:
    """Kontextmenü je nach Zeilentyp anzeigen."""
    item_id = self._tv.identify_row(event.y)
    if not item_id:
        return
    tags = self._tv.item(item_id, "tags")
    if self.TAG_FOLDER in tags:
        self._show_folder_menu(item_id, event)
    elif self.TAG_SESSION in tags:
        self._show_session_menu(item_id, event)

def _show_folder_menu(self, item_id: str, event: tk.Event) -> None:
    """Kontextmenü für Ordner-Zeilen."""
    menu = tk.Menu(self, tearoff=False)
    menu.add_command(
        label="Alle im Ordner auswählen",
        command=lambda: self._set_folder_checked(item_id, True),
    )
    menu.add_command(
        label="Alle im Ordner abwählen",
        command=lambda: self._set_folder_checked(item_id, False),
    )
    menu.tk_popup(event.x_root, event.y_root)

def _show_session_menu(self, item_id: str, event: tk.Event) -> None:
    """Kontextmenü für Session-Zeilen mit Farb-Submenu."""
    session = self._item_to_session[item_id]
    current_color = self._session_colors.get(session.key)

    menu = tk.Menu(self, tearoff=False)
    color_menu = tk.Menu(menu, tearoff=False)
    for name, hex_color in PALETTE:
        prefix = "✓" if hex_color == current_color else "  "
        color_menu.add_command(
            label=f"{prefix} {name}",
            command=lambda hc=hex_color, sk=session.key: self.set_session_color(sk, hc),
        )
    color_menu.add_separator()
    color_menu.add_command(
        label="✕ Farbe entfernen",
        command=lambda sk=session.key: self.set_session_color(sk, None),
    )
    menu.add_cascade(label="Farbe…", menu=color_menu)
    menu.tk_popup(event.x_root, event.y_root)
```

- [ ] **Schritt 2: Tests ausführen**

```
pytest tests/test_logic.py -v
```
Erwartet: alle 20 Tests grün.

- [ ] **Schritt 3: Committen**

```bash
git add ssh_manager.py
git commit -m "feat: right-click color submenu for sessions"
```

---

## Task 5: `SSHManagerApp` – `initial_session_colors` übergeben

**Files:**
- Modify: `ssh_manager.py` (Methode `_build_ui` in `SSHManagerApp`)

- [ ] **Schritt 1: `initial_session_colors` an `SessionTree` übergeben**

In `_build_ui()` den `SessionTree`-Konstruktor-Aufruf anpassen:

```python
self._tree = SessionTree(
    self,
    sessions=self._sessions,
    img_unchecked=self._img_unchecked,
    img_checked=self._img_checked,
    on_selection_changed=self._on_selection_changed,
    initial_open_folders=self._initial_open_folders,
    initial_session_colors=self._initial_session_colors,
)
```

- [ ] **Schritt 2: Alle Tests ausführen**

```
pytest tests/test_logic.py -v
```
Erwartet: alle 20 Tests grün.

- [ ] **Schritt 3: Syntaxcheck**

```
python -c "import ast; ast.parse(open('ssh_manager.py').read()); print('Syntax OK')"
```

- [ ] **Schritt 4: Committen**

```bash
git add ssh_manager.py
git commit -m "feat: wire session colors into SSHManagerApp lifecycle"
```
