from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .dns_lookup import DnsLookupResult, normalize_dns_server
from .ui_components import install_context_help, build_dialog_actions, build_dialog_header, center_on_parent, fit_window_to_parent, set_validation_state


MODE_LABELS = {
    "auto": "Automatisch",
    "forward": "DNS -> IP",
    "reverse": "IP -> DNS",
}

MODE_BY_LABEL = {label: key for key, label in MODE_LABELS.items()}

SYSTEM_DNS_LABEL = "Aktueller DNS (System)"
DNS_SERVER_OPTIONS = {
    SYSTEM_DNS_LABEL: None,
    "Google (8.8.8.8)": "8.8.8.8",
    "Cloudflare (1.1.1.1)": "1.1.1.1",
    "Quad9 (9.9.9.9)": "9.9.9.9",
    "OpenDNS (208.67.222.222)": "208.67.222.222",
}


def resolve_dns_server_selection(value: str) -> str | None:
    cleaned = value.strip()
    if cleaned in DNS_SERVER_OPTIONS:
        return DNS_SERVER_OPTIONS[cleaned]
    return normalize_dns_server(cleaned)


class DnsLookupDialog(tk.Toplevel):
    """Dialog for one manual DNS/IP lookup query."""

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        install_context_help(self, "network", layout="grid", row=3)
        self.title("DNS/IP auflösen")
        self.resizable(False, False)
        self.result: tuple[str, str, str | None] | None = None
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build()
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        build_dialog_header(
            frame,
            "DNS/IP auflösen",
            "Vorwärts- oder Rückwärtsauflösung mit dem gewünschten Resolver starten.",
            columnspan=2,
        )

        ttk.Label(frame, text="IP, DNS-Name oder URL:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        self._query_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self._query_var, width=42)
        entry.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        self._query_entry = entry
        entry.focus_set()

        ttk.Label(frame, text="Richtung:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        self._mode_var = tk.StringVar(value=MODE_LABELS["auto"])
        combo = ttk.Combobox(frame, textvariable=self._mode_var, values=list(MODE_LABELS.values()), state="readonly", width=18)
        combo.grid(row=2, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="DNS-Server:").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(0, 14))
        self._dns_server_var = tk.StringVar(value=SYSTEM_DNS_LABEL)
        server_combo = ttk.Combobox(
            frame,
            textvariable=self._dns_server_var,
            values=list(DNS_SERVER_OPTIONS),
            width=30,
        )
        server_combo.grid(row=3, column=1, sticky="ew", pady=(0, 14))
        self._server_combo = server_combo
        self._validation_var = tk.StringVar()
        ttk.Label(frame, textvariable=self._validation_var, style="ValidationError.TLabel").grid(
            row=4, column=0, columnspan=2, sticky="w"
        )

        build_dialog_actions(
            frame,
            row=5,
            columnspan=2,
            primary_text="Auflösen",
            primary_command=self._on_ok,
            cancel_command=self._on_cancel,
        )

    def _on_ok(self) -> None:
        query = self._query_var.get().strip()
        if not query:
            set_validation_state(
                getattr(self, "_query_entry", None),
                getattr(self, "_validation_var", None),
                "Bitte eine IP-Adresse, einen DNS-Namen oder eine URL eingeben.",
            )
            messagebox.showwarning("Leere Eingabe", "Bitte eine IP-Adresse, einen DNS-Namen oder eine URL eingeben.", parent=self)
            return
        try:
            dns_server = resolve_dns_server_selection(self._dns_server_var.get())
        except ValueError as exc:
            set_validation_state(
                getattr(self, "_server_combo", None),
                getattr(self, "_validation_var", None),
                str(exc),
                normal_style="TCombobox",
                invalid_style="Invalid.TCombobox",
            )
            messagebox.showwarning("Ungültiger DNS-Server", str(exc), parent=self)
            return
        set_validation_state(getattr(self, "_query_entry", None), getattr(self, "_validation_var", None))
        self.result = (query, MODE_BY_LABEL.get(self._mode_var.get(), "auto"), dns_server)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        center_on_parent(self, parent)


class DnsServerDialog(tk.Toplevel):
    """Selects the resolver used for DNS lookups on a session selection."""

    def __init__(self, parent: tk.Tk, target_count: int):
        super().__init__(parent)
        install_context_help(self, "network", layout="grid", row=3)
        self.title("DNS-Server auswählen")
        self.resizable(False, False)
        self.result: str | None = None
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build(target_count)
        self._center_on_parent(parent)
        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self._on_cancel())

    def _build(self, target_count: int) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        count_text = "eine Verbindung" if target_count == 1 else f"{target_count} Verbindungen"
        build_dialog_header(
            frame,
            "DNS-Server auswählen",
            f"Resolver für {count_text} festlegen.",
        )
        self._dns_server_var = tk.StringVar(value=SYSTEM_DNS_LABEL)
        combo = ttk.Combobox(
            frame,
            textvariable=self._dns_server_var,
            values=list(DNS_SERVER_OPTIONS),
            width=34,
        )
        combo.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        combo.focus_set()

        build_dialog_actions(
            frame,
            row=2,
            primary_text="Auflösen",
            primary_command=self._on_ok,
            cancel_command=self._on_cancel,
        )

    def _on_ok(self) -> None:
        try:
            dns_server = resolve_dns_server_selection(self._dns_server_var.get())
        except ValueError as exc:
            messagebox.showwarning("Ungültiger DNS-Server", str(exc), parent=self)
            return
        self.result = dns_server or ""
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        center_on_parent(self, parent)


