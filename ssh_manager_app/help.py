"""Offline, searchable help. Content stays independent of Tk for testing/export."""
from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

from .shortcuts import DEFAULT_ACTION_ORDER, default_shortcuts
from .themes import palette_for_theme
from .ui_components import build_dialog_header


@dataclass(frozen=True)
class HelpTopic:
    id: str
    title: str
    body: str


TOPICS = (
    HelpTopic("start", "Schnellstart und Auswahl", """Der SSH-Manager sammelt Verbindungen aus mehreren Quellen in einem Baum. Er öffnet SSH-Verbindungen im konfigurierten Terminal; er ist selbst kein SSH-Terminal.

Einzelne Verbindung öffnen
Suche nach einem Namen oder Hostnamen, klicke auf eine Verbindung oder navigiere mit den Pfeiltasten. Enter oder ein Doppelklick öffnet diese Verbindung. Falls erforderlich, wähle den SSH-Benutzer im folgenden Dialog.

Zeile und Checkbox sind verschieden
Die hervorgehobene Zeile ist der Tastaturfokus. Häkchen sind die Mehrfachauswahl. Mit Hoch/Runter bewegst du nur den Fokus; vorhandene Häkchen bleiben bestehen. Enter benutzt die fokussierte Zeile, nicht automatisch alle Häkchen.

Mehrere Verbindungen öffnen
Setze Häkchen per Mausklick oder Leertaste. Strg+Enter (Standard) oder Aktionen → Auswahl verbinden öffnet die angehakten Sessions. Ohne Häkchen wird keine Verbindung geöffnet. Eine Ordner-Checkbox wählt auch Sessions in Unterordnern.

Alle auswählen / Alle abwählen / Auswahl umkehren
Diese Aktionen ändern die Checkbox-Auswahl im aktuellen Baum. Nutze sie für gemeinsame Aktionen auf mehreren Hosts. Prüfe vor einer Serveraktion die im Dialog aufgeführten Zielhosts.

Voraussetzungen
Für SSH muss der Zielhost erreichbar sein und eine Anmeldung erlauben. Windows Terminal und Git Bash müssen für den Standard-Startpfad installiert sein. Herdr ist eine optionale Terminalwahl in den Einstellungen."""),
    HelpTopic("keys", "Tastatur und Tastenkürzel", """Im Verbindungsbaum
↑ / ↓: Zur vorherigen/nächsten sichtbaren Zeile wechseln.
→: Geschlossenen Ordner öffnen; im offenen Ordner zum ersten Kind wechseln.
←: Offenen Ordner schließen; sonst zum übergeordneten Ordner wechseln.
Enter (Standard): Fokussierte Verbindung öffnen oder Ordner auf-/zuklappen.
Strg+Enter (Standard): Angekreuzte Verbindungen öffnen.
Shift+Enter: Keine eigene Aktion. Bei der Standardbelegung greift auch hier die Enter-Bindung von Tk; die fokussierte Zeile wird aktiviert. Es ist kein Kürzel für die Checkbox-Auswahl.
Leertaste: Häkchen der Zeile umschalten; bei Ordnern alle enthaltenen Sessions einschließlich Unterordnern auswählen/abwählen.
Shift+F10 / Menütaste: Kontextmenü der fokussierten Zeile öffnen.

Bearbeiten und Löschen
F2 (Standard) öffnet Bearbeiten: Eine einzelne angehakte Session hat Vorrang, sonst wird die Kontextzeile verwendet. Importierte Verbindungen bieten nur die unterstützten App-internen Anpassungen.
Entf (Standard) löscht nach Bestätigung: Eine einzelne angehakte Session hat Vorrang, sonst wird die Kontextzeile verwendet. Das gilt für eigene Verbindungen und Alias-Kopien, nicht für die externen Originalquellen.

Eigene Kürzel
Unter Einstellungen → Tastenkürzel ein Feld anklicken und die gewünschte Kombination drücken. Escape bricht die Erfassung ab, Backspace entfernt das Kürzel, Reset stellt den Standard wieder her. Nicht jede feste Baumtaste ist dort konfigurierbar.

Wo gelten Kürzel?
Enter und Auswahl verbinden benötigen Tastaturfokus im Verbindungsbaum. Textfelder behalten ihre vorgesehenen Texteingaben. Modale Dialoge verwenden ihre eigene Bedienung. Im Hilfefenster lösen App-Kürzel keine Aktionen im Hauptfenster aus; Escape schließt die Hilfe.

Aktuelle Belegung und Standards
{shortcuts}"""),
    HelpTopic("folders", "Ordner auf- und zuklappen", """Einzelner Ordner
Klicke auf den kleinen Pfeil am Ordner. Mit der Tastatur: Ordner fokussieren und Enter zum Umschalten, Rechts zum Öffnen oder Links zum Schließen drücken. Ist der Ordner schon geöffnet, wechselt Rechts zum ersten Kind. Links wechselt von einer Verbindung oder einem geschlossenen Ordner zum Elternordner.

Ordner einschließlich Unterordnern
Im Rechtsklick-Menü des Ordners stehen rekursive Aktionen zum Auf- und Zuklappen. Sie betreffen diesen Ordner und seine Unterordner.

Alle Ordner
Ansicht → Ausklappen / Einklappen, die entsprechenden Toolbar-Buttons oder die Palettenaktionen „Ordner ausklappen“ / „Ordner einklappen“ wirken auf den gesamten Baum. Die Toolbar-Buttons können in den Einstellungen ausgeblendet sein.

Ordnerzustand und Suche
Der normale Auf-/Zuklappzustand wird gespeichert. Bei aktiver Suche öffnet die App Trefferordner vorübergehend. Nach dem Leeren der Suche kehrt der gespeicherte Benutzerzustand zurück.

Alle im Ordner verbinden
Diese Kontextmenüaktion verbindet die Sessions des Ordners, ohne zuvor Checkboxen setzen zu müssen. Auswahlaktionen im Ordner-Menü setzen oder entfernen stattdessen nur Häkchen.

Ordner verwalten
Eigene Verbindungen und Alias-Kopien lassen sich in Ordner verschieben. Ordner umbenennen wirkt auch auf zugehörige Unterordner. Löschen ist nur für unterstützte App-Verbindungen verfügbar; externe Quellen werden nicht verändert."""),
    HelpTopic("palette", "Befehlspalette", """Öffnen und suchen
Strg+P (Standard) oder Datei → Befehlspalette öffnet die Palette. Tippe einen Verbindungsnamen, Hostnamen, Benutzer, Ordner oder eine Aktion. Die unscharfe Suche findet Zeichen in derselben Reihenfolge, auch wenn sie nicht direkt nebeneinander stehen. Sie sucht in Namen und Zusatztexten; sie ist keine Volltextsuche über alle Sessiondaten.

Nur Aktionen finden
Ein führendes > beschränkt die Ergebnisse auf Aktionen. Beispiel: „> einklappen“ findet die Aktion zum Schließen aller Ordner. Ohne > werden Sessions und Aktionen gemeinsam angezeigt. Zuletzt genutzte Verbindungen und Aktionen werden bevorzugt einsortiert.

Bedienung
Hoch/Runter wechselt den Treffer, Enter führt ihn aus, Escape schließt die Palette. Ein Session-Treffer öffnet genau diese Verbindung. Ein Aktions-Treffer führt die benannte App-Aktion aus.

Auswahlabhängige Aktionen
„Verbinden mit Auswahl“ verwendet die angehakten Sessions. „Bearbeiten“ und „Löschen“ in der Palette benötigen genau eine angehakte Session; Löschen ist nur für eigene Sessions und Alias-Kopien erlaubt. Ohne passende Auswahl passiert nichts. Diese Auswahlregeln unterscheiden sich von Enter/F2/Entf im Baum.

Weitere Aktionen
Neue Verbindung, Einstellungen, Suche fokussieren, neu laden, DNS/IP auflösen, Auswahl ändern, Ordner aus-/einklappen, Zuletzt verwendet umschalten, Einstellungen importieren/exportieren und Hilfe öffnen sind über die Palette erreichbar. Weitere Serverwerkzeuge findest du im Menü Aktionen und in den Kontextmenüs.

Fensterbreite
Die Palette lässt sich in der Breite verändern; die Breite wird gespeichert. Lange Treffer zeigen beim Darüberfahren einen Tooltip."""),
    HelpTopic("sources", "Verbindungen, Quellen und Benutzer", """Neue Verbindung
Datei → Neue Verbindung legt eine eigene App-Verbindung mit Name, Host, Port, Benutzer und Ordner an. Sie wird in app_sessions.json gespeichert. Name und Host sind verschiedene Felder: Der Name ist die Anzeige, der Host das SSH-Ziel.

Quellen
WinSCP: Liest gespeicherte Sessions aus der Windows-Registry. „In WinSCP öffnen“ ist nur für diese Quelle verfügbar und benötigt WinSCP.
SSH Config: Liest ~/.ssh/config. Verbunden wird über den Alias („ssh ALIAS“); Benutzer und weitere SSH-Optionen kommen aus der SSH-Konfiguration.
SSH-Alias-Kopie: Eine App-interne Kopie eines Alias für eigene Ordnerorganisation. Die Verbindung nutzt weiterhin den Alias.
FileZilla Config: Liest Sites aus sitemanager.xml; SSH verbindet zum gespeicherten Host. Die Datei wird nicht zurückgeschrieben.
Eigene App-Verbindungen: Im SSH-Manager angelegt und vollständig dort verwaltbar.

Bearbeiten, Duplizieren, Verschieben und Löschen
Eigene Verbindungen und Alias-Kopien können umbenannt, verschoben und gelöscht werden. Duplizieren erstellt eine weitere App-Verbindung; einen SSH-Config-Alias kannst du als Alias-Kopie in einen eigenen Ordner übernehmen. Importierte Originalquellen lassen sich nicht wie eigene Sessions verändern.

Benutzer wählen und merken
Normale Host-Verbindungen verwenden den festen Benutzer oder die Benutzerwahl mit Schnellauswahl. „Benutzer setzen“ und „Benutzer entfernen“ ändern App-interne Benutzerzuordnungen, auch für eine Auswahl. SSH-Config-Verbindungen verwenden den Alias und überspringen den Benutzer-Dialog. Benutzer-Overrides werden nicht in die externen Quellen geschrieben.

SSH Config ansehen
„Konfiguration anzeigen (ssh -G)“ zeigt die von SSH aufgelösten Optionen für einen Alias. „SSH Config in VS Code öffnen“ öffnet die Konfigurationsdatei im Editor; benötigt VS Code.

Neu laden
F5 (Standard) liest die Verbindungen erneut ein. Nutze es, wenn du WinSCP, FileZilla oder die SSH-Konfiguration außerhalb der App geändert hast. Die Quellenfilter bestimmen, welche Quellen sichtbar sind."""),
    HelpTopic("organize", "Notizen, Farben und Favoriten", """Notizen
Über das Kontextmenü eine Notiz zur Session hinterlegen. Sie erscheint als Tooltip und optional in der Notizen-Spalte. Notizen liegen ausschließlich in notes.json; WinSCP, FileZilla und SSH Config werden nicht geändert. Notiz kopieren übernimmt den Text in die Zwischenablage.

Farben
Das Kontextmenü kann eine Session, eine Checkbox-Auswahl oder die Sessions eines Ordners einfärben. Damit markierst du beispielsweise Umgebungen oder Zuständigkeiten. „Farbe entfernen“ entfernt die einzelne Zuordnung; Ansicht → Farben zurücksetzen entfernt die App-Farbzuordnungen.

Session-Favoriten
„Zu Favoriten hinzufügen“ macht eine Verbindung im virtuellen Favoritenordner erreichbar. Der Dialog steuert auch die Anzeige im Originalbaum. „Favorit entfernen“ entfernt den Favoritenstatus, nicht die Originalverbindung. Mehrere angehakte Verbindungen können gemeinsam hinzugefügt werden.

Zuletzt verwendet
Geöffnete Verbindungen erscheinen im virtuellen Ordner „Zuletzt verwendet“. Das ist eine zusätzliche Ansicht derselben Sessions, keine weitere Datenquelle. Strg+Shift+R (Standard) schaltet diesen Ordner um.

Runbook-Favoriten sind getrennt
Favoriten im Remote-Befehl-Dialog speichern Befehle/Skript-Einstellungen. Sie sind unabhängig von Session-Favoriten."""),
    HelpTopic("network", "Hosts prüfen, DNS, Jumphost und Tunnel", """Hosts prüfen
Prüft eine TCP-Verbindung zum SSH-Port der Session. Im Baum erscheinen ⏳, ✓ oder ✗. Das prüft Erreichbarkeit, nicht die Anmeldung oder den Zustand eines Dienstes. Kontextmenüaktionen wirken auf den Host, die Auswahl oder den Ordner entsprechend ihrer Beschriftung. Beim Neuaufbau des Baums wird der Status zurückgesetzt.

DNS/IP auflösen
Aktionen → DNS/IP auflösen öffnet eine freie Abfrage. Die Auswahlvarianten lösen die ausgewählten Hostnamen auf; „DNS-Auswahl“ erlaubt einen anderen DNS-Server. Nutze das zur Prüfung von Namensauflösung und IP-Adressen. Die Abfrage verändert keine DNS-Einträge.

Über Jumphost öffnen
Öffnet eine SSH-Verbindung über einen vorgeschalteten SSH-Server. Nützlich, wenn ein Ziel nur aus einem internen Netz erreichbar ist. Trage den Sprungserver und die erforderlichen Zugangsdaten im Dialog ein. Beide SSH-Strecken müssen erreichbar sein.

Tunnel öffnen
Ein lokaler Port wird über SSH an einen Zielhost und Zielport weitergeleitet: ssh -N -L lokalerPort:Zielhost:Zielport Benutzer@SSH-Server. Beispiel: Lokalport 15432, SSH-Server gateway.example, Zielhost localhost, Zielport 5432. Ein Datenbankprogramm verbindet dann lokal zu localhost:15432.
„localhost“ als Zielhost meint den SSH-Server. Ein anderer Zielhost wird vom SSH-Server aus erreicht. Der lokale Port muss frei sein. Das Terminal hält den Tunnel offen; beende den SSH-Prozess, um ihn zu schließen. Die Funktion erstellt lokale Portweiterleitungen, keine Reverse-Tunnel oder SOCKS-Proxys."""),
    HelpTopic("remote", "Remote-Befehle und Skript-Runbooks", """Ziele und Benutzer
„Befehl ausführen“ öffnet den Runner für die im Aufruf benannten Hosts. Kontextmenüs unterscheiden Einzelhost und Auswahl; Toolbar/Menü verwenden die Checkbox-Auswahl. Eine Befehlskette verwendet einen Benutzer, nicht einen Benutzer pro Schritt. SSH-Anmeldung und benötigte Programme auf den Zielhosts müssen funktionieren.

Nur Remote-Befehl
Führt den eingegebenen Befehl per SSH auf den Zielhosts aus. Beispiel: „uname -a“ für Systeminformationen. Jeder Host erhält seinen eigenen Terminal-Output. Prüfe Hostliste und Befehl vor der Bestätigung; ein Befehl kann je nach Inhalt Serverdaten verändern.

Lokales Skript hochladen
Wähle eine lokale Skriptdatei, Interpreter und Argumente. Die App überträgt das Skript per scp nach /tmp, führt es per SSH aus und entfernt die temporäre Remote-Datei danach. Upload und Ausführung sind im Terminal getrennt sichtbar. Lokale Datei, scp und der Remote-Interpreter müssen verfügbar sein.

Skript liegt auf Server
Gib den vorhandenen Remote-Pfad, Interpreter und Argumente an. Es findet kein Upload statt. Der Benutzer muss das Skript lesen/ausführen dürfen. Beispiel: /opt/tools/check.sh mit bash.

Vor- und Nach-Befehl
In den Skript-Modi können zusätzliche Befehle vor und nach dem Skript eingegeben werden. Der Terminal-Output zeigt die geplante Reihenfolge und getrennte Bereiche „Output vom Vor-Befehl“, „Output vom Skript“ und „Output vom Nach-Befehl“. Prüfe die Ausgaben jedes Schritts; der Nach-Befehl ist kein garantiertes Rollback.

Favoriten und Verlauf
Ein Runbook-Favorit speichert das vollständige Spec mit Name, Notiz und Pin-Status. Über den Favoriten-Dialog anlegen/bearbeiten, löschen oder anpinnen; angepinnte Einträge stehen oben. Der Verlauf hilft, frühere Einstellungen wiederzuverwenden. Das erneute Auswählen eines Eintrags ersetzt nicht die Prüfung der aktuellen Zielhosts."""),
    HelpTopic("server", "Dateien, Zertifikate und Serverneustart", """Dateien übertragen
Überträgt die ausgewählten lokalen Dateien auf die Zielhosts. Die Dateien werden zunächst nach /tmp hochgeladen und dann mit sudo in den Zielordner kopiert. Wähle den Remote-Zielordner und prüfe die Option „Vorhandene Dateien überschreiben“. Benötigt scp, SSH-Zugriff und passende sudo-Rechte. Es ist ein Upload-Werkzeug, kein allgemeiner bidirektionaler Dateimanager.

Zertifikate ersetzen
Wähle neue lokale Dateien und absolute Whitelist-Suchpfade, beispielsweise /etc/myservice. „Treffer suchen“ sucht ausschließlich in diesen Pfaden nach regulären Dateien mit exakt gleichem Dateinamen. Eine leere Whitelist blockiert die Suche. In der Vorschau bestehende und neue Dateidaten prüfen und die zu ersetzenden Treffer auswählen; erst danach den Austausch bestätigen. Es werden vorhandene Dateien ersetzt, keine beliebigen neuen Zielpfade angelegt.
Das optionale Keystore-/P12-Passwort ermöglicht die Prüfung von Zertifikatsdaten in JKS/P12; ohne Passwort werden dort nur Dateizeitstempel angezeigt. Ein optionaler Nach-Befehl (auch aus einem Favoriten) kann anschließend etwa einen Dienst neu starten. „Tab nach Erfolg schließen“ schließt erfolgreiche Terminal-Tabs. Benötigt SSH/scp, passende sudo-Rechte und je nach Format OpenSSL/keytool. Die Aktion verändert Zertifikatsdateien auf den Servern.

Server neu starten
Löst auf den bestätigten Hosts einen Neustart mit sudo aus. Laufende Verbindungen und Dienste werden dabei unterbrochen; ein ausgelöster Neustart lässt sich nicht rückgängig machen. Der Dialog zeigt die Zielhosts und eine maximale Wartezeit. Optional kann eine systemd-Unit angegeben werden, die nach der SSH-Rückkehr geprüft wird. Ohne Unit werden Neustart und SSH-Rückkehr geprüft. Das sudo-Passwort wird für diesen Lauf verwendet und nicht gespeichert.

Einzelhost, Auswahl und Ordner
Die Beschriftung des Kontextmenüs nennt den Geltungsbereich. Im Menü Aktionen und in der Toolbar werden die angehakten Sessions übergeben. Vor dem Start die endgültige Hostliste im jeweiligen Dialog prüfen. Die Hilfe selbst führt keine Serveraktion aus."""),
    HelpTopic("sshkeys", "SSH-Keys übertragen und entfernen", """SSH Key übertragen
Überträgt einen öffentlichen SSH-Key auf die ausgewählten Hosts, damit spätere Anmeldungen mit dem passenden privaten Schlüssel möglich sind. Wähle die öffentliche Schlüsseldatei und den Benutzer im Dialog. Erfordert zunächst eine funktionierende Anmeldung und Schreibrechte auf die SSH-Autorisierung des Benutzers. Ein privater Schlüssel bleibt lokal.

SSH Key entfernen
Entfernt den ausgewählten Schlüssel aus der Autorisierung des Remote-Benutzers. Dadurch kann der zugehörige private Schlüssel den Zugriff verlieren. Prüfe Benutzer, Hosts und Schlüssel; stelle sicher, dass eine andere Anmeldung möglich bleibt. Der lokale private Schlüssel wird durch diese Aktion nicht gelöscht.

Geltungsbereich
Die Kontextmenüs bieten Einzelhost- und Auswahlaktionen entsprechend den unterstützten Sessiontypen. Die Aktion verändert die SSH-Zugangsberechtigung auf den Servern, nicht nur eine Einstellung im SSH-Manager."""),
    HelpTopic("settings", "Suche, Ansicht und Einstellungen", """Suche und Suchverlauf
Das Suchfeld filtert die Hauptansicht live nach Name, Hostname und Ordnerpfad, ohne Beachtung der Groß-/Kleinschreibung. Es sucht nicht nach Port oder Notiztext. Strg+F (Standard) setzt den Fokus hinein. Leeren zeigt wieder die normale Ansicht. Der Verlauf-Button übernimmt frühere Suchbegriffe; „Verlauf leeren“ entfernt den gespeicherten Suchverlauf. Hauptsuche und Befehlspalette sind unterschiedliche Suchoberflächen.

Toolbar und Quellen
Einstellungen steuern sichtbare Toolbar-Aktionen und Datenquellen einschließlich Favoriten/Zuletzt verwendet. Bei wenig Platz liegen Toolbar-Aktionen im „Mehr“-Überlauf. Eine ausgeblendete Quelle wird nicht gelöscht.

Spalten
Benutzer, Hostname, Port und Notizen sind ein-/ausblendbar. Sichtbare Datenspalten können per Drag & Drop umgeordnet werden. Name bleibt als Baumspalte links. Das Ausblenden ändert nur die Ansicht.

Darstellung
Theme, Akzentfarbe, UI-/Baumschrift und Zeilenhöhe passen die Darstellung an. Einstellungen wirken auf die entsprechenden UI-Bereiche live.

Terminal und Benutzer
Windows Terminal ist das Standardziel; Herdr ist optional und muss installiert sein. Die Terminal-Einstellungen steuern unter anderem Profil, Farben und Titel. Schnellauswahl-Benutzer und Standardbenutzer vereinfachen die Anmeldung.

Start, Import und Prüfzeit
Beim Start können Ordner aufgeklappt, eingeklappt oder mit dem gemerkten Zustand angezeigt werden. Die Wartezeit für Hosts prüfen begrenzt den TCP-Verbindungsversuch. Importoptionen steuern die Übernahme von WinSCP-/FileZilla-Benutzern. Die WinSCP-Einstellung bestimmt das Öffnen in Tabs oder Fenstern.

Einstellungen zurücksetzen
Stellt die Einstellungsdefaults wieder her. „Ansicht auf Startzustand zurücksetzen“ leert die Suche und stellt Ordner und Farben vom App-Start wieder her; „Farben zurücksetzen“ entfernt Farbzuordnungen. Diese Aktionen löschen keine Verbindungen.

Hilfe
F1 (Standard), Hilfe → Hilfe öffnen oder „Hilfe öffnen“ in der Palette öffnet dieses Fenster. Du kannst es neben dem Hauptfenster verwenden. Themen und Suchtext bleiben beim erneuten Aufrufen erhalten."""),
    HelpTopic("data", "Kopieren, Export, Import und App-Daten", """Kopieren
Das Kontextmenü kopiert SSH-Befehl, Hostname, Name oder Notiz einer Session. Die Auswahlvarianten kopieren die entsprechenden Werte mehrerer angehakter Sessions; Ordneraktionen die enthaltenen Sessions. „Angezeigte Verbindungen als Markdown kopieren“ im Menü Aktionen kopiert die aktuell dargestellten Verbindungen als Tabelle.

CSV und Excel
„Angezeigte Verbindungen als CSV/Excel exportieren“ exportiert die sichtbaren Verbindungen. Filter und Quellenanzeige beeinflussen den Inhalt. Nutze es für Listen und Dokumentation; es ist kein vollständiges Backup aller Einstellungen und Quellen.

Einstellungen exportieren/importieren
Öffne zuerst die Einstellungsansicht: Die Import-/Exportaktionen verwenden diese Ansicht. Export schreibt die App-Einstellungen in eine Datei. Import übernimmt Einstellungen aus einer passenden Datei. Das ist kein Import beliebiger CSV/Excel-Verbindungslisten. Externe WinSCP-, FileZilla- und SSH-Config-Quellen müssen separat gesichert werden.

App-Daten und Backup
Unter %APPDATA%/SSH-Manager liegen settings.json (Einstellungen), ui_state.json (Ansicht, Suchverlauf, Favoriten, Benutzerzuordnungen und Runner-Daten), app_sessions.json (eigene Sessions und Alias-Kopien) und notes.json (Notizen). Für ein vollständiges lokales Backup diese Dateien bei geschlossener App sichern und verwendete externe Quellen zusätzlich sichern.

JSONs in VS Code öffnen
Datei → JSONs in VS Code öffnen öffnet die App-Datendateien im Editor. Benötigt VS Code. Direkte Änderungen erfordern gültiges JSON; vor manuellen Änderungen eine Sicherung erstellen. Repository-Dateien sind nicht die persönlichen Verbindungsdaten."""),
)


