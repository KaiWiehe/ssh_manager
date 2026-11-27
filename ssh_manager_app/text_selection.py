"""Read-only drag selection aligned with the original display text."""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import font, ttk
from weakref import WeakSet


NATIVE_HEADER_THEMES = ("vista", "xpnative")


@dataclass(frozen=True)
class DisplayText:
    text: str
    box: tuple[int, int, int, int]
    style: str = ""
    anchor: str = ""
    row: str = ""
    column: str = ""
    font: str = ""
    foreground: str = ""
    wrap: str = ""
    justify: str = ""
    clip_left: int = 0


def widget_option(widget, key):
    try:
        return widget.cget(key) or ""
    except tk.TclError:
        return ""


def label_text(widget):
    variable = widget_option(widget, "textvariable")
    return str(widget.getvar(str(variable)) if variable else widget_option(widget, "text"))


def element_box(widget, element, x, y):
    """Find a themed label element's parcel using Tk's hit testing."""
    if not widget.identify(x, y).endswith(element):
        return None
    left, right = x, x + 1
    top, bottom = y, y + 1
    while left > 0 and widget.identify(left - 1, y).endswith(element):
        left -= 1
    while right < widget.winfo_width() and widget.identify(right, y).endswith(element):
        right += 1
    while top > 0 and widget.identify(x, top - 1).endswith(element):
        top -= 1
    while bottom < widget.winfo_height() and widget.identify(x, bottom).endswith(element):
        bottom += 1
    return left, top, right - left, bottom - top


def heading_text(tree, column, x, y, style):
    # Tk exposes heading hit tests but no bounding box.
    show_tree = "tree" in map(str, tree.cget("show"))
    columns = ["#0"] if show_tree else []
    displayed = tree.cget("displaycolumns")
    columns += list(tree.cget("columns") if displayed == ("#all",) else displayed)
    widths = [tree.column(col, "width") for col in columns]
    index = int(column[1:]) - (0 if show_tree else 1)
    if not 0 <= index < len(columns):
        return None
    top, bottom = y, y + 1
    while top > 0 and tree.identify_region(x, top - 1) == "heading":
        top -= 1
    while bottom < tree.winfo_height() and tree.identify_region(x, bottom) == "heading":
        bottom += 1
    edge = next(i for i in range(x + 1) if tree.identify_region(i, y) in ("heading", "separator"))
    left = edge - round(tree.xview()[0] * sum(widths)) + sum(widths[:index])
    name = f"{style}.Heading"
    theme = ttk.Style(tree)
    padding = tree.tk.splitlist(theme.lookup(name, "padding") or "0")
    border = theme.lookup(name, "borderwidth")
    if theme.theme_use() in NATIVE_HEADER_THEMES:
        # Windows' native HeaderItem element adds four pixels per side.
        border = 4
    elif "lightcolor" in theme.element_options("Treeheading.border"):
        # Clam and its descendants use a two-pixel border for a width of one.
        border = int(border if border != "" else 2)
        if border == 1:
            border = 2
    else:
        border = int(border if border != "" else 1)
    before = tree.winfo_pixels(padding[0]) + border
    after = tree.winfo_pixels(padding[2] if len(padding) > 2 else padding[0]) + border
    box = (left + before, top, widths[index] - before - after, bottom - top)
    heading = tree.heading(column)
    return DisplayText(str(heading["text"]), box, name, heading["anchor"],
                       column=column, clip_left=edge)


def tree_label_inset(tree, row):
    # Native hit-testing cannot see the text origin once it scrolls past the
    # left edge. Measure the same indicator and image in an offscreen cell.
    probe = ttk.Treeview(tree, show="tree", height=1, style=tree.cget("style"))
    try:
        probe.column("#0", width=200, stretch=False)
        item = probe.insert("", "end", text="M", image=tree.item(row, "image"),
                            open=tree.item(row, "open"))
        if tree.get_children(row):
            probe.insert(item, "end")
        probe.place(x=-220, y=0, width=210, height=100)
        probe.update_idletasks()
        left, top, width, height = probe.bbox(item, "#0")
        middle = top + height // 2
        return next((x - left for x in range(left, left + width)
                     if probe.identify_element(x, middle).endswith("text")), 0)
    finally:
        probe.destroy()


