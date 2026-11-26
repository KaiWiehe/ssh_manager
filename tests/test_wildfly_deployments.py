import json
import re
import subprocess
from threading import Event
from unittest.mock import Mock

import pytest

from ssh_manager_app import mass_restart
from ssh_manager_app.wildfly_deployments import (
    WildFlyScannerInspectionRequired, WildFlySnapshot, parse_wildfly_snapshot, validate_wildfly_settings, wildfly_deployment_result,
    wildfly_expected_deployments,
)


def wildfly_settings(*, scanner=False):
    return validate_wildfly_settings({
        "cli_path": "/opt/wildfly/bin/jboss-cli.sh",
        "base_dir": "/opt/wildfly/standalone",
        "expected": ["backend.war", "ui.war"],
        "scanner_dirs": ["/opt/wildfly/standalone/deployments"] if scanner else [],
    })


def wildfly_response(token, deployments, *, base="/opt/wildfly/standalone", access=None,
                     scanner=None, scanner_found=False, markers=(), runtime="1489@node", pids="1488\n1489"):
    subsystems = ["deployment-scanner"] if scanner_found or scanner is not None else []
    result = {"step-1": {"outcome": "success", "result": base},
              "step-2": {"outcome": "success", "result": deployments},
              "step-3": {"outcome": "success", "result": subsystems},
              "step-4": {"outcome": "success", "result": runtime}}
    if access:
        result["step-2"]["response-headers"] = {"access-control": access}
    if scanner is not None:
        result["step-5"] = {"outcome": "success", "result": scanner}
    return (
        f"SSH banner\n{token}\n" + json.dumps({"outcome": "success", "result": result}) +
        f"\n\n{token}\nnode\0{pids}\0" + "".join(name + "\0" for name in markers)
    )


def deployment(status, enabled=True, **attrs):
    return {"enabled": enabled, "status": status, **attrs}


def test_scanner_failure_for_missing_model_entry_and_disabled_deployment():
    settings = wildfly_settings(scanner=True)
    scanner = {"default": {"scan-enabled": True, "path": "deployments", "relative-to": "jboss.server.base.dir"}}
    response = wildfly_response("token", {"backend.war": deployment("OK"), "archive.war": deployment("STOPPED", False)},
                                scanner=scanner, markers=("ui.war.failed",))
    snapshot = parse_wildfly_snapshot(response, "token", settings, inspect_scanners=True)
    expected = wildfly_expected_deployments(settings, snapshot)
    ready, failed, result = wildfly_deployment_result(snapshot, expected)
    assert expected == {"backend.war", "ui.war"}
    assert not ready and failed
    assert "1 von 2 Deployments OK" in result
    assert "ui.war · fehlt · Scanner FAILED" in result
    assert "Deaktiviert: archive.war" in result


@pytest.mark.parametrize(("response_options", "expected"), [
    ({"base": "/opt/another/standalone"}, "Basisverzeichnis"),
    ({"runtime": "1489@another-host"}, "systemd-Unit"),
    ({"pids": "1488\n1490"}, "systemd-Unit"),
    ({"access": [{"filtered-attributes": ["status"]}]}, "gefiltert"),
    ({"scanner": {"default": {"scan-enabled": True, "path": "/other", "relative-to": None}}}, "Scanner-Verzeichnisse"),
])
def test_parser_rejects_wrong_instance_and_incomplete_scope(response_options, expected):
    response = wildfly_response("token", {"backend.war": deployment("OK")}, **response_options)
    with pytest.raises(ValueError, match=expected):
        parse_wildfly_snapshot(response, "token", wildfly_settings(scanner="scanner" in response_options),
                               inspect_scanners="scanner" in response_options)


def test_scanner_installation_without_configuration_cannot_hide_failed_markers():
    settings = wildfly_settings()
    good = {"backend.war": deployment("OK"), "ui.war": deployment("OK")}
    with pytest.raises(WildFlyScannerInspectionRequired):
        parse_wildfly_snapshot(wildfly_response("token", good, scanner_found=True), "token", settings)
    enabled = {"default": {"scan-enabled": True, "path": "deployments", "relative-to": "jboss.server.base.dir"}}
    with pytest.raises(ValueError, match="aktive Scanner"):
        parse_wildfly_snapshot(wildfly_response("token", good, scanner=enabled), "token", settings, inspect_scanners=True)
    disabled = {"default": {"scan-enabled": False}}
    snapshot = parse_wildfly_snapshot(wildfly_response("token", good, scanner=disabled), "token", settings,
                                      inspect_scanners=True)
    assert wildfly_deployment_result(snapshot, wildfly_expected_deployments(settings, snapshot))[0]


def test_probe_checks_registered_scanners_even_when_no_directory_was_entered(monkeypatch):
    good = {"backend.war": deployment("OK"), "ui.war": deployment("OK")}
    scanner = {"default": {"scan-enabled": True, "path": "deployments", "relative-to": "jboss.server.base.dir"}}
    called = []

    def ssh(_session, _user, command, _cancel, **_options):
        token = re.search(r"SSH_MANAGER_WILDFLY_[0-9a-f]+", command)[0]
        has_scan_query = "child-type=scanner" in command
        called.append(has_scan_query)
        reply = wildfly_response(token, good, scanner_found=True, scanner=scanner if has_scan_query else None)
        return subprocess.CompletedProcess([], 0, reply, "")

    monkeypatch.setattr(mass_restart, "mass_ssh", ssh)
    identity = mass_restart.RestartIdentity("a" * 32, "11111111-1111-1111-1111-111111111111")
    kind, detail = mass_restart.probe_wildfly_deployments(None, "ops", "wf.service", wildfly_settings(),
                                                         identity, Event())
    assert called == [False, True]
    assert kind == "error" and "aktive Scanner" in detail