def shortcut_table(mapping: dict[str, str]) -> str:
    return "\n".join(
        f"{label}: {mapping.get(action, default) or 'Nicht belegt'}  (Standard: {default or 'Nicht belegt'})"
        for action, label, default in DEFAULT_ACTION_ORDER
    )


def topic_body(topic: HelpTopic, mapping: dict[str, str]) -> str:
    return topic.body.replace("{shortcuts}", shortcut_table(mapping))


def search_topics(query: str, mapping: dict[str, str]) -> list[HelpTopic]:
    words = query.casefold().split()
    return [topic for topic in TOPICS if all(
        word in (topic.title + "\n" + topic_body(topic, mapping)).casefold()
        for word in words
    )]


def open_help(app) -> None:
    window = getattr(app, "_help_window", None)
    if window is None or not window.winfo_exists():
        window = HelpWindow(app)
        app._help_window = window
    window.deiconify()
    window.lift()
    window.refresh()
    window.search_entry.focus_set()


class HelpWindow(tk.Toplevel):
    """Nonmodal help with a separate shortcut boundary."""
    _blocks_app_shortcuts = True

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("SSH Manager – Hilfe")
        self.geometry("1000x720")
        self.minsize(680, 440)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", self.close)
        self.bind("<FocusIn>", self._on_focus, add="+")
        self.mapping = default_shortcuts()
        self.filtered: list[HelpTopic] = []
        self.selected_id = "start"
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        build_dialog_header(frame, "Hilfe zum SSH-Manager", "Bedienung, Tastatur und Aktionen – offline nachschlagen.")
        search = ttk.Frame(frame)
        search.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Hilfe durchsuchen:").grid(row=0, column=0, padx=(0, 10))
        self.query = tk.StringVar()
        self.search_entry = ttk.Entry(search, textvariable=self.query)
        self.search_entry.grid(row=0, column=1, sticky="ew")
        ttk.Button(search, text="Leeren", command=lambda: self.query.set("")).grid(row=0, column=2, padx=(10, 0))
        pane = ttk.Panedwindow(frame, orient="horizontal")
        pane.grid(row=2, column=0, sticky="nsew")
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=1)
        pane.add(right, weight=3)
        self.topics = ttk.Treeview(left, show="tree", selectmode="browse", height=12)
        self.topics.column("#0", width=250, minwidth=170)
        topic_scroll = ttk.Scrollbar(left, command=self.topics.yview)
        self.topics.configure(yscrollcommand=topic_scroll.set)
        topic_scroll.pack(side="right", fill="y")
        self.topics.pack(fill="both", expand=True)
        self.text = tk.Text(right, wrap="word", state="disabled", width=60, padx=16, pady=12, relief="flat", borderwidth=0)
        scroll = ttk.Scrollbar(right, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        footer = ttk.Frame(frame)
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.status = ttk.Label(footer, style="Muted.TLabel")
        self.status.pack(side="left")
        ttk.Button(footer, text="Schließen", command=self.close).pack(side="right")
        self.topics.bind("<<TreeviewSelect>>", self._select_topic)
        self.query.trace_add("write", lambda *_: self._filter())
        self.refresh()

    def close(self, _event=None):
        self.app._help_window = None
        self.destroy()
        return "break"

    def _on_focus(self, event):
        if event.widget is self:
            self.refresh()

    def refresh(self):
        manager = getattr(self.app, "_shortcut_manager", None)
        self.mapping = manager.current_mapping() if manager else default_shortcuts()
        appearance = self.app.settings.appearance
        palette = palette_for_theme(appearance.theme)
        self.configure(background=palette.bg)
        font = ttk.Style(self).lookup("TLabel", "font") or "TkDefaultFont"
        self.text.configure(background=palette.surface, foreground=palette.text,
                            selectbackground=palette.selected, selectforeground=palette.text, font=font)
        self.text.tag_configure("title", font=(appearance.ui_font_family, appearance.ui_font_size + 4, "bold"), spacing3=14)
        self.text.tag_configure("heading", font=(appearance.ui_font_family, appearance.ui_font_size, "bold"), spacing1=8, spacing3=5)
        self._filter()

    def _filter(self):
        self.filtered = search_topics(self.query.get(), self.mapping)
        self.topics.delete(*self.topics.get_children())
        for topic in self.filtered:
            self.topics.insert("", "end", iid=topic.id, text=topic.title)
        self.status.configure(text=f"{len(self.filtered)} von {len(TOPICS)} Themen")
        if self.filtered:
            ids = {topic.id for topic in self.filtered}
            selected = self.selected_id if self.selected_id in ids else self.filtered[0].id
            self.topics.selection_set(selected)
            self.topics.focus(selected)
            self._select_topic()
        else:
            self._render("Keine Treffer", "Kein Hilfethema passt zur Suche. Versuche einen anderen Begriff oder leere die Suche.")

    def _select_topic(self, _event=None):
        selected = self.topics.selection()
        if not selected:
            return
        self.selected_id = selected[0]
        topic = next(topic for topic in self.filtered if topic.id == self.selected_id)
        self._render(topic.title, topic_body(topic, self.mapping))

    def _render(self, title: str, body: str):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", title + "\n", "title")
        for paragraph in body.split("\n\n"):
            lines = paragraph.split("\n", 1)
            if len(lines) == 2:
                self.text.insert("end", lines[0] + "\n", "heading")
                self.text.insert("end", lines[1] + "\n\n")
            else:
                self.text.insert("end", paragraph + "\n\n")
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
