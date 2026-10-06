# Security & Code Audit TODO

Erstellt: 2026-10-02
Geprüft: Frontend + Backend + Package-Scan

> Kontext: Python/Tkinter-Desktop-App. „Frontend“ = Tkinter-UI (`tree.py`, `ui*.py`, `dialogs_*.py`, `palette.py`, `shortcuts.py`), „Backend“ = Logik-/Prozess-/Datei-Schicht (`core.py`, `storage.py`, `actions_*.py`, `dns_lookup.py`, `exports.py`, `ssh_manager.py`, `scripts/`). Zeilennummern beziehen sich auf Commit `21f78f7`. Die Funde DC-C1 und DC-C2 sind manuell verifiziert.

---

## 🔒 Security

### HOCH
#### [S-H1] Sudo-Passwort im Klartext in lokalen Temp-Skripten, Skripte werden nicht zuverlässig gelöscht
**Datei:** `ssh_manager_app/core.py` (Z. 109–123, 220–244, 364–390, 618–625, 741), `ssh_manager_app/actions_remote.py` (Z. 281)
**Problem:** `SSH_MANAGER_SUDO_PASSWORD='...'` wird in eine `.sh` unter `%APPDATA%\SSH-Manager\tmp` geschrieben. Gelöscht wird nur per `trap` beim Skriptende. Startet WT nicht, wird der Tab hart geschlossen oder greift der Herdr-Fallback, bleibt das Passwort auf der Platte. Skripte ohne Sudo-Passwort (Remote-Befehl, Remote-Skript, Tunnel) werden nie gelöscht und sammeln Hosts, User und Befehle an. Keine restriktiven ACLs. Der Kommentar „encrypted SSH payload“ trifft für die lokale Datei nicht zu.
**Fix:** Passwort nicht ins Skript schreiben, sondern per stdin oder Umgebungsvariable des Child-Prozesses übergeben. Jedes Skript bekommt `trap 'rm -f "$0"' EXIT`. Beim Start-Fehler die Datei löschen. Beim App-Start `tmp/*.sh` älter als 1 h aufräumen.

#### [S-H2] Zertifikate und private Keys liegen auf dem Zielhost weltlesbar in `/tmp`, Deploy setzt keine Rechte
**Datei:** `ssh_manager_app/core.py` (Z. 440–444, 489, 574, 589)
**Problem:** Der Upload per `scp` nach `/tmp/ssh-manager-cert-<uuid>-N` passiert ohne `umask` und `chmod`. Je nach Remote-umask können andere lokale User die Dateien lesen. Bei fehlgeschlagenem Upload wird nicht aufgeräumt. Das Deploy mit `sudo cp -f` erzeugt neue Zieldateien mit Default-Rechten (typisch 0644), private Keys in `/etc/ssl/private` wären dann lesbar.
**Fix:** Vor dem Upload `ssh host 'umask 077; mkdir -m 700 /tmp/ssh-manager-cert-<uuid>'` ausführen und dorthin hochladen. Beim Deploy `sudo install -m 0600 -o root -g root -- src dst` verwenden (Mode wählbar, Default restriktiv). Aufräumen auch im Fehlerpfad.

### MITTEL
#### [S-M1] Fester Here-Doc-Delimiter und ungeprüfter `interpreter` aus Favoriten/History
**Datei:** `ssh_manager_app/core.py` (Z. 331–362), `ssh_manager_app/dialogs_remote.py` (Z. 775–799, 868–899), `ssh_manager_app/storage.py` (Z. 203–208)
**Problem:** Remote-Befehle laufen in einem Here-Doc mit festem Delimiter `__REMOTE_CMD__`. Eine Zeile `__REMOTE_CMD__` im Befehl beendet es, und der Rest läuft **lokal** in Git Bash. `interpreter` kommt über `_apply_spec` ungeprüft aus `ui_state.json` und steht unquotet in der Skriptzeile.
**Fix:** Delimiter pro Lauf zufällig erzeugen (`__REMOTE_CMD_{uuid4().hex}__`). `interpreter` gegen `{"bash", "sh", "python3", "python", "direct"}` prüfen. Das Spec-Dict beim Laden validieren.

#### [S-M2] Vorhersagbarer Remote-Temp-Pfad für lokale Skripte
**Datei:** `ssh_manager_app/core.py` (Z. 345–359)
**Problem:** `remote_tmp = f"/tmp/ssh-manager-$(date +%s)-$$-{basename}"` wird anschließend single-quoted, `$(date)` und `$$` werden also nie expandiert. Der Pfad ist fest und vorhersagbar (Symlink- und Race-Risiko auf Multi-User-Hosts). `basename` geht ungefiltert ein.
**Fix:** Den Namen lokal erzeugen: `f"/tmp/ssh-manager-{uuid.uuid4().hex}-{re.sub(r'[^A-Za-z0-9._-]', '_', basename)}"`, remote `umask 077` setzen.

#### [S-M4] CSV-/Formula-Injection im Export
**Datei:** `ssh_manager_app/exports.py` (Z. 31–41)
**Problem:** Namen, Hosts und Notizen, die mit `=`, `+`, `-` oder `@` beginnen, wertet Excel als Formel aus. XLSX ist nicht betroffen (`inlineStr`).
**Fix:**
```python
def _csv_safe(v: str) -> str:
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
```

#### [S-M6] FileZilla-XML ohne Entity-Schutz und Größenlimit
**Datei:** `ssh_manager_app/storage.py` (Z. 321–367)
**Problem:** `ET.fromstring` expandiert interne Entities (Billion-Laughs-Risiko). Die Datei hat kein Größenlimit. `session_key` enthält `name`, `host` und `port` unescaped, gleiche Einträge kollidieren.
**Fix:** DOCTYPE/ENTITY ablehnen und die Größe begrenzen (`st_size < 5_000_000`), alternativ `defusedxml`. Den Key um einen Index ergänzen.

### NIEDRIG
#### [S-L1] Keystore-Passwort in lokaler Temp-Datei im Standard-Temp-Verzeichnis
**Datei:** `ssh_manager_app/actions_certificate_replace.py` (Z. 78–85, 114–124)
**Problem:** Die Datei wird nur im `finally` gelöscht und bleibt bei einem Prozessabbruch liegen. Remote fehlt `umask 077` vor `printf >`.
**Fix:** Remote `umask 077` setzen. Lokal im App-tmp anlegen und beim Start alte `ssh-manager-keystore-*`-Dateien aufräumen.

#### [S-L2] Passwörter bleiben nach Nutzung in `StringVar` und Result-Dicts
**Datei:** `ssh_manager_app/dialogs_remote.py` (Z. 687–698, 897–898), `ssh_manager_app/dialogs_certificates.py` (Z. 225–226, 382), `ssh_manager_app/dialogs_certificate_replace.py` (Z. 23–24, 104), `ssh_manager_app/dialogs_restart.py` (Z. 20, 118)
**Problem:** Sudo- und Keystore-Passwörter werden nach dem Bauen der Befehle nicht geleert.
**Fix:** Nach dem Bauen der Befehle `var.set("")` und `spec["sudo_password"] = ""` setzen.

