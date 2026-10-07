from __future__ import annotations

import json
import hashlib
import os
import tempfile
import shutil
import time
from .ssh_utils import valid_color, read_port
import xml.etree.ElementTree as ET
from pathlib import Path

from .constants import (
    _APP_PREFIX,
    _APP_SESSIONS_FILE,
    _FILEZILLA_CONFIG_DEFAULT_FOLDER,
    _NOTES_FILE,
    _SETTINGS_FILE,
    _SSH_ALIAS_PREFIX,
    _SSH_CONFIG_DEFAULT_FOLDER,
    _SSH_CONFIG_FILE,
    _SSH_CONFIG_PREFIX,
    _STATE_FILE,
)
from .models import AppSettings, AppearanceSettings, ImportSettings, Session, SourceVisibilitySettings, ToolbarSettings, WindowsTerminalSettings, WinSCPSettings, default_settings, settings_to_dict
from .shortcuts import merge_with_defaults as _merge_shortcuts
from .source_status import source_load


def atomic_write_text(path: Path, text: str) -> None:
    """Replace only after a complete, flushed write in the same directory."""
    if path.is_symlink():
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


_load_warnings: dict[Path, str] = {}
_blocked_paths: set[Path] = set()


def take_load_warnings() -> list[str]:
    warnings = list(_load_warnings.values())
    _load_warnings.clear()
    return warnings


def _preserve_invalid(path: Path) -> None:
    if path in _load_warnings or not path.exists():
        return
    backup = path.with_name(path.name + f".corrupt-{time.time_ns()}")
    try:
        shutil.copy2(path, backup)
        _load_warnings[path] = f"{path.name}: ungültige Daten; Original gesichert unter {backup}."
    except OSError:
        _blocked_paths.add(path)
        _load_warnings[path] = f"{path}: konnte nicht gesichert werden. Speichern ist zum Schutz der Originaldaten gesperrt."


def _read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON-Wurzel muss ein Objekt sein.")
    return data


def _atomic_write_json(path: Path, data: dict) -> None:
    if path in _blocked_paths:
        raise OSError(f"Speichern gesperrt: Originaldaten konnten nicht gesichert werden ({path}).")
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def _backup_paths() -> dict[str, Path]:
    return {"settings.json": _SETTINGS_FILE, "app_sessions.json": _APP_SESSIONS_FILE,
            "notes.json": _NOTES_FILE, "ui_state.json": _STATE_FILE}


def validate_app_backup(payload: dict) -> dict[str, dict]:
    """Accept only our four app stores. Never interpret archive paths."""
    if payload.get("format") != "ssh-manager-backup" or payload.get("schema") != 1:
        raise ValueError("Kein unterstütztes SSH-Manager-App-Backup.")
    documents = payload.get("documents")
    if not isinstance(documents, dict) or set(documents) != set(_backup_paths()):
        raise ValueError("Das Backup muss genau die vier App-Datendateien enthalten.")
    if not all(isinstance(value, dict) for value in documents.values()):
        raise ValueError("Ungültige App-Datendatei im Backup.")
    settings = documents["settings.json"]
    schema = settings_to_dict(default_settings())
    if not settings or not any(key in schema for key in settings):
        raise ValueError("Einstellungen fehlen.")
    for key, value in settings.items():
        if key in schema and type(value) is not type(schema[key]):
            raise ValueError("Ungültige Einstellungen.")
        if key in schema and isinstance(value, dict):
            for field, item in value.items():
                if field in schema[key] and type(item) is not type(schema[key][field]):
                    raise ValueError("Ungültige Einstellungseigenschaft.")
    entries = documents["app_sessions.json"].get("sessions")
    if not isinstance(entries, list):
        raise ValueError("Verbindungsliste fehlt.")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("source", "app") not in ("app", "ssh_alias"):
            raise ValueError("Ungültige eigene Verbindung.")
        for field in ("id", "name", "hostname", "folder", "username"):
            if not isinstance(entry.get(field, ""), str):
                raise ValueError("Ungültiges Verbindungsfeld.")
        if not entry.get("id") or not entry.get("name"):
            raise ValueError("Verbindungs-ID oder Name fehlt.")
        identity = (entry.get("source", "app"), entry["id"])
        if identity in seen:
            raise ValueError("Doppelte Verbindungs-ID.")
        seen.add(identity)
        read_port(entry.get("port", 22))
    notes = documents["notes.json"].get("notes")
    if not isinstance(notes, dict) or not all(isinstance(v, str) for v in notes.values()):
        raise ValueError("Ungültige Notizen.")
    state = documents["ui_state.json"]
    if not isinstance(state.get("expanded_folders", []), list) or not all(isinstance(v, str) for v in state.get("expanded_folders", [])):
        raise ValueError("Ungültiger Ordnerzustand.")
    for key in ("session_colors", "toolbar_search_texts", "favorite_sessions", "session_user_overrides"):
        if not isinstance(state.get(key, {}), dict):
            raise ValueError("Ungültiger Ansichtsstatus.")
    return documents


