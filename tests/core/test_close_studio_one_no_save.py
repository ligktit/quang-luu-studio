"""Đóng Studio One với save=False phải LUÔN chọn "Không lưu".

Nút mặc định của hộp thoại hỏi lưu là "Save", nên nhấn Enter cho xong là lưu đè
đúng cái bài mà bản mẫu .song sắp phục hồi. Đây là bộ chốt chặn cho điều đó.
"""
from unittest.mock import MagicMock, patch

import pytest

from core import so_windows
from core.engine._lifecycle import _LifecycleMixin


# ── Nhận diện nhãn nút ───────────────────────────────────────────────────────

@pytest.mark.parametrize("label", [
    "Don't Save", "&Don't Save", "Dont Save", "Do Not Save", "Discard",
    "No", "Không lưu", "KHÔNG LƯU", "  don't save  ",
])
def test_nhan_dien_nut_khong_luu(label):
    assert so_windows.is_no_save_label(label) is True


@pytest.mark.parametrize("label", [
    "Save", "&Save", "Save As...", "Save All", "Cancel", "Yes", "OK",
    "Lưu", "Huỷ", "", None,
])
def test_khong_nham_sang_nut_khac(label):
    assert so_windows.is_no_save_label(label) is False


# ── Lớp win32: bấm đúng nút con ──────────────────────────────────────────────

def _fake_dialog(children, dlg_class=so_windows.DIALOG_CLASS, ids=None,
                 child_class="Button"):
    """win32gui giả cho một hộp thoại: children = [(hwnd, nhãn)]."""
    win32gui = MagicMock()
    labels = dict(children)
    ids = ids or {}

    def _enum(hwnd, cb, extra):
        for child, _ in children:
            cb(child, extra)

    win32gui.EnumChildWindows.side_effect = _enum
    win32gui.GetWindowText.side_effect = lambda h: labels[h]
    win32gui.GetClassName.side_effect = lambda h: dlg_class if h not in labels else child_class
    win32gui.GetDlgCtrlID.side_effect = lambda h: ids.get(h, 0)
    return win32gui


def test_hop_thoai_studio_one_yes_no_cancel_bam_nut_no():
    # Studio One hỏi bằng MessageBox chuẩn: tiêu đề "Studio One", Yes - No - Cancel.
    children = [(101, "&Yes"), (102, "&No"), (103, "Cancel")]
    ids = {101: 6, 102: so_windows.IDNO, 103: 2}
    win32gui = _fake_dialog(children, ids=ids)

    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), None)):
        assert so_windows.click_no_save(50) is True

    win32gui.PostMessage.assert_called_once_with(102, so_windows.BM_CLICK, 0, 0)


def test_bat_theo_id_nen_khong_phu_thuoc_ngon_ngu():
    # Windows tiếng Đức: nhãn "Nein" không nằm trong bảng nhãn, nhưng ID vẫn là 7.
    children = [(101, "&Ja"), (102, "&Nein"), (103, "Abbrechen")]
    ids = {101: 6, 102: so_windows.IDNO, 103: 2}
    win32gui = _fake_dialog(children, ids=ids)

    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), None)):
        assert so_windows.click_no_save(50) is True

    win32gui.PostMessage.assert_called_once_with(102, so_windows.BM_CLICK, 0, 0)


def test_khong_bam_id_7_cua_hop_thoai_khong_chuan():
    # Cửa sổ tự vẽ (không phải #32770): ID 7 vô nghĩa, chỉ được tin vào nhãn.
    children = [(101, "Save"), (102, "Apply")]
    ids = {102: so_windows.IDNO}
    win32gui = _fake_dialog(children, dlg_class="JUCEWindow", ids=ids)

    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), None)), \
         patch.object(so_windows, "_click_no_save_uia", return_value=False):
        assert so_windows.click_no_save(50) is False

    win32gui.PostMessage.assert_not_called()



def test_click_no_save_bam_dung_nut_con():
    win32gui = MagicMock()
    children = [(101, "&Save"), (102, "&Don't Save"), (103, "Cancel")]

    def _enum(hwnd, cb, extra):
        for child, _ in children:
            cb(child, extra)

    win32gui.EnumChildWindows.side_effect = _enum
    win32gui.GetWindowText.side_effect = lambda h: dict(children)[h]

    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), None)):
        assert so_windows.click_no_save(50) is True

    win32gui.PostMessage.assert_called_once_with(102, so_windows.BM_CLICK, 0, 0)


def test_click_no_save_khong_thay_nut_thi_bao_false():
    win32gui = MagicMock()
    children = [(101, "&Save"), (103, "Cancel")]

    def _enum(hwnd, cb, extra):
        for child, _ in children:
            cb(child, extra)

    win32gui.EnumChildWindows.side_effect = _enum
    win32gui.GetWindowText.side_effect = lambda h: dict(children)[h]

    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), None)), \
         patch.object(so_windows, "_click_no_save_uia", return_value=False):
        assert so_windows.click_no_save(50) is False

    win32gui.PostMessage.assert_not_called()


# ── Vòng đóng Studio One ─────────────────────────────────────────────────────

class _Engine(_LifecycleMixin):
    def __init__(self):
        self._force_kill_studio_one = MagicMock()


def _fake_so_windows(pids_seq, click_ok):
    """Giả lập core.so_windows: có 1 hộp thoại (hwnd 20) mọc lên sau WM_CLOSE."""
    m = MagicMock()
    m.studio_one_pids.side_effect = list(pids_seq) + [set()] * 50
    m.win32_modules.return_value = (MagicMock(), MagicMock(), None)
    m.main_windows.return_value = [10]
    m.all_windows.side_effect = [[10]] + [[10, 20]] * 50
    m.force_foreground.return_value = True
    m.click_no_save.return_value = click_ok
    win32gui = m.win32_modules.return_value[0]
    win32gui.IsWindowVisible.return_value = True
    win32gui.GetWindowText.return_value = "Save changes?"
    return m


def test_save_false_bam_khong_luu_va_khong_gui_enter(monkeypatch):
    fake = _fake_so_windows([{1}, {1}, {1}], click_ok=True)
    import core
    monkeypatch.setattr(core, "so_windows", fake, raising=False)

    with patch("core.engine._lifecycle.pyautogui") as pg:
        result = _Engine().close_studio_one_safely(timeout_sec=3, save=False)

    assert result["status"] == "closed"
    assert result["saved"] is False
    fake.click_no_save.assert_called_once_with(20)
    pg.press.assert_not_called()
    pg.hotkey.assert_not_called()


def test_save_false_khong_thay_nut_thi_huy_dong(monkeypatch):
    fake = _fake_so_windows([{1}] * 20, click_ok=False)
    import core
    monkeypatch.setattr(core, "so_windows", fake, raising=False)

    with patch("core.engine._lifecycle.pyautogui") as pg:
        result = _Engine().close_studio_one_safely(timeout_sec=3, save=False)

    assert result["status"] == "no_save_button"
    assert result["saved"] is False
    fake.cancel_dialog.assert_called_once_with(20)
    pg.press.assert_not_called()
    pg.hotkey.assert_not_called()


def test_save_false_khong_bao_gio_gui_ctrl_s(monkeypatch):
    fake = _fake_so_windows([{1}, set()], click_ok=True)
    import core
    monkeypatch.setattr(core, "so_windows", fake, raising=False)

    with patch("core.engine._lifecycle.pyautogui") as pg:
        _Engine().close_studio_one_safely(timeout_sec=3, save=False)

    pg.hotkey.assert_not_called()
