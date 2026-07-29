from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .dialogs_certificates import RemoteFolderBrowserDialog


class CertificateReplaceDialog(tk.Toplevel):
    """Collect certificate files and persistent remote search roots."""

    def __init__(self, parent, target_count: int, whitelist: list[str], favorites: list[dict], on_whitelist_changed, reference_sessions=None):
        super().__init__(parent)
        self.title("Zertifikate ersetzen")
        self.geometry("780x620")
        self.result = None
        self._files: list[str] = []
        self._favorites = [item for item in favorites if item.get("mode", "command") == "command" and str(item.get("command", "")).strip()]
        self._on_whitelist_changed = on_whitelist_changed
        self._reference_sessions = reference_sessions or []
        self._sudo_password = tk.StringVar()
        self._keystore_password = tk.StringVar()
        self._close_on_success = tk.BooleanVar(value=False)
        self._build(target_count, whitelist)
        self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build(self, target_count, whitelist):
        root = ttk.Frame(self, padding=14); root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        ttk.Label(root, text=f"Zertifikate auf {target_count} Host(s) ersetzen", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Label(root, text="Es werden nur reguläre Dateien mit exakt gleichem Namen innerhalb der Whitelist ersetzt.", foreground="#666666").pack(anchor="w", pady=(2, 10))
        files = ttk.LabelFrame(root, text="Neue Zertifikatsdateien", padding=8); files.pack(fill="both", expand=True)
        self._files_list = tk.Listbox(files, height=7); self._files_list.pack(fill="both", expand=True)
        row = ttk.Frame(files); row.pack(anchor="w", pady=(6, 0))
        ttk.Button(row, text="Dateien auswählen…", command=self._choose).pack(side="left")
        ttk.Button(row, text="Auswahl entfernen", command=self._remove).pack(side="left", padx=6)
        roots = ttk.LabelFrame(root, text="Whitelist-Suchpfade", padding=8); roots.pack(fill="x", pady=(10, 0))
        self._roots = scrolledtext.ScrolledText(roots, height=4, wrap="none"); self._roots.pack(fill="x")
        self._roots.insert("1.0", "\n".join(whitelist))
        root_controls = ttk.Frame(roots); root_controls.pack(fill="x", pady=(6, 0))
        self._browse_roots_button = ttk.Button(root_controls, text="Auf Server durchsuchen…", command=self._browse_roots)
        self._browse_roots_button.pack(side="left")
        if not self._reference_sessions: self._browse_roots_button.configure(state="disabled")
        ttk.Label(roots, text="Absolute Linux-Pfade, einer pro Zeile. Die Liste wird dauerhaft gespeichert; leer blockiert die Suche.", foreground="#666666").pack(anchor="w", pady=(4, 0))
        secure = ttk.Frame(root); secure.pack(fill="x", pady=(10, 0)); secure.columnconfigure(1, weight=1)
        ttk.Label(secure, text="sudo-Passwort (optional):").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(secure, textvariable=self._sudo_password, show="•").grid(row=0, column=1, sticky="ew")
        ttk.Checkbutton(secure, text="Tab nach Erfolg schließen", variable=self._close_on_success).grid(row=0, column=2, padx=(10, 0))
        ttk.Label(secure, text="Keystore-/P12-Passwort (optional):").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(6, 0))
        ttk.Entry(secure, textvariable=self._keystore_password, show="•").grid(row=1, column=1, sticky="ew", pady=(6, 0))
        ttk.Label(secure, text="Ohne Passwort werden für JKS/P12 nur Dateizeitstempel angezeigt.", foreground="#666666").grid(row=2, column=1, sticky="w", pady=(3, 0))
        after = ttk.LabelFrame(root, text="Nachaktion (optional)", padding=8); after.pack(fill="x", pady=(10, 0)); after.columnconfigure(1, weight=1)
        labels = [str(item.get("name") or item.get("label") or item["command"].splitlines()[0]) for item in self._favorites]
        self._favorite = ttk.Combobox(after, values=labels, state="readonly"); self._favorite.grid(row=0, column=0, columnspan=2, sticky="ew")
        self._favorite.bind("<<ComboboxSelected>>", lambda _event: self._apply_favorite())
        self._post = scrolledtext.ScrolledText(after, height=3, wrap="word"); self._post.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        buttons = ttk.Frame(root); buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Abbrechen", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="Treffer suchen…", command=self._ok).pack(side="right", padx=8)

    def _choose(self):
        for path in filedialog.askopenfilenames(parent=self, title="Neue Zertifikatsdateien auswählen"):
            if path and path not in self._files: self._files.append(path)
        self._refresh()

    def _remove(self):
        selected = {self._files_list.get(i) for i in self._files_list.curselection()}
        self._files = [path for path in self._files if path not in selected]; self._refresh()

    def _refresh(self):
        self._files_list.delete(0, "end")
        for path in self._files: self._files_list.insert("end", path)

    def _roots_value(self):
        return list(dict.fromkeys(line.strip().rstrip("/") or "/" for line in self._roots.get("1.0", "end").splitlines() if line.strip()))

    def _browse_roots(self):
        roots = self._roots_value()
        dialog = RemoteFolderBrowserDialog(self, self._reference_sessions, roots[-1] if roots else "/", self._sudo_password.get())
        self.wait_window(dialog)
        if dialog.result and dialog.result not in roots:
            roots.append(dialog.result)
            self._roots.delete("1.0", "end")
            self._roots.insert("1.0", "\n".join(roots))

    def _apply_favorite(self):
        index = self._favorite.current()
        if index >= 0:
            self._post.delete("1.0", "end"); self._post.insert("1.0", str(self._favorites[index]["command"]).strip())

    def _ok(self):
        roots = self._roots_value(); self._on_whitelist_changed(roots)
        if not roots:
            messagebox.showwarning("Leere Whitelist", "Bitte mindestens einen Whitelist-Suchpfad angeben.", parent=self); return
        if any(not root.startswith("/") for root in roots):
            messagebox.showwarning("Ungültiger Pfad", "Whitelist-Pfade müssen absolut sein.", parent=self); return
        if not self._files or any(not Path(path).is_file() for path in self._files):
            messagebox.showwarning("Dateien fehlen", "Bitte mindestens eine vorhandene Zertifikatsdatei auswählen.", parent=self); return
        names = [Path(path).name for path in self._files]
        if len(names) != len(set(names)):
            messagebox.showwarning("Doppelte Namen", "Ausgewählte Dateien müssen unterschiedliche Namen haben.", parent=self); return
        self.result = {"files": list(self._files), "roots": roots, "sudo_password": self._sudo_password.get(), "keystore_password": self._keystore_password.get(), "post_command": self._post.get("1.0", "end").strip(), "close_on_success": self._close_on_success.get()}
        self.destroy()

    def _cancel(self): self.result = None; self.destroy()


