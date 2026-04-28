"""Compatibility aggregator for legacy dialog imports.

Prefer importing from the split dialog modules directly.
"""

from .dialogs_base import UserDialog
from .dialogs_move_folder import MoveFolderDialog
from .dialogs_remote import (
    JumpHostDialog,
    RemoteCommandConfirmDialog,
    RemoteCommandDialog,
    SshCopyIdDialog,
    SshRemoveKeyDialog,
    SshTunnelDialog,
)
from .dialogs_session_edit import SessionEditDialog
from .dialogs_settings_misc import SettingsView, SshConfigInspectDialog
from .dialogs_toast import ToastNotification

__all__ = [
    "JumpHostDialog",
    "MoveFolderDialog",
    "RemoteCommandConfirmDialog",
    "RemoteCommandDialog",
    "SessionEditDialog",
    "SettingsView",
    "SshConfigInspectDialog",
    "SshCopyIdDialog",
    "SshRemoveKeyDialog",
    "SshTunnelDialog",
    "ToastNotification",
    "UserDialog",
]