def tree_text(tree, x, y):
    region = tree.identify_region(x, y)
    column = tree.identify_column(x)
    style = tree.cget("style") or "Treeview"
    if region == "heading":
        return heading_text(tree, column, x, y, style)
    if region not in ("tree", "cell"):
        return None
    row = tree.identify_row(y)
    hit = tree.identify_element(x, y)
    if not row or "indicator" in hit or "image" in hit:
        return None
    bounds = tree.bbox(row, column)
    if not bounds:
        return None
    left, top, width, height = bounds
    right = left + width
    clip_left = next(i for i in range(x + 1)
                     if tree.identify_region(i, y) in ("tree", "cell"))
    if column == "#0":
        # Find the native text start after indentation and the indicator/image.
        middle = top + height // 2
        visible_start = max(clip_left, left)
        text_left = next((i for i in range(visible_start, min(right, tree.winfo_width()))
                          if tree.identify_element(i, middle).endswith("text")), right)
        if left < clip_left and text_left == clip_left:
            text_left = left + tree_label_inset(tree, row)
        left = text_left
        value = tree.item(row, "text")
    else:
        # Tk's Treeview draws data cells with four horizontal padding pixels.
        left += 4
        right -= 4
        value = tree.set(row, column)
    return DisplayText(str(value), (left, top, right - left, height), style,
                       tree.column(column, "anchor"), row, column, clip_left=clip_left)


def labelframe_text(widget, text, y):
    if widget.cget("labelwidget"):
        return None
    style = ttk.Style(widget)
    name = widget.cget("style") or "TLabelframe"
    label_style = f"{name}.Label"
    margins = widget.tk.splitlist(style.lookup(name, "labelmargins") or "8 0 8 0")
    left = widget.winfo_pixels(margins[0])
    top = widget.winfo_pixels(margins[1] if len(margins) > 1 else margins[0])
    right = widget.winfo_pixels(margins[2] if len(margins) > 2 else margins[0])
    label_font = style.lookup(label_style, "font") or "TkDefaultFont"
    height = font.Font(root=widget, font=label_font).metrics("linespace")
    if not top <= y < top + height:
        return None
    box = (left, top, widget.winfo_width() - left - right, height)
    return DisplayText(text, box, label_style, widget.cget("labelanchor"), font=label_font)


