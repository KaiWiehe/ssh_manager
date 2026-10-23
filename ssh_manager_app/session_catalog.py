"""Shared session identity/user rules and a window-free CLI catalog."""
from __future__ import annotations

from dataclasses import dataclass, replace

from .models import AppSettings, Session

SOURCE_LABELS = {"winscp": "WinSCP", "ssh_config": "SSH Config",
                 "filezilla_config": "FileZilla", "app": "Eigene Verbindungen"}


def effective_session(session: Session, settings: AppSettings, overrides: dict) -> Session:
    override = overrides.get(session.key)
    if override is not None:
        return replace(session, username=override)
    if session.source == "winscp" and not settings.import_settings.winscp_include_username:
        return replace(session, username="")
    if session.source == "filezilla_config" and not settings.import_settings.filezilla_include_username:
        return replace(session, username="")
    return session


@dataclass(frozen=True)
class CatalogEntry:
    session: Session
    user: str
    note: str = ""
    favorite: bool = False
    recent: bool = False

    @property
    def identity(self) -> tuple[str, str]:
        return self.session.source, self.session.key


@dataclass
class Catalog:
    entries: list[CatalogEntry]
    settings: AppSettings
    statuses: dict
    warnings: list[str]


def load_catalog() -> Catalog:
    from . import storage
    from .core import RegistryReader
    from .source_status import STATUSES

    settings = storage.load_settings()
    _, _, toolbar = storage.load_ui_state()
    notes = storage.load_notes()
    sessions = []
    warnings = []
    loaders = [RegistryReader().load_sessions, storage.load_ssh_config_sessions,
               storage.load_filezilla_config_sessions, storage.load_app_sessions]
    for loader in loaders:
        try:
            loaded = loader()
            if loaded and loaded[0].source == "filezilla_config":
                # Interpret legacy metadata exactly like the GUI, without writing it.
                notes, _, toolbar = storage.migrate_filezilla_metadata(loaded, notes, {}, toolbar)
            sessions.extend(loaded)
        except FileNotFoundError:
            pass  # The source status explicitly records missing sources.
        except (OSError, ValueError):
            warnings.append("Eine Datenquelle konnte nicht gelesen werden; siehe Quellenstatus.")
    favorites = toolbar.get("favorite_sessions", {})
    recent = toolbar.get("recent_sessions", [])
    entries = {}
    for original in sessions:
        session = effective_session(original, settings, toolbar.get("session_user_overrides", {}))
        # Aliases delegate user/host/port resolution to the SSH client.
        user = "" if session.is_ssh_config_session else session.username or settings.default_user
        entry = CatalogEntry(session, user, notes.get(session.key, ""),
                             session.key in favorites, session.key in recent)
        entries[entry.identity] = entry
    warnings.extend(storage.take_load_warnings())
    return Catalog(list(entries.values()), settings, dict(STATUSES), warnings)
