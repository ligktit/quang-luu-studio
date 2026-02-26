# -*- mode: python ; coding: utf-8 -*-

import os
import customtkinter

ctk_path = os.path.dirname(customtkinter.__file__)

# LOẠI BỎ CÁC THƯ VIỆN NẶNG KHÔNG DÙNG ĐẾN
excluded_modules = [
    'matplotlib',
    'notebook',
    'IPython',
    'jedi',
    'sqlite3',
    'unittest',
    'test',
    'PIL',
    'tkinter.test',
    'scipy.spatial.tests',
    'librosa.display', # Thường kéo theo matplotlib
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[], # Để trống, ta sẽ không nén ffmpeg vào trong EXE
    datas=[
        (ctk_path, 'customtkinter'),
        ('activation.json', '.'),
        ('activation_codes.txt', '.'),
        ('saved_songs.json', '.'),
        ('manual_timelines.json', '.'),
    ],
    hiddenimports=[
        'rtmidi',
        'mido.backends.rtmidi',
        'mido.backends.rtmidi.backend',
        'librosa',
        'soundcard',
        'yt_dlp',
        'sklearn.utils._typedefs',
        'sklearn.utils._heap',
        'sklearn.utils._sorting',
        'sklearn.neighbors._partition_nodes',
        'sklearn.neighbors._quad_tree',
        'sklearn.tree._utils',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LiveStudio_Lite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True, # Dùng UPX nén mạnh
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