def read_app_backup(path: Path) -> dict:
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError("Backup ist größer als 20 MB.")
    payload = _read_json(path)
    validate_app_backup(payload)
    return payload


def create_app_backup(path: Path) -> None:
    _recover_app_restore()
    _recover_session_transaction()
    defaults = {"settings.json": settings_to_dict(default_settings()), "app_sessions.json": {"sessions": []},
                "notes.json": {"notes": {}}, "ui_state.json": {}}
    if path.resolve() in {p.resolve() for p in _backup_paths().values()}:
        raise ValueError("Backup darf keine App-Datendatei überschreiben.")
    documents = {name: _read_json(source) if source.exists() else defaults[name] for name, source in _backup_paths().items()}
    payload = {"format": "ssh-manager-backup", "schema": 1, "documents": documents}
    validate_app_backup(payload)
    _atomic_write_json(path, payload)


def _recover_app_restore() -> None:
    journal = _STATE_FILE.with_name("app-restore-pending.json")
    if not journal.exists():
        return
    try:
        documents = validate_app_backup(_read_json(journal))
    except (ValueError, TypeError, OSError) as exc:
        raise OSError("App-Wiederherstellung: Journal ungültig; Originaldateien bleiben geschützt.") from exc
    for name, path in _backup_paths().items():
        _atomic_write_json(path, documents[name])
    journal.unlink()


def restore_app_backup(payload: dict) -> Path:
    validate_app_backup(payload)
    _recover_app_restore()
    _recover_session_transaction()
    if any(path in _blocked_paths for path in _backup_paths().values()):
        raise OSError("App-Daten sind wegen eines fehlgeschlagenen Sicherungsversuchs gesperrt.")
    safety = _STATE_FILE.with_name(f"before-restore-{time.time_ns()}.json")
    create_app_backup(safety)
    _atomic_write_json(_STATE_FILE.with_name("app-restore-pending.json"), payload)
    _recover_app_restore()
    return safety


def _recover_session_transaction() -> None:
    journal = _APP_SESSIONS_FILE.with_name("session-notes-pending.json")
    if not journal.exists():
        return
    try:
        payload = _read_json(journal)
    except (ValueError, OSError):
        _preserve_invalid(journal)
        _blocked_paths.update({_APP_SESSIONS_FILE, _NOTES_FILE})
        raise OSError("Verbindungen/Notizen: Wiederherstellungsjournal konnte nicht gelesen werden.")
    if not isinstance(payload.get("sessions"), dict) or not isinstance(payload.get("notes"), dict):
        _preserve_invalid(journal)
        _blocked_paths.update({_APP_SESSIONS_FILE, _NOTES_FILE})
        raise OSError("Ungültiges Journal; Verbindungen/Notizen werden vor Überschreiben geschützt.")
    if "ui_state" in payload and not isinstance(payload["ui_state"], dict):
        _blocked_paths.update({_APP_SESSIONS_FILE, _NOTES_FILE, _STATE_FILE})
        raise OSError("Ungültiges Journal für lokale Metadaten.")
    _atomic_write_json(_APP_SESSIONS_FILE, payload["sessions"])
    _atomic_write_json(_NOTES_FILE, payload["notes"])
    if "ui_state" in payload:
        _atomic_write_json(_STATE_FILE, payload["ui_state"])
    journal.unlink()


