from __future__ import annotations

from subprocess import CompletedProcess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ssh_manager_app.dns_lookup import (
    detect_lookup_mode,
    parse_nslookup_output,
    parse_resolve_dns_name_json,
    resolve_dns_value,
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

    _FakeMenu.instances = []
    with patch("ssh_manager_app.tree.tk.Menu", side_effect=lambda *a, **k: _FakeMenu()):
        SessionTree._show_session_menu(tree, "i1", SimpleNamespace(x_root=1, y_root=2))

    root_menu = _FakeMenu.instances[0]
    dns_commands = [item for item in root_menu.commands if str(item.get("label", "")).startswith("DNS/IP")]
    assert [item["label"] for item in dns_commands] == [
        "DNS/IP auflösen…",
        "DNS/IP für Auswahl auflösen… (2)",
    ]

    dns_commands[0]["command"]()
    tree._on_resolve_dns.assert_called_with([session_a])
    dns_commands[1]["command"]()
    tree._on_resolve_dns.assert_called_with([session_a, session_b])


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
