from types import SimpleNamespace
from unittest.mock import patch
import tkinter as tk

import pytest

from ssh_manager_app.models import Session
from ssh_manager_app.remote_browser import ReferenceBrowser, list_services


@pytest.fixture
def root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def hosts():
    return [Session("a", "Alpha", [], "a.test", "ops"), Session("b", "Beta", [], "b.test", "deploy")]


def test_script_browser_selects_file_and_does_not_apply_late_results_from_other_host(root):
    selected, work = [], []
    browser = ReferenceBrowser(root, hosts(), selected.append, user_getter=lambda: "fallback")
    with patch("ssh_manager_app.remote_browser.run_worker", side_effect=lambda *args: work.append(args)):
        browser.load()
        browser.host.current(1)
        browser.load()
    work[0][2]([("f", "/wrong-host.sh")])
    assert not browser.entries
    work[1][2]([("d", "/opt"), ("f", "/run script.sh")])
    browser.listbox.selection_set(1)
    browser.select()
    assert selected == ["/run script.sh"]
    assert "Beta" in browser.warning.get()
    assert "allen Zielhosts" in browser.warning.get()
    browser.destroy()


def test_directory_navigation_and_user_snapshot_are_read_only(root):
    selected, work = [], []
    browser = ReferenceBrowser(root, hosts(), selected.append, user_getter=lambda: "fallback")
    with patch("ssh_manager_app.remote_browser.run_worker", side_effect=lambda *args: work.append(args)):
        browser.entries = [("d", "/opt")]
        browser.filter()
        browser.listbox.selection_set(0)
        browser.select()
    assert browser.path.get() == "/opt"
    assert not selected
    with patch("ssh_manager_app.dialogs_certificates._ssh_folder_list_command", return_value=([], "")) as listing:
        work[0][1]()
    listing.assert_called_once_with(hosts()[0], "ops", "/opt", "")
    browser.destroy()


def test_script_dialog_browser_is_half_width_and_preserves_manual_path(root):
    from ssh_manager_app.dialogs_remote import RemoteCommandDialog
    dialog = RemoteCommandDialog(root, 2, run_mode="remote_script", reference_sessions=hosts())
    dialog._remote_path_var.set("/opt/run.sh")
    with patch("ssh_manager_app.remote_browser.run_worker"):
        dialog._browse_remote()
    root.update()
    assert abs(dialog._body.sashpos(0) - dialog._body.winfo_width() // 2) <= 3
    assert dialog._browser.path.get() == "/opt"
    assert not dialog._library.winfo_manager()
    dialog._browser.on_select("/srv/job.sh")
    assert dialog._remote_path_var.get() == "/srv/job.sh"
    dialog._close_browser()
    assert dialog._library.winfo_manager() == "grid"
    assert not dialog._browser.winfo_manager()
    dialog._on_cancel()


def test_collapsed_advanced_commands_are_preserved_in_editor_but_not_executed(root):
    from ssh_manager_app.dialogs_remote import RemoteCommandDialog
    dialog = RemoteCommandDialog(root, 2, run_mode="local_script")
    dialog._apply_spec({"mode": "local_script", "path": "/test.sh", "before_command": "echo before", "after_command": "echo after"})
    dialog._advanced_flow.set(False)
    dialog._update_help()
    assert dialog._current_spec()["before_command"] == ""
    assert dialog._current_spec()["after_command"] == ""
    dialog._advanced_flow.set(True)
    assert dialog._current_spec()["before_command"] == "echo before"
    dialog._on_cancel()


def test_services_combine_installed_and_runtime_units_and_preserve_alias():
    session = hosts()[0]
    session.source = "ssh_config"
    output = "nginx.service enabled enabled\nworker@one.service static -\nnginx.service loaded active running\nunsafe;reboot.service loaded\n"
    with patch("ssh_manager_app.remote_browser.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=output)) as run:
        result = list_services(session, "ignored")
    assert result == [("service", "nginx.service"), ("service", "worker@one.service")]
    args = run.call_args.args[0]
    assert args[args.index("--") + 1] == "Alpha"
    assert "StrictHostKeyChecking=yes" in args
    assert "list-unit-files" in args[-1] and "list-units" in args[-1]


def test_service_browser_search_and_selection_keep_free_input(root):
    selected = []
    browser = ReferenceBrowser(root, hosts(), selected.append, kind="service", default_user="ops")
    browser.entries = [("service", "nginx.service"), ("service", "wildfly.service")]
    browser.search.set("wild")
    browser.listbox.selection_set(0)
    browser.select()
    assert selected == ["wildfly.service"]
    assert "Dienst wurde nicht gefunden" in browser.warning.get()
    browser.destroy()


def test_remote_form_user_is_used_for_unset_hosts_without_second_prompt():
    from ssh_manager_app.actions_remote import resolve_users_for_sessions
    sessions = hosts()
    sessions[1].username = ""
    with patch("ssh_manager_app.actions_remote.UserDialog") as prompt:
        users = resolve_users_for_sessions(SimpleNamespace(), sessions, "all", shared_user="chosen")
    prompt.assert_not_called()
    assert users == [(sessions[0], "ops"), (sessions[1], "chosen")]
