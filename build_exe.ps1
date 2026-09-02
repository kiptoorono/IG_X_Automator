$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script = Join-Path $root 'DEepseek\Main_Launcher_pro.py'
$output = Join-Path $root 'dist'
$spec = Join-Path $root 'build_spec.spec'
$pythonExe = "C:\Users\Rono\AppData\Local\Microsoft\WindowsApps\python3.11.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
}

if (-not $pythonExe) {
    $pythonExe = "python"
}

if (-not (Test-Path $script)) {
    Write-Error "Launcher script not found: $script"
    exit 1
}

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    Write-Host 'Installing PyInstaller into the global Python environment...'
    & $pythonExe -m pip install --upgrade pyinstaller
}

$platformTools = Join-Path $root 'platform-tools'
if (-not (Test-Path $platformTools)) {
    Write-Error "platform-tools folder not found: $platformTools"
    exit 1
}

$escapedRoot = $root -replace '\\', '/'
$escapedPlatformTools = $platformTools -replace '\\', '/'
$specContent = @"
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

u2_datas = collect_data_files('uiautomator2')
all_datas = [('DEepseek/config.py', 'DEepseek'), ('DEepseek/adb_bundle.py', 'DEepseek')] + u2_datas

a = Analysis(
    ['DEepseek/Main_Launcher_pro.py'],
    pathex=['$escapedRoot'],
    binaries=[('$escapedPlatformTools', 'platform-tools')],
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
"@

Set-Content -Path $spec -Value $specContent -Encoding UTF8

& $pythonExe -m PyInstaller --clean --noconfirm $spec

$exePath = Join-Path $output 'IG_Automator.exe'
$zipPath = Join-Path $output 'IG_Automator_windows.zip'

if (Test-Path $exePath) {
    if (Test-Path $zipPath) {
        Remove-Item $zipPath -Force
    }
    Compress-Archive -Path $exePath, $platformTools -DestinationPath $zipPath -Force
}

Write-Host "Build finished. Output folder: $output"
Write-Host "Distribution ZIP: $zipPath"
