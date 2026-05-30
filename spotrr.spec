# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for SpotRR
# Build: pyinstaller spotrr.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect data files for spotdl
spotdl_data = collect_data_files('spotdl')

a = Analysis(
    ['spotrr.py'],
    pathex=[],
    binaries=[
        ('assets/ffmpeg.exe', 'assets'),
    ],
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
    runtime_hooks=['rthook_no_console.py'],
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
    icon='assets/icon.ico',
    version_file=None,
)