def save_sessions_and_notes(sessions: list[Session], notes: dict[str, str]) -> None:
    _recover_session_transaction()
    if _APP_SESSIONS_FILE in _blocked_paths or _NOTES_FILE in _blocked_paths:
        raise OSError("Speichern gesperrt: Originaldaten konnten nicht gesichert werden.")
    journal = _APP_SESSIONS_FILE.with_name("session-notes-pending.json")
    _atomic_write_json(journal, {"sessions": _session_payload(sessions), "notes": {"notes": notes}})
    _recover_session_transaction()


def save_local_undo_state(sessions, notes, expanded, colors, toolbar):
    _recover_session_transaction()
    if {_APP_SESSIONS_FILE, _NOTES_FILE, _STATE_FILE} & _blocked_paths:
        raise OSError("Lokale Daten sind gegen Überschreiben gesperrt.")
    payload = {"sessions": _session_payload(sessions), "notes": {"notes": notes},
               "ui_state": _ui_state_payload(expanded, colors, toolbar)}
    _atomic_write_json(_APP_SESSIONS_FILE.with_name("session-notes-pending.json"), payload)
    _recover_session_transaction()


def load_settings() -> AppSettings:
    _recover_app_restore()
    try:
        return load_settings_from_path(_SETTINGS_FILE)
    except (OSError, ValueError, TypeError, AttributeError):
        _preserve_invalid(_SETTINGS_FILE)
        return default_settings()


def save_settings(settings: AppSettings) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(_SETTINGS_FILE, settings_to_dict(settings))


