"""Keyboard-first terminal picker: filtered original tree and detail inspector."""
from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (ConditionalContainer, DynamicContainer, Float,
                                  FloatContainer, FormattedTextControl, HSplit,
                                  Layout, VSplit, Window)
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import (Button, CheckboxList, Dialog, Frame, Label,
                                   RadioList, TextArea)

from .cli_search import SearchFilters, entry_details, safe_text, tree_rows
from .session_catalog import SOURCE_LABELS
from .version import APP_VERSION


class SessionPicker:
    def __init__(self, catalog, query="", *, input=None, output=None):
        from prompt_toolkit.output.defaults import create_output
        self.output = output or create_output()
        self.catalog = catalog
        self.filters = SearchFilters()
        self.collapsed = set()
        self.rows = []
        self.index = 0
        self.filter_open = False
        self.search = TextArea(text=query, multiline=False, prompt="Suche: ", height=1)
        self.details = TextArea(text="", read_only=True, scrollbar=True, wrap_lines=True)
        self.tree_control = FormattedTextControl(self.tree_text, focusable=True,
                                               get_cursor_position=lambda: Point(0, self.index))
        self.tree_window = Window(self.tree_control, wrap_lines=False)
        self.tree_frame = Frame(self.tree_window, title="Verbindungen")
        self.detail_frame = Frame(self.details, title="Details (Tab: wechseln, Bild ↑/↓: scrollen)")
        self.wide = VSplit([self.tree_frame, self.detail_frame], padding=1)
        self.narrow = HSplit([self.tree_frame, self.detail_frame])
        self.search.buffer.on_text_changed += lambda _: self.refresh()
        self.source_choices = CheckboxList(list(SOURCE_LABELS.items()), default_values=list(SOURCE_LABELS))
        paths = {tuple(e.session.folder_path[:i]) for e in catalog.entries
                 for i in range(1, len(e.session.folder_path) + 1)}
        self.folder_choices = RadioList([((), "Alle Ordner"), *[(p, safe_text(" / ".join(p))) for p in sorted(paths)]])
        self.view_choices = RadioList([("all", "Alle"), ("favorites", "Favoriten"), ("recent", "Zuletzt verwendet")])
        self.filter_dialog = Dialog(
            title="Filter (Quellen + Ordner + Ansicht wirken gemeinsam)",
            body=VSplit([Frame(self.source_choices, title="Quellen"),
                         Frame(self.folder_choices, title="Ordner inkl. Unterordner"),
                         Frame(self.view_choices, title="Ansicht")], padding=1),
            buttons=[Button("Anwenden", handler=self.apply_filters),
                     Button("Zurücksetzen", handler=self.reset_filters),
                     Button("Abbrechen", handler=self.close_filters)],
            width=Dimension(preferred=110), with_background=True,
        )
        body = HSplit([
            Window(FormattedTextControl(f"SSH Manager CLI {APP_VERSION}"), height=1, style="class:title"),
            self.search,
            Window(FormattedTextControl(self.filter_text), height=1),
            DynamicContainer(self.body_layout),
            Window(FormattedTextControl(self.source_text), height=Dimension(min=1, max=3)),
            Window(FormattedTextControl("Enter: verbinden/Ordner | ↑↓: Auswahl | Tab: Bereich | F2: Filter | F3: Reset | Esc: Ende"), height=2),
        ])
        container = FloatContainer(body, floats=[Float(
            ConditionalContainer(self.filter_dialog, filter=Condition(lambda: self.filter_open)),
            left=1, right=1, top=2, bottom=2,
        )])
        kb = self.key_bindings()
        self.app = Application(layout=Layout(container, focused_element=self.search),
                               key_bindings=kb, full_screen=True, mouse_support=False,
                               style=Style.from_dict({"title": "bold", "selected": "reverse",
                                                      "folder": "ansicyan", "favorite": "ansiyellow"}),
                               input=input, output=self.output)
        self.refresh()

    def body_layout(self):
        size = self.output.get_size()
        if size.rows < 14 or size.columns < 45:
            return Window(FormattedTextControl("Terminal zu klein. Bitte auf mindestens 45 × 14 vergrößern."))
        return self.wide if size.columns >= 100 else self.narrow

    def refresh(self):
        identity = self.rows[self.index].identity if self.rows and self.index < len(self.rows) else None
        self.rows = tree_rows(self.catalog.entries, self.search.text, self.filters, self.collapsed)
        self.index = next((i for i, row in enumerate(self.rows) if row.identity == identity), 0)
        self.update_details()

    def update_details(self):
        from prompt_toolkit.document import Document
        row = self.rows[self.index] if self.rows else None
        if row is None:
            text = "Keine Treffer. Suche ändern oder mit F3 alle Filter zurücksetzen."
        elif row.entry:
            text = entry_details(row.entry)
        else:
            text = safe_text("Ordner:\n" + " / ".join(row.path), multiline=True)
        self.details.buffer.set_document(Document(text, 0), bypass_readonly=True)
        if hasattr(self, "app"):
            self.app.invalidate()

    def tree_text(self):
        if not self.rows:
            return [("", "Keine Treffer – F3 setzt Filter zurück.")]
        fragments = []
        for i, row in enumerate(self.rows):
            prefix = "  " * row.depth
            if row.entry:
                prefix += "★ " if row.entry.favorite else "  "
            else:
                prefix += "▾ " if row.expanded else "▸ "
            style = "class:selected" if i == self.index else "class:folder" if not row.entry else ""
            fragments.append((style, prefix + row.label + "\n"))
        return fragments

    def filter_text(self):
        sources = ", ".join(SOURCE_LABELS[s] for s in SOURCE_LABELS if s in self.filters.sources) or "Keine"
        folder = " / ".join(self.filters.folder) or "Alle"
        view = {"all": "Alle", "favorites": "Favoriten", "recent": "Zuletzt verwendet"}[self.filters.view]
        return safe_text(f"Quellen: {sources} | Ordner: {folder} | Ansicht: {view}")

    def source_text(self):
        from .source_status import STATUS_LABELS
        statuses = " | ".join(f"{SOURCE_LABELS.get(s, s)}: {STATUS_LABELS.get(v['state'], v['state'])} ({v['count']})"
                              for s, v in self.catalog.statuses.items())
        warnings = "\n" + " · ".join(self.catalog.warnings) if self.catalog.warnings else ""
        return safe_text(statuses + warnings, multiline=True)

    def open_filters(self):
        self.source_choices.current_values = list(self.filters.sources)
        self.folder_choices.current_value = self.filters.folder
        self.view_choices.current_value = self.filters.view
        self.filter_open = True
        self.app.layout.focus(self.source_choices)

    def close_filters(self):
        self.filter_open = False
        self.app.layout.focus(self.search)

    def apply_filters(self):
        self.filters = SearchFilters(set(self.source_choices.current_values),
                                     self.folder_choices.current_value, self.view_choices.current_value)
        self.close_filters()
        self.refresh()

    def reset_filters(self):
        self.filters = SearchFilters()
        self.close_filters()
        self.refresh()

    def activate(self):
        size = self.app.output.get_size()
        if not self.rows or size.rows < 14 or size.columns < 45:
            return
        row = self.rows[self.index]
        if row.entry:
            self.app.exit(result=row.entry)
        else:
            self.toggle_folder(row.path)

    def toggle_folder(self, path):
        if self.search.text.strip():
            return  # Search ancestors stay open so matches cannot disappear.
        if path in self.collapsed:
            self.collapsed.remove(path)
        else:
            self.collapsed.add(path)
        self.refresh()

    def key_bindings(self):
        kb = KeyBindings()
        main = Condition(lambda: not self.filter_open)
        tree_or_search = main & (has_focus(self.tree_control) | has_focus(self.search))

        @kb.add("up", filter=tree_or_search)
        def up(event):
            self.index = max(0, self.index - 1)
            self.update_details()

        @kb.add("down", filter=tree_or_search)
        def down(event):
            self.index = min(max(0, len(self.rows) - 1), self.index + 1)
            self.update_details()

        @kb.add("left", filter=main & has_focus(self.tree_control))
        def left(event):
            if self.rows:
                row = self.rows[self.index]
                if not row.entry and row.expanded:
                    self.toggle_folder(row.path)
                elif row.path:
                    parent = row.path if row.entry else row.path[:-1]
                    self.index = next((i for i, item in enumerate(self.rows) if not item.entry and item.path == parent), self.index)
                    self.update_details()

        @kb.add("right", filter=main & has_focus(self.tree_control))
        def right(event):
            if self.rows:
                row = self.rows[self.index]
                if not row.entry:
                    if not row.expanded:
                        self.toggle_folder(row.path)
                    elif self.index + 1 < len(self.rows):
                        self.index += 1
                        self.update_details()

        @kb.add("enter", filter=tree_or_search)
        def enter(event):
            self.activate()

        @kb.add("tab", filter=main)
        def tab(event):
            event.app.layout.focus_next()

        @kb.add("s-tab", filter=main)
        def backtab(event):
            event.app.layout.focus_previous()

        @kb.add("f2", filter=main)
        def filters(event):
            self.open_filters()

        @kb.add("f3", filter=main)
        def reset(event):
            self.reset_filters()

        @kb.add("escape", eager=True)
        def escape(event):
            if self.filter_open:
                self.close_filters()
            else:
                event.app.exit(result=None)

        @kb.add("c-c", eager=True)
        def cancel(event):
            event.app.exit(result=None)

        return kb

    def run(self):
        return self.app.run()