---

## 🎨 Design — Code-Architektur

### KRITISCH
#### [DC-C1] `JumpHostDialog._build()` wirft `NameError` (`parent` nicht im Scope) ✔ verifiziert
**Datei:** `ssh_manager_app/dialogs_remote.py` (Z. 64)
**Problem:** `_resolve_jump_host_default_user(parent)` steht in `_build(self)`, `parent` existiert nur in `__init__`. „Über Jumphost öffnen“ stürzt ab. Die Tests umgehen das mit `__new__`.
**Fix:** `_resolve_jump_host_default_user(self.master)` aufrufen und einen Test ergänzen, der den Dialog wirklich konstruiert.

#### [DC-C2] `_append_ssh_config_alias()` wirft `NameError` (`load_ssh_config_sessions` nicht importiert) ✔ verifiziert
**Datei:** `ssh_manager_app/core.py` (Z. 20, 171)
**Problem:** `core.py` importiert aus dem Paket nur `PALETTE, REGISTRY_PATH, SKIP_SESSIONS, Session, WindowsTerminalSettings`. „Als SSH-Config speichern…“ stürzt ab. `actions_remote.py` (Z. 352–357) fängt nur `ValueError` und `OSError`.
**Fix:** `from .storage import load_ssh_config_sessions` ergänzen. Mittelfristig die Funktion nach `storage.py` verschieben (Datei-Logik gehört laut AGENTS.md dorthin).

#### [DC-C3] Startup-Crash bei Nicht-UTF-8-Config oder JSON-Wurzel ≠ Objekt
**Datei:** `ssh_manager_app/storage.py` (Z. 188–189, 227, 328–330, 372–374), `ssh_manager.py` (Z. 213, 222)
**Problem:** `load_ssh_config_sessions` fängt nur `OSError`, `load_filezilla_config_sessions` nur `OSError` und `ET.ParseError`. Eine ANSI-kodierte `~/.ssh/config` oder `sitemanager.xml` wirft `UnicodeDecodeError` im Konstruktor von `SSHManagerApp`, die App startet nicht. `load_ui_state` crasht mit `AttributeError`, wenn `ui_state.json` eine Liste oder `null` enthält.
**Fix:** `isinstance(data, dict)` prüfen. `UnicodeDecodeError`/`ValueError` in die except-Tupel aufnehmen und `read_text(encoding="utf-8", errors="replace")` verwenden.

#### [DC-C4] Zirkuläre Abhängigkeiten, nur durch Funktions-lokale Imports kaschiert
**Datei:** `ssh_manager_app/actions_ui.py` (Z. 9), `ssh_manager_app/ui.py` (Z. 14, 139–505), `ssh_manager_app/dialogs_settings_misc.py` (Z. 807–1131), `ssh_manager_app/actions_remote.py`, `ssh_manager_app/actions_sessions.py`, `ssh_manager_app/actions_app.py`
**Problem:** Es gibt folgende Zyklen:
- `actions_ui` ↔ `ui`
- `ui` → `dialogs_settings_misc` → `actions_ui` (14 lazy Imports)
- `actions_remote` ↔ `actions_ui`
- `actions_sessions` ↔ `actions_app`

Dazu kommen rund 70 Einzeiler-`*_callback`-Wrapper in `ui.py`, die nur den Lazy-Import tragen. Eine geänderte Importreihenfolge kann zu `ImportError` führen.
**Fix:** Die Richtung Models/Storage → Core → Actions → UI festlegen. Die Verdrahtung in einem Composition-Root bündeln, Views bekommen Callbacks injiziert. Klein und schrittweise vorgehen (AGENTS.md-Refactor-Regeln).

### HOCH
#### [DC-H1] Settings-Aliasing: „Zurück“ und „Gespeicherten Stand wiederherstellen“ wirken nicht
**Datei:** `ssh_manager.py` (Z. 195–197), `ssh_manager_app/actions_ui.py` (Z. 12–15, 61–74), `ssh_manager_app/dialogs_settings_misc.py` (Z. 818–826, 1032, 1086–1099)
**Problem:** `settings`, `_persisted_settings` und `_startup_settings` sind **dasselbe** Objekt. `preview_*` mutiert in-place, damit ändert sich der „gespeicherte“ Stand mit. `_import_settings` setzt `_persisted_settings` nicht neu. `_startup_settings` ist ungenutzt.
**Fix:** Beim Start `copy.deepcopy` verwenden. `preview_*` per `dataclasses.replace` auf neue Objekte setzen. `_persisted_settings` nur in `apply_settings` und beim Laden schreiben.

#### [DC-H2] Toter, nicht lauffähiger Duplikat-`SessionEditDialog` in `dialogs_remote.py`
**Datei:** `ssh_manager_app/dialogs_remote.py` (Z. 1176–1442)
**Problem:** Die zweite Kopie von `SessionEditDialog` (das Original liegt in `dialogs_session_edit.py`) referenziert die nicht importierten Namen `uuid`, `_APP_PREFIX` und `_SSH_ALIAS_PREFIX`. Das ist ein Rest eines Splits. `QUICK_USERS` ist ungenutzt importiert.
**Fix:** Block Z. 1176–1442 löschen und den Import entfernen.

#### [DC-H3] Herdr-JSON wird ungeprüft verschachtelt gelesen, der Fallback greift dann nicht
**Datei:** `ssh_manager_app/core.py` (Z. 839–877, 909, 929, 960)
**Problem:** `payload.get("result", {}).get(...)` und `int(item.get("number", 0))` werfen bei `null` oder falschem Typ `AttributeError` bzw. `ValueError`. `launch_tabs` fängt nur `OSError`, `RuntimeError` und `TimeoutExpired`. Der Start bricht ab, und der WT-Fallback wird nicht ausgeführt.
**Fix:** Einen Helper `_dig(payload, *keys, default)` mit `isinstance`-Prüfungen verwenden. `AttributeError`, `ValueError` und `TypeError` in `RuntimeError` umwandeln.

#### [DC-H4] `core.py` ist ein God-Module (1192 Z.) mit fremden Verantwortlichkeiten
**Datei:** `ssh_manager_app/core.py` (gesamt; Z. 165–198, 1145, 1190)
**Problem:** `core.py` mischt WT-/Bash-Builder, Herdr, Launcher, Registry, Hostprüfung, Tk-Pixelbilder (UI-Code) und das Schreiben von `~/.ssh/config` (gehört in `storage`). Der Tab-Befehl wird achtmal identisch zusammengesetzt. Der Abschnittskommentar „UI-State Persistenz“ ist leer.
**Fix:** Eine gemeinsame Funktion `_build_wt_tab(...)` einführen. Schrittweise in `terminal/`, `sources/winscp_registry.py` und `ui/checkbox_images.py` aufteilen.

