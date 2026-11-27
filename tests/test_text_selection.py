"""Actual Tk drag/copy, source actions, and dynamic widget coverage."""
import tkinter as tk
from types import SimpleNamespace
from tkinter import font, ttk

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
    original = selection.overlay.itemcget(selection.item, "text")
    selection.overlay.event_generate("<KeyPress>", keysym="x")
    assert selection.overlay.itemcget(selection.item, "text") == original
    selection.close()
    variable.set("Neuer Status")
    label.event_generate("<ButtonPress-1>", x=5, y=5)
    label.event_generate("<ButtonRelease-1>", x=5, y=5)
    assert actions == ["clicked"]
    assert drag(app, label, end=70) == "Neuer Status"


def test_button_still_clicks_and_has_no_text_selection(app):
    controller = install_text_selection(app)
    calls = []
    button = ttk.Button(app, text="Server entfernen", command=lambda: calls.append(True))
    button.pack()
    app.update()
    assert controller.tag not in button.bindtags()
    button.event_generate("<Enter>")
    button.event_generate("<ButtonPress-1>", x=5, y=5)
    button.event_generate("<ButtonRelease-1>", x=5, y=5)
    assert calls == [True]
    assert controller.overlay is None


def test_tree_cell_text_drag_and_normal_selection(app):
    install_text_selection(app)
    tree = ttk.Treeview(app, columns=("host",), show="headings")
    tree.heading("host", text="Hostname")
    tree.column("host", width=84, stretch=False)
    tree.insert("", "end", iid="one", values=("server.example.invalid",))
    tree.pack()
    app.update()
    _, y, width, height = tree.bbox("one", "host")
    assert drag(app, tree, y=y+height//2, end=width-2) == "server.example.invalid"
    controller = app._display_text_selection
    assert controller.overlay.winfo_width() < width
    assert controller.overlay.winfo_height() <= height
    assert controller.overlay.itemcget(controller.item, "width") == "0"
    controller.close()
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
    x, y, end = 8, 10, 110
    if kind == "heading":
        widget = ttk.Treeview(app, columns=("host",), show="tree headings")
        widget.column("#0", width=100, stretch=False)
        widget.column("host", width=200, stretch=False)
        widget.heading("host", text="Hostname kopieren", anchor="w", command=lambda: calls.append(True))
        x, end = 120, 190
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
        widget = ttk.LabelFrame(app, text="Gruppentitel kopieren", width=280, height=80,
                                style="SettingsGroup.TLabelframe")
    else:
        widget = ttk.Checkbutton(app, text="Option kopieren", command=lambda: calls.append(True))
    widget.pack()
    copied = drag(app, widget, x=x, y=y, end=end)
    assert "kopieren" in copied or "Vorlagen" in copied
    if kind == "heading":
        assert controller.overlay.winfo_x() > 100
    if kind == "frame":
        label_style = "SettingsGroup.TLabelframe.Label"
        label_font = ttk.Style(app).lookup(label_style, "font")
        assert controller.overlay.itemcget(controller.item, "font") == label_font
        assert controller.overlay.winfo_y() == 0
    assert calls == []
    controller.close()
    if kind == "heading":
        widget.event_generate("<ButtonPress-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
        app.update()
        assert calls == [True]


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


def test_header_title_stays_single_line_and_copies_dragged_letters(app):
    controller = install_text_selection(app)
    title = ttk.Label(app, text="SSH Manager", style="HeaderTitle.TLabel")
    title.pack()
    app.update()
    title_font = font.Font(root=app, font=ttk.Style(app).lookup("HeaderTitle.TLabel", "font"))
    start = 5
    end = title_font.measure("SSH M")
    title.event_generate("<ButtonPress-1>", x=start, y=title.winfo_height() // 2)
    title.event_generate("<B1-Motion>", x=end, y=title.winfo_height() // 2)
    title.event_generate("<ButtonRelease-1>", x=end, y=title.winfo_height() // 2)
    app.update()
    overlay = controller.overlay
    assert overlay.master is title
    assert int(overlay.cget("highlightthickness")) == 0
    assert int(overlay.cget("borderwidth")) == 0
    assert int(overlay.itemcget(controller.item, "width").split(".")[0]) == 0
    assert overlay.winfo_height() == title_font.metrics("linespace")
    assert overlay.winfo_width() == title_font.measure("SSH Manager")
    overlay.event_generate("<Control-c>")
    assert app.clipboard_get() == "SSH "


def test_dns_results_copy_text_in_place(app):
    from ssh_manager_app.dialogs_dns import DnsLookupResultsDialog
    from ssh_manager_app.dns_lookup import DnsLookupResult

    result = DnsLookupResult("example.invalid", "forward", ["192.0.2.10"], "Test", "ok")
    dialog = DnsLookupResultsDialog(app, [result])
    tree = dialog._tree
    app.update()
    iid = tree.get_children()[0]
    x, y, width, height = tree.bbox(iid, "result")
    assert drag(app, tree, x=x+6, y=y+height//2, end=x+width-10) == "192.0.2.10"
    controller = app._display_text_selection
    assert controller.overlay.master is tree
    controller.overlay.event_generate("<Escape>")
    assert dialog.winfo_exists()
    assert controller.overlay is None
    tree.event_generate("<ButtonPress-1>", x=x+6, y=y+height//2)
    tree.event_generate("<ButtonRelease-1>", x=x+6, y=y+height//2)
    app.update()
    assert controller.overlay.master is tree
    controller.overlay.event_generate("<Control-a>")
    controller.overlay.event_generate("<Control-c>")
    assert app.clipboard_get() == "192.0.2.10"
    dialog.destroy()


def test_horizontally_scrolled_tree_text_uses_original_character_positions(app):
    controller = install_text_selection(app)
    tree = ttk.Treeview(app, columns=("host",))
    tree.column("#0", width=340, stretch=False)
    tree.column("host", width=400, stretch=False)
    folder = tree.insert("", "end", text="Folder", open=True)
    iid = tree.insert(folder, "end", text="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    tree.place(x=10, y=10, width=400, height=100)
    app.update()
    initial_x, y, _, height = tree.bbox(iid, "#0")
    middle = y + height // 2
    first_text_x = next(x for x in range(initial_x, 100)
                        if tree.identify_element(x, middle).endswith("text"))
    tree.xview_moveto(0.10)
    app.update()
    scrolled_x, _, _, _ = tree.bbox(iid, "#0")
    expected_x = first_text_x + scrolled_x - initial_x
    assert expected_x < 0
    drag(app, tree, x=10, y=middle, end=120)
    overlay = controller.overlay
    assert overlay.winfo_x() > expected_x
    assert overlay.winfo_x() + overlay.coords(controller.item)[0] == expected_x

    controller.overlay_press(SimpleNamespace(
        x_root=tree.winfo_rootx() + 10, y_root=tree.winfo_rooty() + middle,
    ))
    assert controller.anchor > 0


@pytest.mark.parametrize("export", [True, False])
def test_list_text_selection_preserves_selected_row_and_colors(app, export):
    controller = install_text_selection(app)
    widget = tk.Listbox(app, exportselection=export, selectbackground="#345678")
    widget.insert("end", "List text stays put")
    widget.itemconfigure(0, selectforeground="#f0edf4")
    widget.pack()
    assert drag(app, widget, end=80) == "List text stays put"
    assert widget.curselection() == (0,)
    assert controller.overlay.cget("background") == "#345678"
    assert controller.overlay.itemcget(controller.item, "fill") == "#f0edf4"
    controller.close()
    app.update()
    assert widget.curselection() == (0,)
    assert bool(widget.cget("exportselection")) == export
