"""Panel Công cụ: nút bật/tắt hiển thị trạng thái như nút MODE.

Auto-Tune (và Fix Méo, Bè, Tắt Ồn, nút tự thêm có cờ toggle) trước đây là
PainterButton: luôn tô đầy màu, "đang bật" chỉ là chấm trắng 4px ở góc. Nút MODE
đã đổi sang ModeToggleButton (tắt = viền mỏng, bật = đổ đầy + phát sáng); nhóm
toggle ở panel Công cụ phải cùng ngôn ngữ đó. Nút bấm một lần (Dò Lại, Chế độ
Nhanh/Full, nút tuỳ chỉnh không toggle) không có trạng thái bật nên giữ nguyên.
"""
from unittest.mock import MagicMock, patch

import pytest

from ui.components.painter_button import PainterButton
from ui.components.mode_button import ModeToggleButton


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


_TOOLS = [
    {"id": "btn_fast_mode", "type": "button", "label": "Chế độ: Nhanh", "color": "#f97316",
     "action": "toggle_scan_mode", "desc": "", "hidden": False},
    {"id": "btn_rescan", "type": "button", "label": "Dò Lại", "color": "#14b8a6",
     "action": "force_rescan", "desc": "", "hidden": False},
    {"id": "btn_autotune", "type": "button", "label": "Auto-Tune", "color": "#ec4899",
     "action": "tone_auto", "desc": "", "hidden": False},
    {"id": "btn_fixmeo", "type": "button", "label": "Fix Méo", "color": "#8b5cf6",
     "action": "fix_meo", "desc": "", "hidden": False},
    {"id": "btn_be", "type": "button", "label": "Bè", "color": "#eab308",
     "action": "be", "desc": "", "hidden": False},
    {"id": "btn_tat_on", "type": "button", "label": "Tắt Ồn", "color": "#3b82f6",
     "action": "tat_on", "desc": "", "hidden": False},
    # Nút tự thêm ở Dev Mode: CC số, có / không có cờ toggle.
    {"id": "custom_toggle", "type": "button", "label": "Vang", "color": "#22c55e",
     "cc": 90, "is_toggle": True, "on_value": 127, "off_value": 0, "hidden": False},
    {"id": "custom_once", "type": "button", "label": "Bíp", "color": "#22c55e",
     "cc": 91, "is_toggle": False, "on_value": 127, "off_value": 0, "hidden": False},
]


class _Dash:
    """Dashboard giả: chỉ những gì build_panel_tools cần."""
    is_dev_mode = False
    tune_state = True
    fix_meo_state = False
    be_state = True
    tat_on_state = False

    def __init__(self):
        self._func_buttons = {}
        self._tone_value_labels = {}
        self.engine = MagicMock()

    def _embedded_player_enabled(self):
        return False

    def _refresh_tone_offset_label(self, key):
        pass

    def _tone_offset(self, key):
        return 0

    def _set_tone_offset(self, key, value):
        pass


def _build(qtbot):
    from ui.panels.tools import build_panel_tools
    dash = _Dash()
    with patch("ui.panels.tools.backend.UiConfigManager.load_ui_config",
               return_value={"tools": _TOOLS}):
        panel = build_panel_tools(dash)
    qtbot.addWidget(panel)
    dash.panel = panel   # giữ tham chiếu, kẻo Qt dọn panel (và nút) giữa test
    return dash


@pytest.mark.parametrize("label", ["Auto-Tune", "Fix Méo", "Bè", "Tắt Ồn", "Vang"])
def test_nut_bat_tat_dung_kieu_nut_mode(qapp, qtbot, label):
    dash = _build(qtbot)
    assert isinstance(dash._func_buttons[label], ModeToggleButton), label


@pytest.mark.parametrize("label", ["Chế độ: Nhanh", "Dò Lại", "Bíp"])
def test_nut_bam_mot_lan_giu_painter_button(qapp, qtbot, label):
    dash = _build(qtbot)
    btn = dash._func_buttons[label]
    assert isinstance(btn, PainterButton) and not isinstance(btn, ModeToggleButton), label


def test_trang_thai_ban_dau_theo_dashboard(qapp, qtbot):
    dash = _build(qtbot)
    assert dash._func_buttons["Auto-Tune"].isActive() is True
    assert dash._func_buttons["Fix Méo"].isActive() is False
    assert dash._func_buttons["Bè"].isActive() is True
    assert dash._func_buttons["Tắt Ồn"].isActive() is False


def test_nut_tuy_chinh_toggle_dao_trang_thai_va_gui_cc(qapp, qtbot):
    from PySide6.QtCore import Qt
    dash = _build(qtbot)
    btn = dash._func_buttons["Vang"]
    assert btn.isActive() is False
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert btn.isActive() is True
    dash.engine.send_midi.assert_called_with(90, 127)
    qtbot.mouseClick(btn, Qt.LeftButton)
    assert btn.isActive() is False
    dash.engine.send_midi.assert_called_with(90, 0)