#### [DC-H5] `SessionTree` ist eine God-Class (1877 Z., ~45 Callback-Parameter)
**Datei:** `ssh_manager_app/tree.py` (Z. 44–90, 1223–1663, 1809–1861)
**Problem:** `_show_session_menu` hat 345 Zeilen mit kopierten Blöcken. Treeview, Overlay, Tooltip, Suche, Host-Check-Threads und Business-Regeln (`source in ("app","ssh_alias")`) liegen in einer Klasse.
**Fix:** Callbacks als ein `TreeActions`-Objekt übergeben. Menüs nach `tree_menus.py` auslagern. `Session.is_editable` ergänzen.

#### [DC-H6] `ui.py` (1188 Z.) und `build_main_ui()` (250 Z.) bündeln Theming, Toolbar, Menü und Verdrahtung
**Datei:** `ssh_manager_app/ui.py` (Z. 508–663, 938–1187)
**Problem:** `build_main_ui` legt dynamisch Attribute auf `tk.Tk` an. Das ist genau die „stille“ UI-Split-Gefahr aus AGENTS.md.
**Fix:** Mittelfristig in `theme_styles.py`, `toolbar.py`, `menubar.py` und `main_window.py` aufteilen.

#### [DC-H7] `SettingsView` (~1050 Z.) mischt zehn Sektionen, Drag & Drop, Shortcut-Capture und Import/Export
**Datei:** `ssh_manager_app/dialogs_settings_misc.py` (Z. 82–1133)
**Problem:** Die View greift auf `app._persisted_settings`, `app._shortcut_manager` und andere Interna zu. Die Typannotation `"SSHManagerApp"` wird nicht importiert. `SshConfigInspectDialog` ist fachfremd, der Kommentar „MoveFolderDialog“ (Z. 77) verwaist.
**Fix:** Eine Klasse pro Sektion mit `load()` und `collect()`. `SshConfigInspectDialog` in eine eigene Datei.

#### [DC-H8] Actions koppeln über ~180 Zugriffe an private App-Attribute
**Datei:** `ssh_manager_app/actions_*.py`, `ssh_manager.py` (Z. 212–236)
**Problem:** `app` ist untypisiert. `_initial_toolbar_search_texts` dient als Laufzeit-Ablage für Palette, Remote-Favoriten und Whitelist (irreführender Name). `getattr(app, "_x", …)` und `app.__dict__.get(...)` werden als Ersatz für eine Zustandsklasse genutzt.
**Fix:** Einen `AppState`-Dataclass und ein `AppContext`-Protocol einführen. `load_ui_state` und `save_ui_state` typisieren.

### MITTEL
#### [DC-M1] Worker-Threads ohne Fehlerbehandlung hinterlassen hängende Dialoge
**Datei:** `ssh_manager_app/actions_certificate_replace.py` (Z. 183–193), `ssh_manager_app/actions_restart.py` (Z. 270–286), `ssh_manager_app/actions_dns.py` (Z. 69–95), `ssh_manager_app/dns_lookup.py` (Z. 85–86)
**Problem:** Siehe DX-H3 und DX-H4. Bei `dns_lookup` liegt `normalize_*` außerhalb des `try`-Blocks.
**Fix:** Ein einheitliches Worker-Muster (`try/except` → Queue → `after`-Polling) als Hilfsklasse.

#### [DC-M2] `after()` wird aus Worker-Threads aufgerufen (nicht thread-sicher)
**Datei:** `ssh_manager_app/tree.py` (Z. 1814–1816), `ssh_manager_app/dialogs_certificates.py` (Z. 144–154), `ssh_manager_app/actions_certificate_replace.py` (Z. 191), `ssh_manager_app/actions_dns.py` (Z. 91–93)
**Problem:** Wird das Fenster geschlossen, entsteht `RuntimeError` bzw. `TclError`. Die Behandlung ist inkonsistent.
**Fix:** `queue.Queue` plus `after`-Polling im Main-Thread verwenden (wie bereits in `actions_restart`).

#### [DC-M3] Duplizierte SSH-Hilfslogik (Quoting, Sudo-Prelude, ssh-Argv, Regexes)
**Datei:** `ssh_manager_app/core.py` (Z. 104–106, 135–143, 681, 702–711, 1048–1049), `ssh_manager_app/actions_certificate_replace.py` (Z. 20–22, 105–114), `ssh_manager_app/dialogs_certificates.py` (Z. 14–63), `ssh_manager_app/actions_restart.py` (Z. 30–46), `ssh_manager_app/dialogs_base.py` (Z. 10–11)
**Problem:** Folgende Logik ist mehrfach vorhanden:
- `_shell_single_quote` dreifach
- Sudo-Wrapper dreifach
- ssh-Argumentlisten vierfach
- `_HOSTNAME_RE` und `_USERNAME_RE` doppelt mit unterschiedlicher Regel (leerer User erlaubt bzw. nicht erlaubt)

**Fix:** Ein Modul `ssh_utils.py` mit `shell_quote`, `ssh_argv`, `scp_target`, `SUDO_PRELUDE` und den Regexes.

#### [DC-M4] Duplizierte Dialoge und handkopierte Zentrierlogik
**Datei:** `ssh_manager_app/dialogs_remote.py` (Z. 225–430), `ssh_manager_app/actions_sessions.py` (Z. 224–355), `ssh_manager_app/actions_notes.py` (Z. 11–68)
**Problem:** `SshCopyIdDialog` und `SshRemoveKeyDialog` sind fast identisch. Inline-Toplevels stehen in der Action-Schicht. Die Zentrierlogik ist rund zehnmal kopiert, obwohl `center_on_parent` existiert.
**Fix:** Eine Basisklasse `ModalDialog` und `KeySelectDialog(mode)` einführen. Die Inline-Dialoge nach `dialogs_*` verschieben.

#### [DC-M5] Fachlogik in Dialog- und Action-Modulen, Schichtverletzungen
**Datei:** `ssh_manager_app/actions_certificate_replace.py` (Z. 20–159), `ssh_manager_app/dialogs_certificates.py` (Z. 18–63), `ssh_manager_app/actions_open.py` (Z. 28–49), `ssh_manager_app/exports.py` (Z. 8), `ssh_manager_app/tree.py` (Z. 10)
**Problem:** Die Schichtgrenzen sind an mehreren Stellen verletzt:
- Der Zertifikat-Scan steckt in einer Action.
- Das SSH-Folder-Listing steckt im Dialog.
- WinSCP-Registry-Schreiben und -Lesen sind getrennt.
- `exports.py` importiert aus `dialogs_export`.
- Der Tree ruft `core.check_host_reachable` direkt auf.