def load_settings_from_path(path: Path, *, require_settings: bool = False) -> AppSettings:
    defaults = default_settings()
    raw = _read_json(path)
    if require_settings:
        schema = settings_to_dict(defaults)
        meaningful = False
        for key, value in raw.items():
            if key not in schema:
                continue
            expected = schema[key]
            if type(value) is not type(expected):
                raise ValueError(f"Ungültiges Format für Einstellung {key}.")
            if isinstance(expected, dict):
                for field, item in value.items():
                    if field not in expected:
                        continue
                    if type(item) is not type(expected[field]):
                        raise ValueError(f"Ungültiges Format für Einstellung {key}.{field}.")
                    if isinstance(item, list) and not all(isinstance(entry, str) for entry in item):
                        raise ValueError(f"Ungültige Liste für Einstellung {key}.{field}.")
                    meaningful = True
            else:
                if isinstance(value, list) and not all(isinstance(entry, str) for entry in value):
                    raise ValueError(f"Ungültige Liste für Einstellung {key}.")
                meaningful = True
        if not meaningful:
            raise ValueError("Die Datei enthält keine erkennbaren SSH-Manager-Einstellungen.")
    raw_dict = raw if isinstance(raw, dict) else {}
    toolbar_raw = raw_dict.get("toolbar", {})
    if not isinstance(toolbar_raw, dict):
        toolbar_raw = {}
    wt_raw = raw_dict.get("windows_terminal", {})
    if not isinstance(wt_raw, dict):
        wt_raw = {}
    winscp_raw = raw_dict.get("winscp", {})
    if not isinstance(winscp_raw, dict):
        winscp_raw = {}
    visibility_raw = raw_dict.get("source_visibility", {})
    if not isinstance(visibility_raw, dict):
        visibility_raw = {}
    appearance_raw = raw_dict.get("appearance", {})
    if not isinstance(appearance_raw, dict):
        appearance_raw = {}
    import_raw = raw_dict.get("import_settings", {})
    if not isinstance(import_raw, dict):
        import_raw = {}
    shortcuts_raw = raw_dict.get("keyboard_shortcuts", {})
    if not isinstance(shortcuts_raw, dict):
        shortcuts_raw = {}

    quick_users = raw_dict.get("quick_users", defaults.quick_users)
    if not isinstance(quick_users, list):
        quick_users = defaults.quick_users
    quick_users = [str(user).strip() for user in quick_users if str(user).strip()] or list(defaults.quick_users)

    default_user = str(raw_dict.get("default_user", defaults.default_user)).strip() or quick_users[0]
    if default_user not in quick_users:
        quick_users.insert(0, default_user)

    host_timeout = raw_dict.get("host_check_timeout_seconds", defaults.host_check_timeout_seconds)
    try:
        host_timeout = max(1, int(host_timeout))
    except (TypeError, ValueError):
        host_timeout = defaults.host_check_timeout_seconds

    startup_expand_mode = str(raw_dict.get("startup_expand_mode", defaults.startup_expand_mode))
    if startup_expand_mode not in {"remember", "expanded", "collapsed"}:
        startup_expand_mode = defaults.startup_expand_mode
    winscp_open_mode = str(winscp_raw.get("open_mode", defaults.winscp.open_mode))
    if winscp_open_mode not in {"tabs", "windows"}:
        winscp_open_mode = defaults.winscp.open_mode
    ssh_open_mode = str(wt_raw.get("ssh_open_mode", defaults.windows_terminal.ssh_open_mode))
    if ssh_open_mode not in {"windows_terminal", "herdr"}:
        ssh_open_mode = defaults.windows_terminal.ssh_open_mode

    theme = str(appearance_raw.get("theme", defaults.appearance.theme)).strip() or defaults.appearance.theme
    if theme not in {"default", "modern_light", "dark_neutral", "midnight"}:
        theme = defaults.appearance.theme
    accent_color = str(appearance_raw.get("accent_color", defaults.appearance.accent_color)).strip().lower()
    if accent_color == "#2563eb":
        # Migrate the former, very bright default to the calmer blue introduced in 0.2.17.
        accent_color = defaults.appearance.accent_color
    allowed_accents = {
        "#5b78a6", "#4f6f8f", "#4f8096", "#5f8a72", "#3f7d5b", "#71824a",
        "#a37b4b", "#a76545", "#a95656", "#80658f", "#9a6079", "#5f6b7a",
        "#2563eb", "#14b8a6", "#22c55e", "#f59e0b", "#a855f7", "#ec4899",
    }
    if accent_color not in allowed_accents:
        accent_color = defaults.appearance.accent_color

    allowed_fonts = {"Segoe UI", "Arial", "Calibri", "Consolas", "Cascadia Mono", "Verdana"}
    ui_font_family = str(appearance_raw.get("ui_font_family", defaults.appearance.ui_font_family)).strip() or defaults.appearance.ui_font_family
    if ui_font_family not in allowed_fonts:
        ui_font_family = defaults.appearance.ui_font_family
    tree_font_family = str(appearance_raw.get("tree_font_family", defaults.appearance.tree_font_family)).strip() or defaults.appearance.tree_font_family
    if tree_font_family not in allowed_fonts:
        tree_font_family = defaults.appearance.tree_font_family
    try:
        ui_font_size = min(14, max(8, int(appearance_raw.get("ui_font_size", defaults.appearance.ui_font_size))))
    except (TypeError, ValueError):
        ui_font_size = defaults.appearance.ui_font_size
    try:
        tree_font_size = min(16, max(8, int(appearance_raw.get("tree_font_size", defaults.appearance.tree_font_size))))
    except (TypeError, ValueError):
        tree_font_size = defaults.appearance.tree_font_size
    try:
        tree_row_height = min(44, max(22, int(appearance_raw.get("tree_row_height", defaults.appearance.tree_row_height))))
    except (TypeError, ValueError):
        tree_row_height = defaults.appearance.tree_row_height

    allowed_columns = {"username", "notes", "hostname", "port"}
    column_raw = toolbar_raw.get("column_order", defaults.toolbar.column_order)
    if not isinstance(column_raw, list):
        column_raw = defaults.toolbar.column_order
    column_order = [col for col in column_raw if isinstance(col, str) and col in allowed_columns]
    if not column_order:
        column_order = list(defaults.toolbar.column_order)
    elif "username" not in column_order:
        hostname_index = column_order.index("hostname") if "hostname" in column_order else 0
        column_order.insert(hostname_index, "username")

    return AppSettings(
        quick_users=quick_users,
        default_user=default_user,
        toolbar=ToolbarSettings(
            show_select_all=bool(toolbar_raw.get("show_select_all", defaults.toolbar.show_select_all)),
            show_deselect_all=bool(toolbar_raw.get("show_deselect_all", defaults.toolbar.show_deselect_all)),
            show_expand_all=bool(toolbar_raw.get("show_expand_all", defaults.toolbar.show_expand_all)),
            show_collapse_all=bool(toolbar_raw.get("show_collapse_all", defaults.toolbar.show_collapse_all)),
            show_add_connection=bool(toolbar_raw.get("show_add_connection", defaults.toolbar.show_add_connection)),
            show_reload=bool(toolbar_raw.get("show_reload", defaults.toolbar.show_reload)),
            show_open_tunnel=bool(toolbar_raw.get("show_open_tunnel", defaults.toolbar.show_open_tunnel)),
            show_run_remote_command=bool(toolbar_raw.get("show_run_remote_command", defaults.toolbar.show_run_remote_command)),
            show_deploy_certificate_files=bool(toolbar_raw.get("show_deploy_certificate_files", defaults.toolbar.show_deploy_certificate_files)),
            show_replace_certificates=bool(toolbar_raw.get("show_replace_certificates", defaults.toolbar.show_replace_certificates)),
            show_check_hosts=bool(toolbar_raw.get("show_check_hosts", defaults.toolbar.show_check_hosts)),
            show_restart_servers=bool(toolbar_raw.get("show_restart_servers", defaults.toolbar.show_restart_servers)),
            show_username_column=bool(toolbar_raw.get("show_username_column", defaults.toolbar.show_username_column)),
            show_hostname_column=bool(toolbar_raw.get("show_hostname_column", defaults.toolbar.show_hostname_column)),
            show_port_column=bool(toolbar_raw.get("show_port_column", defaults.toolbar.show_port_column)),
            show_notes_column=bool(toolbar_raw.get("show_notes_column", defaults.toolbar.show_notes_column)),
            column_order=column_order,
        ),
        host_check_timeout_seconds=host_timeout,
        startup_expand_mode=startup_expand_mode,
        windows_terminal=WindowsTerminalSettings(
            profile_name=str(wt_raw.get("profile_name", defaults.windows_terminal.profile_name)).strip() or defaults.windows_terminal.profile_name,
            use_tab_color=bool(wt_raw.get("use_tab_color", defaults.windows_terminal.use_tab_color)),
            title_mode=(wt_raw.get("title_mode") if str(wt_raw.get("title_mode")) in {"default", "name", "host", "user_host", "name_host"} else defaults.windows_terminal.title_mode),
            ssh_open_mode=ssh_open_mode,
        ),
        winscp=WinSCPSettings(open_mode=winscp_open_mode),
        source_visibility=SourceVisibilitySettings(
            show_winscp=bool(visibility_raw.get("show_winscp", defaults.source_visibility.show_winscp)),
            show_ssh_config=bool(visibility_raw.get("show_ssh_config", defaults.source_visibility.show_ssh_config)),
            show_filezilla_config=bool(visibility_raw.get("show_filezilla_config", defaults.source_visibility.show_filezilla_config)),
            show_app_connections=bool(visibility_raw.get("show_app_connections", defaults.source_visibility.show_app_connections)),
            show_favorites=bool(visibility_raw.get("show_favorites", defaults.source_visibility.show_favorites)),
            show_recent=bool(visibility_raw.get("show_recent", defaults.source_visibility.show_recent)),
        ),
        import_settings=ImportSettings(
            winscp_include_username=bool(import_raw.get("winscp_include_username", defaults.import_settings.winscp_include_username)),
            filezilla_include_username=bool(import_raw.get("filezilla_include_username", defaults.import_settings.filezilla_include_username)),
        ),
        appearance=AppearanceSettings(
            theme=theme,
            accent_color=accent_color,
            ui_font_family=ui_font_family,
            ui_font_size=ui_font_size,
            tree_font_family=tree_font_family,
            tree_font_size=tree_font_size,
            tree_row_height=tree_row_height,
        ),
        keyboard_shortcuts=_merge_shortcuts(shortcuts_raw),
    )


