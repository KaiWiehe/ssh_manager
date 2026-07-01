from __future__ import annotations

import ast
import base64
import threading
from pathlib import Path
from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ssh_manager_app.dns_lookup import (
    DnsLookupResult,
    detect_lookup_mode,
    normalize_dns_server,
    parse_nslookup_output,
    parse_resolve_dns_name_json,
    resolve_dns_value,
)
from ssh_manager_app.dialogs_dns import (
    DnsLookupProgressDialog,
    DnsLookupResultsDialog,
    resolve_dns_server_selection,
)
from ssh_manager_app.models import Session
from ssh_manager_app.tree import SessionTree


def test_detect_lookup_mode_distinguishes_ips_and_names():
    assert detect_lookup_mode("10.0.0.1") == "reverse"
    assert detect_lookup_mode("2001:4860:4860::8888") == "reverse"
    assert detect_lookup_mode("db.internal.example") == "forward"


def test_parse_resolve_dns_name_json_reads_forward_addresses():
    output = '[{"Name":"example.com","IPAddress":"93.184.216.34","Type":"A"},{"Name":"example.com","IPAddress":"2606:2800:220:1:248:1893:25c8:1946","Type":"AAAA"}]'

    assert parse_resolve_dns_name_json(output, "forward") == [
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    ]


def test_parse_resolve_dns_name_json_reads_reverse_names():
    output = '{"Name":"8.8.8.8.in-addr.arpa","NameHost":"dns.google","Type":"PTR"}'

    assert parse_resolve_dns_name_json(output, "reverse") == ["dns.google"]


def test_parse_nslookup_output_reads_forward_answers_without_dns_server_address():
    output = """
Server:  router.local
Address:  192.168.1.1

Nicht autorisierende Antwort:
Name:    example.com
Addresses:  2606:2800:220:1:248:1893:25c8:1946
          93.184.216.34
"""

    assert parse_nslookup_output(output, "forward") == [
        "2606:2800:220:1:248:1893:25c8:1946",
        "93.184.216.34",
    ]


def test_parse_nslookup_output_reads_reverse_answers():
    output = """
Server:  router.local
Address:  192.168.1.1

8.8.8.8.in-addr.arpa    name = dns.google
"""

    assert parse_nslookup_output(output, "reverse") == ["dns.google"]


def test_resolve_dns_value_falls_back_from_powershell_to_nslookup():
    with patch("ssh_manager_app.dns_lookup._resolve_with_powershell", side_effect=RuntimeError("missing")), \
         patch("ssh_manager_app.dns_lookup._resolve_with_nslookup", return_value=["dns.google"]) as nslookup, \
         patch("ssh_manager_app.dns_lookup._resolve_with_socket") as socket_resolver:
        result = resolve_dns_value("8.8.8.8")

    assert result.status == "ok"
    assert result.mode == "reverse"
    assert result.resolver == "nslookup"
    assert result.results == ["dns.google"]
    nslookup.assert_called_once()
    socket_resolver.assert_not_called()


def test_resolve_dns_value_uses_socket_after_empty_external_results():
    with patch("ssh_manager_app.dns_lookup._resolve_with_powershell", return_value=[]), \
         patch("ssh_manager_app.dns_lookup._resolve_with_nslookup", return_value=[]), \
         patch("ssh_manager_app.dns_lookup._resolve_with_socket", return_value=["10.0.0.1"]):
        result = resolve_dns_value("db.internal")

    assert result.status == "ok"
    assert result.mode == "forward"
    assert result.resolver == "Python socket"
    assert result.results == ["10.0.0.1"]


def test_custom_dns_server_is_used_without_system_socket_fallback():
    with patch("ssh_manager_app.dns_lookup._resolve_with_powershell", return_value=[]), \
         patch("ssh_manager_app.dns_lookup._resolve_with_nslookup", return_value=["93.184.216.34"]) as nslookup, \
         patch("ssh_manager_app.dns_lookup._resolve_with_socket") as socket_resolver:
        result = resolve_dns_value("example.com", dns_server="8.8.8.8")

    assert result.status == "ok"
    assert result.resolver == "nslookup (8.8.8.8)"
    nslookup.assert_called_once_with("example.com", "forward", 8, "8.8.8.8")
    socket_resolver.assert_not_called()


