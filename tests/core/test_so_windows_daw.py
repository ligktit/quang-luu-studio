# tests/core/test_so_windows_daw.py
"""so_windows nhận diện process/cửa sổ theo hồ sơ DAW đang chọn."""
from unittest.mock import MagicMock, patch

import pytest

from core import daw, so_windows


@pytest.fixture(autouse=True)
def _unbind():
    daw.bind(None)
    yield
    daw.bind(None)


def test_mac_dinh_van_la_studio_one():
    daw.bind({})
    assert so_windows.process_keywords() == ("studio one",)
    assert so_windows.title_is_main("Studio One 7 - BaiMau") is True
    assert so_windows.title_is_main("Cubase Pro Project - mau") is False


def test_cubase_bo_qua_cua_so_khong_phai_project():
    daw.bind({"daw_kind": "cubase"})
    assert so_windows.title_is_main("Cubase Pro Project - mau") is True
    assert so_windows.title_is_main("Cubase Artist Project - x.cpr") is True
    assert so_windows.title_is_main("Checking Licenses...") is False
    assert so_windows.title_is_main("Cubase Pro") is False          # cửa sổ SmtgMain
    assert so_windows.title_is_main("MIDI Remote Script Console") is False


def test_main_windows_loc_theo_tieu_de_cubase():
    daw.bind({"daw_kind": "cubase"})
    win32gui = MagicMock()
    titles = {11: "Checking Licenses...", 12: "Cubase Pro", 13: "Cubase Pro Project - mau"}
    win32gui.GetWindowText.side_effect = lambda h: titles[h]
    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), MagicMock())):
        assert so_windows.main_windows([11, 12, 13]) == [13]


def test_pids_theo_tu_khoa_cubase():
    daw.bind({"daw_kind": "cubase"})
    procs = [MagicMock(info={"pid": 1, "name": "Cubase13.exe"}),
             MagicMock(info={"pid": 2, "name": "Studio One.exe"}),
             MagicMock(info={"pid": 3, "name": "loopMIDI.exe"})]
    fake_psutil = MagicMock()
    fake_psutil.process_iter.return_value = procs
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        assert so_windows.studio_one_pids() == {1}


def _fake_dialog(children, dlg_class, child_class="Button"):
    win32gui = MagicMock()
    labels = dict(children)

    def _enum(hwnd, cb, extra):
        for child, _ in children:
            cb(child, extra)

    win32gui.EnumChildWindows.side_effect = _enum
    win32gui.GetWindowText.side_effect = lambda h: labels[h]
    win32gui.GetClassName.side_effect = lambda h: dlg_class if h not in labels else child_class
    win32gui.GetDlgCtrlID.side_effect = lambda h: 0
    return win32gui


def test_hop_thoai_cubase_bam_nut_dont_save():
    # Đo 2026-10-04: class SteinbergWindowClass + 2 ký tự lạ, nút HWND class Button.
    children = [(201, "Save"), (202, "Don't Save"), (203, "Cancel")]
    win32gui = _fake_dialog(children, dlg_class="SteinbergWindowClass\ubec0\u47ce")
    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), None)):
        assert so_windows.click_no_save(77) is True
    win32gui.PostMessage.assert_called_once_with(202, so_windows.BM_CLICK, 0, 0)


def _fake_gui(classes, titles):
    win32gui = MagicMock()
    win32gui.GetClassName.side_effect = lambda h: classes[h]
    win32gui.GetWindowText.side_effect = lambda h: titles[h]
    return win32gui


def test_quit_windows_cubase_la_cua_so_smtgmain():
    # Đóng cửa sổ project chỉ đóng bài, Cubase vẫn chạy ở Steinberg Hub;
    # thoát hẳn phải gửi WM_CLOSE vào cửa sổ ứng dụng (class SmtgMain, "Cubase Pro").
    daw.bind({"daw_kind": "cubase"})
    win32gui = _fake_gui({11: "SteinbergWindowClass뻀䟎", 12: "SmtgMain Cubase13"},
                         {11: "Cubase Pro Project - mau", 12: "Cubase Pro"})
    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), MagicMock())):
        assert so_windows.quit_windows([11, 12]) == [12]


def test_quit_windows_cubase_khong_thay_smtgmain_thi_ve_cua_so_chinh():
    daw.bind({"daw_kind": "cubase"})
    win32gui = _fake_gui({11: "SteinbergWindowClass"}, {11: "Cubase Pro Project - mau"})
    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), MagicMock())):
        assert so_windows.quit_windows([11]) == [11]


def test_quit_windows_studio_one_giu_nhu_main_windows():
    daw.bind({})
    win32gui = _fake_gui({21: "PreSonusWindow", 22: "PreSonusDialog"},
                         {21: "Studio One 7 - BaiMau", 22: "Plugin"})
    with patch.object(so_windows, "win32_modules", return_value=(win32gui, MagicMock(), MagicMock())):
        assert so_windows.quit_windows([21, 22]) == so_windows.main_windows([21, 22]) == [21]