def load_ui_state() -> tuple[set[str], dict[str, str], dict[str, str]]:
    _recover_app_restore()
    _recover_session_transaction()
    try:
        data = _read_json(_STATE_FILE)
        expanded_raw = data.get("expanded_folders", [])
        if not isinstance(expanded_raw, list):
            raise TypeError("expanded_folders must be a list")
        colors_raw = data.get("session_colors", {})
        if not isinstance(colors_raw, dict):
            raise TypeError("session_colors must be a dict")
        toolbar_raw = data.get("toolbar_search_texts", {})
        if not isinstance(toolbar_raw, dict):
            raise TypeError("toolbar_search_texts must be a dict")
        toolbar_texts = dict(toolbar_raw)
        history = toolbar_texts.get("search_history", [])
        if not isinstance(history, list):
            history = []
        toolbar_texts["search_history"] = [str(item).strip() for item in history if str(item).strip()]
        remote_history = toolbar_texts.get("remote_command_history")
        if isinstance(remote_history, list):
            toolbar_texts["remote_command_history"] = [item for item in remote_history if isinstance(item, dict)]
        remote_favorites = toolbar_texts.get("remote_command_favorites")
        if isinstance(remote_favorites, list):
            toolbar_texts["remote_command_favorites"] = [item for item in remote_favorites if isinstance(item, dict)]
        certificate_whitelist = toolbar_texts.get("certificate_replace_whitelist")
        if isinstance(certificate_whitelist, list):
            toolbar_texts["certificate_replace_whitelist"] = [str(item).strip() for item in certificate_whitelist if str(item).strip().startswith("/")]
        favorites = data.get("favorite_sessions", {})
        if not isinstance(favorites, dict):
            favorites = {}
        if favorites:
            toolbar_texts["favorite_sessions"] = {str(k): bool(v) for k, v in favorites.items()}
        user_overrides = data.get("session_user_overrides", {})
        if isinstance(user_overrides, dict) and user_overrides:
            toolbar_texts["session_user_overrides"] = {str(k): str(v) for k, v in user_overrides.items()}
        recent = data.get("recent_sessions", [])
        if not isinstance(recent, list):
            recent = []
        recent_sessions = [str(item) for item in recent if str(item).strip()]
        if recent_sessions:
            toolbar_texts["recent_sessions"] = recent_sessions
        return set(expanded_raw), {str(k): v for k, v in colors_raw.items() if valid_color(v)}, toolbar_texts
    except (OSError, TypeError, ValueError):
        _preserve_invalid(_STATE_FILE)
        return set(), {}, {}