def test_custom_dns_server_remains_visible_when_no_records_are_found():
    with patch("ssh_manager_app.dns_lookup._resolve_with_powershell", return_value=[]), \
         patch("ssh_manager_app.dns_lookup._resolve_with_nslookup", return_value=[]):
        result = resolve_dns_value("missing.example", dns_server="8.8.8.8")

    assert result.status == "not_found"
    assert result.resolver == "8.8.8.8"


def test_nslookup_appends_selected_dns_server_to_commands():
    from ssh_manager_app import dns_lookup

    completed = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("ssh_manager_app.dns_lookup._run_command", return_value=completed) as run:
        dns_lookup._resolve_with_nslookup("example.com", "forward", 2, "1.1.1.1")

    assert run.call_args_list[0].args[0] == ["nslookup", "-type=A", "example.com", "1.1.1.1"]
    assert run.call_args_list[1].args[0] == ["nslookup", "-type=AAAA", "example.com", "1.1.1.1"]


def test_dns_server_selection_supports_system_presets_and_custom_ip():
    assert resolve_dns_server_selection("Aktueller DNS (System)") is None
    assert resolve_dns_server_selection("Google (8.8.8.8)") == "8.8.8.8"
    assert resolve_dns_server_selection("  2001:4860:4860::8888  ") == "2001:4860:4860::8888"
    assert normalize_dns_server("1.1.1.1") == "1.1.1.1"


def test_dns_server_selection_rejects_invalid_custom_value():
    with pytest.raises(ValueError, match="DNS-Server"):
        resolve_dns_server_selection("not a server")


def test_resolve_dns_value_reports_empty_input():
    result = resolve_dns_value("  ")

    assert result.status == "error"
    assert result.error == "Leere Eingabe"


def test_powershell_resolver_parses_json_from_subprocess():
    from ssh_manager_app import dns_lookup

    completed = CompletedProcess(
        args=[],
        returncode=0,
        stdout='{"NameHost":"dns.google"}',
        stderr="",
    )
    with patch("ssh_manager_app.dns_lookup._run_command", return_value=completed) as run:
        result = dns_lookup._resolve_with_powershell("8.8.8.8", "reverse", 2)

    assert result == ["dns.google"]
    assert run.call_args.args[0][0] == "powershell"


def test_powershell_resolver_uses_selected_dns_server():
    from ssh_manager_app import dns_lookup

    completed = CompletedProcess(args=[], returncode=0, stdout="[]", stderr="")
    with patch("ssh_manager_app.dns_lookup._run_command", return_value=completed) as run:
        dns_lookup._resolve_with_powershell("example.com", "forward", 2, "9.9.9.9")

    encoded = run.call_args.args[0][-1]
    command = base64.b64decode(encoded).decode("utf-16le")
    assert "-Server '9.9.9.9'" in command


def test_run_command_replaces_undecodable_output_bytes():
    from ssh_manager_app import dns_lookup

    with patch("ssh_manager_app.dns_lookup.subprocess.run", return_value=CompletedProcess(args=[], returncode=0)) as run:
        dns_lookup._run_command(["nslookup", "example.com"], 3)

    assert run.call_args.kwargs["text"] is True
    assert run.call_args.kwargs["errors"] == "replace"


