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


def test_context_exports_use_folder_or_exact_checked_selection(app, tmp_path):
    import tkinter as tk
    from test_action_menus import setup_hosts, invoke
    from ssh_manager_app.actions_app import export_visible_sessions, copy_visible_sessions_as_markdown
    from types import SimpleNamespace
    a, b, ids = setup_hosts(app)
    app._tree.set_all_checked(True)
    menus = []
    with patch.object(tk.Menu, 'tk_popup', autospec=True, side_effect=lambda menu, *args: menus.append(menu)):
        app._tree._show_session_menu(ids[a.key], x_root=0, y_root=0)
    with patch('ssh_manager_app.actions_app.export_visible_sessions') as export:
        invoke(menus[-1], 'Auswahl als CSV exportieren…')
    assert {s.key for s in export.call_args.args[2]} == {'a', 'b'}
    with patch('ssh_manager_app.actions_app.ToastNotification'):
        copy_visible_sessions_as_markdown(app, [a])
    assert a.hostname in app.clipboard_get()
    assert b.hostname not in app.clipboard_get()
    path = tmp_path / 'folder.csv'
    dialog = SimpleNamespace(result=['display_name', 'hostname'], scope='all', excel_safe=True)
    with patch('ssh_manager_app.actions_app.ExportColumnsDialog', return_value=dialog) as columns, patch.object(app, 'wait_window'), patch('ssh_manager_app.actions_app.filedialog.asksaveasfilename', return_value=str(path)), patch('ssh_manager_app.actions_app.ToastNotification'):
        export_visible_sessions(app, 'csv', [a])
    assert columns.call_args.kwargs['scope_counts'] == {'context': 1}
    assert a.hostname in path.read_text(encoding='utf-8-sig')
    assert b.hostname not in path.read_text(encoding='utf-8-sig')

