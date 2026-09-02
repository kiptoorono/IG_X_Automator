# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

u2_datas = collect_data_files('uiautomator2')
all_datas = [('DEepseek/config.py', 'DEepseek'), ('DEepseek/adb_bundle.py', 'DEepseek')] + u2_datas

a = Analysis(
    ['DEepseek/Main_Launcher_pro.py'],
    pathex=['C:/Users/Rono/Desktop/IG Automator'],
    binaries=[('C:/Users/Rono/Desktop/IG Automator/platform-tools', 'platform-tools')],
    datas=all_datas,
    hiddenimports=['selenium', 'webdriver_manager', 'pyfiglet', 'uiautomator2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='IG_Automator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