def _ui_state_payload(expanded_folders, session_colors, toolbar_search_texts):
    toolbar_search_texts = dict(toolbar_search_texts or {})
    favorite_sessions = toolbar_search_texts.pop("favorite_sessions", {})
    recent_sessions = toolbar_search_texts.pop("recent_sessions", [])
    user_overrides = toolbar_search_texts.pop("session_user_overrides", {})
    payload = {
        "expanded_folders": sorted(expanded_folders),
        "session_colors": session_colors,
        "toolbar_search_texts": toolbar_search_texts,
    }
    if favorite_sessions:
        payload["favorite_sessions"] = favorite_sessions
    if recent_sessions:
        payload["recent_sessions"] = recent_sessions
    if user_overrides:
        payload["session_user_overrides"] = user_overrides
    return payload


def save_ui_state(expanded_folders: set[str], session_colors: dict[str, str], toolbar_search_texts: dict[str, str] | None = None) -> None:
    _recover_session_transaction()
    _atomic_write_json(_STATE_FILE, _ui_state_payload(expanded_folders, session_colors, toolbar_search_texts))


def load_notes() -> dict[str, str]:
    _recover_app_restore()
    try:
        _recover_session_transaction()
        data = _read_json(_NOTES_FILE)
        if not isinstance(data, dict):
            return {}
        notes = data.get("notes", {})
        if not isinstance(notes, dict):
            raise ValueError("notes must be an object")
        return {str(k): str(v) for k, v in notes.items() if str(v).strip()}
    except (OSError, ValueError):
        _preserve_invalid(_NOTES_FILE)
        return {}


def save_notes(notes: dict[str, str]) -> None:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _recover_session_transaction()
    _atomic_write_json(_NOTES_FILE, {"notes": notes})


