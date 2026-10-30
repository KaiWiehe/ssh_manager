"""Read-only drag selection for display text, without replacing source widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class DisplayTextSelection:
    def __init__(self, app):
        self.app = app
        self.tag = "DisplayTextSelection" + str(id(self))
        self.start = None
        self.overlay = None
        self.source = None
        self.replay = None
        self.anchor = "1.0"
        for sequence, callback in (("<ButtonPress-1>", self.press),
                                   ("<B1-Motion>", self.drag),
                                   ("<ButtonRelease-1>", self.release),
                                   ("<Control-c>", self.copy), ("<Control-C>", self.copy)):
            app.bind_class(self.tag, sequence, callback)
        app.bind_all("<Map>", self.mapped, add="+")
        app.bind_all("<ButtonPress-1>", self.outside_press, add="+")
        app.bind_all("<MouseWheel>", lambda _: self.close(), add="+")
        app.bind_class(self.tag, "<MouseWheel>", self.wheel)
        self.install(app)

    def install(self, widget):
        if not isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, tk.Spinbox, ttk.Spinbox, ttk.Combobox)):
            tags = widget.bindtags()
            if self.tag not in tags:
                widget.bindtags((self.tag,) + tags)
        for child in widget.winfo_children():
            self.install(child)

    def outside_press(self, event):
        if self.overlay is not None and event.widget is not self.overlay:
            self.close()

    @staticmethod
    def deferred(widget):
        return isinstance(widget, ttk.Notebook) or isinstance(widget, (tk.Label, ttk.Label, tk.Message))

    def wheel(self, _event):
        self.close()
        return None

    def mapped(self, event):
        try:
            self.install(event.widget)
        except (tk.TclError, AttributeError):
            pass

    @staticmethod
    def content(widget, x, y):
        """Return display text and its rectangle in widget coordinates."""
        if isinstance(widget, ttk.Treeview):
            region = widget.identify_region(x, y)
            column = widget.identify_column(x)
            if region == "heading":
                # Heading bbox is not exposed; use the visible column widths.
                columns = (["#0"] if "tree" in widget.cget("show") else [])
                displayed = widget.cget("displaycolumns")
                columns += list(widget.cget("columns") if displayed == ("#all",) else displayed)
                left = -int(widget.xview()[0] * sum(widget.column(c, "width") for c in columns))
                for col in columns:
                    width = widget.column(col, "width")
                    if left <= x < left + width:
                        return str(widget.heading(col, "text")), (left, 0, width, 28)
                    left += width
                return None
            row = widget.identify_row(y)
            if region not in ("tree", "cell") or not row:
                return None
            # Leave expand/collapse and checkbox gestures alone.
            element = widget.identify_element(x, y)
            if "indicator" in element or "image" in element:
                return None
            bbox = widget.bbox(row, column)
            value = widget.item(row, "text") if column == "#0" else widget.set(row, column)
            return str(value), bbox
        if isinstance(widget, tk.Listbox):
            index = widget.nearest(y)
            bbox = widget.bbox(index)
            if bbox:
                return str(widget.get(index)), (0, bbox[1], widget.winfo_width(), bbox[3])
            return None
        if isinstance(widget, ttk.Notebook):
            try:
                index = widget.index(f"@{x},{y}")
            except tk.TclError:
                return None
            # An overlay containing the whole tab title also handles clipped tabs.
            return str(widget.tab(index, "text")), (x, y, 220, 28)
        if isinstance(widget, tk.Canvas):
            hits = widget.find_overlapping(widget.canvasx(x), widget.canvasy(y), widget.canvasx(x), widget.canvasy(y))
            for item in reversed(hits):
                if widget.type(item) == "text":
                    a, b, c, d = widget.bbox(item)
                    return widget.itemcget(item, "text"), (a - widget.canvasx(0), b - widget.canvasy(0), c-a, d-b)
            return None
        if isinstance(widget, (ttk.LabelFrame, tk.LabelFrame)):
            if y > 28:
                return None
            text = str(widget.cget("text"))
            return text, (8, 0, min(widget.winfo_width()-8, max(80, len(text)*10)), 28)
        try:
            variable = widget.cget("textvariable")
            text = str(widget.getvar(str(variable))) if variable else str(widget.cget("text"))
        except tk.TclError:
            try:
                text = str(widget.cget("text"))
            except tk.TclError:
                return None
        return (text, (0, 0, widget.winfo_width(), widget.winfo_height())) if text else None

    def press(self, event):
        if self.replay is event.widget:
            self.replay = None
            return None
        self.close()
        try:
            content = self.content(event.widget, event.x, event.y)
        except tk.TclError:
            return None
        if not content or not content[0] or not content[1]:
            return None
        # Preserve application-specific reorder/drag controls. Ctrl+drag selects
        # their caption explicitly; ordinary dragging keeps its original purpose.
        if event.widget.bind("<B1-Motion>") and not (event.state & 0x4):
            return None
        self.start = (event.widget, event.x_root, event.y_root, content)
        # Labels may have immediate click commands. Defer these until release so
        # a drag can select their text without opening a browser or another window.
        if self.deferred(event.widget):
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
            self.select_to(event.x_root, event.y_root)
            return "break"
        return None

    def release(self, event):
        start, self.start = self.start, None
        if self.overlay is not None:
            return "break"
        if start is not None and self.deferred(event.widget):
            self.replay = event.widget
            event.widget.event_generate("<ButtonPress-1>", x=event.x, y=event.y)
        return None

    def open(self, widget, content, x_root, y_root):
        text, (x, y, width, height) = content
        top = widget.winfo_toplevel()
        style = ttk.Style(widget)
        try:
            name = widget.cget("style") or widget.winfo_class()
        except tk.TclError:
            name = widget.winfo_class()
        def option(key, fallback):
            try:
                value = widget.cget(key)
            except tk.TclError:
                value = ""
            return value or style.lookup(name, key) or fallback
        overlay = tk.Text(top, wrap="word", relief="flat", borderwidth=0,
                          highlightthickness=1, padx=3, pady=2, cursor="xterm",
                          background=option("background", "SystemWindow"),
                          foreground=option("foreground", "SystemWindowText"),
                          font=option("font", "TkDefaultFont"), exportselection=False,
                          selectbackground="SystemHighlight", selectforeground="SystemHighlightText")
        # Keep centered captions in place while the user starts a drag on
        # their visible letters (wide buttons otherwise jump to the left).
        anchor = str(option("anchor", "center" if isinstance(widget, (tk.Button, ttk.Button)) else "w"))
        justify = "right" if anchor in ("e", "ne", "se") else "center" if anchor in ("center", "n", "s") else "left"
        overlay.tag_configure("content", justify=justify)
        overlay.insert("1.0", text, "content")
        overlay.configure(state="disabled")
        left = max(0, widget.winfo_rootx() - top.winfo_rootx() + int(x))
        upper = max(0, widget.winfo_rooty() - top.winfo_rooty() + int(y))
        overlay.place(x=left, y=upper, width=max(30, min(max(int(width), 100), top.winfo_width()-left)),
                      height=max(24, min(max(int(height), 24), top.winfo_height()-upper)))
        overlay.lift()
        overlay.focus_set()
        self.overlay, self.source = overlay, widget
        overlay.update_idletasks()
        self.anchor = overlay.index(f"@{x_root-overlay.winfo_rootx()},{y_root-overlay.winfo_rooty()}")
        overlay.bind("<ButtonPress-1>", self.overlay_press)
        overlay.bind("<B1-Motion>", lambda e: self.select_to(e.x_root, e.y_root))
        overlay.bind("<Control-a>", self.select_all)
        overlay.bind("<Control-A>", self.select_all)
        overlay.bind("<Control-c>", self.copy)
        overlay.bind("<Control-C>", self.copy)
        overlay.bind("<Escape>", lambda _: self.close())
        position = (widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height())
        timer = None
        def follow_source():
            nonlocal timer
            timer = None
            try:
                current = (widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_width(), widget.winfo_height())
                if not widget.winfo_ismapped() or current != position:
                    self.close()
                elif self.overlay is overlay:
                    timer = overlay.after(50, follow_source)
            except tk.TclError:
                self.close()
        def cancel_timer(event):
            if event.widget is overlay and timer is not None:
                overlay.after_cancel(timer)
        overlay.bind("<Destroy>", cancel_timer)
        timer = overlay.after(50, follow_source)
        # A drag on a command widget must never leave its pressed appearance on.
        if isinstance(widget, ttk.Widget):
            widget.state(["!pressed"])
        self.select_to(x_root, y_root)

    def overlay_press(self, event):
        self.anchor = self.overlay.index(f"@{event.x},{event.y}")
        self.overlay.tag_remove("sel", "1.0", "end")
        return "break"

    def select_to(self, x_root, y_root):
        text = self.overlay
        end = text.index(f"@{x_root-text.winfo_rootx()},{y_root-text.winfo_rooty()}")
        text.tag_remove("sel", "1.0", "end")
        a, b = (self.anchor, end) if text.compare(self.anchor, "<=", end) else (end, self.anchor)
        text.tag_add("sel", a, b)
        return "break"

    def select_all(self, _event=None):
        self.overlay.tag_add("sel", "1.0", "end-1c")
        return "break"

    def copy(self, _event=None):
        if self.overlay is None:
            return None
        try:
            value = self.overlay.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self.app.clipboard_clear()
        self.app.clipboard_append(value)
        return "break"

    def close(self):
        self.start = None
        overlay, self.overlay = self.overlay, None
        self.source = None
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass
        return "break"


def install_text_selection(app):
    if not getattr(app, "_display_text_selection", None):
        app._display_text_selection = DisplayTextSelection(app)
    return app._display_text_selection
