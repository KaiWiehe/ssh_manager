from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .dns_lookup import DnsLookupResult


MODE_LABELS = {
    "auto": "Automatisch",
    "forward": "DNS -> IP",
    "reverse": "IP -> DNS",
}

MODE_BY_LABEL = {label: key for key, label in MODE_LABELS.items()}


class DnsLookupDialog(tk.Toplevel):
    """Dialog for one manual DNS/IP lookup query."""

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("DNS/IP auflösen")
        self.resizable(False, False)
        self.result: tuple[str, str] | None = None
        self.transient(parent)
        self.grab_set()
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

        ttk.Label(frame, text="Richtung:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(0, 14))
        self._mode_var = tk.StringVar(value=MODE_LABELS["auto"])
        combo = ttk.Combobox(frame, textvariable=self._mode_var, values=list(MODE_LABELS.values()), state="readonly", width=18)
        combo.grid(row=1, column=1, sticky="w", pady=(0, 14))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2)
        ttk.Button(btn_frame, text="Auflösen", command=self._on_ok, width=12).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=12).pack(side="left", padx=4)

    def _on_ok(self) -> None:
        query = self._query_var.get().strip()
        if not query:
            messagebox.showwarning("Leere Eingabe", "Bitte eine IP-Adresse oder einen DNS-Namen eingeben.", parent=self)
            return
        self.result = (query, MODE_BY_LABEL.get(self._mode_var.get(), "auto"))
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


class DnsLookupResultsDialog(tk.Toplevel):
    """Shows DNS/IP lookup results in a compact table."""

    def __init__(self, parent: tk.Tk, results: list[DnsLookupResult]):
        super().__init__(parent)
        self.title("DNS/IP Ergebnisse")
        self.resizable(True, True)
        self.geometry("780x420")
        self._results = list(results)
        self.transient(parent)
        self.grab_set()
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

        columns = ("direction", "result", "resolver", "status")
        self._tree = ttk.Treeview(frame, columns=columns, show="tree headings", selectmode="extended")
        self._tree.heading("#0", text="Eingabe")
        self._tree.heading("direction", text="Richtung")
        self._tree.heading("result", text="Ergebnis")
        self._tree.heading("resolver", text="Resolver")
        self._tree.heading("status", text="Status")
        self._tree.column("#0", width=180, minwidth=130)
        self._tree.column("direction", width=80, minwidth=75, anchor="center")
        self._tree.column("result", width=300, minwidth=160)
        self._tree.column("resolver", width=120, minwidth=90)
        self._tree.column("status", width=100, minwidth=80)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for result in self._results:
            direction = "IP -> DNS" if result.mode == "reverse" else "DNS -> IP"
            result_text = ", ".join(result.results) if result.results else (result.error or "Keine Treffer")
            self._tree.insert(
                "",
                "end",
                text=result.query,
                values=(direction, result_text, result.resolver, self._status_label(result)),
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
        lines = ["Eingabe\tRichtung\tErgebnis\tResolver\tStatus"]
        for result in self._results:
            direction = "IP -> DNS" if result.mode == "reverse" else "DNS -> IP"
            values = ", ".join(result.results) if result.results else (result.error or "Keine Treffer")
            lines.append(f"{result.query}\t{direction}\t{values}\t{result.resolver}\t{self._status_label(result)}")
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
