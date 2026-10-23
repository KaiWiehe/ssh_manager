# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = Path(SPECPATH)
PACKAGE_DATA = (
    collect_data_files('ttkbootstrap')
    + copy_metadata('ttkbootstrap')
    + copy_metadata('Pillow')
)


a = Analysis(
    ['ssh_manager.py'],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'assets' / 'ssh-manager.ico'), 'assets'),
        (str(ROOT / 'assets' / 'ssh-manager.png'), 'assets'),
    ] + PACKAGE_DATA,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SSH Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'assets' / 'ssh-manager.ico'),
    version=str(ROOT / 'packaging' / 'ssh_manager_version_info.txt'),
)

# A genuine console executable is required for inherited stdin/stdout and SSH.
# Keep the GUI's windowed bootloader above unchanged.
cli = Analysis(
    ['sshm.py'], pathex=[str(ROOT)], binaries=[],
    datas=copy_metadata('prompt_toolkit') + copy_metadata('wcwidth'),
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=[], noarchive=False,
)
cli_pyz = PYZ(cli.pure)
cli_exe = EXE(
    cli_pyz, cli.scripts, cli.binaries, cli.datas, [],
    name='sshm', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, upx_exclude=[], runtime_tmpdir=None,
    console=True, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
    icon=str(ROOT / 'assets' / 'ssh-manager.ico'),
    version=str(ROOT / 'packaging' / 'ssh_manager_version_info.txt'),
)
