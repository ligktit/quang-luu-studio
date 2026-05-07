"""
core.accessibility.shortcuts
============================
Đăng ký bộ QShortcut tập trung cho MainDashboard.

Mỗi shortcut được khai báo dưới dạng (sequence, callback_attr_or_callable, description).
Khi gọi register_shortcuts(dashboard) sẽ tạo QShortcut + lưu vào
dashboard._a11y_shortcuts (dict) để tham chiếu sau (vd: F1 đọc help).

Hotkey không gắn được (callback không tồn tại) sẽ được log warning thay vì crash.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication, QAbstractSlider

log = logging.getLogger("accessibility.shortcuts")


# Bảng phím tắt — danh sách (sequence, dashboard_method_name, description).
# Một số method có thể chưa tồn tại → fallback callable cũng được hỗ trợ qua
# tham số extra của register_shortcuts.
_DEFAULT_BINDINGS = [
    ("F1",          "_a11y_speak_help",         "Đọc danh sách phím tắt"),
    ("F2",          "_a11y_speak_status",       "Đọc trạng thái hiện tại"),
    ("Ctrl+D",      "_on_force_rescan",         "Dò lại tone"),
    ("Ctrl+R",      "_on_record",               "Bật/tắt ghi âm"),
    ("Ctrl+S",      "_on_save",                 "Lưu bài hát"),
    ("Ctrl+O",      "_show_songs_list",         "Mở danh sách bài"),
    ("Ctrl+P",      "_on_score",                "Chấm điểm"),
    ("Ctrl+,",      "_show_settings_dialog",    "Mở thiết lập"),
    ("Ctrl+Shift+V", "_a11y_toggle_tts",        "Bật/tắt giọng đọc TTS"),
    ("Ctrl+H",      "_a11y_toggle_high_contrast", "Bật/tắt tương phản cao"),
    ("Ctrl++",      "_a11y_increase_font",      "Tăng cỡ chữ"),
    ("Ctrl+=",      "_a11y_increase_font",      "Tăng cỡ chữ"),
    ("Ctrl+-",      "_a11y_decrease_font",      "Giảm cỡ chữ"),
    ("Ctrl+0",      "_a11y_reset_font",         "Khôi phục cỡ chữ"),
    ("[",           "_a11y_tone_music_down",    "Tone Nhạc giảm 1"),
    ("]",           "_a11y_tone_music_up",      "Tone Nhạc tăng 1"),
    (";",           "_a11y_tone_voice_down",    "Tone Giọng giảm 1"),
    ("'",           "_a11y_tone_voice_up",      "Tone Giọng tăng 1"),
    ("1",           "_a11y_toggle_mute_music",  "Tắt/bật âm Nhạc"),
    ("2",           "_a11y_toggle_mute_mic",    "Tắt/bật âm Mic"),
    ("3",           "_a11y_toggle_mute_reverb", "Tắt/bật âm Vang"),
    ("4",           "_a11y_toggle_mute_backing","Tắt/bật âm Giọng đệm"),
]


def _resolve(dashboard, target) -> Optional[Callable]:
    if callable(target):
        return target
    if isinstance(target, str):
        fn = getattr(dashboard, target, None)
        if callable(fn):
            return fn
    return None


def register_shortcuts(dashboard, extra: Optional[dict] = None):
    """
    Đăng ký toàn bộ shortcut. Idempotent — gọi nhiều lần sẽ huỷ shortcut cũ.

    extra: dict {sequence: callable} — override hoặc bổ sung phím tắt riêng.
    """
    # Cleanup nếu đã register trước đó
    old = getattr(dashboard, "_a11y_shortcuts", None)
    if isinstance(old, dict):
        for sc in old.values():
            try:
                sc.setEnabled(False)
                sc.deleteLater()
            except Exception:
                pass
    dashboard._a11y_shortcuts = {}
    dashboard._a11y_help_lines = []

    bindings = list(_DEFAULT_BINDINGS)
    if extra:
        for seq, cb in extra.items():
            bindings.append((seq, cb, ""))

    for seq, target, desc in bindings:
        cb = _resolve(dashboard, target)
        if cb is None:
            log.debug("Bỏ qua shortcut '%s' — không có callback %r", seq, target)
            continue
        try:
            sc = QShortcut(QKeySequence(seq), dashboard)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(cb)
            dashboard._a11y_shortcuts[seq] = sc
            if desc:
                dashboard._a11y_help_lines.append(f"{seq}: {desc}")
        except Exception as e:
            log.warning("Không đăng ký được shortcut '%s': %s", seq, e)

    log.info("Đã đăng ký %d phím tắt trợ năng", len(dashboard._a11y_shortcuts))
    return dashboard._a11y_shortcuts