**Fix:** Service-Module (`services/certificates.py`, `services/winscp.py`) einführen. `EXPORT_COLUMNS` nach `exports.py` verschieben.

#### [DC-M6] Polymorphe Dialog-Results und toter Legacy-Pfad
**Datei:** `ssh_manager_app/dialogs_base.py` (Z. 140), `ssh_manager_app/dialogs_remote.py` (Z. 527, 868–899), `ssh_manager_app/actions_remote.py` (Z. 168–230)
**Problem:** `UserDialog.result` ist `str` oder `tuple`. `RemoteCommandDialog.result` hat 3, 4 oder 5 Elemente. `hasattr(self, "_run_mode")` ist ein toter Legacy-Zweig. `resolve_users_for_sessions` ignoriert Quick-Users und Default-User aus den Settings.
**Fix:** Result-Dataclasses (`UserChoice`, `RemoteRunSpec`) einführen und den Legacy-Zweig entfernen.

#### [DC-M8] `_export_settings` ruft `_collect_settings()` außerhalb des `try`-Blocks auf
**Datei:** `ssh_manager_app/dialogs_settings_misc.py` (Z. 776–790), `ssh_manager_app/actions_app.py` (Z. 43, 50)
**Problem:** Der `ValueError` endet als stille Callback-Exception. `actions_app` greift auf die private Methode zu. `__import__("json")` statt `json`.
**Fix:** `ValueError` abfangen und melden. Eine öffentliche `export_settings()`-Methode anbieten.

#### [DC-M9] Dialog-Styling hängt am deutschen Button-Text, `<Map>`-Hook läuft bei jedem Mapping
**Datei:** `ssh_manager_app/ui.py` (Z. 710–746, 795–825)
**Problem:** `label.startswith("löschen")` steuert Stil und Icon. Eine Textänderung ändert unbemerkt das Verhalten. Der Widget-Baum wird bei jedem Map dreimal durchlaufen.
**Fix:** Den Stil explizit über `build_dialog_actions(primary_style=…)` setzen. Restyle nur einmal pro Toplevel.

#### [DC-M10] `socket.setdefaulttimeout()` prozessweit aus Worker-Threads
**Datei:** `ssh_manager_app/dns_lookup.py` (Z. 243–254)
**Problem:** Der Aufruf beeinflusst parallel laufende Host-Checks (Race).
**Fix:** Einen Resolver-Thread mit `Future.result(timeout)` verwenden.

#### [DC-M11] `ssh_manager.py` ist keine dünne Bootstrap-Shell mehr
**Datei:** `ssh_manager.py` (Z. 42–183, 242)
**Problem:** Dort stehen 140 Zeilen Win32-ctypes-Code für das Icon, dazu Magic Numbers (`"750x550"`, 250 ms, AppUserModelID).
**Fix:** `set_window_icon` nach `ssh_manager_app/window_icon.py` verschieben und die Konstanten benennen.

#### [DC-M12] Magic Strings für Quellen und virtuelle Ordner
**Datei:** `ssh_manager_app/tree.py` (Z. 654, 1296ff), `ssh_manager_app/actions_ui.py` (Z. 286, 290, 367, 399), `ssh_manager_app/actions_app.py` (Z. 175, 183), `ssh_manager_app/actions_remote.py` (Z. 233–245)
**Problem:** `("app", "ssh_alias")` steht rund zwölfmal im Code. `"★ Favoriten"` und `"↺ Zuletzt verwendet"` sind hartkodiert, dazu Limits wie `[:10]`, `[:25]` und `450` ms.
**Fix:** Ein `SessionSource`-Enum und Konstanten in `constants.py` anlegen, dazu `Session.is_editable`.

#### [DC-M13] `actions_sessions`: manuelles Feld-Kopieren, `rename_folder` ohne Validierung
**Datei:** `ssh_manager_app/actions_sessions.py` (Z. 78–110, 142–165, 199–207, 94)
**Problem:** Mehrere Schwachstellen:
- `Session` wird dreimal von Hand kopiert.
- Ein `/` im neuen Ordnernamen zerlegt den Pfad.
- Bei Namenskollisionen werden Ordner still zusammengelegt.
- `sessions[0]` wird ohne Leerprüfung verwendet.

**Fix:** `dataclasses.replace` verwenden und den Namen validieren (leer, `/`, Duplikat).

#### [DC-M14] Whitelist wird vor der Validierung persistiert, Stil-Ausreißer im Dialog
**Datei:** `ssh_manager_app/dialogs_certificate_replace.py` (Z. 27–45, 94)
**Problem:** `_ok` speichert die Whitelist, bevor die Eingabe geprüft ist. Dazu kommen Semikolon-Ketten, die vom Dialogstil der übrigen Module abweichen.
**Fix:** Erst nach erfolgreicher Validierung persistieren.

### NIEDRIG
#### [DC-L1] Root-`winreg.py`-Stub ist irreführend
**Datei:** `winreg.py`, `ssh_manager_app/core.py` (Z. 18), `tests/conftest.py`
**Problem:** Unter Windows ist `winreg` ein Built-in-Modul und wird **nicht** überschattet (geprüft: `'winreg' in sys.builtin_module_names` → `True`). Der Stub ist also nur für Nicht-Windows-Plattformen relevant und doppelt den Test-Stub in `conftest.py`.
**Fix:** Den Root-Stub entfernen, wenn kein Nicht-Windows-Start nötig ist. Sonst `winreg` in `core.py` lazy bzw. per `try/except ImportError` importieren.

#### [DC-L2] Callback-Vertrag `on_copy_ssh_command` inkonsistent
**Datei:** `ssh_manager_app/tree.py` (Z. 80, 1301–1304, 1443–1446), `ssh_manager_app/ui.py` (Z. 380–385), `ssh_manager_app/actions_remote.py` (Z. 335)
**Problem:** Die Annotation lautet `Session`, aufgerufen wird der Callback mit `list[Session]`. `copy_ssh_command` ist ungenutzt.
**Fix:** Die Signatur auf `list[Session]` vereinheitlichen und den toten Wrapper entfernen.

#### [DC-L3] `check_folder_hosts`: `and`/`or`-Präzedenz und verstecktes Timeout-Attribut
**Datei:** `ssh_manager_app/tree.py` (Z. 1836–1852)
**Problem:** Die Bedingung steht ohne Klammern, danach wird doppelt gefiltert. Das Timeout kommt per `getattr(self, "_host_check_timeout", 3)`.
**Fix:** Einmal filtern und das Timeout als Parameter übergeben.

