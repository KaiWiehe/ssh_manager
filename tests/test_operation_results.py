from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest

from ssh_manager_app.models import Session
from ssh_manager_app.operation_results import OperationJob, track_results, result_statement
from ssh_manager_app import core


def target(key="a"):
    return Session(key, key, [], "dummy.invalid", "ops", source="app")


def test_results_require_receipts_and_retry_excludes_success_unknown(tmp_path):
    a, b, c = target("a"), target("b"), target("c")
    job = OperationJob([a, b, c], "Test", directory=tmp_path)
    job.launched()
    assert all(state[0] == "started" for state in job.poll().values())
    job.paths[a.key].write_text("exit\t0\n")
    job.paths[b.key].write_text("exit\t7\n")
    job.paths[c.key].write_text("exit\t999\n")
    assert job.poll()[a.key] == ("success", "Exit-Code 0")
    assert job.failed_sessions() == [b]
    job.started_at -= 100
    job.paths[c.key].unlink()
    assert job.poll()[c.key][0] == "unknown"


def test_partial_launch_is_uncertain_until_script_confirms(tmp_path):
    job = OperationJob([target()], "Test", directory=tmp_path)
    job.uncertain_launch()
    assert job.failed_sessions() == []
    job.paths["a"].write_text("running\t-\n")
    assert job.poll()["a"][0] == "running"
    job.paths["a"].write_text("exit\t0\n")
    job.poll()
    job.paths["a"].write_text("running\t-\n")
    assert job.poll()["a"][0] == "success"


@pytest.mark.parametrize("exit_code", [0, 7])
def test_real_local_bash_reports_remote_exit_before_terminal_followup(tmp_path, exit_code):
    bash = core._find_git_bash()
    session = target()
    job = OperationJob([session], "Test", directory=tmp_path)
    captured = []
    with track_results(job), patch.object(core, "_build_ssh_command", return_value=f"bash -c 'exit {exit_code}'"), patch.object(core, "_write_temp_bash_script", side_effect=lambda prefix, content: captured.append(content) or "dummy.sh"):
        core.build_remote_command_wt_command([(session, "ops", "true")], close_on_success=True)
    script = tmp_path / "run.sh"
    script.write_text(captured[0], encoding="utf-8", newline="\n")
    result = subprocess.run([bash, str(script)], input="\n", text=True, capture_output=True, timeout=10)
    assert result.returncode == exit_code
    assert job.poll()["a"][0] == ("success" if exit_code == 0 else "failed")
    assert captured[0].index("'exit' $status") < captured[0].index("if [ $status -ne 0 ]; then read")
    assert result_statement(session) == ":"  # Context cannot leak into later builds.


def test_local_script_early_upload_setup_failure_has_receipt(tmp_path):
    session = target()
    job = OperationJob([session], "Test", directory=tmp_path)
    captured = []
    spec = {"mode": "local_script", "local_path": "dummy.sh", "interpreter": "bash"}
    with track_results(job), patch.object(core, "_build_ssh_command", return_value="bash -c 'exit 7'"), patch.object(core, "_write_temp_bash_script", side_effect=lambda prefix, content: captured.append(content) or "dummy.sh"):
        core.build_remote_script_wt_command([(session, "ops", spec)], close_on_success=True)
    script = tmp_path / "run.sh"
    script.write_text(captured[0], encoding="utf-8", newline="\n")
    result = subprocess.run([core._find_git_bash(), str(script)], text=True, capture_output=True, timeout=10)
    assert result.returncode == 1
    assert job.poll()["a"] == ("failed", "Exit-Code 1")


def test_simple_upload_exit_trap_preserves_actual_failure_code(tmp_path):
    session = target()
    job = OperationJob([session], "Test", directory=tmp_path)
    captured = []
    source = tmp_path / "data.txt"
    source.write_text("data")
    spec = {"files": [str(source)], "target_dirs": ["/home/ops"], "overwrite": False, "close_on_success": True}
    with track_results(job), patch.object(core, "_private_upload_start", return_value=["cleanup_upload() { :; }"]), patch.object(core, "_write_temp_bash_script", side_effect=lambda prefix, content: captured.append(content) or "dummy.sh"):
        core.build_file_upload_wt_command([(session, "ops", spec)])
    # Replace only local SCP with a deterministic failure. No SSH is executed.
    lines = captured[0].splitlines()
    lines[next(i for i, line in enumerate(lines) if line.startswith("scp "))] = "false"
    script = tmp_path / "run.sh"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    result = subprocess.run([core._find_git_bash(), str(script)], input="\n", text=True, capture_output=True, timeout=10)
    assert result.returncode == 1
    assert job.poll()["a"] == ("failed", "Exit-Code 1")
