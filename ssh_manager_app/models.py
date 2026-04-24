from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .constants import DEFAULT_USER, QUICK_USERS


def color_tag(hex_color: str) -> str:
    return f"color_{hex_color.lstrip('#')}"


@dataclass
class Session:
    key: str
    display_name: str
    folder_path: list[str]
    hostname: str
    username: str = ""
    port: int = 22
    source: str = "winscp"

    @property
    def folder_key(self) -> str:
        return "/".join(self.folder_path)

    @property
    def is_app_session(self) -> bool:
        return self.source == "app"

    @property
    def is_ssh_config_session(self) -> bool:
        return self.source in ("ssh_config", "ssh_alias")

    @property
    def is_ssh_alias_copy(self) -> bool:
        return self.source == "ssh_alias"


@dataclass
class ToolbarSettings:
    show_select_all: bool = True
    show_deselect_all: bool = True
    show_expand_all: bool = True
    show_collapse_all: bool = True
    show_add_connection: bool = True
    show_reload: bool = True
    show_open_tunnel: bool = True
    show_check_hosts: bool = True
    show_hostname_column: bool = True
    show_port_column: bool = True
    show_notes_column: bool = True
    column_order: list[str] = field(default_factory=lambda: ["notes", "hostname", "port"])


@dataclass
class WindowsTerminalSettings:
    profile_name: str = "Git Bash"
    use_tab_color: bool = True
    title_mode: str = "default"


@dataclass
class SourceVisibilitySettings:
    show_winscp: bool = True
    show_ssh_config: bool = True
    show_filezilla_config: bool = False
    show_app_connections: bool = True


@dataclass
class AppSettings:
    quick_users: list[str] = field(default_factory=lambda: list(QUICK_USERS))
    default_user: str = DEFAULT_USER
    toolbar: ToolbarSettings = field(default_factory=ToolbarSettings)
    host_check_timeout_seconds: int = 3
    startup_expand_mode: str = "remember"
    windows_terminal: WindowsTerminalSettings = field(default_factory=WindowsTerminalSettings)
    source_visibility: SourceVisibilitySettings = field(default_factory=SourceVisibilitySettings)


def default_settings() -> AppSettings:
    return AppSettings()


def settings_to_dict(settings: AppSettings) -> dict:
    return asdict(settings)
