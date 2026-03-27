"""
SSH-Manager – öffnet mehrere WinSCP-Sessions als SSH-Tabs in Windows Terminal.
Benötigt: Python 3.8+, Windows, Windows Terminal (wt.exe), Git Bash-Profil.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote
import winreg

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
REGISTRY_PATH = r"Software\Martin Prikryl\WinSCP 2\Sessions"
SKIP_SESSIONS = {"Default Settings"}
QUICK_USERS = ["tool-admin", "dev-sys", "de-nb-statist"]
DEFAULT_USER = "tool-admin"
WINDOW_TITLE = "SSH-Manager"
WINDOW_MIN_SIZE = (600, 450)

# ---------------------------------------------------------------------------
# Datenmodell
# ---------------------------------------------------------------------------
@dataclass
class Session:
    """Repräsentiert eine WinSCP-Session aus der Registry."""
    key: str                        # originaler Registry-Subkey-Name
    display_name: str               # URL-dekodierter Session-Name (letzter Teil)
    folder_path: list[str]          # URL-dekodierte Ordnerpfad-Teile
    hostname: str                   # HostName-Wert aus der Registry
    username: str = ""              # UserName-Wert (optional)
    port: int = 22                  # PortNumber (default 22)

    @property
    def folder_key(self) -> str:
        """Ordner-Pfad als String, z.B. 'Extern/Sub'."""
        return "/".join(self.folder_path)


# ---------------------------------------------------------------------------
# Reine Hilfsfunktionen (testbar ohne GUI/Registry)
# ---------------------------------------------------------------------------
def parse_session_key(key: str) -> tuple[list[str], str]:
    """
    Zerlegt einen WinSCP-Registry-Subkey-Namen in Ordner-Pfad und Session-Name.
    URL-Encoding wird dekodiert.

    Beispiele:
      "Extern/Bundo"                  → (["Extern"], "Bundo")
      "Others/10.120.137.10%20-%20DB" → (["Others"], "10.120.137.10 - DB")
      "tool-admin@10.120.67.31"       → ([], "tool-admin@10.120.67.31")
    """
    parts = key.split("/")
    folder_path = [unquote(p) for p in parts[:-1]]
    name = unquote(parts[-1])
    return folder_path, name


def build_wt_command(sessions: list[Session], user: str) -> str:
    """
    Erzeugt den wt.exe-Befehl, der alle Sessions als neue Tabs öffnet.
    Alle Tabs landen im selben Windows Terminal Fenster.

    Format:
      wt.exe new-tab -p "Git Bash" -- ssh USER@HOST
        ; new-tab -p "Git Bash" -- ssh -p PORT USER@HOST2
        ...
    """
    parts = []
    for i, session in enumerate(sessions):
        if session.port != 22:
            ssh_cmd = f"ssh -p {session.port} {user}@{session.hostname}"
        else:
            ssh_cmd = f"ssh {user}@{session.hostname}"

        if i == 0:
            parts.append(f'wt.exe new-tab -p "Git Bash" -- {ssh_cmd}')
        else:
            parts.append(f'new-tab -p "Git Bash" -- {ssh_cmd}')

    return " ; ".join(parts)


# ---------------------------------------------------------------------------
# TerminalLauncher
# ---------------------------------------------------------------------------
class TerminalLauncher:
    """Startet wt.exe mit mehreren SSH-Tabs."""

    @staticmethod
    def launch(sessions: list[Session], user: str) -> None:
        """
        Öffnet alle Sessions als neue Tabs in einem Windows Terminal Fenster.
        Hinweis: Da shell=True genutzt wird, wirft Popen keine Exception wenn
        wt.exe fehlt – cmd.exe startet, aber wt.exe schlägt intern fehl.
        """
        if not sessions:
            return
        cmd = build_wt_command(sessions, user)
        # shell=True nötig: wt.exe parst `;` als eigenen Subcommand-Separator,
        # cmd.exe behandelt `;` nicht als Sonderzeichen und reicht es durch.
        subprocess.Popen(cmd, shell=True)


# ---------------------------------------------------------------------------
# RegistryReader
# ---------------------------------------------------------------------------

# Allowlist patterns for input validation (defence against shell injection via
# registry data that ends up in build_wt_command which uses shell=True).
# Colon allowed for IPv6 addresses.
_HOSTNAME_RE = re.compile(r'^[A-Za-z0-9.\-:_]+$')
_USERNAME_RE = re.compile(r'^[A-Za-z0-9.\-_]*$')


class RegistryReader:
    """Liest WinSCP-Sessions aus der Windows-Registry."""

    REGISTRY_BASE = winreg.HKEY_CURRENT_USER

    def load_sessions(self) -> list[Session]:
        """
        Gibt alle gültigen Sessions aus der Registry zurück.
        Sortiert nach folder_key + display_name.
        Raises OSError wenn der Registry-Pfad nicht existiert.
        """
        sessions: list[Session] = []

        with winreg.OpenKey(self.REGISTRY_BASE, REGISTRY_PATH) as base_key:
            index = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(base_key, index)
                    index += 1
                except OSError:
                    break

                # "Default Settings" überspringen
                decoded_name = unquote(subkey_name)
                if decoded_name in SKIP_SESSIONS:
                    continue

                session = self._read_session(subkey_name)
                if session is not None:
                    sessions.append(session)

        sessions.sort(key=lambda s: (s.folder_key.lower(), s.display_name.lower()))
        return sessions

    def _read_session(self, subkey_name: str) -> Optional[Session]:
        """Liest eine einzelne Session. Gibt None zurück wenn kein HostName oder Validierung fehlschlägt."""
        full_path = REGISTRY_PATH + "\\" + subkey_name
        try:
            with winreg.OpenKey(self.REGISTRY_BASE, full_path) as session_key:
                try:
                    hostname, _ = winreg.QueryValueEx(session_key, "HostName")
                except FileNotFoundError:
                    return None  # Session ohne Hostname überspringen

                if not hostname:
                    return None

                username = ""
                try:
                    username, _ = winreg.QueryValueEx(session_key, "UserName")
                except FileNotFoundError:
                    pass

                port = 22
                try:
                    port, _ = winreg.QueryValueEx(session_key, "PortNumber")
                except FileNotFoundError:
                    pass

        except OSError:
            return None

        # Input validation: reject entries with shell metacharacters
        if not _HOSTNAME_RE.match(hostname):
            print(
                f"WARNING: Skipping session '{subkey_name}' – "
                f"hostname contains invalid characters: {hostname!r}",
                file=sys.stderr,
            )
            return None

        if username and not _USERNAME_RE.match(username):
            print(
                f"WARNING: Skipping session '{subkey_name}' – "
                f"username contains invalid characters: {username!r}",
                file=sys.stderr,
            )
            return None

        folder_path, display_name = parse_session_key(subkey_name)
        return Session(
            key=subkey_name,
            display_name=display_name,
            folder_path=folder_path,
            hostname=hostname,
            username=username,
            port=port,
        )


# ---------------------------------------------------------------------------
# Checkbox-Images (werden in SessionTree und SSHManagerApp verwendet)
# ---------------------------------------------------------------------------
def _create_checkbox_images(root: tk.Tk) -> tuple[tk.PhotoImage, tk.PhotoImage]:
    """
    Erzeugt zwei 16×16 PhotoImages für checked/unchecked Checkboxen.
    Gibt (img_unchecked, img_checked) zurück.
    """
    size = 16
    border_color = "#808080"
    bg_color = "#ffffff"
    check_color = "#1a7a3a"

    def make(checked: bool) -> tk.PhotoImage:
        img = tk.PhotoImage(width=size, height=size)
        # Alle Pixel mit Hintergrundfarbe füllen
        row_bg = "{" + " ".join([bg_color] * size) + "}"
        for y in range(size):
            img.put(row_bg, to=(0, y, size, y + 1))
        # Rahmen zeichnen
        border_row = "{" + " ".join([border_color] * size) + "}"
        img.put(border_row, to=(0, 0, size, 1))        # oben
        img.put(border_row, to=(0, size - 1, size, size))  # unten
        for y in range(size):
            img.put("{" + border_color + "}", to=(0, y, 1, y + 1))       # links
            img.put("{" + border_color + "}", to=(size - 1, y, size, y + 1))  # rechts
        if checked:
            # Häkchen: kurzer Abstieg (3,9)→(6,12), dann Aufstieg (6,12)→(13,5)
            check_px = "{" + check_color + "}"
            coords_down = [(3, 9), (4, 10), (5, 11), (6, 12)]
            coords_up = [(7, 11), (8, 10), (9, 9), (10, 8), (11, 7), (12, 6), (13, 5)]
            for x, y in coords_down + coords_up:
                if 0 < x < size and 0 < y < size:
                    img.put(check_px, to=(x, y, x + 1, y + 1))
                    # Doppelt breit für bessere Sichtbarkeit
                    if y + 1 < size:
                        img.put(check_px, to=(x, y + 1, x + 1, y + 2))
        return img

    return make(False), make(True)


# ---------------------------------------------------------------------------
# SessionTree
# ---------------------------------------------------------------------------
class SessionTree(ttk.Frame):
    """
    ttk.Treeview-Wrapper mit Checkbox-Unterstützung.
    Zeigt Sessions gruppiert nach Ordnern an.
    Unterstützt Live-Filter, Rechtsklick-Kontextmenü, Checkbox-Toggle.
    """

    # Tag-Konstanten
    TAG_SESSION = "session"
    TAG_FOLDER = "folder"

    def __init__(
        self,
        parent: tk.Widget,
        sessions: list[Session],
        img_unchecked: tk.PhotoImage,
        img_checked: tk.PhotoImage,
        on_selection_changed,  # Callable[[int], None]
    ):
        super().__init__(parent)
        self._sessions = sessions
        self._img_unchecked = img_unchecked
        self._img_checked = img_checked
        self._on_selection_changed = on_selection_changed

        # item_id → Session (nur für Session-Zeilen, nicht Ordner)
        self._item_to_session: dict[str, Session] = {}
        # item_id → checked state
        self._checked: dict[str, bool] = {}

        self._build()
        self.populate(sessions)

    def _build(self) -> None:
        """Erstellt Treeview + Scrollbar."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self._tv = ttk.Treeview(
            self,
            columns=("hostname", "port"),
            selectmode="none",  # Selektion via Checkboxen, nicht Highlight
        )
        self._tv.heading("#0", text="Name", anchor="w")
        self._tv.heading("hostname", text="Hostname", anchor="w")
        self._tv.heading("port", text="Port", anchor="w")
        self._tv.column("#0", width=260, stretch=True)
        self._tv.column("hostname", width=200, stretch=True)
        self._tv.column("port", width=60, stretch=False)

        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=vsb.set)

        self._tv.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Events
        self._tv.bind("<ButtonRelease-1>", self._on_left_click)
        self._tv.bind("<ButtonRelease-3>", self._on_right_click)

    def populate(self, sessions: list[Session]) -> None:
        """Füllt den Baum mit Sessions. Löscht vorherige Inhalte."""
        # Zustand merken (welche Ordner waren offen?)
        open_folders: set[str] = set()
        for item_id in self._tv.get_children():
            if self._tv.item(item_id, "open"):
                open_folders.add(self._tv.item(item_id, "text").strip())

        # Alles löschen
        self._tv.delete(*self._tv.get_children())
        self._item_to_session.clear()
        self._checked.clear()

        # Ordner-Nodes: folder_key → item_id
        folder_items: dict[str, str] = {}

        for session in sessions:
            # Ordner-Hierarchie aufbauen
            parent_id = ""
            for depth, folder_name in enumerate(session.folder_path):
                folder_key = "/".join(session.folder_path[: depth + 1])
                if folder_key not in folder_items:
                    was_open = folder_name in open_folders
                    folder_id = self._tv.insert(
                        parent_id, "end",
                        text=f"  {folder_name}",
                        open=was_open,
                        tags=(self.TAG_FOLDER,),
                    )
                    folder_items[folder_key] = folder_id
                parent_id = folder_items[folder_key]

            # Session-Zeile
            port_str = str(session.port) if session.port != 22 else ""
            item_id = self._tv.insert(
                parent_id, "end",
                image=self._img_unchecked,
                text=f"  {session.display_name}",
                values=(session.hostname, port_str),
                tags=(self.TAG_SESSION,),
            )
            self._item_to_session[item_id] = session
            self._checked[item_id] = False

    def _on_left_click(self, event: tk.Event) -> None:
        """Checkbox togglen wenn auf eine Session-Zeile geklickt wird."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        if self.TAG_SESSION not in self._tv.item(item_id, "tags"):
            return
        self._toggle(item_id)

    def _toggle(self, item_id: str) -> None:
        """Checkbox-Zustand einer Session-Zeile umschalten."""
        new_state = not self._checked.get(item_id, False)
        self._checked[item_id] = new_state
        self._tv.item(
            item_id,
            image=self._img_checked if new_state else self._img_unchecked,
        )
        self._notify_count()

    def _notify_count(self) -> None:
        count = sum(1 for v in self._checked.values() if v)
        self._on_selection_changed(count)

    def get_selected_sessions(self) -> list[Session]:
        """Gibt alle ausgewählten (gecheckte) Sessions zurück."""
        return [
            self._item_to_session[iid]
            for iid, checked in self._checked.items()
            if checked
        ]

    def set_all_checked(self, state: bool) -> None:
        """Alle sichtbaren Session-Zeilen an-/abhaken."""
        for item_id in self._checked:
            self._checked[item_id] = state
            self._tv.item(
                item_id,
                image=self._img_checked if state else self._img_unchecked,
            )
        self._notify_count()

    def _set_folder_checked(self, folder_item_id: str, state: bool) -> None:
        """Alle Session-Zeilen unter einem Ordner an-/abhaken (rekursiv)."""
        self._set_folder_checked_inner(folder_item_id, state)
        self._notify_count()

    def _set_folder_checked_inner(self, folder_item_id: str, state: bool) -> None:
        """Rekursiver Kern ohne Notification – nur von _set_folder_checked aufrufen."""
        for child_id in self._tv.get_children(folder_item_id):
            tags = self._tv.item(child_id, "tags")
            if self.TAG_SESSION in tags:
                self._checked[child_id] = state
                self._tv.item(
                    child_id,
                    image=self._img_checked if state else self._img_unchecked,
                )
            elif self.TAG_FOLDER in tags:
                self._set_folder_checked_inner(child_id, state)

    def _on_right_click(self, event: tk.Event) -> None:
        """Kontextmenü für Ordner-Zeilen anzeigen."""
        item_id = self._tv.identify_row(event.y)
        if not item_id:
            return
        if self.TAG_FOLDER not in self._tv.item(item_id, "tags"):
            return

        menu = tk.Menu(self, tearoff=False)
        menu.add_command(
            label="Alle im Ordner auswählen",
            command=lambda: self._set_folder_checked(item_id, True),
        )
        menu.add_command(
            label="Alle im Ordner abwählen",
            command=lambda: self._set_folder_checked(item_id, False),
        )
        menu.tk_popup(event.x_root, event.y_root)

    def filter(self, query: str) -> None:
        """
        Filtert sichtbare Sessions nach query (case-insensitive, Name + Hostname).
        Bei leerem query werden alle Sessions wieder angezeigt.
        Checkbox-Zustände bleiben beim Filtern erhalten.
        """
        q = query.strip().lower()

        # Checkbox-Zustände vor dem Neuaufbau sichern (item_id ändert sich)
        checked_keys = {
            self._item_to_session[iid].key
            for iid, v in self._checked.items()
            if v
        }

        if q:
            filtered = [
                s for s in self._sessions
                if q in s.display_name.lower() or q in s.hostname.lower()
            ]
        else:
            filtered = self._sessions

        self.populate(filtered)

        # Checkbox-Zustände wiederherstellen
        for item_id, session in self._item_to_session.items():
            if session.key in checked_keys:
                self._checked[item_id] = True
                self._tv.item(item_id, image=self._img_checked)

        self._notify_count()


# ---------------------------------------------------------------------------
# UserDialog
# ---------------------------------------------------------------------------
class UserDialog(tk.Toplevel):
    """
    Modaler Dialog zur Benutzernamen-Auswahl.
    Nach Schließen: self.result = gewählter Username (str) oder None (Abbrechen).
    """

    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.title("Benutzername auswählen")
        self.resizable(False, False)
        self.result: Optional[str] = None

        # Modal machen
        self.transient(parent)
        self.grab_set()

        self._build()
        self._center_on_parent(parent)

        # Tastaturkürzel
        self.bind("<Return>", lambda _: self._on_ok())
        self.bind("<Escape>", lambda _: self._on_cancel())

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Quickselect:").grid(
            row=0, column=0, columnspan=len(QUICK_USERS), sticky="w", pady=(0, 4)
        )

        self._user_var = tk.StringVar(value=DEFAULT_USER)

        # Quickselect-Buttons
        for col, username in enumerate(QUICK_USERS):
            ttk.Button(
                frame,
                text=username,
                command=lambda u=username: self._user_var.set(u),
                width=14,
            ).grid(row=1, column=col, padx=2, pady=(0, 8))

        # Freitext-Eingabe
        ttk.Label(frame, text="Benutzername:").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        entry = ttk.Entry(frame, textvariable=self._user_var, width=36)
        entry.grid(row=3, column=0, columnspan=len(QUICK_USERS), sticky="ew", pady=(0, 12))
        entry.select_range(0, "end")
        entry.focus()

        # OK / Abbrechen
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=len(QUICK_USERS))
        ttk.Button(btn_frame, text="OK", command=self._on_ok, width=10).pack(
            side="left", padx=4
        )
        ttk.Button(btn_frame, text="Abbrechen", command=self._on_cancel, width=10).pack(
            side="left", padx=4
        )

    def _on_ok(self) -> None:
        user = self._user_var.get().strip()
        if not user:
            return  # Leeres Feld: Dialog bleibt offen
        if not _USERNAME_RE.match(user):
            messagebox.showwarning(
                "Ungültiger Benutzername",
                "Nur Buchstaben, Ziffern, Punkte, Bindestriche und Unterstriche erlaubt.",
                parent=self,
            )
            return
        self.result = user
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
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")


# ---------------------------------------------------------------------------
# SSHManagerApp
# ---------------------------------------------------------------------------
class SSHManagerApp(tk.Tk):
    """Hauptfenster der SSH-Manager Applikation."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.minsize(*WINDOW_MIN_SIZE)
        self.geometry("750x550")

        # Stil
        style = ttk.Style(self)
        style.theme_use("clam")

        # Registry laden
        try:
            reader = RegistryReader()
            self._sessions = reader.load_sessions()
        except OSError as e:
            messagebox.showerror(
                "Registry-Fehler",
                f"WinSCP-Sessions konnten nicht geladen werden:\n{e}\n\n"
                f"Pfad: HKCU\\{REGISTRY_PATH}"
            )
            self._sessions = []

        # Checkbox-Images (nach Tk-Initialisierung erzeugen!)
        self._img_unchecked, self._img_checked = _create_checkbox_images(self)

        self._build_ui()

    def _build_ui(self) -> None:
        """Erstellt alle UI-Elemente."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Toolbar (Zeile 0)
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="Suche:").grid(row=0, column=0, padx=(0, 4))
        self._search_var = tk.StringVar()
        search_entry = ttk.Entry(toolbar, textvariable=self._search_var)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        ttk.Button(toolbar, text="Alle auswählen",
                   command=self._select_all).grid(row=0, column=2, padx=2)
        ttk.Button(toolbar, text="Alle abwählen",
                   command=self._deselect_all).grid(row=0, column=3, padx=2)

        # SessionTree (Zeile 1)
        self._tree = SessionTree(
            self,
            sessions=self._sessions,
            img_unchecked=self._img_unchecked,
            img_checked=self._img_checked,
            on_selection_changed=self._on_selection_changed,
        )
        self._tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))

        # Verbinden-Button (Zeile 2)
        bottom = ttk.Frame(self, padding=(8, 6))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        self._connect_btn = ttk.Button(
            bottom,
            text="Verbinden",
            command=self._on_connect,
            state=tk.DISABLED,
        )
        self._connect_btn.grid(row=0, column=0)

        # Suche verdrahten
        self._search_var.trace_add("write", lambda *_: self._on_search_changed())

    def _on_selection_changed(self, count: int) -> None:
        """Callback vom SessionTree – aktualisiert den Verbinden-Button."""
        if count > 0:
            self._connect_btn.config(
                text=f"Verbinden ({count} ausgewählt)",
                state=tk.NORMAL,
            )
        else:
            self._connect_btn.config(text="Verbinden", state=tk.DISABLED)

    def _on_search_changed(self) -> None:
        self._tree.filter(self._search_var.get())

    def _select_all(self) -> None:
        self._tree.set_all_checked(True)

    def _deselect_all(self) -> None:
        self._tree.set_all_checked(False)

    def _on_connect(self) -> None:
        selected = self._tree.get_selected_sessions()
        if not selected:
            return
        dialog = UserDialog(self)
        self.wait_window(dialog)
        if dialog.result is None:
            return  # Abbrechen gedrückt
        user = dialog.result
        try:
            TerminalLauncher.launch(selected, user)
        except Exception as e:
            messagebox.showerror("Fehler beim Starten", str(e))


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = SSHManagerApp()
    app.mainloop()