#### [DC-L4] Tote Reste und unbenutzte Imports
**Datei:** `ssh_manager_app/tree.py` (Z. 3, 812, 1875), `ssh_manager_app/core.py` (Z. 212), `ssh_manager_app/actions_ui.py` (Z. 151, 251, 262), `ssh_manager_app/dialogs_settings_misc.py` (Z. 667, 699–706)
**Problem:** Gefunden wurden:
- `import socket` ungenutzt
- Zeile `settings = …` doppelt
- No-op-`tag_bind`
- `restore_saved_settings` ungenutzt
- `_MOD_ALIASES` ungenutzt
- `Session` als Annotation ohne Import
- verwaiste Abschnittskommentare

**Fix:** Mit ruff/pyflakes prüfen und aufräumen.

#### [DC-L5] `__init__.py` mit Star-Imports ohne `__all__`, `__import__("re")`, `dialogs_user.py`-Re-Export
**Datei:** `ssh_manager_app/__init__.py` (Z. 1–3), `ssh_manager_app/dialogs_base.py` (Z. 10–11), `ssh_manager_app/dialogs_user.py`
**Problem:** Der Star-Import leakt `json`, `os`, `Path` usw. Module importieren über das Paket-Root statt aus den konkreten Modulen.
**Fix:** `__all__` pflegen und auf konkrete Modul-Imports umstellen.

#### [DC-L6] AGENTS.md-Modulübersicht veraltet
**Datei:** `AGENTS.md` (Abschnitt „Schichten / Module“)
**Problem:** Nicht beschrieben sind `actions_*.py`, `palette.py`, `shortcuts.py`, `dns_lookup.py`, `exports.py`, `ui_components.py` und mehrere `dialogs_*`.
**Fix:** Die Übersicht und die Abhängigkeitsrichtung aktualisieren.

---

## 🖥️ Design — UI/UX

### KRITISCH
#### [DX-C1] Kein `report_callback_exception`, Fehler in der EXE sind unsichtbar
**Datei:** `ssh_manager.py` (Z. 189–254, Klasse `SSHManagerApp`)
**Problem:** Jede unbehandelte Exception in einem Tk-Callback geht nur nach stderr. Die portable EXE hat keine Konsole. Der User klickt, und es passiert nichts.
**Fix:**
```python
def report_callback_exception(self, exc, val, tb):
    logging.error("".join(traceback.format_exception(exc, val, tb)))
    messagebox.showerror("Unerwarteter Fehler", f"{exc.__name__}: {val}", parent=self)
```
Dazu ein Logfile unter `%APPDATA%\SSH-Manager\error.log` einrichten.

### HOCH
#### [DX-H1] `save_*` ohne Fehlerbehandlung, `close_app` kann das Schließen blockieren
**Datei:** `ssh_manager_app/storage.py` (Z. 31–33, 231–248, 264–266, 301–318), `ssh_manager_app/actions_app.py` (Z. 54–56), `ssh_manager_app/actions_sessions.py`, `ssh_manager_app/actions_notes.py` (Z. 38), `ssh_manager_app/actions_ui.py` (Z. 45, 130, 385)
**Problem:** Mehrere Folgen bei einem `OSError` (Platte voll, Datei gesperrt):
- Die Änderung ist nur im Speicher, und der User merkt es nicht.
- `close_app` wirft vor `destroy()`, das Fenster lässt sich nicht schließen.
- `add_session` kann Notes und Sessions inkonsistent speichern.

**Fix:** Bei `close_app` `try/except OSError` → Warnung, `finally: app.destroy()`. Für Speicheraufrufe einen Wrapper `safe_save(app, fn, *args)` mit messagebox.

#### [DX-H2] Korrupte JSON-Dateien führen still zu Datenverlust
**Datei:** `ssh_manager_app/storage.py` (Z. 24–28, 186–228, 251–261, 269–298)
**Problem:** Bei einem `JSONDecodeError` laden die Loader leere Defaults. Der nächste `save_app_sessions` überschreibt die defekte Datei, und alle eigenen Verbindungen sind weg, ohne Meldung und ohne Backup.
**Fix:** Die defekte Datei nach `*.corrupt-<timestamp>` kopieren, eine Warnung sammeln und nach `build_main_ui` anzeigen. Zusätzlich atomar schreiben (siehe BP-M2).

#### [DX-H3] Zertifikat-Replace: Worker ohne `try/except`, modaler Dialog hängt
**Datei:** `ssh_manager_app/actions_certificate_replace.py` (Z. 183–193), `ssh_manager_app/dialogs_certificate_replace.py` (Z. 219–236)
**Problem:** Eine unerwartete Exception lässt den Thread sterben. Der `grab_set`-Progress-Dialog bleibt offen. Der Fortschritt ist nur indeterminate (40 s Timeout pro Host, seriell), und es gibt keinen Abbrechen-Button.
**Fix:** Den Worker in `try/except` kapseln, bei einem Fehler `progress.close()` und `showerror` per `after`. Dazu „Host X von N“ anzeigen und einen Abbrechen-Button ergänzen.

#### [DX-H4] Server-Neustart: `run_one` ohne `try/except`, Dialog bleibt auf „Neustart läuft…“
**Datei:** `ssh_manager_app/actions_restart.py` (Z. 270–304)
**Problem:** Ohne das `done`-Event läuft `pump_events` endlos. Nach dem Schließen des Dialogs folgen `TclError`s auf zerstörten Widgets.
**Fix:** In `run_one` `except Exception` abfangen und ein `RestartResult("error", …)` zurückgeben. In `pump_events` `if not progress.winfo_exists(): return` einbauen.

#### [DX-H5] Remote-Befehl: Command-Build außerhalb des `try`-Blocks, nach Bestätigung passiert nichts
**Datei:** `ssh_manager_app/actions_remote.py` (Z. 257–281)
**Problem:** `build_remote_command_wt_command` und `build_remote_script_wt_command` können `ValueError` bzw. `OSError` werfen (Temp-Datei, fehlendes Skript). Das endet als stille Callback-Exception.
**Fix:** Die `cmd = …`-Zeilen in den bestehenden `try`-Block verschieben.

### MITTEL
#### [DX-M1] Empty State zeigt bei 0 Suchtreffern den Erstnutzer-Text
**Datei:** `ssh_manager_app/tree.py` (Z. 255–262, 836, 1726)
**Problem:** „Keine Verbindungen vorhanden“ plus „+ Verbindung hinzufügen“ erscheint auch bei einer aktiven Suche ohne Treffer. Das wirkt, als wären alle Verbindungen verschwunden.
**Fix:** `_update_empty_state(sessions, filtered=bool(q))` verwenden. Bei aktiver Suche: „Keine Treffer für ‚…‘“ plus „Suche zurücksetzen“.

