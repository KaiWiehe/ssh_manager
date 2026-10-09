from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


POWERSHELL = shutil.which("powershell.exe")
pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not POWERSHELL,
    reason="Windows PowerShell build integration tests",
)
BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_windows.ps1"
STEPS = [
    ["--version"],
    ["scripts\\bump_version.py", "--check"],
    ["-m", "pip", "install", "-r", "requirements-dev.txt"],
    ["-m", "PyInstaller", "--clean", "--noconfirm", "ssh_manager.spec"],
]


@pytest.fixture
def build_sandbox(tmp_path):
    root = tmp_path / "repo with spaces"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(BUILD_SCRIPT, root / "scripts" / "build_windows.ps1")
    for directory in ("build", "dist"):
        (root / directory).mkdir()
        (root / directory / "old-output").write_text("previous build")
    (root / "dist" / "SSH Manager.exe").write_bytes(b"old exe")
    binaries = tmp_path / "fake bin"
    binaries.mkdir()
    driver = binaries / "driver.py"
    driver.write_text(
        '''import json, os, sys
from pathlib import Path
root = Path.cwd()
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
step = ("python" if args == ["--version"] else
        "version" if "--check" in args else
        "pip" if "pip" in args else "pyinstaller")
if step == "pyinstaller":
    assert not (root / "build").exists()
    assert not (root / "dist").exists()
    mode = os.environ.get("EXE_MODE", "valid")
    if mode != "missing":
        (root / "dist").mkdir()
        (root / "dist" / "SSH Manager.exe").write_bytes(
            b"new exe" if mode == "valid" else b"")
print("fake " + step)
sys.exit(23 if os.environ.get("FAIL_STEP") == step else 0)
''',
        encoding="utf-8",
    )
    (binaries / "python.cmd").write_text(
        f'@echo off\n"{sys.executable}" "{driver}" %*\nexit /b %errorlevel%\n',
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PATH"] = str(binaries) + os.pathsep + env["PATH"]
    env.pop("FAIL_STEP", None)
    env.pop("EXE_MODE", None)
    return root, env


def run_build(root, env):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(root / "scripts" / "build_windows.ps1")],
        cwd=root.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def calls(root):
    return [json.loads(line) for line in (root / "calls.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("step,index", [("python", 0), ("version", 1), ("pip", 2)])
def test_preflight_failure_preserves_outputs(build_sandbox, step, index):
    root, env = build_sandbox
    env["FAIL_STEP"] = step
    result = run_build(root, env)
    assert result.returncode != 0
    assert calls(root) == STEPS[:index + 1]
    assert "exit code 23" in result.stderr
    assert "Fertig:" not in result.stdout
    assert (root / "build" / "old-output").exists()
    assert (root / "dist" / "SSH Manager.exe").read_bytes() == b"old exe"


def test_cleanup_failure_stops_before_pyinstaller(build_sandbox):
    root, env = build_sandbox
    locked_file = root / "build" / "old-output"
    # Windows open handles without delete sharing block Remove-Item even with -Force.
    with locked_file.open("rb"):
        result = run_build(root, env)
    assert result.returncode != 0
    assert calls(root) == STEPS[:3]
    assert "Fertig:" not in result.stdout
    assert (root / "dist" / "SSH Manager.exe").read_bytes() == b"old exe"


def test_pyinstaller_failure_rejects_created_exe(build_sandbox):
    root, env = build_sandbox
    env["FAIL_STEP"] = "pyinstaller"
    result = run_build(root, env)
    assert result.returncode != 0
    assert calls(root) == STEPS
    assert "exit code 23" in result.stderr
    assert "Fertig:" not in result.stdout
    assert (root / "dist" / "SSH Manager.exe").read_bytes() == b"new exe"


@pytest.mark.parametrize("mode", ["missing", "empty"])
def test_successful_pyinstaller_requires_nonempty_exe(build_sandbox, mode):
    root, env = build_sandbox
    env["EXE_MODE"] = mode
    result = run_build(root, env)
    assert result.returncode != 0
    assert calls(root) == STEPS
    assert "Fertig:" not in result.stdout


@pytest.mark.parametrize("old_outputs", [True, False])
def test_success_reports_only_current_build(build_sandbox, old_outputs):
    root, env = build_sandbox
    if not old_outputs:
        shutil.rmtree(root / "build")
        shutil.rmtree(root / "dist")
    result = run_build(root, env)
    assert result.returncode == 0, result.stderr
    assert calls(root) == STEPS
    assert result.stdout.count("Fertig:") == 1
    assert (root / "dist" / "SSH Manager.exe").read_bytes() == b"new exe"
    assert not (root / "dist" / "old-output").exists()


def test_unstartable_interpreter_aborts_before_cleanup(build_sandbox):
    root, env = build_sandbox
    interpreter = root / ".venv" / "Scripts" / "python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"invalid executable")
    result = run_build(root, env)
    assert result.returncode != 0
    assert "could not run" in result.stderr
    assert not (root / "calls.jsonl").exists()
    assert "Fertig:" not in result.stdout
    assert (root / "dist" / "SSH Manager.exe").read_bytes() == b"old exe"
