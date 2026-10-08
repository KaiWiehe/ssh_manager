import shlex
import subprocess
from unittest.mock import patch

import pytest
from test_help import app
from ssh_manager_app.models import Session


@pytest.mark.parametrize('count', [1, 3])
def test_real_dns_input_and_result_dialogs_use_grid_without_conflicts(app, count):
    from ssh_manager_app.dialogs_dns import DnsLookupDialog, DnsServerDialog, DnsLookupResultsDialog
    from ssh_manager_app.dns_lookup import DnsLookupResult
    for dialog in (DnsLookupDialog(app), DnsServerDialog(app, count)):
        app.update()
        assert dialog._context_help_button.master.winfo_manager() == 'grid'
        dialog.destroy()
    result = DnsLookupResult(query='example.invalid', mode='forward', results=['127.0.0.1'], resolver='system', status='ok')
    dialog = DnsLookupResultsDialog(app, [result] * count)
    app.update()
    assert dialog._context_help_button.master.grid_info()['row'] == 3
    dialog.destroy()


@pytest.mark.parametrize('action', ['status', 'restart', 'logs'])
def test_service_ssh_options_precede_target_and_remote_shell_receives_stdin(tmp_path, action):
    from ssh_manager_app import core
    from ssh_manager_app.services import service_command
    captured = []
    session = Session('test', 'Test', [], 'example.invalid', 'ops')
    with patch.object(core, '_write_temp_bash_script', side_effect=lambda prefix, content: captured.append(content) or 'dummy.sh'):
        core.build_remote_command_wt_command([(session, 'ops', service_command(action, 'nginx'))], close_on_success=False)
    # Simulate SSH's -- boundary and remote-shell execution, using real Git Bash.
    fake = '''ssh() {
      while [ "$1" != -- ]; do shift; done
      shift; shift
      if [ "$#" = 0 ]; then return 0; fi
      if [ "$1" != 'bash -s' ]; then echo BAD_REMOTE_COMMAND; return 19; fi
      bash -s
    }
    systemctl() { if [ "$1" = show ]; then echo loaded; fi; return 0; }
    journalctl() { return 0; }
    export -f systemctl journalctl
    '''
    script = tmp_path / 'local.sh'
    script.write_text(fake + captured[0].replace('exec ssh', 'ssh'), encoding='utf-8', newline='\n')
    result = subprocess.run([core._find_git_bash(), str(script)], input='\n', capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'BAD_REMOTE_COMMAND' not in result.stdout
    assert "ssh -t -- ops@example.invalid 'bash -s'" in captured[0]