#### [DX-M2] Command Palette ohne „Keine Treffer“-Hinweis
**Datei:** `ssh_manager_app/palette.py` (Z. 573–600)
**Problem:** Die Liste ist leer, und der Placeholder ist ausgeblendet. Der User sieht eine leere Fläche.
**Fix:** Bei `not ranked and raw_query.strip()` ein Label „Keine Treffer“ einblenden.

#### [DX-M3] Palette verschluckt Callback-Fehler mit `traceback.print_exc()`
**Datei:** `ssh_manager_app/palette.py` (Z. 674–679)
**Problem:** Die Palette ist schon geschlossen, und in der EXE geht der Fehler verloren.
**Fix:** `showerror` aufrufen oder an `report_callback_exception` weiterreichen.

#### [DX-M4] Hosts prüfen: Mehrfachauslösung, unbegrenzte Threads, veraltete Item-IDs, kein Feedback
**Datei:** `ssh_manager_app/tree.py` (Z. 1809–1824), `ssh_manager_app/core.py` (Z. 718–724)
**Problem:** Mehrere Schwachstellen:
- Jeder Klick startet neue Threads, ohne Limit.
- Nach einem Rebuild führt eine veraltete Item-ID zu `TclError: Item not found`.
- Der Grund (DNS-Fehler oder Timeout) wird nicht angezeigt.
- Bei leerer Auswahl gibt es keine Meldung.

**Fix:** `self._tv.exists(iid)` prüfen und einen Generations-Zähler einführen. `ThreadPoolExecutor(max_workers=20)` verwenden. Bei leerer Auswahl einen Toast zeigen.

#### [DX-M5] Zertifikats-Ordnerauswahl: Buttons während des Ladens aktiv, Fehler lässt UI disabled
**Datei:** `ssh_manager_app/dialogs_certificates.py` (Z. 128–154)
**Problem:** Eine Exception im Worker lässt Combobox und Listbox dauerhaft auf `disabled`. „Diesen Ordner verwenden“ ist während des Ladens klickbar.
**Fix:** Im Worker `try/except` mit einem Fehlertext. Die Buttons während des Ladens deaktivieren.

#### [DX-M6] DNS-Auflösung: Worker ohne `try/except`, Progress-Dialog bleibt stehen
**Datei:** `ssh_manager_app/actions_dns.py` (Z. 69–95)
**Problem:** Eine Exception in `resolve_dns_value` lässt den Thread sterben. `except Exception: return` um `after` schluckt Fehler.
**Fix:** `except Exception` → `progress.close()` und `showerror` per `after`.

#### [DX-M7] „In WinSCP öffnen“ friert die UI ein (`wait` + `sleep` im UI-Thread)
**Datei:** `ssh_manager_app/actions_open.py` (Z. 70–80)
**Problem:** Im Tab-Modus bis zu ca. 5 s pro Session, bei 5 Sessions rund 25 s „Keine Rückmeldung“.
**Fix:** Die Schleife in einen Daemon-Thread oder eine `after`-Kette verlagern und einen Toast „WinSCP wird geöffnet…“ zeigen.

#### [DX-M8] Registry-Fehler: modaler Dialog bei jedem Start, falscher Erfolgs-Toast, stille Skips
**Datei:** `ssh_manager.py` (Z. 201–210), `ssh_manager_app/actions_ui.py` (Z. 295–308, 412–414), `ssh_manager_app/core.py` (Z. 1115–1129)
**Problem:** Mehrere Schwächen:
- Der Fehlerdialog erscheint auch ohne installiertes WinSCP oder bei ausgeblendeter Quelle, und das ohne `parent`.
- Nach einem Fehler kommt trotzdem der Toast „neu geladen“.
- Übersprungene Sessions werden nur nach stderr geschrieben.

**Fix:** `FileNotFoundError` still behandeln. `rebuild_sessions` gibt einen Status zurück. Einen Hinweis „n Sessions übersprungen“ anzeigen.

#### [DX-M9] Settings-Import akzeptiert fremde JSON-Dateien und setzt still alles auf Default
**Datei:** `ssh_manager_app/storage.py` (Z. 38–39), `ssh_manager_app/dialogs_settings_misc.py` (Z. 802–811)
**Problem:** Der Import von z. B. `notes.json` meldet „Einstellungen importiert“ und setzt alles zurück, ohne Rückfrage.
**Fix:** Mindestens einen bekannten Schlüssel verlangen, sonst `ValueError`. Vor dem Anwenden per `askyesno` bestätigen lassen.

### NIEDRIG
#### [DX-L1] SSH-Config-Inspect blockiert die UI (`ssh -G` synchron im Konstruktor)
**Datei:** `ssh_manager_app/dialogs_settings_misc.py` (Z. 48–58)
**Problem:** Die App friert bis zu 5 s ein. Timeout und fehlendes `ssh` erscheinen als generische Fehlermeldung.
**Fix:** Den Dialog sofort mit „Lade…“ öffnen und `ssh -G` im Thread ausführen. `TimeoutExpired` und `FileNotFoundError` gezielt melden.

#### [DX-L2] Fehlerdialoge ohne `parent`, uneinheitliche Titel, kein Start-Feedback
**Datei:** `ssh_manager_app/actions_remote.py` (Z. 124, 142, 165), `ssh_manager_app/actions_sessions.py` (Z. 191)
**Problem:** Die Dialoge können hinter dem Hauptfenster landen. Die Titel weichen voneinander ab („Fehler“, „Fehler beim Starten“ …).
**Fix:** `parent=app` setzen und einen gemeinsamen `show_error(app, title, msg)` einführen. Optional einen Toast „Terminal gestartet“.

---

## ✅ Best Practice

### HOCH
#### [BP-H1] Zertifikats-Zielordner nur mit `startswith("/")` geprüft
**Datei:** `ssh_manager_app/dialogs_certificates.py` (Z. 358–386)
**Problem:** `..`, Steuerzeichen und Systemwurzeln (`/`, `/etc`, `/usr`) werden für Schreiboperationen mit sudo akzeptiert.
**Fix:** Mit `posixpath.normpath` normalisieren und `..` sowie Steuerzeichen ablehnen. Bei kritischen Wurzeln zusätzlich bestätigen lassen.

#### [BP-H2] Ports aus Registry, JSON und XML werden nicht auf 1–65535 geprüft
**Datei:** `ssh_manager_app/core.py` (Z. 1107), `ssh_manager_app/storage.py` (FileZilla- und App-Session-Loader)
**Problem:** `int(...)` ohne Bereichsprüfung. Werte aus der Registry können einen beliebigen Typ haben.
**Fix:** `1 <= int(port) <= 65535` prüfen, sonst 22 bzw. den Eintrag verwerfen.