class DnsLookupProgressDialog(tk.Toplevel):
    """Small modal progress indicator while DNS lookups run in the background."""

    def __init__(self, parent: tk.Tk, target_count: int):
        super().__init__(parent)
        self.title("DNS/IP auflösen")
        self.resizable(False, False)
        self._cancel_event = threading.Event()
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._progress: ttk.Progressbar | None = None
        self._build(target_count)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _e: self._on_cancel())

    def _build(self, target_count: int) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)

        count_text = "1 Eintrag" if target_count == 1 else f"{target_count} Einträge"
        build_dialog_header(frame, "DNS/IP-Auflösung läuft", count_text)
        self._progress = ttk.Progressbar(frame, mode="indeterminate", length=320)
        self._progress.grid(row=1, column=0, sticky="ew")
        self._progress.start(12)
        ttk.Button(
            frame,
            text="Abbrechen",
            command=lambda: DnsLookupProgressDialog._on_cancel(self),
            width=12,
        ).grid(row=2, column=0, sticky="e", pady=(12, 0))

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _on_cancel(self) -> None:
        self._cancel_event.set()
        self.close()

    def close(self) -> None:
        try:
            if self._progress is not None:
                self._progress.stop()
        except tk.TclError:
            pass
        try:
            self.grab_release()
        except tk.TclError:
            pass
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _center_on_parent(self, parent: tk.Tk) -> None:
        center_on_parent(self, parent)


