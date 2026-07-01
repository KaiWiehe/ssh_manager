from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .dns_lookup import DnsLookupResult, normalize_dns_server


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

        ttk.Label(frame, text="IP oder DNS-Name:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        self._query_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self._query_var, width=42)
        entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        entry.focus_set()

        ttk.Label(frame, text="Richtung:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 8))
        self._mode_var = tk.StringVar(value=MODE_LABELS["auto"])
        combo = ttk.Combobox(frame, textvariable=self._mode_var, values=list(MODE_LABELS.values()), state="readonly", width=18)
        combo.grid(row=1, column=1, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="DNS-Server:").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(0, 14))
        self._dns_server_var = tk.StringVar(value=SYSTEM_DNS_LABEL)
        server_combo = ttk.Combobox(
            frame,
            textvariable=self._dns_server_var,
            values=list(DNS_SERVER_OPTIONS),
            width=30,
        )
        server_combo.grid(row=2, column=1, sticky="ew", pady=(0, 14))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=3, column=0, columnspan=2)
        ttk.Button(btn_frame, text="Auflösen", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        query = self._query_var.get().strip()
        if not query:
            messagebox.showwarning("Leere Eingabe", "Bitte eine IP-Adresse oder einen DNS-Namen eingeben.", parent=self)
            return
        try:
            dns_server = resolve_dns_server_selection(self._dns_server_var.get())
        except ValueError as exc:
            messagebox.showwarning("Ungültiger DNS-Server", str(exc), parent=self)
            return
        self.result = (query, MODE_BY_LABEL.get(self._mode_var.get(), "auto"), dns_server)
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on_parent(self, parent: tk.Tk) -> None:
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


class DnsServerDialog(tk.Toplevel):
    """Selects the resolver used for DNS lookups on a session selection."""

    def __init__(self, parent: tk.Tk, target_count: int):
        super().__init__(parent)
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
        ttk.Label(frame, text=f"DNS-Server für {count_text}:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self._dns_server_var = tk.StringVar(value=SYSTEM_DNS_LABEL)
        combo = ttk.Combobox(
            frame,
            textvariable=self._dns_server_var,
            values=list(DNS_SERVER_OPTIONS),
            width=34,
        )
        combo.grid(row=1, column=0, sticky="ew", pady=(0, 14))
        combo.focus_set()

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0)
        ttk.Button(btn_frame, text="Auflösen", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

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
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


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
        ttk.Label(frame, text=f"DNS/IP-Auflösung läuft… ({count_text})").grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._progress = ttk.Progressbar(frame, mode="indeterminate", length=320)
        self._progress.grid(row=1, column=0, sticky="ew")
        self._progress.start(12)

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
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")


class DnsLookupResultsDialog(tk.Toplevel):
    """Shows DNS/IP lookup results in a compact table."""

    def __init__(self, parent: tk.Tk, results: list[DnsLookupResult]):
        super().__init__(parent)
        self.title("DNS/IP Ergebnisse")
        self.resizable(True, True)
        self._results = list(results)
        self._show_connection_names = any(result.connection_name for result in self._results)
        self.geometry("960x420" if self._show_connection_names else "780x420")
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._build(parent)
        self._center_on_parent(parent)
        self.bind("<Escape>", lambda _e: self.destroy())

    def _build(self, parent: tk.Tk) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        frame = ttk.Frame(self, padding=(10, 10, 10, 4))
        frame.grid(row=0, column=0, sticky="nsew")
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
        self._tree.column("result", width=300, minwidth=160, anchor="w")
        self._tree.column("resolver", width=120, minwidth=90, anchor="w")
        self._tree.column("status", width=100, minwidth=80, anchor="w")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for result in self._results:
            direction = "IP -> DNS" if result.mode == "reverse" else "DNS -> IP"
            result_text = ", ".join(result.results) if result.results else (result.error or "Keine Treffer")
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
        btn_frame.grid(row=1, column=0, sticky="ew")
        ttk.Button(btn_frame, text="Alle kopieren", command=lambda: self._copy_all(parent), width=14).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Ergebnisse kopieren", command=lambda: self._copy_values(parent), width=18).pack(side="left", padx=(0, 6))
        ttk.Button(btn_frame, text="Schließen", command=self.destroy, width=12).pack(side="right")

    def _status_label(self, result: DnsLookupResult) -> str:
        if result.status == "ok":
            return "OK"
        if result.status == "not_found":
            return "Keine Treffer"
        return "Fehler"

    def _copy_all(self, parent: tk.Tk) -> None:
        if self._show_connection_names:
            lines = ["Verbindung\tHostname\tRichtung\tErgebnis\tResolver\tStatus"]
        else:
            lines = ["Eingabe\tRichtung\tErgebnis\tResolver\tStatus"]
        for result in self._results:
            direction = "IP -> DNS" if result.mode == "reverse" else "DNS -> IP"
            values = ", ".join(result.results) if result.results else (result.error or "Keine Treffer")
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
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
