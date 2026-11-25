from copy import deepcopy
import runpy
import subprocess
import sys
from threading import Event

import pytest

from ssh_manager_app.dialogs_restart_templates import RestartTemplatesDialog
from ssh_manager_app.models import Session
from ssh_manager_app.restart_export import render_restart_script
from ssh_manager_app.restart_templates import new_template, resolve_targets, validate_template
from test_restart_templates_ui import app, screenshot


@pytest.fixture
def exported_script(tmp_path):
    def export(*, mode="serial", on_error="continue", common=False, individual=None):
        connections = [Session("one", "Direkt", [], "direct.example.invalid", "ops", 2201, "app"),
                       Session("two", "via-jump", [], "only-in-ssh-config.invalid", "deploy", source="ssh_alias")]
        template = new_template(connections)
        template.update(name="Nächtliche Wartung", mode=mode, on_error=on_error,
                        reboot_timeout=11, service_timeout=7, password_per_connection=individual is not None)
        template["targets"][0]["checks"] = [{"unit": "app.service", "expected": "active"}]
        template["targets"][1]["checks"] = [{"unit": "old.service", "expected": "inactive"}]
        template = validate_template(template, runnable=True)
        script = render_restart_script(template, resolve_targets(template, connections),
                                       common_password_required=common, target_passwords_required=individual or [False, False])
        path = tmp_path / "neustart.py"
        path.write_text(script, encoding="utf-8")
        return path
    return export


def test_standalone_preview_in_isolated_python(exported_script):
    path = exported_script(mode="all_parallel", on_error="pause", individual=[False, True])
    result = subprocess.run([sys.executable, "-I", "-X", "utf8", str(path)], cwd=path.parent,
                            capture_output=True, text=True, encoding="utf-8", timeout=10, check=True)
    assert "Nächtliche Wartung" in result.stdout
    assert "Alle parallel durchstarten · Bei Fehlern: weiterlaufen" in result.stdout
    assert "Neustart/SSH: 11 s · danach Services: 7 s" in result.stdout
    assert "direct.example.invalid · Port 2201 · Benutzer ops) · sudo ohne Passwort" in result.stdout
    assert "Alias via-jump · Benutzer deploy) · sudo Passwortabfrage" in result.stdout
    assert "only-in-ssh-config.invalid" not in result.stdout
    assert "app.service: active" in result.stdout and "old.service: inactive" in result.stdout
    assert "Zum Ausführen --execute angeben" in result.stdout


def load_script(path):
    return runpy.run_path(str(path))["main"].__globals__


def test_execute_confirms_reboot_and_service_states_using_matching_ssh_arguments(exported_script, monkeypatch, capsys):
    script = load_script(exported_script())
    original_monitor = script["monitor_template_restart"]
    monkeypatch.setitem(script, "monitor_template_restart", lambda *args: original_monitor(*args, poll_interval=0))
    monkeypatch.setattr(sys, "argv", ["neustart.py", "--execute"])
    monkeypatch.setattr(script["shutil"], "which", lambda name: name)
    reboots = set()
    calls = []

    def ssh(args, **options):
        calls.append((args, options))
        destination, command = args[-2:]
        if "systemctl" in command:
            state = "active" if "app.service" in command else "inactive"
            return subprocess.CompletedProcess(args, 0, f"LoadState=loaded\nActiveState={state}\n", "")
        if command.startswith("sudo"):
            assert destination not in reboots
            reboots.add(destination)
            return subprocess.CompletedProcess(args, 255, "", "Connection closed")
        boot_id = "22222222" if destination in reboots else "11111111"
        return subprocess.CompletedProcess(args, 0, f"__SSH_MANAGER_CONNECTED__\n{boot_id}-1111-1111-1111-111111111111\n", "")

    monkeypatch.setattr(script["subprocess"], "run", ssh)
    assert script["main"](script["PLAN"], script["TARGETS"]) == 0
    assert reboots == {"ops@direct.example.invalid", "via-jump"}
    assert calls[0][0][-5:-1] == ["-p", "2201", "--", "ops@direct.example.invalid"]
    assert next(args for args, _ in calls if args[-2] == "via-jump")[-5:-1] == ["-l", "deploy", "--", "via-jump"]
    for destination in reboots:
        commands = [args[-1] for args, _ in calls if args[-2] == destination]
        assert len(commands) == 6
        assert commands[0].startswith("systemctl show") and commands[-1] == commands[0]
        assert commands[2] == "sudo -n -p '' reboot"
    output = capsys.readouterr().out
    assert output.count("Boot-ID geändert") == 2
    assert "Soll active, Ist active" in output and "Soll inactive, Ist inactive" in output


