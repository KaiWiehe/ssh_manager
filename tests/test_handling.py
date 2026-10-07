import tkinter as tk
from unittest.mock import patch

import pytest

from ssh_manager_app.dialogs_remote import RemoteCommandDialog


@pytest.fixture
def root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(str(exc))
    root.withdraw()
    yield root
    root.destroy()


@pytest.mark.parametrize("mode", ["command", "local_script", "remote_script"])
def test_remote_task_only_exposes_relevant_inputs(root, mode):
    dialog = RemoteCommandDialog(root, 2, run_mode=mode)
    root.update()
    assert dialog._run_mode.get() == mode
    assert bool(dialog._command_text.frame.winfo_manager()) == (mode == "command")
    assert not dialog._before_text.frame.winfo_manager()
    assert not dialog._after_text.frame.winfo_manager()
    if mode != "command":
        dialog._advanced_flow.set(True)
        dialog._update_help()
        assert dialog._before_text.frame.winfo_manager() == "grid"
        assert dialog._after_text.frame.winfo_manager() == "grid"
    dialog._on_cancel()


def test_saved_script_cannot_silently_switch_command_task(root):
    dialog = RemoteCommandDialog(root, 1, run_mode="command")
    with patch("ssh_manager_app.dialogs_remote.messagebox.showinfo") as info:
        dialog._apply_spec({"mode": "remote_script", "path": "/tmp/run.sh", "interpreter": "bash"})
    assert dialog._run_mode.get() == "command"
    info.assert_called_once()
    dialog._on_cancel()
