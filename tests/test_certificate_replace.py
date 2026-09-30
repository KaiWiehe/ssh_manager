from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ssh_manager_app.actions_certificate_replace import _earliest_certificate_expiry, _format_timestamp, _scan_host, _selected_deployments, _show_replace_preview
from ssh_manager_app.dialogs_certificate_replace import CertificateReplacePreviewDialog
from ssh_manager_app.models import AppSettings, Session


def test_certificate_scan_returns_regular_matches_and_reports_symlinks_without_command_password():
    session = Session("srv", "Server", [], "10.0.0.9")
    completed = SimpleNamespace(
        returncode=0,
        stdout=b"M\tf\tkeystore.jks\t/opt/wildfly-a/keystore.jks\t2026-08-01 10:00:00\tAug 1 2030\nM\tl\tkeystore.jks\t/opt/current/keystore.jks\n",
        stderr=b"",
    )
    with patch("ssh_manager_app.actions_certificate_replace.subprocess.run", return_value=completed) as run:
        result = _scan_host(session, "deploy", ["/opt", "/etc/nginx"], ["keystore.jks"], "secret")

    assert result["matches"] == [("keystore.jks", "/opt/wildfly-a/keystore.jks", "2026-08-01 10:00:00", "Aug 1 2030")]
    assert result["symlinks"] == [("keystore.jks", "/opt/current/keystore.jks", "", "")]
    assert "secret" not in run.call_args.args[0]
    script = run.call_args.kwargs["input"].decode("utf-8")
    assert "-type f -name \"$name\"" in script
    assert "-type l -name \"$name\"" in script


def test_certificate_scan_uses_a_temporary_remote_file_for_keystore_password():
    session = Session("srv", "Server", [], "10.0.0.9")
    completed = SimpleNamespace(returncode=0, stdout=b"", stderr=b"")
    with patch("ssh_manager_app.actions_certificate_replace.subprocess.run", return_value=completed) as run:
        _scan_host(session, "deploy", ["/opt"], ["keystore.p12"], "", "store-secret")

    assert "store-secret" not in run.call_args.args[0]
    script = run.call_args.kwargs["input"].decode("utf-8")
    assert "keystore_password_file=$(mktemp /tmp/ssh-manager-keystore-pass-XXXXXX)" in script
    assert "-passin file:\"$keystore_password_file\"" in script
    assert "-storepass:file \"$keystore_password_file\"" in script


def test_certificate_replace_preview_assigns_visual_tags():
    assert CertificateReplacePreviewDialog._line_tag("  HINWEIS: /etc/nginx fehlt") == "warning"
    assert CertificateReplacePreviewDialog._line_tag("  FEHLER: SSH-Scan fehlgeschlagen") == "error"
    assert CertificateReplacePreviewDialog._line_tag("Produktivserver (10.0.0.9)") == "host"


def test_certificate_timestamp_format_is_compact_and_readable():
    assert _format_timestamp("2026-07-29 13:12:38.781885924 +0200") == "29.07.2026 13:12:38 (+02:00)"
    assert _format_timestamp("Sat Jan 30 00:59:59 CET 2027, Tue Jan 19 00:59:59 CET 2038") == "30.01.2027 00:59:59, 19.01.2038 00:59:59"


def test_certificate_expiry_uses_only_the_earliest_date_from_a_keystore_chain():
    assert _earliest_certificate_expiry("2027-01-30 00:59:59 +0100, 2036-03-22 00:59:59 +0100, 2038-01-19 00:59:59 +0100") == "30.01.2027 00:59:59"


def test_selected_deployments_only_includes_checked_certificate_matches():
    session = Session("srv", "Server", [], "10.0.0.9")
    scanned = [(
        session, "deploy", {"errors": [], "matches": [
            ("one.jks", "/opt/one.jks", "timestamp", "expiry"),
            ("two.p12", "/opt/two.p12", "timestamp", "expiry"),
        ]},
    )]

    deployments = _selected_deployments(scanned, {"files": ["one.jks", "two.p12"]}, {(0, "two.p12", "/opt/two.p12")})

    assert len(deployments) == 1
    assert deployments[0][2]["matches"] == [("two.p12", "/opt/two.p12")]


def test_certificate_replacement_uses_configured_terminal_launcher():
    app = MagicMock()
    app.settings = AppSettings()
    app._tree.get_session_colors.return_value = {"srv": "#654321"}
    progress = MagicMock()
    session = Session("srv", "Server", [], "10.0.0.9")
    scanned = [(
        session,
        "ops",
        {
            "matches": [("server.p12", "/opt/server.p12", "timestamp", "expiry")],
            "symlinks": [],
            "warnings": [],
            "errors": [],
        },
    )]
    spec = {"post_command": "", "files": ["server.p12"]}
    preview = MagicMock(result={(0, "server.p12", "/opt/server.p12")})
    deployments = [(session, "ops", {**spec, "matches": [("server.p12", "/opt/server.p12")]})]

    with patch("ssh_manager_app.actions_certificate_replace.CertificateReplacePreviewDialog", return_value=preview), \
         patch("ssh_manager_app.actions_certificate_replace._selected_deployments", return_value=deployments), \
         patch("ssh_manager_app.actions_certificate_replace.build_certificate_replace_wt_command", return_value="replace-cmd") as build, \
         patch("ssh_manager_app.actions_certificate_replace.TerminalLauncher.launch_built_command") as launch:
        _show_replace_preview(app, progress, scanned, spec, "Quelle")

    progress.close.assert_called_once_with()
    build.assert_called_once_with(
        deployments,
        session_colors={"srv": "#654321"},
        terminal_settings=app.settings.windows_terminal,
    )
    launch.assert_called_once_with("replace-cmd", ["Server"], app.settings.windows_terminal)