@source_load("app")
def load_app_sessions() -> list[Session]:
    _recover_app_restore()
    try:
        _recover_session_transaction()
        raw = _read_json(_APP_SESSIONS_FILE)
        data = raw if isinstance(raw, dict) else {}
        sessions: list[Session] = []
        entries = data.get("sessions", [])
        if not isinstance(entries, list):
            raise ValueError("sessions must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                _preserve_invalid(_APP_SESSIONS_FILE)
                continue
            try:
                source = str(entry.get("source", "app"))
                folder_str = str(entry.get("folder", ""))
                folder_path = [p for p in folder_str.split("/") if p] if folder_str else []
                session_id = str(entry["id"])
                name = str(entry["name"])
                hostname = str(entry["hostname"])
                key = (_SSH_ALIAS_PREFIX if source == "ssh_alias" else _APP_PREFIX) + session_id
                try:
                    port = read_port(entry.get("port", 22))
                except ValueError:
                    _preserve_invalid(_APP_SESSIONS_FILE)
                    warning = _load_warnings.get(_APP_SESSIONS_FILE, "")
                    if "Port" not in warning:
                        _load_warnings[_APP_SESSIONS_FILE] = warning + " Verbindungen mit ungültigem Port wurden übersprungen; erlaubt sind 1–65535."
                    continue
                sessions.append(Session(
                    key=key,
                    display_name=name,
                    folder_path=folder_path,
                    hostname=hostname,
                    username=str(entry.get("username", "")),
                    port=port,
                    source=source,
                ))
            except (KeyError, TypeError, ValueError):
                _preserve_invalid(_APP_SESSIONS_FILE)
                continue
        return sessions
    except (OSError, ValueError, TypeError):
        _preserve_invalid(_APP_SESSIONS_FILE)
        return []


def _session_payload(sessions: list[Session]) -> dict:
    entries = []
    for s in sessions:
        if s.source not in ("app", "ssh_alias"):
            continue
        prefix = _SSH_ALIAS_PREFIX if s.source == "ssh_alias" else _APP_PREFIX
        session_id = s.key[len(prefix):]
        entries.append({
            "id": session_id,
            "name": s.display_name,
            "folder": s.folder_key,
            "hostname": s.hostname,
            "username": s.username,
            "port": s.port,
            "source": s.source,
        })
    return {"sessions": entries}


def save_app_sessions(sessions: list[Session]) -> None:
    _recover_session_transaction()
    _atomic_write_json(_APP_SESSIONS_FILE, _session_payload(sessions))


FILEZILLA_MAX_BYTES = 5_000_000


def migrate_filezilla_metadata(sessions: list[Session], notes: dict, colors: dict, toolbar: dict) -> tuple[dict, dict, dict]:
    """Move old references; ambiguous old IDs transfer metadata to every match."""
    aliases: dict[str, list[str]] = {}
    for session in sessions:
        if session.legacy_key:
            aliases.setdefault(session.legacy_key, []).append(session.key)
    if not aliases:
        return notes, colors, toolbar

    def mapping(values):
        result = dict(values)
        for old, keys in aliases.items():
            if old in result:
                value = result.pop(old)
                for key in keys:
                    result.setdefault(key, value)
        return result

    updated = dict(toolbar)
    for name in ("favorite_sessions", "session_user_overrides"):
        if isinstance(updated.get(name), dict):
            updated[name] = mapping(updated[name])
    if isinstance(updated.get("recent_sessions"), list):
        updated["recent_sessions"] = list(dict.fromkeys(key for old in updated["recent_sessions"] for key in aliases.get(old, [old])))
    return mapping(notes), mapping(colors), updated


def save_filezilla_migration(expanded: set[str], notes: dict, colors: dict, toolbar: dict) -> None:
    """Keep the exact old files as backups before migrating either store."""
    for path in (_NOTES_FILE, _STATE_FILE):
        backup = path.with_name(path.name + ".filezilla-v1.bak")
        if path.exists() and not backup.exists():
            shutil.copy2(path, backup)
    save_notes(notes)
    save_ui_state(expanded, colors, toolbar)


@source_load("filezilla_config")
def load_filezilla_config_sessions() -> list[Session]:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    candidates = [appdata / "FileZilla" / "sitemanager.xml", appdata / "filezilla" / "sitemanager.xml"]
    file_path = next((path for path in candidates if path.exists()), None)
    if file_path is None:
        return []
    try:
        with file_path.open("rb") as stream:
            payload = stream.read(FILEZILLA_MAX_BYTES + 1)
        if len(payload) > FILEZILLA_MAX_BYTES:
            _load_warnings[file_path] = "FileZilla: Quelldatei überschreitet das Größenlimit von 5 MB. Bitte ungenutzte Sites in FileZilla archivieren; Quelldatei unverändert."
            return []
        # Removing NUL bytes also exposes declaration tokens in UTF-16/32 input.
        declarations = payload.replace(b"\x00", b"").upper()
        if b"<!DOCTYPE" in declarations or b"<!ENTITY" in declarations:
            raise ValueError("XML declarations are not supported")
        root = ET.fromstring(payload)
    except (OSError, ET.ParseError, ValueError):
        _load_warnings[file_path] = f"FileZilla-Quelle konnte nicht gelesen werden: {file_path}. Original unverändert."
        return []

    sessions: list[Session] = []
    occurrences: dict[str, int] = {}

    def walk_folder(node: ET.Element, folder_path: list[str]) -> None:
        for child in list(node):
            if child.tag == "Folder":
                name = child.attrib.get("Name", "Ordner").strip() or "Ordner"
                walk_folder(child, folder_path + [name])
            elif child.tag == "Server":
                host = (child.findtext("Host") or "").strip()
                if not host:
                    continue
                protocol = (child.findtext("Protocol") or "0").strip()
                if protocol not in {"0", "1"}:
                    continue
                name = (child.findtext("Name") or host).strip() or host
                user = (child.findtext("User") or "").strip()
                port_text = (child.findtext("Port") or "22").strip()
                try:
                    port = read_port(port_text)
                except ValueError:
                    _load_warnings[file_path] = "FileZilla: Verbindungen mit ungültigem Port wurden übersprungen. Erlaubt sind 1–65535; Quelldatei unverändert."
                    continue
                full_folder = [_FILEZILLA_CONFIG_DEFAULT_FOLDER] + folder_path
                legacy_key = f"__filezilla__{'/'.join(full_folder)}/{name}/{host}/{port}"
                identity = json.dumps([full_folder, name, host, port, user, protocol], ensure_ascii=False, separators=(",", ":"))
                digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
                occurrences[digest] = occurrences.get(digest, 0) + 1
                session_key = f"__filezilla_v2__{digest}:{occurrences[digest]}"
                sessions.append(Session(
                    key=session_key,
                    display_name=name,
                    folder_path=full_folder,
                    hostname=host,
                    username=user,
                    port=port,
                    source="filezilla_config",
                    legacy_key=legacy_key,
                ))

    for servers in root.findall("Servers"):
        walk_folder(servers, [])
    return sessions


@source_load("ssh_config")
def load_ssh_config_sessions() -> list[Session]:
    try:
        text = _SSH_CONFIG_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeError):
        _load_warnings[_SSH_CONFIG_FILE] = f"SSH-Config konnte nicht als UTF-8 gelesen werden: {_SSH_CONFIG_FILE}. Original unverändert."
        return []

    sessions: list[Session] = []
    current_alias: str | None = None
    current_hostname: str | None = None
    current_user: str = ""
    current_port: int = 22

    def flush() -> None:
        nonlocal current_alias, current_hostname, current_user, current_port
        if current_alias and current_port is not None and '*' not in current_alias and '?' not in current_alias:
            sessions.append(Session(
                key=_SSH_CONFIG_PREFIX + current_alias,
                display_name=current_alias,
                folder_path=[_SSH_CONFIG_DEFAULT_FOLDER],
                hostname=current_hostname or current_alias,
                username=current_user,
                port=current_port,
                source="ssh_config",
            ))
        current_alias = None
        current_hostname = None
        current_user = ""
        current_port = 22

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        parts = stripped.split(None, 1)
        if len(parts) < 2:
            continue
        kw, val = parts[0].lower(), parts[1].strip()
        if kw == "host":
            flush()
            current_alias = val if ' ' not in val else None
        elif kw == "hostname" and current_alias:
            current_hostname = val
        elif kw == "user" and current_alias:
            current_user = val
        elif kw == "port" and current_alias:
            try:
                current_port = read_port(val)
            except ValueError:
                current_port = None
                _load_warnings[_SSH_CONFIG_FILE] = "SSH-Config: Aliase mit ungültigem Port wurden übersprungen. Erlaubt sind 1–65535; Quelldatei unverändert."
    flush()
    return sessions
