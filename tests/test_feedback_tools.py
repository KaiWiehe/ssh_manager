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


def test_toolbar_individual_actions_preview_execute_and_persist(app, tmp_path):
    from test_action_menus import setup_hosts
    from ssh_manager_app.storage import save_settings, load_settings_from_path
    setup_hosts(app)
    catalog = app._extra_toolbar_catalog
    expected = ['Verbindung diagnostizieren…', 'Lokales Skript ausführen…', 'Serverskript ausführen…',
                'Dienststatus anzeigen…', 'Dienst neu starten…', 'Dienstlogs anzeigen…', 'Datei hochladen…', 'Runbook-Bibliothek…']
    labels = [label for label, _ in catalog.values()]
    assert all(any(label.endswith(' → ' + action) for label in labels) for action in expected)
    key = next(key for key, (label, _) in catalog.items() if label == 'Aktionen → Dienststatus anzeigen…')
    view = app._settings_view
    view._extra_toolbar_vars[key].set(True)
    view._on_toolbar_changed()
    assert key in app.settings.toolbar.extra_actions
    with patch('ssh_manager_app.services.run_service_action') as service:
        app._toolbar_buttons[key].invoke()
    assert service.call_args.args[2] == 'status'
    path = tmp_path / 'settings.json'
    with patch('ssh_manager_app.storage._SETTINGS_FILE', path):
        save_settings(view._collect_settings())
    assert key in load_settings_from_path(path).toolbar.extra_actions


def test_editable_tunnel_and_service_presets_roundtrip_and_dialogs(app, tmp_path):
    from ssh_manager_app.storage import save_settings, load_settings_from_path
    from ssh_manager_app.dialogs_remote import SshTunnelDialog
    from ssh_manager_app.services import ServiceActionDialog
    view = app._settings_view
    view._tunnel_presets_text.delete('1.0', 'end')
    view._tunnel_presets_text.insert('1.0', 'Redis | 16379 | 6379')
    view._service_presets_text.delete('1.0', 'end')
    view._service_presets_text.insert('1.0', 'redis.service\ncustom@one.service')
    settings = view._collect_settings()
    path = tmp_path / 'settings.json'
    with patch('ssh_manager_app.storage._SETTINGS_FILE', path):
        save_settings(settings)
    app.settings = load_settings_from_path(path)
    assert app.settings.service_presets == ['redis.service', 'custom@one.service']
    dialog = SshTunnelDialog(app)
    dialog._port_preset.set('Redis')
    dialog._apply_tunnel_preset()
    assert (dialog._local_port_var.get(), dialog._remote_port_var.get()) == ('16379', '6379')
    dialog.destroy()
    dialog = ServiceActionDialog(app, 'status', 1)
    def combos(widget):
        for child in widget.winfo_children():
            if child.winfo_class() == 'TCombobox':
                yield child
            yield from combos(child)
    assert any(tuple(combo.cget('values')) == ('redis.service', 'custom@one.service') for combo in combos(dialog))
    dialog.destroy()


@pytest.mark.parametrize('text', ['Bad | 0 | 80', 'Same | 1 | 2\nSame | 3 | 4', 'Missing fields', 'Bad | 22 | 65536'])
def test_tunnel_settings_reject_invalid_or_duplicate_presets(text):
    from ssh_manager_app.tool_presets import parse_tunnels
    with pytest.raises(ValueError):
        parse_tunnels(text)


def test_folder_export_callbacks_capture_descendants_not_other_checked_hosts(app):
    import tkinter as tk
    from test_action_menus import setup_hosts, invoke
    a, b, _ = setup_hosts(app)
    descendant = Session('c', 'Child', ['Folder', 'Nested'], 'c.invalid', 'ops', source='app')
    app._tree.refresh([a, b, descendant])
    app._tree.set_all_checked(True)
    folder = next(iid for iid, name in app._tree._item_to_folder_key.items() if name == 'Folder')
    menu = app._tree._show_folder_menu(folder, return_menu=True)
    app._tree.set_all_checked(False)
    with patch('ssh_manager_app.actions_app.export_visible_sessions') as export:
        invoke(menu, 'Ordner als Excel exportieren…')
    assert {s.key for s in export.call_args.args[2]} == {'a', 'c'}
    assert export.call_args.args[1] == 'xlsx'


def test_invalid_saved_presets_fall_back_and_empty_lists_stay_empty(tmp_path):
    import json
    from ssh_manager_app.storage import load_settings_from_path
    path = tmp_path / 'settings.json'
    path.write_text(json.dumps({'tunnel_presets': [{'name': 'Bad', 'local': 0, 'remote': 1}], 'service_presets': ['bad; command']}), encoding='utf-8')
    settings = load_settings_from_path(path)
    assert settings.tunnel_presets[0]['name'] == 'PostgreSQL'
    assert settings.service_presets[0] == 'nginx.service'
    path.write_text(json.dumps({'tunnel_presets': [], 'service_presets': []}), encoding='utf-8')
    settings = load_settings_from_path(path)
    assert settings.tunnel_presets == settings.service_presets == []


def test_real_certificate_replace_dialog_opens_and_cancel_preserves_whitelist(app):
    from ssh_manager_app.dialogs_certificate_replace import CertificateReplaceDialog
    changed = []
    dialog = CertificateReplaceDialog(app, 1, ['/etc/ssl'], [], changed.append)
    app.update()
    assert dialog._context_help_button.winfo_exists()
    assert dialog._roots.get('1.0', 'end').strip() == '/etc/ssl'
    dialog._cancel()
    app.update()
    assert dialog.result is None
    assert changed == []