def test_dns_results_dialog_left_aligns_columns_and_headers():
    dialog = SimpleNamespace(
        _results=[DnsLookupResult("example.com", "forward", ["10.0.0.1"], "Resolve-DnsName", "ok")],
        _show_connection_names=False,
        columnconfigure=MagicMock(),
        rowconfigure=MagicMock(),
        _status_label=lambda result: "OK",
        _result_label=lambda result: ", ".join(result.results),
        _copy_all=MagicMock(),
        _copy_values=MagicMock(),
        destroy=MagicMock(),
    )
    parent = MagicMock()
    frame = MagicMock()
    button_frame = MagicMock()
    tree = MagicMock()

    with patch("ssh_manager_app.dialogs_dns.ttk.Frame", side_effect=[frame, button_frame]), \
         patch("ssh_manager_app.dialogs_dns.ttk.Treeview", return_value=tree), \
         patch("ssh_manager_app.dialogs_dns.ttk.Scrollbar", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_dns.ttk.Button", return_value=MagicMock()):
        DnsLookupResultsDialog._build(dialog, parent)

    for call in tree.heading.call_args_list:
        assert call.kwargs["anchor"] == "w"
    for call in tree.column.call_args_list:
        assert call.kwargs["anchor"] == "w"


def test_dns_results_dialog_adds_connection_name_before_hostname_for_sessions():
    result = DnsLookupResult(
        "server.example.com",
        "forward",
        ["10.0.0.1"],
        "Resolve-DnsName",
        "ok",
        connection_name="Produktivserver",
    )
    dialog = SimpleNamespace(
        _results=[result],
        _show_connection_names=True,
        columnconfigure=MagicMock(),
        rowconfigure=MagicMock(),
        _status_label=lambda lookup: "OK",
        _result_label=lambda lookup: ", ".join(lookup.results),
        _copy_all=MagicMock(),
        _copy_values=MagicMock(),
        destroy=MagicMock(),
    )
    tree = MagicMock()

    with patch("ssh_manager_app.dialogs_dns.ttk.Frame", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_dns.ttk.Treeview", return_value=tree) as tree_cls, \
         patch("ssh_manager_app.dialogs_dns.ttk.Scrollbar", side_effect=[MagicMock(), MagicMock()]), \
         patch("ssh_manager_app.dialogs_dns.ttk.Button", return_value=MagicMock()):
        DnsLookupResultsDialog._build(dialog, MagicMock())

    assert tree_cls.call_args.kwargs["columns"][0] == "query"
    assert tree.heading.call_args_list[0].kwargs["text"] == "Verbindung"
    assert tree.heading.call_args_list[1].args[0] == "query"
    assert tree.heading.call_args_list[1].kwargs["text"] == "Hostname"
    assert tree.insert.call_args.kwargs["text"] == "Produktivserver"
    assert tree.insert.call_args.kwargs["values"][0] == "server.example.com"


def test_dns_results_dialog_is_non_modal():
    result = DnsLookupResult("example.com", "forward", ["10.0.0.1"], "Python socket", "ok")

    with patch("ssh_manager_app.dialogs_dns.tk.Toplevel.__init__", return_value=None), \
         patch.object(DnsLookupResultsDialog, "title"), \
         patch.object(DnsLookupResultsDialog, "resizable"), \
         patch.object(DnsLookupResultsDialog, "geometry"), \
         patch.object(DnsLookupResultsDialog, "transient"), \
         patch.object(DnsLookupResultsDialog, "protocol"), \
         patch.object(DnsLookupResultsDialog, "grab_set") as grab_set, \
         patch.object(DnsLookupResultsDialog, "_build"), \
         patch.object(DnsLookupResultsDialog, "_center_on_parent"), \
         patch.object(DnsLookupResultsDialog, "bind"):
        DnsLookupResultsDialog(MagicMock(), [result])

    grab_set.assert_not_called()


def test_dns_results_copy_includes_connection_name_only_for_session_results():
    result = DnsLookupResult(
        "server.example.com",
        "forward",
        ["10.0.0.1"],
        "Resolve-DnsName",
        "ok",
        connection_name="Produktivserver",
    )
    dialog = SimpleNamespace(
        _results=[result],
        _show_connection_names=True,
        _status_label=lambda lookup: "OK",
        _result_label=lambda lookup: ", ".join(lookup.results),
        _copy=MagicMock(),
    )
    parent = MagicMock()

    DnsLookupResultsDialog._copy_all(dialog, parent)

    copied = dialog._copy.call_args.args[1]
    assert copied.startswith("Verbindung\tHostname\t")
    assert "Produktivserver\tserver.example.com\t" in copied


def test_dns_result_label_hides_multiline_clixml_errors():
    result = DnsLookupResult(
        "10.0.0.99",
        "reverse",
        [],
        "8.8.8.8",
        "not_found",
        error="Resolve-DnsName: #< CLIXML\n<Objs>very long technical output</Objs>",
    )

    label = DnsLookupResultsDialog._result_label(None, result)

    assert label == "Keine Treffer"
    assert "\n" not in label


def test_dns_progress_dialog_builds_running_indicator():
    dialog = SimpleNamespace(_progress=None)
    frame = MagicMock()
    label = MagicMock()
    progress = MagicMock()

    with patch("ssh_manager_app.dialogs_dns.ttk.Frame", return_value=frame), \
         patch("ssh_manager_app.dialogs_dns.ttk.Label", return_value=label) as label_cls, \
         patch("ssh_manager_app.dialogs_dns.ttk.Progressbar", return_value=progress) as progress_cls:
        DnsLookupProgressDialog._build(dialog, 3)

    label_cls.assert_called_once()
    assert "3 Einträge" in label_cls.call_args.kwargs["text"]
    progress_cls.assert_called_once_with(frame, mode="indeterminate", length=320)
    progress.start.assert_called_once_with(12)
    assert dialog._progress is progress


def test_dns_progress_dialog_close_button_marks_lookup_cancelled():
    dialog = SimpleNamespace(_cancel_event=threading.Event(), close=MagicMock())

    DnsLookupProgressDialog._on_cancel(dialog)

    assert dialog._cancel_event.is_set()
    dialog.close.assert_called_once_with()


def test_show_dns_lookup_results_closes_progress_before_showing_results():
    from ssh_manager_app.actions_dns import _show_dns_lookup_results

    app = MagicMock()
    progress = MagicMock()
    progress.cancelled = False
    results = [DnsLookupResult("example.com", "forward", ["10.0.0.1"], "Python socket", "ok")]

    with patch("ssh_manager_app.actions_dns.DnsLookupResultsDialog") as results_dialog:
        _show_dns_lookup_results(app, progress, results)

    progress.close.assert_called_once_with()
    results_dialog.assert_called_once_with(app, results)


def test_show_dns_lookup_results_does_nothing_after_progress_was_cancelled():
    from ssh_manager_app.actions_dns import _show_dns_lookup_results

    app = MagicMock()
    progress = MagicMock()
    progress.cancelled = True

    with patch("ssh_manager_app.actions_dns.DnsLookupResultsDialog") as results_dialog:
        _show_dns_lookup_results(app, progress, [])

    progress.close.assert_not_called()
    results_dialog.assert_not_called()


def test_session_dns_lookup_keeps_connection_names_for_shared_hostname():
    from ssh_manager_app.actions_dns import resolve_dns_for_sessions

    app = MagicMock()
    sessions = [
        Session("a", "Server A", [], "shared.example.com"),
        Session("b", "Server B", [], "shared.example.com"),
    ]

    with patch("ssh_manager_app.actions_dns._resolve_values_async") as resolve_async:
        resolve_dns_for_sessions(app, sessions)

    resolve_async.assert_called_once_with(
        app,
        [
            ("shared.example.com", "auto", "Server A"),
            ("shared.example.com", "auto", "Server B"),
        ],
    )


def test_manual_dns_lookup_passes_selected_server_to_resolver():
    from ssh_manager_app.actions_dns import open_dns_lookup_dialog

    app = SimpleNamespace(
        wait_window=MagicMock(),
        _winscp_sessions=[],
        _app_sessions=[],
        _ssh_config_sessions=[],
        _filezilla_sessions=[],
    )
    dialog = MagicMock()
    dialog.result = ("example.com", "forward", "8.8.8.8")

    with patch("ssh_manager_app.actions_dns.DnsLookupDialog", return_value=dialog), \
         patch("ssh_manager_app.actions_dns._resolve_values_async") as resolve_async:
        open_dns_lookup_dialog(app)

    resolve_async.assert_called_once_with(
        app,
        [("example.com", "forward", "")],
        dns_server="8.8.8.8",
        match_sessions=[],
    )


def test_selection_dns_server_action_keeps_existing_lookup_separate():
    from ssh_manager_app.actions_dns import resolve_dns_for_sessions_with_server_selection

    app = SimpleNamespace(wait_window=MagicMock())
    sessions = [
        Session("a", "Server A", [], "server-a.example.com"),
        Session("b", "Server B", [], "server-b.example.com"),
    ]
    dialog = MagicMock()
    dialog.result = "1.1.1.1"

    with patch("ssh_manager_app.actions_dns.DnsServerDialog", return_value=dialog) as dialog_cls, \
         patch("ssh_manager_app.actions_dns._resolve_values_async") as resolve_async:
        resolve_dns_for_sessions_with_server_selection(app, sessions)

    dialog_cls.assert_called_once_with(app, 2)
    resolve_async.assert_called_once_with(
        app,
        [
            ("server-a.example.com", "auto", "Server A"),
            ("server-b.example.com", "auto", "Server B"),
        ],
        dns_server="1.1.1.1",
    )


def test_async_dns_lookup_resolves_shared_hostname_once_and_labels_each_result():
    from ssh_manager_app.actions_dns import _resolve_values_async

    app = MagicMock()
    app.after.side_effect = lambda _delay, callback: callback()
    progress = MagicMock()
    progress.cancelled = False
    resolved = DnsLookupResult("shared.example.com", "forward", ["10.0.0.1"], "Python socket", "ok")

    def run_thread_immediately(*, target, daemon):
        thread = MagicMock()
        thread.start.side_effect = target
        return thread

    with patch("ssh_manager_app.actions_dns.DnsLookupProgressDialog", return_value=progress), \
         patch("ssh_manager_app.actions_dns.resolve_dns_value", return_value=resolved) as resolver, \
         patch("ssh_manager_app.actions_dns.DnsLookupResultsDialog") as results_dialog, \
         patch("ssh_manager_app.actions_dns.threading.Thread", side_effect=run_thread_immediately):
        _resolve_values_async(
            app,
            [
                ("shared.example.com", "auto", "Server A"),
                ("shared.example.com", "auto", "Server B"),
            ],
        )

    resolver.assert_called_once_with("shared.example.com", mode="auto")
    shown_results = results_dialog.call_args.args[1]
    assert [result.connection_name for result in shown_results] == ["Server A", "Server B"]


def test_manual_forward_lookup_matches_connections_by_dns_name_and_result_ip():
    from ssh_manager_app.actions_dns import _matching_connection_names

    result = DnsLookupResult(
        "service.example.com",
        "forward",
        ["10.0.0.25"],
        "Python socket",
        "ok",
    )
    sessions = [
        Session("dns", "DNS-Verbindung", [], "service.example.com."),
        Session("ip", "IP-Verbindung", [], "10.0.0.25"),
        Session("other", "Andere Verbindung", [], "10.0.0.99"),
    ]

    assert _matching_connection_names(result, sessions) == "DNS-Verbindung, IP-Verbindung"


def test_manual_lookup_searches_real_sources_without_virtual_session_duplicates():
    from ssh_manager_app.actions_dns import _all_sessions

    session = Session("prod", "Produktivserver", [], "10.0.0.25")
    app = SimpleNamespace(
        _winscp_sessions=[session],
        _app_sessions=[],
        _ssh_config_sessions=[],
        _filezilla_sessions=[],
        _sessions=[session, session],
    )

    assert _all_sessions(app) == [session]


def test_manual_lookup_omits_connection_name_when_no_forward_match_exists():
    from ssh_manager_app.actions_dns import _matching_connection_names

    forward_result = DnsLookupResult("service.example.com", "forward", ["10.0.0.25"], "Python socket", "ok")
    reverse_result = DnsLookupResult("10.0.0.25", "reverse", ["service.example.com"], "Python socket", "ok")
    sessions = [Session("other", "Andere Verbindung", [], "10.0.0.99")]

    assert _matching_connection_names(forward_result, sessions) == ""
    assert _matching_connection_names(reverse_result, sessions) == ""


def test_async_manual_lookup_adds_matched_connection_name_to_result():
    from ssh_manager_app.actions_dns import _resolve_values_async

    app = MagicMock()
    app.after.side_effect = lambda _delay, callback: callback()
    progress = MagicMock()
    progress.cancelled = False
    resolved = DnsLookupResult("service.example.com", "forward", ["10.0.0.25"], "Python socket", "ok")
    sessions = [Session("ip", "Produktivserver", [], "10.0.0.25")]

    def run_thread_immediately(*, target, daemon):
        thread = MagicMock()
        thread.start.side_effect = target
        return thread

    with patch("ssh_manager_app.actions_dns.DnsLookupProgressDialog", return_value=progress), \
         patch("ssh_manager_app.actions_dns.resolve_dns_value", return_value=resolved), \
         patch("ssh_manager_app.actions_dns.DnsLookupResultsDialog") as results_dialog, \
         patch("ssh_manager_app.actions_dns.threading.Thread", side_effect=run_thread_immediately):
        _resolve_values_async(
            app,
            [("service.example.com", "auto", "")],
            match_sessions=sessions,
        )

    shown_result = results_dialog.call_args.args[1][0]
    assert shown_result.connection_name == "Produktivserver"


def test_all_titled_dialog_classes_handle_the_window_close_button():
    dialog_classes = {
        "dialogs_base.py": {"UserDialog"},
        "dialogs_dns.py": {"DnsLookupDialog", "DnsServerDialog", "DnsLookupProgressDialog", "DnsLookupResultsDialog"},
        "dialogs_move_folder.py": {"MoveFolderDialog"},
        "dialogs_remote.py": {
            "JumpHostDialog",
            "SshCopyIdDialog",
            "SshRemoveKeyDialog",
            "RemoteFavoriteEditDialog",
            "RemoteCommandDialog",
            "RemoteCommandConfirmDialog",
            "SshTunnelDialog",
            "SessionEditDialog",
        },
        "dialogs_session_edit.py": {"SessionEditDialog"},
        "dialogs_settings_misc.py": {"SshConfigInspectDialog"},
    }
    package_dir = Path(__file__).parents[1] / "ssh_manager_app"

    for filename, expected_classes in dialog_classes.items():
        tree = ast.parse((package_dir / filename).read_text(encoding="utf-8"))
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        for class_name in expected_classes:
            calls = [
                node
                for node in ast.walk(classes[class_name])
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "protocol"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "WM_DELETE_WINDOW"
            ]
            assert calls, f"{filename}:{class_name} behandelt das Fenster-X nicht"


class _FakeMenu:
    instances: list["_FakeMenu"] = []

    def __init__(self, *_args, **_kwargs):
        self.commands = []
        self.cascades = []
        _FakeMenu.instances.append(self)

    def add_command(self, **kwargs):
        self.commands.append(kwargs)

    def add_separator(self):
        pass

    def add_cascade(self, **kwargs):
        self.cascades.append(kwargs)

    def tk_popup(self, *_args):
        pass


def _set_tree_menu_defaults(tree: SessionTree) -> None:
    callback_names = [
        "_on_quick_connect",
        "_on_connect_sessions",
        "_on_edit_session",
        "_on_set_sessions_username",
        "_on_clear_sessions_username",
        "_on_delete_session",
        "_on_delete_folder",
        "_on_rename_folder",
        "_on_add_session",
        "_on_add_session_in_folder",
        "_on_duplicate_ssh_alias",
        "_on_inspect_ssh_config",
        "_on_duplicate_app_session",
        "_on_move_session",
        "_on_move_sessions",
        "_on_open_ssh_config_in_vscode",
        "_on_deploy_ssh_key",
        "_on_remove_ssh_key",
        "_on_open_tunnel",
        "_on_open_in_winscp",
        "_on_run_remote_command",
        "_on_resolve_dns_with_server",
        "_on_open_via_jumphost",
        "_on_copy_ssh_command",
        "_on_ui_state_changed",
        "_on_edit_note",
        "_on_add_favorite",
        "_on_add_favorites",
        "_on_remove_favorite",
        "_on_hide_column",
    ]
    for name in callback_names:
        setattr(tree, name, None)
    tree._favorite_keys_getter = lambda: set()
    tree._session_colors = {}


def test_session_context_menu_calls_dns_callback_for_single_and_selection():
    session_a = Session("a", "srv-a", [], "10.0.0.1")
    session_b = Session("b", "srv-b", [], "db.internal")
    tree = object.__new__(SessionTree)
    _set_tree_menu_defaults(tree)
    tree._item_to_session = {"i1": session_a, "i2": session_b}
    tree._checked = {"i1": True, "i2": True}
    tree.get_selected_sessions = MagicMock(return_value=[session_a, session_b])
    tree._on_resolve_dns = MagicMock()
    tree._on_resolve_dns_with_server = MagicMock()

    _FakeMenu.instances = []
    with patch("ssh_manager_app.tree.tk.Menu", side_effect=lambda *a, **k: _FakeMenu()):
        SessionTree._show_session_menu(tree, "i1", SimpleNamespace(x_root=1, y_root=2))

    root_menu = _FakeMenu.instances[0]
    dns_commands = [item for item in root_menu.commands if str(item.get("label", "")).startswith("DNS/IP")]
    assert [item["label"] for item in dns_commands] == [
        "DNS/IP auflösen…",
        "DNS/IP für Auswahl auflösen… (2)",
        "DNS/IP für Auswahl auflösen… (DNS-Auswahl) (2)",
    ]

    dns_commands[0]["command"]()
    tree._on_resolve_dns.assert_called_with([session_a])
    dns_commands[1]["command"]()
    tree._on_resolve_dns.assert_called_with([session_a, session_b])
    dns_commands[2]["command"]()
    tree._on_resolve_dns_with_server.assert_called_once_with([session_a, session_b])


def test_folder_context_menu_calls_dns_callback_for_folder_sessions():
    session_a = Session("a", "srv-a", [], "10.0.0.1")
    session_b = Session("b", "srv-b", [], "db.internal")
    tree = object.__new__(SessionTree)
    _set_tree_menu_defaults(tree)
    tree._item_to_folder_key = {"folder": "Prod"}
    tree._get_folder_sessions = MagicMock(return_value=[session_a, session_b])
    tree._on_resolve_dns = MagicMock()

    _FakeMenu.instances = []
    with patch("ssh_manager_app.tree.tk.Menu", side_effect=lambda *a, **k: _FakeMenu()):
        SessionTree._show_folder_menu(tree, "folder", SimpleNamespace(x_root=1, y_root=2))

    root_menu = _FakeMenu.instances[0]
    dns_command = next(item for item in root_menu.commands if str(item.get("label", "")).startswith("DNS/IP"))
    assert dns_command["label"] == "DNS/IP für Ordner auflösen… (2)"

    dns_command["command"]()
    tree._on_resolve_dns.assert_called_once_with([session_a, session_b])


def test_main_actions_menu_contains_dns_entries():
    from ssh_manager_app import ui

    source = ui.build_main_ui.__code__.co_consts
    labels = "\n".join(str(item) for item in source)

    assert "DNS/IP auflösen…" in labels
    assert "DNS/IP für Auswahl auflösen…" in labels
    assert "DNS/IP für Auswahl auflösen… (DNS-Auswahl)" in labels