class DnsLookupResultsDialog(tk.Toplevel):
    """Shows DNS/IP lookup results in a compact table."""

    def __init__(self, parent: tk.Tk, results: list[DnsLookupResult]):
        super().__init__(parent)
        install_context_help(self, "network", layout="grid", row=3)
        self.title("DNS/IP Ergebnisse")
        self.resizable(True, True)
        self._results = list(results)
        self._show_connection_names = any(result.connection_name for result in self._results)
        self._selection_entry: tk.Entry | None = None
        self._selection_entry_var: tk.StringVar | None = None
        self._selection_anchor: int | None = None
        self.geometry("1080x420" if self._show_connection_names else "900x420")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build(parent)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _build(self, parent: tk.Tk) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        successful = sum(result.status == "ok" for result in self._results)
        header = ttk.Frame(self, padding=(10, 10, 10, 0))
        header.grid(row=0, column=0, sticky="ew")
        build_dialog_header(
            header,
            "DNS/IP-Ergebnisse",
            f"{successful} von {len(self._results)} Abfragen erfolgreich.",
        )

        frame = ttk.Frame(self, padding=(10, 10, 10, 4))
        frame.grid(row=1, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        if self._show_connection_names:
            columns = ("query", "direction", "result", "resolver", "status")
            first_heading = "Verbindung"
        else:
            columns = ("direction", "result", "resolver", "status")
            first_heading = "Eingabe"
        self._tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="extended")
        self._tree.heading("#0", text=first_heading, anchor="w")
        if self._show_connection_names:
            self._tree.heading("query", text="Hostname", anchor="w")
        self._tree.heading("direction", text="Richtung", anchor="w")
        self._tree.heading("result", text="Ergebnis", anchor="w")
        self._tree.heading("resolver", text="Resolver", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")
        self._tree.column("#0", width=180, minwidth=130, anchor="w")
        if self._show_connection_names:
            self._tree.column("query", width=180, minwidth=130, anchor="w")
        self._tree.column("direction", width=80, minwidth=75, anchor="w")
        self._tree.column("result", width=260, minwidth=160, anchor="w")
        self._tree.column("resolver", width=190, minwidth=130, anchor="w")
        self._tree.column("status", width=100, minwidth=80, anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self._tree.bind("<ButtonPress-1>", self._start_cell_selection, add="+")
        self._tree.bind("<B1-Motion>", self._extend_cell_selection, add="+")

        for result in self._results:
            direction = "IP -> DNS" if result.mode == "reverse" else "DNS -> IP"
            result_text = self._result_label(result)
            if self._show_connection_names:
                row_text = result.connection_name
                values = (result.query, direction, result_text, result.resolver, self._status_label(result))
            else:
                row_text = result.query
                values = (direction, result_text, result.resolver, self._status_label(result))
            self._tree.insert(
                "",
                "end",
                text=row_text,
                values=values,
            )

        btn_frame = ttk.Frame(self, padding=(10, 4, 10, 10))
        btn_frame.grid(row=2, column=0, sticky="ew")
        ttk.Button(btn_frame, text="Alle kopieren", command=lambda: self._copy_all(parent), width=14).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Ergebnisse kopieren", command=lambda: self._copy_values(parent), width=18).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Schließen", command=self.destroy, width=12, style="Accent.TButton").pack(side="right")

    def _start_cell_selection(self, event: tk.Event) -> str | None:
        item_id = self._tree.identify_row(event.y)
        column_id = self._tree.identify_column(event.x)
        region = self._tree.identify_region(event.x, event.y)
        if not item_id or not column_id or region not in {"tree", "cell"}:
            self._close_cell_selection()
            return None

        bbox = self._tree.bbox(item_id, column_id)
        if not bbox:
            self._close_cell_selection()
            return None
        text = self._cell_text(item_id, column_id)
        self._close_cell_selection()

        cell_x, cell_y, cell_width, cell_height = bbox
        self._selection_entry_var = tk.StringVar(value=text)
        style = ttk.Style(self)
        background = style.lookup("Treeview", "background") or "SystemWindow"
        foreground = style.lookup("Treeview", "foreground") or "SystemWindowText"
        font = style.lookup("Treeview", "font") or "TkDefaultFont"
        entry = tk.Entry(
            self._tree,
            textvariable=self._selection_entry_var,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            readonlybackground=background,
            background=background,
            foreground=foreground,
            selectbackground="SystemHighlight",
            selectforeground="SystemHighlightText",
            selectborderwidth=0,
            insertwidth=0,
            font=font,
        )
        entry.configure(state="readonly")
        entry.place(x=cell_x + 1, y=cell_y, width=max(1, cell_width - 2), height=cell_height)
        entry.focus_set()
        self._selection_entry = entry

        index = int(entry.index(f"@{max(0, event.x - cell_x - 1)}"))
        self._selection_anchor = index
        entry.icursor(index)
        entry.selection_clear()
        entry.bind("<ButtonPress-1>", self._restart_cell_selection)
        entry.bind("<B1-Motion>", self._extend_cell_selection)
        entry.bind("<Escape>", self._close_cell_selection)
        entry.bind("<Control-a>", self._select_entire_cell)
        entry.bind("<Control-A>", self._select_entire_cell)
        return "break"

    def _restart_cell_selection(self, event: tk.Event) -> str:
        entry = self._selection_entry
        if entry is not None:
            index = int(entry.index(f"@{event.x}"))
            self._selection_anchor = index
            entry.icursor(index)
            entry.selection_clear()
        return "break"

    def _extend_cell_selection(self, event: tk.Event) -> str | None:
        entry = self._selection_entry
        anchor = self._selection_anchor
        if entry is None or anchor is None:
            return None
        try:
            pointer_x = event.x_root - entry.winfo_rootx()
            index = int(entry.index(f"@{pointer_x}"))
            entry.selection_clear()
            if index != anchor:
                entry.selection_range(min(anchor, index), max(anchor, index))
            entry.icursor(index)
        except tk.TclError:
            self._close_cell_selection()
        return "break"

    def _select_entire_cell(self, _event: tk.Event | None = None) -> str:
        entry = self._selection_entry
        if entry is not None:
            entry.selection_range(0, "end")
            entry.icursor("end")
        return "break"

    def _close_cell_selection(self, _event: tk.Event | None = None) -> str:
        entry = getattr(self, "_selection_entry", None)
        if entry is not None:
            try:
                entry.destroy()
            except tk.TclError:
                pass
        self._selection_entry = None
        self._selection_entry_var = None
        self._selection_anchor = None
        return "break"

    def _cell_text(self, item_id: str, column_id: str) -> str:
        if column_id == "#0":
            return str(self._tree.item(item_id, "text"))
        try:
            value_index = int(column_id[1:]) - 1
        except (TypeError, ValueError):
            return ""
        values = self._tree.item(item_id, "values")
        if value_index < 0 or value_index >= len(values):
            return ""
        return str(values[value_index])

    def _status_label(self, result: DnsLookupResult) -> str:
        if result.status == "ok":
            return "OK"
        if result.status == "not_found":
            return "Keine Treffer"
        return "Fehler"

    def _result_label(self, result: DnsLookupResult) -> str:
        if result.results:
            return ", ".join(result.results)
        if result.status == "not_found":
            return "Keine Treffer"
        error = " ".join((result.error or "").split())
        if not error:
            return "DNS-Abfrage fehlgeschlagen"
        if "#< CLIXML" in error or len(error) > 80:
            return "DNS-Abfrage fehlgeschlagen"
        return error

    def _copy_all(self, parent: tk.Tk) -> None:
        if self._show_connection_names:
            lines = ["Verbindung\tHostname\tRichtung\tErgebnis\tResolver\tStatus"]
        else:
            lines = ["Eingabe\tRichtung\tErgebnis\tResolver\tStatus"]
        for result in self._results:
            direction = "IP -> DNS" if result.mode == "reverse" else "DNS -> IP"
            values = self._result_label(result)
            row = f"{result.query}\t{direction}\t{values}\t{result.resolver}\t{self._status_label(result)}"
            if self._show_connection_names:
                row = f"{result.connection_name}\t{row}"
            lines.append(row)
        self._copy(parent, "\n".join(lines))

    def _copy_values(self, parent: tk.Tk) -> None:
        values = []
        for result in self._results:
            values.extend(result.results)
        self._copy(parent, "\n".join(values))

    def _copy(self, parent: tk.Tk, text: str) -> None:
        parent.clipboard_clear()
        parent.clipboard_append(text)

    def _center_on_parent(self, parent: tk.Tk) -> None:
        preferred_width = 1080 if self._show_connection_names else 900
        fit_window_to_parent(self, parent, preferred_width, 520, min_width=680, min_height=360)
