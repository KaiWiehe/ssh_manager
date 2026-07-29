from types import SimpleNamespace
from unittest.mock import patch

from ssh_manager_app.actions_certificate_replace import _scan_host
from ssh_manager_app.dialogs_certificate_replace import CertificateReplacePreviewDialog
from ssh_manager_app.models import Session


def test_certificate_scan_returns_regular_matches_and_reports_symlinks_without_command_password():
    session = Session("srv", "Server", [], "10.0.0.9")
    completed = SimpleNamespace(
        returncode=0,
        stdout=b"M\tf\tkeystore.jks\t/opt/wildfly-a/keystore.jks\nM\tl\tkeystore.jks\t/opt/current/keystore.jks\n",
        stderr=b"",
    )
    with patch("ssh_manager_app.actions_certificate_replace.subprocess.run", return_value=completed) as run:
        result = _scan_host(session, "deploy", ["/opt", "/etc/nginx"], ["keystore.jks"], "secret")

    assert result["matches"] == [("keystore.jks", "/opt/wildfly-a/keystore.jks")]
    assert result["symlinks"] == [("keystore.jks", "/opt/current/keystore.jks")]
    assert "secret" not in run.call_args.args[0]
    script = run.call_args.kwargs["input"].decode("utf-8")
    assert "-type f -name \"$name\"" in script
    assert "-type l -name \"$name\"" in script


def test_certificate_replace_preview_assigns_visual_tags():
    assert CertificateReplacePreviewDialog._line_tag("  HINWEIS: /etc/nginx fehlt") == "warning"
    assert CertificateReplacePreviewDialog._line_tag("  FEHLER: SSH-Scan fehlgeschlagen") == "error"
    assert CertificateReplacePreviewDialog._line_tag("Produktivserver (10.0.0.9)") == "host"
