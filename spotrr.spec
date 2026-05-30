# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SpotRR — Windows · macOS · Linux
# Build: pyinstaller spotrr.spec

import os, sys
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

spotdl_data = collect_data_files('spotdl')

# FFmpeg is bundled only on Windows (assets/ffmpeg.exe must exist at build time).
# On macOS/Linux spotdl downloads it automatically on first launch.
_binaries = []
if sys.platform == 'win32' and os.path.exists('assets/ffmpeg.exe'):
    _binaries = [('assets/ffmpeg.exe', 'assets')]

# settings.json is optional — create a blank one if missing so the build doesn't fail.
if not os.path.exists('settings.json'):
    with open('settings.json', 'w') as _f:
        _f.write('{"client_id":"","client_secret":"","default_output_folder":""}')

# Icon: .icns for macOS, .ico for Windows/Linux
_icon = (
    'assets/icon.icns' if sys.platform == 'darwin' and os.path.exists('assets/icon.icns')
    else 'assets/icon.ico'
)

# Runtime hook (CREATE_NO_WINDOW) is Windows-only
_runtime_hooks = ['rthook_no_console.py'] if sys.platform == 'win32' else []

a = Analysis(
    ['spotrr.py'],
    pathex=[],
    binaries=_binaries,
    datas=[
        ('assets', 'assets'),
        ('settings.json', '.'),
        *spotdl_data,
    ],
    hiddenimports=[
        'tkinter', 'tkinter.filedialog', 'tkinter.messagebox',
        'tkinter.ttk', 'tkinter.simpledialog', 'tkinter.scrolledtext',
        'tkinter.font',
        'PIL', 'PIL.Image', 'PIL.ImageTk',
        'spotipy', 'spotipy.oauth2',
        'spotdl',
        'mutagen', 'rapidfuzz',
        'qrcode', 'qrcode.image.pil',
        'tkinterdnd2',
        'requests', 'tqdm',
        'certifi', 'urllib3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=_runtime_hooks,
    excludes=['matplotlib', 'numpy', 'scipy', 'pandas', 'jupyter'],
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
    name='SpotRR',
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
    icon=_icon,
    version_file=None,
)

# macOS: wrap the EXE inside a proper .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='SpotRR.app',
        icon=_icon,
        bundle_identifier='com.spotrr.app',
        info_plist={
            'CFBundleShortVersionString': '2.1.0',
            'CFBundleVersion':            '2.1.0',
            'NSHighResolutionCapable':    True,
        },
    )