def display_text(widget, x, y):
    if isinstance(widget, ttk.Treeview):
        return tree_text(widget, x, y)
    if isinstance(widget, tk.Listbox):
        index = widget.nearest(y)
        box = widget.bbox(index)
        if box and box[1] <= y < box[1] + box[3]:
            return DisplayText(str(widget.get(index)), box, anchor="nw")
        return None
    if isinstance(widget, ttk.Notebook):
        index = widget.index(f"@{x},{y}")
        label_x = next((i for i in range(widget.winfo_width())
                        if widget.identify(i, y).endswith("label")
                        and widget.index(f"@{i},{y}") == index), None)
        if label_x is None:
            return None
        box = element_box(widget, "label", label_x, y)
        style = widget.cget("style") or "TNotebook"
        return DisplayText(str(widget.tab(index, "text")), box, f"{style}.Tab", "center")
    if isinstance(widget, tk.Canvas):
        cx, cy = widget.canvasx(x), widget.canvasy(y)
        for item in reversed(widget.find_overlapping(cx, cy, cx, cy)):
            if widget.type(item) == "text":
                a, b, c, d = widget.bbox(item)
                box = (int(a - widget.canvasx(0)) + 1, int(b - widget.canvasy(0)), c-a-2, d-b)
                return DisplayText(widget.itemcget(item, "text"), box, anchor="nw",
                                   font=widget.itemcget(item, "font"),
                                   foreground=widget.itemcget(item, "fill"),
                                   wrap=widget.itemcget(item, "width"),
                                   justify=widget.itemcget(item, "justify"))
        return None
    text = label_text(widget)
    if not text:
        return None
    width, height = widget.winfo_width(), widget.winfo_height()
    box = (0, 0, width, height)
    if isinstance(widget, ttk.LabelFrame):
        return labelframe_text(widget, text, y)
    if isinstance(widget, tk.LabelFrame):
        if y > 28:
            return None
        box = (8, 0, width - 8, min(28, height))
    elif isinstance(widget, (ttk.Label, ttk.Checkbutton, ttk.Radiobutton)):
        box = element_box(widget, "label", x, y) or element_box(
            widget, "label", width // 2, height // 2)
        if box is None:
            return None
    elif isinstance(widget, (tk.Label, tk.Message)):
        dx = sum(widget.winfo_pixels(widget_option(widget, key) or 0)
                 for key in ("padx", "borderwidth", "highlightthickness"))
        dy = sum(widget.winfo_pixels(widget_option(widget, key) or 0)
                 for key in ("pady", "borderwidth", "highlightthickness"))
        box = (dx, dy, width - 2 * dx, height - 2 * dy)
        if isinstance(widget, tk.Message):
            wrap = widget_option(widget, "width") or widget.winfo_reqwidth() - 2 * dx
            return DisplayText(text, box, wrap=str(wrap))
    return DisplayText(text, box)


class DisplayTextSelection:
    def __init__(self, app):
        self.app = app
        self.tag = "DisplayTextSelection" + str(id(self))
        self.start = None
        self.overlay = None
        self.item = None
        self.previous_focus = None
        self.previous_selection_owner = None
        self.click_select_trees = WeakSet()
        self.replay = None
        self.anchor = 0
        for sequence, callback in (("<ButtonPress-1>", self.press),
                                   ("<B1-Motion>", self.drag),
                                   ("<ButtonRelease-1>", self.release),
                                   ("<MouseWheel>", self.dismiss)):
            app.bind_class(self.tag, sequence, callback)
        app.bind_all("<Map>", self.mapped, add="+")
        app.bind_all("<ButtonPress-1>", self.outside_press, add="+")
        app.bind_all("<MouseWheel>", self.dismiss, add="+")
        self.install(app)

    def install(self, widget):
        self.install_widget(widget)
        for child in widget.winfo_children():
            self.install(child)

    def install_widget(self, widget):
        if widget is self.overlay or isinstance(
            widget, (tk.Entry, ttk.Entry, tk.Text, tk.Spinbox, ttk.Spinbox, ttk.Combobox,
                     tk.Button, ttk.Button, tk.Menubutton, ttk.Menubutton)
        ):
            return
        tags = widget.bindtags()
        if self.tag not in tags:
            widget.bindtags((self.tag,) + tags)

    def outside_press(self, event):
        if self.overlay is not None and event.widget is not self.overlay:
            self.close()

    def select_cells_on_click(self, tree):
        self.click_select_trees.add(tree)

    @staticmethod
    def deferred(widget, content):
        return (isinstance(widget, (ttk.Notebook, tk.Label, ttk.Label, tk.Message))
                or bool(content.column and not content.row))

    def dismiss(self, _event):
        self.close()

    def mapped(self, event):
        try:
            self.install_widget(event.widget)
        except (tk.TclError, AttributeError):
            pass

    def press(self, event):
        if self.replay is event.widget:
            self.replay = None
            return None
        self.close()
        # Keep a widget's own drag gesture unless Ctrl explicitly requests text.
        if event.widget.bind("<B1-Motion>") and not (event.state & 0x4):
            return None
        try:
            content = display_text(event.widget, event.x, event.y)
        except tk.TclError:
            return None
        if not content or not content.text or min(content.box[2:]) <= 0:
            return None
        self.start = (event.widget, event.x_root, event.y_root, content)
        if content.row and event.widget in self.click_select_trees:
            self.open(event.widget, content, event.x_root, event.y_root)
            if self.overlay is not None:
                return "break"
        # A click on a header still runs its command. A drag shouldn't leave
        # the heading pressed or trigger the command on release.
        if self.deferred(event.widget, content):
            return "break"
        return None

    def drag(self, event):
        if self.start is None:
            return None
        widget, x, y, content = self.start
        if self.overlay is None:
            if abs(event.x_root-x) + abs(event.y_root-y) < 5:
                return None
            self.open(widget, content, x, y)
        if self.overlay is not None:
            return self.select_to(event.x_root, event.y_root)
        return None

    def release(self, event):
        start, self.start = self.start, None
        if self.overlay is not None:
            return "break"
        if start is not None and self.deferred(event.widget, start[3]):
            self.replay = event.widget
            event.widget.event_generate("<ButtonPress-1>", x=event.x, y=event.y)
        return None

    def open(self, widget, content, x_root, y_root):
        x, y, width, height = content.box
        style = ttk.Style(widget)
        name = content.style or widget_option(widget, "style") or widget.winfo_class()
        state = widget.state() if isinstance(widget, ttk.Widget) else ()
        tags = ()
        if content.row:
            if content.row in widget.selection():
                state += ("selected",)
            tags = tuple(widget.tag_configure(tag) for tag in widget.item(content.row, "tags"))

        def option(key, fallback):
            themed = style.lookup(name, key, state)
            if "selected" in state and themed != style.lookup(name, key):
                return themed
            tagged = next((tag[key] for tag in tags if tag.get(key)), "")
            return widget_option(widget, key) or tagged or themed or fallback

        background = option("background", "SystemWindow")
        foreground = content.foreground or option("foreground", "SystemWindowText")
        if content.column and not content.row and style.theme_use() in NATIVE_HEADER_THEMES:
            # Native headers paint their own hover surface over the ttk
            # background. End that hover while the caption is being selected.
            widget.event_generate("<Leave>")
            background = "SystemWindow"
        if isinstance(widget, tk.Listbox):
            item = widget.nearest(y)
            prefix = "select" if item in widget.curselection() else ""
            background = widget.itemcget(item, prefix + "background") or widget.cget(prefix + "background")
            foreground = widget.itemcget(item, prefix + "foreground") or widget.cget(prefix + "foreground")
        selection, selection_text = "SystemHighlight", "SystemHighlightText"
        if widget.winfo_rgb(background) == widget.winfo_rgb(selection):
            selection, selection_text = selection_text, selection
        overlay = tk.Canvas(widget, borderwidth=0, highlightthickness=0, cursor="xterm",
                            background=background, selectborderwidth=0,
                            selectbackground=selection, selectforeground=selection_text)
        text = overlay.create_text(0, 0, anchor="nw", text=content.text, fill=foreground,
                                   font=content.font or option("font", "TkDefaultFont"),
                                   width=content.wrap or option("wraplength", 0),
                                   justify=content.justify or option("justify", "left"))
        # Canvas draws the same Tk text layout as themed labels. Its bounding
        # box includes an extra pixel on each horizontal side.
        left, top, right, bottom = overlay.bbox(text)
        text_width, text_height = right - left - 2, bottom - top
        anchor = str(content.anchor or option("anchor", "w"))
        if anchor == "center":
            anchor = ""
        extra_width, extra_height = max(0, width - text_width), max(0, height - text_height)
        dx = extra_width if "e" in anchor else 0 if "w" in anchor else extra_width // 2
        dy = extra_height if "s" in anchor else 0 if "n" in anchor else extra_height // 2
        text_left = x + dx
        visible_left = max(content.clip_left, text_left)
        visible_right = min(text_left + min(width, text_width), widget.winfo_width() - content.clip_left)
        if visible_right <= visible_left:
            overlay.destroy()
            return
        overlay.move(text, text_left - visible_left, 0)
        overlay.place(x=visible_left, y=y + dy, width=visible_right - visible_left,
                      height=min(height, text_height), bordermode="ignore")
        self.overlay, self.item = overlay, text
        previous_focus = widget.focus_get()
        if previous_focus is not None and previous_focus.winfo_toplevel() is widget.winfo_toplevel():
            self.previous_focus = previous_focus
        overlay.focus_set()
        overlay.update_idletasks()
        self.anchor = self.index_at(x_root, y_root)
        overlay.bind("<ButtonPress-1>", self.overlay_press)
        overlay.bind("<B1-Motion>", lambda e: self.select_to(e.x_root, e.y_root))
        overlay.bind("<Control-a>", self.select_all)
        overlay.bind("<Control-A>", self.select_all)
        overlay.bind("<Control-c>", self.copy)
        overlay.bind("<Control-C>", self.copy)
        overlay.bind("<Escape>", lambda _: self.close())
        overlay.bind("<MouseWheel>", lambda _: self.close())
        self.watch_source(widget, content, overlay)
        if isinstance(widget, ttk.Widget):
            widget.state(["!pressed"])

    def watch_source(self, widget, content, overlay):
        size = (widget.winfo_width(), widget.winfo_height())
        view = (widget.xview(), widget.yview()) if isinstance(widget, ttk.Treeview) else None
        cell = widget.bbox(content.row, content.column) if content.row else None
        timer = None

        def follow_source():
            nonlocal timer
            timer = None
            try:
                changed = not widget.winfo_ismapped() or size != (
                    widget.winfo_width(), widget.winfo_height())
                changed = changed or (view is not None and view != (widget.xview(), widget.yview()))
                if not changed and isinstance(widget, (tk.Label, ttk.Label, tk.Message)):
                    changed = label_text(widget) != content.text
                if cell and not changed:
                    value = (widget.item(content.row, "text") if content.column == "#0"
                             else widget.set(content.row, content.column))
                    changed = (cell != widget.bbox(content.row, content.column)
                               or str(value) != content.text)
                if changed:
                    self.close()
                elif self.overlay is overlay:
                    timer = overlay.after(50, follow_source)
            except tk.TclError:
                self.close()

        def destroyed(event):
            if event.widget is overlay:
                if timer is not None:
                    overlay.after_cancel(timer)
                if self.overlay is overlay:
                    self.overlay = self.item = self.previous_focus = None
                    self.restore_selection_owner()

        overlay.bind("<Destroy>", destroyed)
        timer = overlay.after(50, follow_source)

    def index_at(self, x_root, y_root):
        overlay = self.overlay
        x, y = x_root - overlay.winfo_rootx(), y_root - overlay.winfo_rooty()
        return overlay.index(self.item, f"@{x},{y}")

    def overlay_press(self, event):
        self.anchor = self.index_at(event.x_root, event.y_root)
        self.overlay.select_clear()
        return "break"

    def select_to(self, x_root, y_root):
        start, end = sorted((self.anchor, self.index_at(x_root, y_root)))
        self.overlay.select_clear()
        if start != end:
            self.select_range(start, end)
        return "break"

    def select_range(self, start, end):
        # Canvas selection claims PRIMARY. Keep the previous widget's local
        # selection intact, especially Listbox selections used by actions.
        if self.previous_selection_owner is None:
            owner = self.app.selection_own_get()
            if owner is not None and owner is not self.overlay:
                if owner.tk.getboolean(widget_option(owner, "exportselection") or False):
                    owner.configure(exportselection=False)
                    self.previous_selection_owner = owner
        self.overlay.select_from(self.item, start)
        self.overlay.select_to(self.item, end - 1)

    def select_all(self, _event=None):
        self.select_range(0, self.overlay.index(self.item, "end"))
        return "break"

    def restore_selection_owner(self):
        owner, self.previous_selection_owner = self.previous_selection_owner, None
        if owner is not None:
            try:
                owner.configure(exportselection=True)
            except tk.TclError:
                pass

    def copy(self, _event=None):
        overlay = self.overlay
        if overlay is None:
            return None
        try:
            first = overlay.index(self.item, "sel.first")
            last = overlay.index(self.item, "sel.last")
        except tk.TclError:
            return "break"
        value = overlay.tk.call("string", "range", overlay.itemcget(self.item, "text"), first, last)
        self.app.clipboard_clear()
        self.app.clipboard_append(value)
        return "break"

    def close(self):
        self.start = None
        overlay, self.overlay = self.overlay, None
        self.item = None
        previous_focus, self.previous_focus = self.previous_focus, None
        if overlay is not None:
            try:
                restore_focus = previous_focus is not None and overlay.focus_get() is overlay
                overlay.destroy()
                if restore_focus and previous_focus.winfo_viewable():
                    previous_focus.focus_set()
            except tk.TclError:
                pass
        self.restore_selection_owner()
        return "break"


def install_text_selection(app):
    if not getattr(app, "_display_text_selection", None):
        app._display_text_selection = DisplayTextSelection(app)
    return app._display_text_selection