### MITTEL
#### [BP-M1] Kein Logging-Konzept, viele `except Exception: pass`
**Datei:** `ssh_manager_app/tree.py` (Z. 321, 351, 359, 385, 637), `ssh_manager_app/palette.py` (Z. 443, 498, 677), `ssh_manager_app/shortcuts.py` (Z. 364–411), `ssh_manager_app/actions_ui.py` (Z. 50, 222), `ssh_manager_app/actions_app.py` (Z. 130, 268), `ssh_manager_app/core.py` (Z. 880–884, 1015–1036, 1116–1128), `ssh_manager_app/dns_lookup.py` (Z. 99–101)
**Problem:** Es gibt drei Muster nebeneinander (messagebox, `print_exc`, `pass`). Der Herdr→WT-Fallback läuft still, ohne Hinweis.
**Fix:** `logging` mit rotierendem Datei-Handler in `%APPDATA%\SSH-Manager` einführen. Konkrete Exceptions fangen. Beim Fallback einen Toast zeigen.

#### [BP-M2] Nicht-atomare Schreibvorgänge, `save_ui_state` mutiert sein Argument
**Datei:** `ssh_manager_app/storage.py` (Z. 31–33, 231–248, 264–266, 301–318, 88–102), `ssh_manager_app/dialogs_settings_misc.py` (Z. 85–111)
**Problem:** Ein Absturz während `write_text` korrumpiert die Datei. `save_ui_state` entfernt per `pop` Keys aus dem übergebenen Dict. Ein einzelnes defektes Feld in `load_settings_from_path` (160 Z.) setzt alle Einstellungen zurück. Die Allowlists (Akzent, Schrift, Theme) sind doppelt gepflegt.
**Fix:** Einen zentralen Helper `_atomic_write_json(path, data)` (Temp-Datei plus `os.replace`) einführen. Auf einer Kopie des Dicts arbeiten. Felder einzeln mit Fallback parsen. Die Allowlists einmal definieren.

#### [BP-M3] Keine Retry-Logik oder `ConnectTimeout` für idempotente SSH-Probes
**Datei:** `ssh_manager_app/actions_restart.py` (Z. 49–65, 120–143), `ssh_manager_app/dialogs_certificates.py` (Z. 21–23, 44–52)
**Problem:** Ein einzelner Netzwerkaussetzer bricht ab. Bei den Probes fehlen `-o ConnectTimeout` und `BatchMode`.
**Fix:** Die Probes (`_read_boot_id`, `_service_*`) mit 2–3 Versuchen und Backoff ausführen, aber nicht `reboot`. `-o ConnectTimeout=5 -o BatchMode=yes` ergänzen.

#### [BP-M4] Unbegrenzte Parallelität bei Restart und serieller Zertifikat-Scan
**Datei:** `ssh_manager_app/actions_restart.py` (Z. 17–19, 286), `ssh_manager_app/actions_certificate_replace.py`
**Problem:** Es läuft ein Thread pro Host, ohne Obergrenze. Der Scan ist seriell mit 40 s pro Host. Bei Massen-Reboots wird die Hostanzahl nicht hervorgehoben.
**Fix:** `ThreadPoolExecutor(max_workers=8)` verwenden. Bei mehr als 5 Hosts die Anzahl in der Bestätigung hervorheben.

### NIEDRIG
#### [BP-L1] `code "…"` mit `shell=True`, Fehlermeldung „VS Code nicht gefunden“ greift nie
**Datei:** `ssh_manager_app/actions_open.py` (Z. 22), `ssh_manager_app/actions_sessions.py` (Z. 189)
**Problem:** Mit `shell=True` löst ein fehlendes `code` keinen `OSError` aus. Die Funktion ist zudem doppelt vorhanden.
**Fix:** `code_path = shutil.which("code")` ermitteln und `subprocess.Popen([code_path, str(path)])` aufrufen. Daraus eine gemeinsame Hilfsfunktion machen.

#### [BP-L2] Build: UPX aktiv, kein Hash-Pinning, keine Signatur
**Datei:** `ssh_manager.spec` (Z. 38), `scripts/build_windows.ps1` (Z. 15)
**Problem:** UPX-gepackte PyInstaller-EXEs werden häufig von Virenscannern markiert. `pip install` läuft ohne `--require-hashes`, und es gibt keinen `signtool`-Schritt.
**Fix:** `upx=False` setzen. Optional `pip-compile --generate-hashes` und `signtool sign` ergänzen.

---

## 📦 Package-Scan

### CVEs
Keine bekannten Schwachstellen. `pip-audit` (PyPI/OSV) meldet für alle direkten und transitiven Abhängigkeiten (ttkbootstrap 2.2.2, Pillow 12.3.0, pytest 9.1.1, pyinstaller 6.22.2) keine Funde.

### Veraltete Versionen
- `pyinstaller`: v6.22.2 installiert, v6.22.3 verfügbar (Patch, keine Breaking Changes)
- `ttkbootstrap`: v2.2.2 installiert, v2.2.3 verfügbar (Patch, keine Breaking Changes)
- `pyinstaller-hooks-contrib` (transitiv): v2026.7 installiert, v2026.8 verfügbar

### Lizenz-Probleme
- `pyinstaller` (GPLv2+ mit Bootloader-Ausnahme): unkritisch, die erzeugte EXE fällt nicht unter die GPL.
- `Pillow` (MIT-CMU) und `ttkbootstrap` (MIT AND (Apache-2.0 OR BSD-2-Clause)): permissiv. Bei Weitergabe der EXE die Lizenztexte mitliefern.

### Unused Dependencies
Keine.

---

## Ursprüngliche Audit-Zusammenfassung (historisch)

| Sektion | KRITISCH | HOCH | MITTEL | NIEDRIG | Total |
|---|---|---|---|---|---|
| 🔒 Security | 2 | 4 | 6 | 2 | 14 |
| 🎨 Design — Architektur | 4 | 8 | 14 | 6 | 32 |
| 🖥️ Design — UI/UX | 1 | 5 | 9 | 2 | 17 |
| ✅ Best Practice | 0 | 2 | 4 | 2 | 8 |
| 📦 Package-Scan | 0 | 0 | 0 | 3 | 3 |
| **Total** | **7** | **19** | **33** | **15** | **74** |

## Done

Abgeschlossene Punkte; ursprüngliche Beschreibung zur Nachvollziehbarkeit.

