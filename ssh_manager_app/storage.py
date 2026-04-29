from __future__ import annotations

import json
import os
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
from .models import AppSettings, Session, SourceVisibilitySettings, ToolbarSettings, WindowsTerminalSettings, default_settings, settings_to_dict


def load_settings() -> AppSettings:
    try:
        return load_settings_from_path(_SETTINGS_FILE)
    except (OSError, json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return default_settings()


def save_settings(settings: AppSettings) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_FILE.write_text(json.dumps(settings_to_dict(settings), ensure_ascii=False, indent=2), encoding="utf-8")


def load_settings_from_path(path: Path) -> AppSettings:
    defaults = default_settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_dict = raw if isinstance(raw, dict) else {}
    toolbar_raw = raw_dict.get("toolbar", {})
    if not isinstance(toolbar_raw, dict):
        toolbar_raw = {}
    wt_raw = raw_dict.get("windows_terminal", {})
    if not isinstance(wt_raw, dict):
        wt_raw = {}
    visibility_raw = raw_dict.get("source_visibility", {})
    if not isinstance(visibility_raw, dict):
        visibility_raw = {}

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
            show_check_hosts=bool(toolbar_raw.get("show_check_hosts", defaults.toolbar.show_check_hosts)),
            show_hostname_column=bool(toolbar_raw.get("show_hostname_column", defaults.toolbar.show_hostname_column)),
            show_port_column=bool(toolbar_raw.get("show_port_column", defaults.toolbar.show_port_column)),
            show_notes_column=bool(toolbar_raw.get("show_notes_column", defaults.toolbar.show_notes_column)),
            column_order=[col for col in toolbar_raw.get("column_order", defaults.toolbar.column_order) if col in {"notes", "hostname", "port"}] or list(defaults.toolbar.column_order),
        ),
        host_check_timeout_seconds=host_timeout,
        startup_expand_mode=startup_expand_mode,
        windows_terminal=WindowsTerminalSettings(
            profile_name=str(wt_raw.get("profile_name", defaults.windows_terminal.profile_name)).strip() or defaults.windows_terminal.profile_name,
            use_tab_color=bool(wt_raw.get("use_tab_color", defaults.windows_terminal.use_tab_color)),
            title_mode=str(wt_raw.get("title_mode", defaults.windows_terminal.title_mode)),
        ),
        source_visibility=SourceVisibilitySettings(
            show_winscp=bool(visibility_raw.get("show_winscp", defaults.source_visibility.show_winscp)),
            show_ssh_config=bool(visibility_raw.get("show_ssh_config", defaults.source_visibility.show_ssh_config)),
            show_filezilla_config=bool(visibility_raw.get("show_filezilla_config", defaults.source_visibility.show_filezilla_config)),
            show_app_connections=bool(visibility_raw.get("show_app_connections", defaults.source_visibility.show_app_connections)),
        ),
    )


def load_ui_state() -> tuple[set[str], dict[str, str], dict[str, str]]:
    try:
        data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        toolbar_raw = data.get("toolbar_search_texts", {})
        if not isinstance(toolbar_raw, dict):
            raise TypeError("toolbar_search_texts must be a dict")
        toolbar_texts = dict(toolbar_raw)
        history = toolbar_texts.get("search_history", [])
        if not isinstance(history, list):
            history = []
        toolbar_texts["search_history"] = [str(item).strip() for item in history if str(item).strip()]
        return set(data.get("expanded_folders", [])), dict(data.get("session_colors", {})), toolbar_texts
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return set(), {}, {}


def save_ui_state(expanded_folders: set[str], session_colors: dict[str, str], toolbar_search_texts: dict[str, str] | None = None) -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(json.dumps({
        "expanded_folders": sorted(expanded_folders),
        "session_colors": session_colors,
        "toolbar_search_texts": toolbar_search_texts or {},
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def load_notes() -> dict[str, str]:
    try:
        data = json.loads(_NOTES_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        notes = data.get("notes", {})
        if not isinstance(notes, dict):
            return {}
        return {str(k): str(v) for k, v in notes.items() if str(v).strip()}
    except (OSError, json.JSONDecodeError, ValueError):
        return {}


def save_notes(notes: dict[str, str]) -> None:
    _NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
    _NOTES_FILE.write_text(json.dumps({"notes": notes}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_app_sessions() -> list[Session]:
    try:
        raw = json.loads(_APP_SESSIONS_FILE.read_text(encoding="utf-8"))
        data = raw if isinstance(raw, dict) else {}
        sessions: list[Session] = []
        for entry in data.get("sessions", []):
            if not isinstance(entry, dict):
                continue
            try:
                source = str(entry.get("source", "app"))
                folder_str = str(entry.get("folder", ""))
                folder_path = [p for p in folder_str.split("/") if p] if folder_str else []
                session_id = str(entry["id"])
                name = str(entry["name"])
                hostname = str(entry["hostname"])
                key = (_SSH_ALIAS_PREFIX if source == "ssh_alias" else _APP_PREFIX) + session_id
                sessions.append(Session(
                    key=key,
                    display_name=name,
                    folder_path=folder_path,
                    hostname=hostname,
                    username=str(entry.get("username", "")),
                    port=int(entry.get("port", 22)),
                    source=source,
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return sessions
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def save_app_sessions(sessions: list[Session]) -> None:
    _APP_SESSIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
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
    _APP_SESSIONS_FILE.write_text(json.dumps({"sessions": entries}, ensure_ascii=False, indent=2), encoding="utf-8")


def load_filezilla_config_sessions() -> list[Session]:
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    candidates = [appdata / "FileZilla" / "sitemanager.xml", appdata / "filezilla" / "sitemanager.xml"]
    file_path = next((path for path in candidates if path.exists()), None)
    if file_path is None:
        return []
    try:
        root = ET.fromstring(file_path.read_text(encoding="utf-8"))
    except (OSError, ET.ParseError):
        return []

    sessions: list[Session] = []

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
                    port = int(port_text) if port_text else 22
                except ValueError:
                    port = 22
                full_folder = [_FILEZILLA_CONFIG_DEFAULT_FOLDER] + folder_path
                session_key = f"__filezilla__{'/'.join(full_folder)}/{name}/{host}/{port}"
                sessions.append(Session(
                    key=session_key,
                    display_name=name,
                    folder_path=full_folder,
                    hostname=host,
                    username=user,
                    port=port,
                    source="filezilla_config",
                ))

    for servers in root.findall("Servers"):
        walk_folder(servers, [])
    return sessions


def load_ssh_config_sessions() -> list[Session]:
    try:
        text = _SSH_CONFIG_FILE.read_text(encoding="utf-8")
    except OSError:
        return []

    sessions: list[Session] = []
    current_alias: str | None = None
    current_hostname: str | None = None
    current_user: str = ""
    current_port: int = 22

    def flush() -> None:
        nonlocal current_alias, current_hostname, current_user, current_port
        if current_alias and '*' not in current_alias and '?' not in current_alias:
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
                current_port = int(val)
            except ValueError:
                pass
    flush()
    return sessions
