from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ssh_manager_app.dialogs_restart import ServerRestartDialog, ServerRestartProgressDialog


def _input_dialog(timeout: str = "5", service: str = "wildfly.service", password: str = "secret"):
    return SimpleNamespace(
        _timeout_var=MagicMock(get=MagicMock(return_value=timeout)),
        _service_var=MagicMock(get=MagicMock(return_value=service)),
        _password_var=MagicMock(get=MagicMock(return_value=password)),
        result=None,
        destroy=MagicMock(),
    )


def test_restart_dialog_returns_password_service_and_seconds():
    dialog = _input_dialog(timeout="7")

    ServerRestartDialog._on_ok(dialog)

    assert dialog.result == {
        "sudo_password": "secret",
        "service": "wildfly.service",
        "timeout_seconds": 420,
        "max_parallel": 0,
    }
    dialog.destroy.assert_called_once_with()


def test_restart_dialog_rejects_timeout_outside_allowed_range():
    dialog = _input_dialog(timeout="61")

    with patch("ssh_manager_app.dialogs_restart.messagebox.showwarning") as warning:
        ServerRestartDialog._on_ok(dialog)

    assert dialog.result is None
    warning.assert_called_once()
    dialog.destroy.assert_not_called()


def test_restart_progress_stop_warns_and_sets_cancel_event():
    dialog = SimpleNamespace(
        _finished=False,
        _cancel_event=MagicMock(),
        _stop_button=MagicMock(),
    )
    dialog._cancel_event.is_set.return_value = False

    with patch("ssh_manager_app.dialogs_restart.messagebox.askyesno", return_value=True) as confirm:
        ServerRestartProgressDialog._on_stop(dialog)

    confirm.assert_called_once()
    dialog._cancel_event.set.assert_called_once_with()
    dialog._stop_button.configure.assert_called_once_with(state="disabled", text="Überwachung wird beendet…")