#### ~~[S-C1] Command Injection über `shell=True`-WT-String (Name, Alias, Host, User, Profil, Farbe)~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/core.py` (Z. 43–101, 135–143, 998), `ssh_manager_app/storage.py` (Z. 278–293, 337–352, 407–413), `ssh_manager_app/dialogs_session_edit.py` (Z. 110–114, 213–261, 299–307)
**Problem:** `build_wt_command()` & Co. bauen einen String, den `TerminalLauncher._launch_windows_command` mit `subprocess.Popen(command, shell=True)` über cmd.exe startet. Unquotiert bzw. nur in `"..."` eingebettet landen dort: `display_name` im `--title`, `ssh {alias}` und `ssh {user}@{host}`, `-p "{profile_name}"` und `--tabColor "{color}"`. Validiert werden Host und User nur beim WinSCP-Registry-Import (`core.py` Z. 1115–1129) und in einigen Dialogen. Nicht validiert werden FileZilla (`sitemanager.xml`), `~/.ssh/config`, `app_sessions.json`, der SSH-Alias im Edit-Dialog (nur „nicht leer“), der Session-Name und WinSCP-Sessionnamen. Beispiel: Ein Name wie `x" & calc & "` führt lokal Befehle aus, und `;` startet über den WT-Subcommand-Parser einen beliebigen weiteren Tab. Dasselbe gilt für den Herdr-Pfad (`core.py` Z. 941).
**Fix:** Allowlist-Validierung zentral beim Laden aller Quellen und im Edit-Dialog:
```python
_ALIAS_RE = re.compile(r"[A-Za-z0-9._-]+")      # .fullmatch, nicht mit '-' beginnend
_HOST_RE  = re.compile(r"[A-Za-z0-9._:-]+")
_TITLE_FORBIDDEN = re.compile(r'["&|<>^%;\r\n]')
```
Titel bereinigen, `profile_name` und Farbe (`#[0-9a-fA-F]{6}`) prüfen. Mittelfristig `wt.exe` als Argumentliste ohne `shell=True` starten (`";"` als eigenes Argument).

#### ~~[S-H3] Tunnel-Befehl ungequotet, Regex-Allowlists lassen `\n` und führendes `-` durch~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/core.py` (Z. 738, 1048–1049), `ssh_manager_app/dialogs_base.py` (Z. 10–11), `ssh_manager_app/dialogs_remote.py` (Z. 1133–1149)
**Problem:** `ssh -N -L {lp}:{remote_host}:{rp} {user}@{ssh_server}` steht ungequotet im Bash-Skript. `_HOSTNAME_RE` und `_USERNAME_RE` nutzen `.match` mit `^...$`, `$` akzeptiert aber ein abschließendes `\n`, ein Zeilenumbruch gelangt so in die Skriptdatei. Werte wie `-oProxyCommand=…` werden nicht abgelehnt (Option-Injection).
**Fix:** `re.fullmatch` verwenden, führendes `-` ablehnen. Im Skript mit `_shell_single_quote` quoten: `ssh -N -L {q(f"{lp}:{rh}:{rp}")} -- {q(f"{user}@{server}")}`.

#### ~~[S-H4] Settings-Import und `ui_state.json` schleusen ungeprüfte Werte in den Terminalstart~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/dialogs_settings_misc.py` (Z. 536, 795–811, 1066), `ssh_manager_app/storage.py` (Z. 155–157, 192–226)
**Problem:** `profile_name` (Freitext), `title_mode` und `session_colors` werden weder in der UI noch beim Laden geprüft und landen im `shell=True`-String (siehe S-C1). `_import_settings` lädt eine beliebige JSON-Datei und wendet sie sofort an. Eine präparierte Datei genügt für eine Befehlsausführung beim nächsten Verbindungsaufbau.
**Fix:** Beim Laden und Import validieren: `re.fullmatch(r"[A-Za-z0-9 ._()-]{1,64}", profile_name)`, `title_mode` gegen eine Allowlist, Farben gegen `#[0-9a-fA-F]{6}`. Ungültige Werte auf den Default setzen.

#### ~~[S-M3] Argument-Injection bei `ssh`, `ssh -G` und `nslookup`~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/dialogs_settings_misc.py` (Z. 48–55), `ssh_manager_app/actions_certificate_replace.py` (Z. 107–111), `ssh_manager_app/actions_restart.py` (Z. 40–46), `ssh_manager_app/dialogs_certificates.py` (Z. 20–26), `ssh_manager_app/dns_lookup.py` (Z. 191–195)
**Problem:** Alias bzw. `user@host` und die DNS-Query werden ohne `--` übergeben. Ein Alias `-oProxyCommand=…` aus einer manipulierten Config wird als ssh-Option ausgeführt. `nslookup` interpretiert eine Query wie `-server=…` als Option.
**Fix:** `["ssh", ..., "--", target]` und `["ssh", "-G", "--", alias]` verwenden. Die Query per `ipaddress.ip_address` oder Hostnamen-Regex ohne führendes `-` prüfen.

#### ~~[S-M5] Ungeprüfte Werte werden in `~/.ssh/config` geschrieben (Direktiven-Injection)~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/core.py` (Z. 165–198)
**Problem:** `_append_ssh_config_alias` schreibt `hostname`, `target_user` und `jump_host` zeilenweise ohne Prüfung. Ein Zeilenumbruch (siehe S-H3) schleust `ProxyCommand` oder `LocalCommand` ein. Es gibt kein Backup, und das Schreiben ist nicht atomar.
**Fix:** Alle Werte mit `fullmatch(r"[A-Za-z0-9._:@-]+")` prüfen. Vor dem Anhängen `config.bak` anlegen.

#### ~~[DC-M7] `TerminalLauncher` parst den fertigen WT-String wieder auseinander~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/core.py` (Z. 971–1017)
**Problem:** `split(" ; ")` und `partition(" -- ")` schlagen fehl, wenn ein Titel oder Pfad diese Zeichenfolgen enthält. Builder liefern mal einen String, mal eine Liste.
**Fix:** Builder liefern strukturierte `TerminalTabSpec`-Objekte, die Launcher rendern daraus ihr Format.

#### ~~[S-C2] Injection in `ssh-copy-id`- und Key-Entfernen-Befehl über `key_filename` und Hostname~~

**Erledigt am 06.10.2026.**

**Datei:** `ssh_manager_app/core.py` (Z. 666–715), `ssh_manager_app/dialogs_remote.py` (Z. 267, 294–308, 374, 399ff)
**Problem:** `key_filename`, `user` und `hostname` werden in `bash -c "..."` innerhalb des `shell=True`-Strings eingesetzt. Die Key-Combobox ist editierbar (`state="normal"`), wenn keine `.pub` gefunden wird. Eine Eingabe wie `x"; calc; "` wird ausgeführt. Zusätzlich verwendet das Key-Entfernen auf dem Zielhost den festen Pfad `/tmp/ak_tmp` (Symlink-/Race-Risiko), und `mv` ersetzt `authorized_keys` mit Besitzer und Rechten der Temp-Datei.
**Fix:** `re.fullmatch(r"[A-Za-z0-9._-]+\.pub", key)` und `Path(key).name == key` prüfen. Remote `mktemp` verwenden und den Inhalt zurückschreiben statt `mv`:
```bash
tmp=$(mktemp) && grep -vxFf - ~/.ssh/authorized_keys > "$tmp"; cat "$tmp" > ~/.ssh/authorized_keys; rm -f "$tmp"
```
