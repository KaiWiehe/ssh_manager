# Design: Session-Farbmarkierung

**Datum:** 2026-03-30
**Status:** Genehmigt

## Problem

Sessions im Tree sind visuell nicht unterscheidbar. Vor allem Test- und Live-Systeme sollen schnell erkennbar sein.

## Lösung

Jede Session kann per Rechtsklick eine Textfarbe zugewiesen bekommen. Die Farbe wird im Tree-Row-Text (foreground) angezeigt und persistent in `ui_state.json` gespeichert.

---

## Farbpalette

8 vordefinierte, dezente Farben (gut lesbar auf weißem Hintergrund):

| Name | Hex | Empfohlener Zweck |
|------|-----|-------------------|
| Grün | `#2d8653` | Test-Systeme |
| Rot | `#c0392b` | Live/Prod-Systeme |
| Blau | `#2980b9` | Dev/Staging |
| Orange | `#d35400` | Warnung |
| Lila | `#8e44ad` | Special |
| Türkis | `#16a085` | Intern |
| Grau | `#7f8c8d` | Inaktiv |
| Gelb | `#b7950b` | Beobachten |

---

## Interaktion

**Rechtsklick auf Session:**
```
┌─────────────────────────┐
│ Farbe…  ►               │──► ● Grün (Test)
└─────────────────────────┘    ● Rot (Live)
                               ● Blau
                               ● Orange
                               ● Lila
                               ● Türkis
                               ● Grau
                               ● Gelb
                               ─────────────
                               ✕ Farbe entfernen
```

- Aktive Farbe der Session erhält ein `✓`-Präfix im Submenu
- Kein extra Fenster, nativ als Cascading-Submenu

**Rechtsklick auf Ordner:** unverändert (Alle auswählen / Alle abwählen)

---

## Technische Umsetzung

### Datenmodell

`Session`-Dataclass: keine Änderung nötig. Farbe ist UI-State, kein Domain-Wert.

### Persistenz

`ui_state.json` wird um `session_colors` erweitert:
```json
{
  "expanded_folders": ["Extern", "Extern/Sub"],
  "session_colors": {
    "Extern/server-live-01": "#c0392b",
    "Others/server-test-03": "#2d8653"
  }
}
```

`_load_ui_state()` und `_save_ui_state()` werden angepasst:
- Laden: gibt `dict[str, str]` für `session_colors` zurück
- Speichern: nimmt zusätzlich `session_colors: dict[str, str]`

### Treeview-Tags

Für jede Farbe wird ein `tag_configure()`-Tag registriert:
```python
PALETTE = [
    ("Grün (Test)",  "#2d8653"),
    ("Rot (Live)",   "#c0392b"),
    ("Blau",         "#2980b9"),
    ("Orange",       "#d35400"),
    ("Lila",         "#8e44ad"),
    ("Türkis",       "#16a085"),
    ("Grau",         "#7f8c8d"),
    ("Gelb",         "#b7950b"),
]
```

Tag-Name: `f"color_{hex[1:]}"` (z.B. `color_2d8653`)

Sessions erhalten beim `populate()` zusätzlich ihren Farb-Tag:
```python
tags = (TAG_SESSION,) + ((color_tag,) if color_tag else ())
```

### SessionTree-Änderungen

- Neues Instanzdict `_session_colors: dict[str, str]` (session.key → hex)
- Methode `set_session_color(session_key: str, color: str | None)` – setzt/entfernt Farbe
- Methode `get_session_colors() -> dict[str, str]` – für Persistenz
- `populate()` bekommt `session_colors: dict[str, str] = {}` Parameter
- `_on_right_click()` wird auf Sessions erweitert; baut Farb-Submenu auf

### SSHManagerApp-Änderungen

- `_load_ui_state()` gibt zusätzlich `session_colors` zurück
- `_save_ui_state()` speichert zusätzlich `session_colors`
- `_on_close()` übergibt `tree.get_session_colors()` an `_save_ui_state()`

---

## Out of Scope

- Keine Ordner-Einfärbung
- Kein freier Farbpicker (nur Palette)
- Keine Hintergrundeinfärbung (nur foreground)
