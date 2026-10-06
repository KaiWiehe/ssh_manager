import tkinter as tk
from unittest.mock import patch

import pytest

from ssh_manager_app.models import AppSettings, Session
from ssh_manager_app.dialogs_certificate_permissions import CertificatePermissionsDialog
from ssh_manager_app.dialogs_certificates import CertificateDeployDialog
from ssh_manager_app.dialogs_restart import ServerRestartDialog
from ssh_manager_app.dialogs_export import ExportColumnsDialog
from ssh_manager_app.ui import configure_app_styles


@pytest.fixture
def root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    root.settings = AppSettings(quick_users=["ops", "nginx"], default_user="ops")
    configure_app_styles(root)
    root.overrideredirect(True)
    root.geometry("750x550+50+50")
    root.update()
    yield root
    root.destroy()


def _buttons(widget):
    result = []
    for child in widget.winfo_children():
        if child.winfo_class() == "TButton":
            result.append(child)
        result.extend(_buttons(child))
    return result


def _small_dialog(dialog, root):
    # Bypass desktop tiling so tests actually exercise the requested small size.
    dialog.overrideredirect(True)
    dialog.geometry("710x510+50+50")
    root.update()


def test_certificate_owner_quickselect_shared_and_per_host_free_entry(root, tmp_path):
    users = [(Session("a", "A", [], "host-a"), "ops"), (Session("b", "B", [], "host-b"), "ops")]
    path = str(tmp_path / "key.pem")
    dialog = CertificatePermissionsDialog(root, users, [path], ["ops", "nginx"], "ops")
    _small_dialog(dialog, root)
    assert str(dialog._host_entries[0].cget("state")) == "disabled"
    next(button for button in _buttons(dialog._quick) if button.cget("text") == "nginx").invoke()
    assert dialog._all_owner.get() == "nginx"
    dialog._mode.set("each")
    dialog._toggle()
    dialog._owners["a"].set("custom-service")
    dialog._owners["b"].set("nginx")
    dialog._file_modes[path].set("0640")
    actions = [button for button in _buttons(dialog) if button.cget("text") == "Übernehmen"]
    assert actions and actions[0].winfo_y() >= 0
    assert actions[0].winfo_rooty() + actions[0].winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
    dialog._ok()
    assert dialog.result == {"owners": {"a": "custom-service", "b": "nginx"}, "file_modes": {path: "0640"}, "apply_to_existing": False}


def test_csv_option_and_restart_limit_can_be_changed(root):
    dialog = ExportColumnsDialog(root, "CSV")
    assert dialog._excel_safe_var.get()
    dialog._excel_safe_var.set(False)
    dialog._on_ok()
    assert not dialog.excel_safe
    users = [(Session(str(i), f"Host{i}", [], f"host{i}"), "ops") for i in range(7)]
    restart = ServerRestartDialog(root, users)
    _small_dialog(restart, root)
    restart._limit_var.set(True)
    restart._toggle_limit()
    restart._parallel_var.set("2")
    root.update()
    button = next(button for button in _buttons(restart) if button.cget("text") == "Server neu starten")
    assert button.winfo_rooty() + button.winfo_height() <= restart.winfo_rooty() + restart.winfo_height()
    assert restart._hosts_text.winfo_height() > 60
    restart._form_canvas.yview_moveto(1)
    root.update()
    assert restart._parallel_entry.winfo_rooty() < button.winfo_rooty()
    with patch("ssh_manager_app.dialogs_restart.messagebox.askyesno", return_value=True) as ask:
        restart._on_ok()
    assert restart.result["max_parallel"] == 2
    assert "7 Server" in ask.call_args.args[1]


def test_deploy_permissions_dialog_cancel_does_not_transfer(root, tmp_path):
    file = tmp_path / "key.pem"
    file.write_text("test")
    dialog = CertificateDeployDialog(root, 1, [(Session("a", "A", [], "host-a"), "ops")])
    _small_dialog(dialog, root)
    dialog._files = [str(file)]
    dialog._target_dirs_text.insert("1.0", "/etc/ssl/private")
    root.update()
    button = next(button for button in _buttons(dialog) if button.cget("text") == "Übertragen")
    assert button.winfo_rooty() + button.winfo_height() <= dialog.winfo_rooty() + dialog.winfo_height()
    assert dialog._files_list.winfo_height() > 50
    dialog._form_canvas.yview_moveto(1)
    root.update()
    assert dialog._post_command.winfo_rooty() < button.winfo_rooty()
    with patch.object(dialog, "_choose_permissions") as choose:
        dialog._on_ok()
    choose.assert_called_once()
    assert dialog.result is None
    dialog._permissions = {"owners": {"a": "nginx"}, "file_modes": {str(file): "0600"}, "apply_to_existing": False}
    dialog._on_ok()
    assert dialog.result["owners"] == {"a": "nginx"}
