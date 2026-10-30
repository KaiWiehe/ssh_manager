"""Actual Tk drag/copy, source actions, and dynamic widget coverage."""
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk

import pytest

from test_restart_templates_ui import app
from ssh_manager_app.text_selection import install_text_selection


def drag(app, widget, x=8, y=10, end=100):
    app.update()
    widget.event_generate("<ButtonPress-1>", x=x, y=y)
    widget.event_generate("<B1-Motion>", x=end, y=y)
    widget.event_generate("<ButtonRelease-1>", x=end, y=y)
    app.update()
    selection = app._display_text_selection
    assert selection.overlay is not None
    selection.select_all()
    selection.copy()
    return app.clipboard_get()


def test_multiline_dynamic_label_drag_does_not_run_click_action(app):
    install_text_selection(app)
    variable = tk.StringVar(value="Server test.invalid\nBenutzer admin")
    label = ttk.Label(app, textvariable=variable, wraplength=300)
    label.pack()
    actions = []
    label.bind("<Button-1>", lambda _: actions.append("clicked"))
    assert drag(app, label) == variable.get()
    assert actions == []
    selection = app._display_text_selection
    original = selection.overlay.get("1.0", "end-1c")
    selection.overlay.event_generate("<KeyPress>", keysym="x")
    assert selection.overlay.get("1.0", "end-1c") == original
    selection.close()
    variable.set("Neuer Status")
    label.event_generate("<ButtonPress-1>", x=5, y=5)
    label.event_generate("<ButtonRelease-1>", x=5, y=5)
    assert actions == ["clicked"]
    assert drag(app, label, end=70) == "Neuer Status"


def test_button_drag_copies_caption_without_invoking_command(app):
    install_text_selection(app)
    calls = []
    button = ttk.Button(app, text="Server entfernen", command=lambda: calls.append(True))
    button.pack()
    assert drag(app, button) == "Server entfernen"
    assert calls == []
    app._display_text_selection.close()
    button.event_generate("<Enter>")
    button.event_generate("<ButtonPress-1>", x=5, y=5)
    button.event_generate("<ButtonRelease-1>", x=5, y=5)
    assert calls == [True]


def test_tree_cell_text_drag_and_normal_selection(app):
    install_text_selection(app)
    tree = ttk.Treeview(app, columns=("host",), show="headings")
    tree.heading("host", text="Hostname")
    tree.insert("", "end", iid="one", values=("server.example.invalid",))
    tree.pack()
    app.update()
    _, y, _, h = tree.bbox("one", "host")
    assert drag(app, tree, y=y+h//2, end=140) == "server.example.invalid"
    app._display_text_selection.close()
    tree.selection_set("one")
    assert tree.selection() == ("one",)


def test_native_entry_and_text_keep_their_selection_bindings(app):
    controller = install_text_selection(app)
    entry = ttk.Entry(app)
    entry.insert(0, "edit me")
    entry.pack()
    text = tk.Text(app, height=2)
    text.insert("1.0", "read only text")
    text.configure(state="disabled")
    text.pack()
    app.update()
    assert controller.tag not in entry.bindtags()
    assert controller.tag not in text.bindtags()
    entry.selection_range(0, 4)
    entry.event_generate("<<Copy>>")
    assert app.clipboard_get() == "edit"
    text.tag_add("sel", "1.0", "1.4")
    text.event_generate("<<Copy>>")
    assert app.clipboard_get() == "read"


def test_new_window_labels_installed_and_close_does_not_leave_overlay(app):
    controller = install_text_selection(app)
    window = tk.Toplevel(app)
    label = ttk.Label(window, text="Ergebnisdetails kopieren")
    label.pack()
    assert drag(app, label) == "Ergebnisdetails kopieren"
    window.destroy()
    controller.close()
    app.update()
    assert controller.overlay is None


@pytest.mark.parametrize("kind", ["heading", "list", "tab", "canvas", "frame", "checkbox"])
def test_display_surfaces_and_controls_support_copy(app, kind):
    controller = install_text_selection(app)
    calls = []
    y = 10
    if kind == "heading":
        widget = ttk.Treeview(app, columns=("host",), show="headings")
        widget.heading("host", text="Hostname kopieren")
    elif kind == "list":
        widget = tk.Listbox(app)
        widget.insert("end", "Listeninhalt kopieren")
    elif kind == "tab":
        widget = ttk.Notebook(app)
        widget.add(ttk.Frame(widget), text="Vorlagen bearbeiten")
    elif kind == "canvas":
        widget = tk.Canvas(app, width=300, height=50)
        widget.create_text(4, 5, anchor="nw", text="Canvas kopieren")
    elif kind == "frame":
        widget = ttk.LabelFrame(app, text="Gruppentitel kopieren", width=280, height=80)
    else:
        widget = ttk.Checkbutton(app, text="Option kopieren", command=lambda: calls.append(True))
    widget.pack()
    copied = drag(app, widget, y=y, end=110)
    assert "kopieren" in copied or "Vorlagen" in copied
    assert calls == []
    controller.close()


def test_copying_tab_does_not_change_active_page(app):
    controller = install_text_selection(app)
    tabs = ttk.Notebook(app)
    tabs.add(ttk.Frame(tabs), text="Erster Tab")
    tabs.add(ttk.Frame(tabs), text="Zweiter Tab")
    tabs.pack()
    app.update()
    x = next(x for x in range(1, tabs.winfo_width()) if tabs.identify(x, 10) and tabs.index(f"@{x},10") == 1)
    assert drag(app, tabs, x=x+4, end=x+45) == "Zweiter Tab"
    assert tabs.index("current") == 0
    controller.close()
    tabs.event_generate("<ButtonPress-1>", x=x+5, y=10)
    tabs.event_generate("<ButtonRelease-1>", x=x+5, y=10)
    assert tabs.index("current") == 1


def test_regular_label_drag_remains_available_ctrl_drag_copies(app):
    install_text_selection(app)
    label = ttk.Label(app, text="Spalte verschieben")
    label.pack()
    moves = []
    label.bind("<B1-Motion>", lambda _: moves.append(True))
    app.update()
    label.event_generate("<ButtonPress-1>", x=4, y=8)
    label.event_generate("<B1-Motion>", x=90, y=8)
    label.event_generate("<ButtonRelease-1>", x=90, y=8)
    assert moves == [True] and app._display_text_selection.overlay is None
    label.event_generate("<ButtonPress-1>", x=4, y=8, state=4)
    label.event_generate("<B1-Motion>", x=90, y=8, state=4|256)
    label.event_generate("<ButtonRelease-1>", x=90, y=8, state=4)
    controller = app._display_text_selection
    assert controller.overlay is not None and moves == [True]
    controller.select_all()
    controller.copy()
    assert app.clipboard_get() == "Spalte verschieben"


def test_drag_on_centered_wide_button_selects_visible_letters(app):
    controller = install_text_selection(app)
    calls = []
    button = ttk.Button(app, text="Dienste auswählen", width=60, command=lambda: calls.append(True))
    button.pack()
    app.update()
    x = button.winfo_width() // 2 - 45
    button.event_generate("<ButtonPress-1>", x=x, y=12)
    button.event_generate("<B1-Motion>", x=x+70, y=12)
    button.event_generate("<ButtonRelease-1>", x=x+70, y=12)
    controller.copy()
    assert len(app.clipboard_get()) > 2
    assert calls == []
    controller.close()