class CertificateReplacePreviewDialog(tk.Toplevel):
    def __init__(self, parent, report: str, matches: list[tuple[int, str, str, str, str, str]]):
        super().__init__(parent); self.title("Zertifikate ersetzen – Vorschau"); self.geometry("850x600"); self.result = False
        frame = ttk.Frame(self, padding=14); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Prüfe die Treffer. Erst mit ‚Ersetzen‘ werden Dateien geändert.", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Alle Treffer sind vorausgewählt. Entferne den Haken bei Dateien, die nicht ersetzt werden sollen.").pack(anchor="w", pady=(3, 7))
        choices = ttk.LabelFrame(frame, text="Zu ersetzende Dateien", padding=6); choices.pack(fill="both", expand=True)
        canvas = tk.Canvas(choices, highlightthickness=0)
        scrollbar = ttk.Scrollbar(choices, orient="vertical", command=canvas.yview)
        self._choices_frame = ttk.Frame(canvas)
        self._choices_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        choices_window = canvas.create_window((0, 0), window=self._choices_frame, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(choices_window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        self._choice_vars: list[tuple[tuple[int, str, str], tk.BooleanVar]] = []
        for host_index, host, name, target, modified, expiry in matches:
            value = tk.BooleanVar(value=True)
            label = f"{host}: {name} → {target}\n    Dateizeitstempel: {modified or 'nicht ermittelt'} | Gültig bis: {expiry or 'nicht ermittelt'}"
            tk.Checkbutton(self._choices_frame, text=label, variable=value, anchor="w", justify="left", wraplength=750).pack(fill="x", anchor="w", pady=2)
            self._choice_vars.append(((host_index, name, target), value))
        controls = ttk.Frame(frame); controls.pack(fill="x", pady=(6, 0))
        ttk.Button(controls, text="Alle auswählen", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(controls, text="Alle abwählen", command=lambda: self._set_all(False)).pack(side="left", padx=(6, 0))
        details = ttk.LabelFrame(frame, text="Hinweise und Scan-Ergebnis", padding=6); details.pack(fill="both", expand=True, pady=(8, 0))
        text = scrolledtext.ScrolledText(details, wrap="word", height=11); text.pack(fill="both", expand=True)
        text.tag_configure("host", font=("Segoe UI", 10, "bold"))
        text.tag_configure("warning", foreground="#b8860b")
        text.tag_configure("error", foreground="#c62828")
        for line in report.splitlines(keepends=True):
            tag = self._line_tag(line.rstrip("\n"))
            text.insert("end", line, tag)
        text.configure(state="disabled")
        buttons = ttk.Frame(frame); buttons.pack(anchor="e")
        ttk.Button(buttons, text="Abbrechen", command=self._cancel).pack(side="right")
        ttk.Button(buttons, text="Ersetzen", command=self._confirm).pack(side="right", padx=8)
        self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self._cancel)
    def _set_all(self, selected: bool):
        for _key, value in self._choice_vars: value.set(selected)

    def _confirm(self):
        self.result = {key for key, value in self._choice_vars if value.get()}
        self.destroy()

    def _cancel(self): self.result = None; self.destroy()

    @staticmethod
    def _line_tag(line: str) -> str | None:
        if line.startswith("  HINWEIS:"):
            return "warning"
        if line.startswith("  FEHLER:"):
            return "error"
        if " (" in line and line.endswith(")") and not line.startswith("  "):
            return "host"
        return None


class CertificateReplaceScanProgressDialog(tk.Toplevel):
    """Modal indeterminate progress indicator while remote certificate scans run."""
    def __init__(self, parent, target_count: int):
        super().__init__(parent); self.title("Zertifikate suchen"); self.resizable(False, False)
        self._cancel_event = threading.Event(); self.transient(parent); self.grab_set(); self.protocol("WM_DELETE_WINDOW", self._cancel)
        frame = ttk.Frame(self, padding=18); frame.pack(fill="both", expand=True)
        count = "1 Host" if target_count == 1 else f"{target_count} Hosts"
        ttk.Label(frame, text=f"Zertifikate werden gesucht … ({count})").pack(anchor="w", pady=(0, 10))
        self._progress = ttk.Progressbar(frame, mode="indeterminate", length=320); self._progress.pack(fill="x"); self._progress.start(12)
        self.update_idletasks(); self.geometry(f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 80}")
    @property
    def cancelled(self): return self._cancel_event.is_set()
    def _cancel(self): self._cancel_event.set(); self.close()
    def close(self):
        try: self._progress.stop()
        except tk.TclError: pass
        try: self.destroy()
        except tk.TclError: pass
