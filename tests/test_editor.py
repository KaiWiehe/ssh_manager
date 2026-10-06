import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch
import pytest
from ssh_manager_app.editor import open_in_vscode


def test_missing_editor_reports_error_before_start(tmp_path):
    with patch("ssh_manager_app.editor.shutil.which", return_value=None), patch("ssh_manager_app.editor.subprocess.Popen") as start:
        with pytest.raises(FileNotFoundError):
            open_in_vscode(tmp_path)
    start.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows batch launcher")
def test_batch_launcher_preserves_special_characters_without_shell_injection(tmp_path):
    directory = tmp_path / "code directory"
    directory.mkdir()
    output = tmp_path / "arguments.json"
    helper = directory / "capture.py"
    helper.write_text("import sys,json; from pathlib import Path; Path(" + repr(str(output)) + ").write_text(json.dumps(sys.argv[1:]))")
    launcher = directory / "code.cmd"
    launcher.write_text('@echo off\n"' + sys.executable + '" "' + str(helper) + '" %*\n')
    target = tmp_path / "name %USERNAME% & ü; test.txt"
    with patch("ssh_manager_app.editor.shutil.which", return_value=str(launcher)):
        open_in_vscode(target)
    end = time.monotonic() + 5
    while not output.exists() and time.monotonic() < end:
        time.sleep(.05)
    assert json.loads(output.read_text()) == [str(target)]


def test_standard_code_cmd_uses_installation_binary(tmp_path):
    directory = tmp_path / "bin"
    directory.mkdir()
    launcher = directory / "code.cmd"
    binary = tmp_path / "Code.exe"
    binary.touch()
    with patch("ssh_manager_app.editor.shutil.which", return_value=str(launcher)), patch("ssh_manager_app.editor.subprocess.Popen") as start:
        open_in_vscode(tmp_path / "config")
    assert start.call_args.args[0] == [str(binary), str(tmp_path / "config")]
    assert start.call_args.kwargs["shell"] is False
