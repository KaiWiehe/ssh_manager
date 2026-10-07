from pathlib import Path
from tkinter import filedialog, messagebox

from . import storage


def backup_app(app):
    path = filedialog.asksaveasfilename(parent=app, title="App sichern", defaultextension=".json",
                                      initialfile="ssh-manager-backup.json", filetypes=[("App-Backup", "*.json")])
    if not path:
        return
    try:
        from .actions_ui import persist_ui_state
        persist_ui_state(app)
        storage.create_app_backup(Path(path))
    except (OSError, ValueError, TypeError):
        messagebox.showerror("Backup fehlgeschlagen", "App-Daten konnten nicht vollständig gesichert werden.", parent=app)
        return
    messagebox.showinfo("App gesichert", "Enthalten: gespeicherte Einstellungen, eigene Verbindungen, Notizen, Favoriten/Runbooks und Ansicht.\n\nNicht enthalten: WinSCP-Registry, FileZilla, SSH Config und SSH-Schlüssel. Diese Quellen separat sichern.", parent=app)


def restore_app(app):
    path = filedialog.askopenfilename(parent=app, title="App-Backup wiederherstellen", filetypes=[("App-Backup", "*.json")])
    if not path:
        return
    try:
        payload = storage.read_app_backup(Path(path))
        documents = payload["documents"]
        count = len(documents["app_sessions.json"]["sessions"])
        notes = len(documents["notes.json"]["notes"])
        if not messagebox.askyesno("Backup-Vorschau", f"{count} eigene Verbindungen und {notes} Notizen wiederherstellen?\nDazu Einstellungen, Favoriten/Runbooks und Ansicht.\n\nDer aktuelle App-Zustand wird vorher gesichert. Die App schließt danach; bitte neu starten. Externe Quellen und SSH-Schlüssel werden nicht verändert.", parent=app):
            return
        safety = storage.restore_app_backup(payload)
    except (OSError, ValueError, TypeError):
        messagebox.showerror("Wiederherstellung fehlgeschlagen", "Backup ungültig oder App-Daten nicht schreibbar. Eine begonnene Wiederherstellung wird beim nächsten App-Start fortgesetzt. Bitte die App schließen und neu starten.", parent=app)
        if storage._STATE_FILE.with_name("app-restore-pending.json").exists():
            app.destroy()  # Avoid stale in-memory writes into a pending restore.
        return
    messagebox.showinfo("Wiederhergestellt", f"App-Backup wiederhergestellt.\nVorheriger Zustand: {safety}\n\nBitte die App erneut starten.", parent=app)
    app.destroy()  # Do not persist the stale pre-restore in-memory view.