def test_invalid_edited_target_blocks_whole_run_before_ssh(exported_script, monkeypatch, capsys):
    script = load_script(exported_script())
    script["TARGETS"][1]["port"] = 2222
    monkeypatch.setattr(sys, "argv", ["neustart.py", "--execute"])
    monkeypatch.setattr(script["shutil"], "which", lambda *_: pytest.fail("Validated after SSH setup"))
    with pytest.raises(SystemExit) as error:
        script["main"](script["PLAN"], script["TARGETS"])
    assert error.value.code == 2
    assert "Port eines SSH-Alias" in capsys.readouterr().err


def test_missing_service_stops_waiting_restarts_and_lists_unchecked_states(exported_script, monkeypatch, capsys):
    script = load_script(exported_script(on_error="stop"))
    monkeypatch.setattr(sys, "argv", ["neustart.py", "--execute"])
    monkeypatch.setattr(script["shutil"], "which", lambda name: name)
    calls = []

    def ssh(args, **_):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "LoadState=not-found\nActiveState=inactive\n", "")

    monkeypatch.setattr(script["subprocess"], "run", ssh)
    assert script["main"](script["PLAN"], script["TARGETS"]) == 1
    assert len(calls) == 1 and calls[0][-1].startswith("systemctl show")
    output = capsys.readouterr().out
    assert "Dienst nicht vorhanden" in output and "Nicht gestartet" in output
    assert "app.service: Soll active, Ist nicht geprüft" in output
    assert "old.service: Soll inactive, Ist nicht geprüft" in output


def test_boot_id_evidence_and_reboot_deadline_in_export(exported_script, monkeypatch):
    script = load_script(exported_script())
    target = script["validate_plan"](script["PLAN"], script["TARGETS"])[0]
    monkeypatch.setitem(script, "_issue_reboot", lambda *_, **__: (True, False, ""))
    probes = iter([(True, "old", ""), (True, "new", ""), (True, None, "")])
    monkeypatch.setitem(script, "_read_boot_id", lambda *_, **__: next(probes))

    result = script["monitor_server_restart"](target, "ops", "", "", 1, Event(), lambda *_: None,
                                              poll_interval_seconds=0, evidence_detail=True)
    assert result.status == "online" and "Boot-ID geändert" in result.detail

    clock = [0]

    class FakeWait(Event):
        def wait(self, seconds):
            clock[0] += seconds
            return False

    monkeypatch.setitem(script, "_read_boot_id", lambda *_, **__: (True, "old", ""))
    result = script["monitor_server_restart"](target, "ops", "", "", 1, FakeWait(), lambda *_: None,
                                              monotonic=lambda: clock[0], evidence_detail=True)
    assert result.status == "timeout" and clock[0] == 1


def test_individual_password_is_prompted_only_for_marked_target_and_redacted_on_error(exported_script, monkeypatch):
    script = load_script(exported_script(individual=[False, True]))
    prompts = []
    secret = " p-übergeben "

    def getpass(prompt):
        prompts.append(prompt)
        return secret

    monkeypatch.setitem(script, "getpass", getpass)
    targets = script["validate_plan"](script["PLAN"], script["TARGETS"])
    assert script["read_passwords"](script["PLAN"], targets) == ["", secret]
    assert len(prompts) == 1 and "via-jump" in prompts[0]

    def remote(session, user, command, **options):
        assert command == "sudo -S -p '' reboot" and options["input_text"] == secret + "\n"
        return subprocess.CompletedProcess([], 1, "", secret)

    monkeypatch.setitem(script, "_run_ssh", remote)
    accepted, uncertain, detail = script["_issue_reboot"](targets[1], "deploy", secret)
    assert (accepted, uncertain, detail) == (False, False, "[ausgeblendet]")


