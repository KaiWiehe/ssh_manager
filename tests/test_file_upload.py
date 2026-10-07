import re
import subprocess
from unittest.mock import patch

import pytest

from ssh_manager_app.core import build_file_upload_wt_command, _find_git_bash
from ssh_manager_app.models import Session


def _git_path(path):
    text = str(path.resolve()).replace("\\", "/")
    return "/" + text[0].lower() + text[2:]


@pytest.mark.parametrize("overwrite", [False, True])
def test_upload_installer_never_clobbers_without_permission(tmp_path, overwrite):
    source = tmp_path / "file.txt"
    source.write_text("new")
    destination = tmp_path / "destination"
    destination.mkdir()
    target = destination / "file.txt"
    target.write_text("old")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "file").write_text("new")
    scripts = []
    spec = {"files": [str(source)], "target_dirs": [_git_path(destination)], "overwrite": overwrite}
    with patch("ssh_manager_app.core._write_temp_bash_script", side_effect=lambda prefix, text: scripts.append(text) or "test.sh"):
        build_file_upload_wt_command([(Session("x", "Test", [], "test.invalid"), "ops", spec)])
    script = scripts[0]
    assert "sudo " not in script
    remote_dir = re.search(r"/tmp/ssh-manager-upload-[a-f0-9]+", script).group()
    body = re.search(r"<<'([^']+)'\n(.*?)\n\1", script, re.S).group(2)
    body = body.replace(remote_dir, _git_path(staging))
    completed = subprocess.run([_find_git_bash(), "-c", body], capture_output=True, text=True, timeout=10)
    assert (completed.returncode == 0) == overwrite
    assert target.read_text() == ("new" if overwrite else "old")
    assert not list(destination.glob(".ssh-manager-*"))


def test_upload_builder_rejects_multiple_hosts():
    with pytest.raises(ValueError):
        build_file_upload_wt_command([None, None])