def test_empty_unknown_invalid_or_scanner_only_deployments_cannot_turn_green():
    settings = wildfly_settings()
    with pytest.raises(ValueError, match="keine Deployments"):
        wildfly_expected_deployments(settings, parse_wildfly_snapshot(wildfly_response("token", {}), "token", settings))
    with pytest.raises(ValueError, match="kein gültiges JSON"):
        parse_wildfly_snapshot("token\n{bad json\n\ntoken\n", "token", settings)
    with pytest.raises(ValueError, match="Scanner-Deployments"):
        parse_wildfly_snapshot(wildfly_response("token", {"backend.war": deployment("OK", persistent=False)}),
                               "token", settings)
    with pytest.raises(ValueError, match="widersprüchliche"):
        parse_wildfly_snapshot(wildfly_response("token", {"backend.war": deployment("OK", enabled=False)}),
                               "token", settings)
    snapshot = parse_wildfly_snapshot(wildfly_response("token", {"backend.war": deployment(None),
                                                                 "ui.war": deployment("STOPPED")}), "token", settings)
    assert wildfly_deployment_result(snapshot, set(settings["expected"]))[:2] == (False, False)
    with pytest.raises(ValueError, match="Laufzeitstatus"):
        wildfly_expected_deployments(settings, snapshot)
    with pytest.raises(ValueError, match="ui.war"):
        wildfly_expected_deployments(settings, WildFlySnapshot({"backend.war": (True, "OK")}, ()))
    with pytest.raises(ValueError, match="Soll-Deployments"):
        validate_wildfly_settings({**wildfly_settings(scanner=True), "expected": []})


def test_preflight_preserves_failed_deployments_as_expected_and_blocks_unreadable_management(monkeypatch):
    settings = wildfly_settings()
    checks = [{"unit": "wf.service", "expected": "active", "wildfly": settings}]
    identity = mass_restart.RestartIdentity("1" * 32, "11111111-1111-1111-1111-111111111111")
    monkeypatch.setattr(mass_restart, "read_restart_identity", lambda *_: ("identity", identity))
    monkeypatch.setattr(mass_restart, "_probe_restart_unit", lambda *_: ("state", "active"))
    permission = Mock(return_value=(subprocess.CompletedProcess([], 0, "", ""), True))
    monkeypatch.setattr(mass_restart, "_call_restart_sudo", permission)
    report = Mock()
    mock_probe = Mock(return_value=("snapshot", WildFlySnapshot({
        "backend.war": (True, "FAILED"), "ui.war": (True, "FAILED"),
    }, ())))
    monkeypatch.setattr(mass_restart, "probe_wildfly_deployments", mock_probe)
    before = mass_restart.check_restart_target(None, "ops", checks, "", Event(), report)
    assert before.status == "online"
    assert before.wildfly_expected == {"wf.service": {"backend.war", "ui.war"}}
    assert "backend.war · FAILED" in before.detail
    assert "backend.war · FAILED" in before.wildfly_before[0]
    assert permission.call_args.kwargs == {"permission_check": True}
    permission.reset_mock()
    mock_probe.return_value = ("error", "WildFly-Authentifizierung oder Leseberechtigung fehlgeschlagen.")
    blocked = mass_restart.check_restart_target(None, "ops", checks, "", Event(), report)
    assert blocked.status == "error" and "Leseberechtigung" in blocked.detail
    permission.assert_not_called()


@pytest.mark.parametrize("recovers", [False, True])
def test_active_systemd_does_not_allow_green_until_all_deployments_recover(monkeypatch, recovers):
    settings = wildfly_settings()
    checks = [{"unit": "wf.service", "expected": "active", "wildfly": settings}]
    now = [0]
    observations = []
    monkeypatch.setattr(mass_restart, "_probe_restart_unit", lambda *_, **kw: ("state", "active"))

    def probe(*_, timeout):
        assert timeout <= 5
        now[0] += 1
        if now[0] == 1:
            return "connection", "WildFly-Management noch nicht erreichbar."
        state = "OK" if recovers and now[0] >= 3 else "FAILED"
        return "snapshot", WildFlySnapshot({"backend.war": (True, state), "ui.war": (True, state)}, ())

    monkeypatch.setattr(mass_restart, "probe_wildfly_deployments", probe)
    outcome = mass_restart.wait_for_restart_services(None, "ops", checks, None, 5, Event(),
        lambda _, detail: observations.append(detail), lambda: now[0], 0,
        {"wf.service": set(settings["expected"])})
    assert any("noch nicht erreichbar" in detail for detail in observations)
    assert any("0 von 2 Deployments OK" in detail for detail in observations)
    assert "Ist active" in outcome.detail
    assert outcome.status == ("online" if recovers else "error")
    assert ("2 von 2 Deployments OK" if recovers else "backend.war · FAILED") in outcome.detail