def test_failure_pause_keeps_active_target_running_and_eof_skips_waiting_target(exported_script, monkeypatch):
    script = load_script(exported_script(mode="parallel", on_error="pause"))
    targets = script["validate_plan"](script["PLAN"], script["TARGETS"])
    targets.append(deepcopy(targets[1]))
    targets[2].label = "Wartet"
    release_second = Event()
    second_completed = Event()
    result = script["RestartResult"]

    def restart(target, *args):
        if target.label == "Direkt":
            return result("error", "Vorprüfung fehlgeschlagen")
        assert target.label == "via-jump"
        assert release_second.wait(5)
        second_completed.set()
        return result("online", "Bestätigt")

    def answer(_):
        release_second.set()
        assert second_completed.wait(5)
        raise EOFError

    monkeypatch.setitem(script, "monitor_template_restart", restart)
    monkeypatch.setitem(script, "input", answer)
    results, interrupted = script["run_targets"](script["PLAN"], targets, [""] * 3, 2, "pause")
    assert not interrupted
    assert [results[index].status for index in range(3)] == ["error", "online", "not_started"]


def test_editor_exports_exact_preview_from_unsaved_fields_without_password_payloads(app, monkeypatch, tmp_path):
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    def button(parent, label):
        return next(widget for widget in descendants(parent)
                    if widget.winfo_class() == "TButton" and widget.cget("text") == label)

    app.geometry("600x450+20+20")
    app.update()
    editor = RestartTemplatesDialog(app, app._app_sessions[:1])
    app.update()
    name = "Noch nicht gespeichert – hier steht ein bewusst längerer Vorlagenname für die schmale Skriptvorschau"
    editor.name.set(name)
    editor.options["reboot_timeout"].set("45")
    editor.rows[0][0].set("deploy")
    editor.rows[0][1].add("app.service", "inactive")
    editor.password_per_connection.set(True)
    field = editor.password_fields[0]
    field._sealed, field._unreadable, field._edited = "dpapi-SYNTHETISCH", True, False
    editor.common_password.set("keinesfalls-im-export")
    monkeypatch.setattr("ssh_manager_app.dialogs_restart_templates.seal", lambda *_: pytest.fail("Export called DPAPI"))
    output = tmp_path / "neustart.py"
    monkeypatch.setattr("ssh_manager_app.file_picker.asksaveasfilename", lambda **_: str(output))
    observed = []

    def inspect_preview(preview):
        app.update()
        assert preview.grab_current() is None
        assert not preview.transient()
        save_button = button(preview, "Python-Datei speichern…")
        assert save_button.winfo_ismapped() and save_button.winfo_width() >= save_button.winfo_reqwidth()
        title = next(widget for widget in descendants(preview)
                     if widget.winfo_class() == "TLabel" and widget.cget("text") == name)
        assert int(title.cget("wraplength")) == title.winfo_width()
        observed.append(preview.text.get("1.0", "end-1c"))
        editor.name.set("Bearbeitung nach Vorschau")
        screenshot(preview, "restart-script-export.png")
        save_button.invoke()

    monkeypatch.setattr(editor, "wait_window", inspect_preview)
    for label in ("Dienststatus prüfen", "Speichern…", "Vorschau und starten…", "Als Skript exportieren…"):
        action = button(editor.editor, label)
        assert action.winfo_ismapped() and action.winfo_width() >= action.winfo_reqwidth()
    button(editor.editor, "Als Skript exportieren…").invoke()
    assert output.read_text(encoding="utf-8") == observed[0]
    assert app._initial_toolbar_search_texts == {}
    assert field._sealed == "dpapi-SYNTHETISCH"
    assert "dpapi-SYNTHETISCH" not in observed[0] and "keinesfalls-im-export" not in observed[0]
    script = load_script(output)
    assert script["PLAN"]["name"] == name
    assert script["PLAN"]["reboot_timeout"] == 45
    assert script["TARGETS"][0]["user"] == "deploy"
    assert script["TARGETS"][0]["services"] == {"app.service": "inactive"}
    assert script["TARGETS"][0]["sudo_password_required"] is True
