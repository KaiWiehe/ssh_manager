"""Explain unavailable menu actions using the same selection rules as execution."""
from .selection import single_action_target


def action_disabled_reason(app, label):
    selected = app._tree.get_selected_sessions()
    bulk = {"Auswahl verbinden", "Hosts prüfen", "Server neu starten…", "Remote-Befehl ausführen", "Lokales Skript ausführen…", "Serverskript ausführen…", "Dateien verteilen…", "Zertifikate ersetzen…", "SSH Key übertragen", "SSH Key entfernen", "Dienststatus anzeigen…", "Dienst neu starten…", "Dienstlogs anzeigen…", "DNS/IP für Auswahl auflösen…", "DNS/IP für Auswahl auflösen… (DNS-Auswahl)"}
    if label in bulk and not selected:
        return "mindestens einen Host anhaken"
    if label == "Datei hochladen…" and single_action_target(app._tree) is None:
        return "genau einen Host wählen"
    if label == "Verbindung diagnostizieren…" and not selected and single_action_target(app._tree) is None:
        return "Verbindung fokussieren oder anhaken"
    if label == "Letzte Sammelergebnisse…" and not app.__dict__.get("_operation_jobs"):
        return "noch keine Sammelaktion"
    return ""


def configure_action_availability(app, menu):
    labels = {index: menu.entrycget(index, "label") for index in range((menu.index("end") or 0) + 1) if menu.type(index) == "command"}
    def refresh():
        for index, label in labels.items():
            reason = action_disabled_reason(app, label)
            menu.entryconfigure(index, state="disabled" if reason else "normal", label=f"{label} — {reason}" if reason else label)
    menu.configure(postcommand=refresh)
