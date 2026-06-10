# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

import os

# ── Data files: program-level config + workers + asset folders ──
# NOTE: User data files (settings.json, saved_songs.json, tone_cache.json,
#       activation.json, manual_timelines.json) are NO LONGER bundled here.
#       They are created at runtime in %APPDATA%\QuangLuuStudio\.
datas = [
    ('app_config.json', '.'),
    ('recorder_worker.py', '.'),
    ('core', 'core'),
    ('tools', 'tools'),           # <-- Sửa lỗi shortcut & CDP
    ('sfx', 'sfx'),
    ('studio_one', 'studio_one'),
    ('Be_Vietnam_Pro', 'Be_Vietnam_Pro'),
    ('ui/styles', 'ui/styles'),   # QSS stylesheet
]

# Chỉ thêm file tồn tại (tránh lỗi build khi thiếu file optional)
datas = [(src, dst) for src, dst in datas if os.path.exists(src)]

binaries = []

# ── Hidden imports: tất cả package/module cần thiết ──
hiddenimports = [
    # MIDI
    'rtmidi', 'mido.backends.rtmidi',
    # Audio analysis
    'librosa', 'scipy', 'scipy.signal', 'numpy',
    # YouTube
    'yt_dlp',
    # Audio recording
    'pyaudiowpatch',
    # UI Automation (YT Watcher)
    'uiautomation',
    # System monitoring
    'psutil', 'pyautogui',
    # Win32 API
    'win32gui', 'win32con', 'win32process',
    # WinRT (Windows Media Monitor)
    'winrt.windows.media.control',
    'winrt.windows.foundation',
    # Audio device (pycaw)
    'pycaw',
    # WebSocket (CDP connectivity)
    'websocket',
    # Qt Multimedia
    'PySide6.QtMultimedia',
    # UI dialogs — lazily imported inside stub methods; static analysis may miss them
    'ui.dialogs.settings_dialog',
    'ui.dialogs.calibration',
    'ui.dialogs.scoring_report',
    'ui.dialogs.songs_list',
    'ui.dialogs.edit_song',
    # UI panels — new package extracted from frontend_qt.py (Phase C)
    'ui.panels',
    'ui.panels.header',
    'ui.panels.mixer',
    'ui.panels.tools',
    'ui.panels.mode',
    'ui.panels.bottom_bar',
    # sklearn internals (required by librosa)
    'sklearn.utils._typedefs',
    'sklearn.utils._heap',
    'sklearn.utils._sorting',
    'sklearn.neighbors._partition_nodes',
    'sklearn.neighbors._quad_tree',
    'sklearn.tree._utils',
]

# ── PySide6: chỉ bundle modules cần thiết (QtWidgets/QtCore/QtGui) ──
# Exclude modules nặng không cần — giảm ~250MB (Qt6WebEngineCore = 192MB, Qt3D, QtQuick, etc.)
_qt_excludes = [
    'PySide6.QtWebEngine', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
    'PySide6.QtQuick', 'PySide6.QtQuickWidgets', 'PySide6.QtQuickControls2',
    'PySide6.QtQml', 'PySide6.QtQmlModels',
    'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
    'PySide6.QtDesigner',
    'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
    'PySide6.QtBluetooth', 'PySide6.QtNfc',
    'PySide6.QtRemoteObjects', 'PySide6.QtSensors', 'PySide6.QtSerialPort',
    'PySide6.QtTest', 'PySide6.QtSql',
    # PySide6.QtSvg và PySide6.QtSvgWidgets KHÔNG exclude — cần cho QSvgRenderer (icon buttons)
    'PySide6.QtXml', 'PySide6.QtHelp',
    'PySide6.QtCharts', 'PySide6.QtDataVisualization',
    'PySide6.QtNetworkAuth', 'PySide6.QtPositioning',
    'PySide6.QtSpatialAudio', 'PySide6.QtStateMachine',
    'PySide6.QtTextToSpeech', 'PySide6.QtHttpServer',
    'PySide6.QtWebSockets', 'PySide6.QtWebChannel',
    'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
    'PySide6.QtScxml',
]

tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('shiboken6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Lọc bỏ binaries/datas của modules không cần (theo tên file DLL/pyd)
_exclude_dlls = [
    'Qt6WebEngine', 'Qt6Quick', 'Qt6Qml', 'Qt63D', 'Qt6Designer',
    'Qt6Pdf', 'Qt6Bluetooth', 'Qt6Nfc',
    'Qt6RemoteObjects', 'Qt6Sensors', 'Qt6SerialPort', 'Qt6Test',
    'Qt6Sql', 'Qt6Xml', 'Qt6Help', 'Qt6Charts',
    'Qt6DataVisualization', 'Qt6NetworkAuth', 'Qt6Positioning',
    'Qt6SpatialAudio', 'Qt6StateMachine', 'Qt6TextToSpeech',
    'Qt6HttpServer', 'Qt6WebSockets', 'Qt6WebChannel', 'Qt6OpenGL',
    'Qt6Scxml', 'opengl32sw',
]

def _should_exclude(path):
    """Kiểm tra cả basename và full path để bắt files trong subdirectories"""
    return any(excl in path for excl in _exclude_dlls)

binaries = [(src, dst) for src, dst in binaries if not _should_exclude(src)]
datas = [(src, dst) for src, dst in datas if not _should_exclude(src)]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_qt_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# ── Post-Analysis: lọc bỏ DLL nặng mà hooks đã re-add ──
# a.binaries/a.datas là TOC objects (list of 3-tuples: name, path, typecode)
def _toc_should_exclude(name):
    return any(excl in name for excl in _exclude_dlls)

a.binaries = [item for item in a.binaries if not _toc_should_exclude(item[0]) and not _toc_should_exclude(item[1])]
a.datas = [item for item in a.datas if not _toc_should_exclude(item[0]) and not _toc_should_exclude(item[1])]

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='QuangLuuStudio',
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
    icon=['app_icon.ico'] if os.path.exists('app_icon.ico') else [],
)
