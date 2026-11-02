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


# ── Ẩn/hiện từng cửa sổ (plugin, ASIO) ──────────────────────────────────────

class _FakeGui:
    """win32gui giả: mỗi hwnd có title/class/rect/visible; hwnd không có là đã chết."""

    def __init__(self, wins):
        self.wins = {h: dict(w) for h, w in wins.items()}
        self.shown = []

    def IsWindow(self, h):
        return h in self.wins

    def IsWindowVisible(self, h):
        return self.wins[h]["vis"]

    def GetWindowText(self, h):
        return self.wins[h]["title"]

    def GetClassName(self, h):
        return self.wins[h].get("cls", "SteinbergWindowClass")

    def GetWindowRect(self, h):
        return self.wins[h].get("rect", (0, 0, 800, 600))

    def ShowWindow(self, h, cmd):
        if h not in self.wins:
            raise Exception("invalid window handle")
        self.shown.append((h, cmd))
        self.wins[h]["vis"] = cmd != so_windows.SW_HIDE

    def SetWindowPos(self, *a):
        self.shown.append(("pos",) + a[:2])


_CUBASE_WINS = {
    21: {"title": "Mic: Ins. 1 - Auto-Tune Pro", "vis": False},
    22: {"title": "", "vis": False},                                    # tooltip
    23: {"title": "Cubase Pro Project - mau", "vis": False},
    24: {"title": "USB Change Listener", "cls": "USB Change Listener", "vis": False},
    25: {"title": "Default IME", "cls": "IME", "vis": False},
    26: {"title": "Cubase Pro", "cls": "SmtgMain Cubase13", "vis": False, "rect": (0, 0, 0, 0)},
    31: {"title": "ASIO Link Pro", "vis": True},
}


@pytest.fixture
def fake_gui():
    daw.bind({"daw_kind": "cubase"})
    gui = _FakeGui(_CUBASE_WINS)
    with patch.object(so_windows, "win32_modules", return_value=(gui, MagicMock(), MagicMock())), \
         patch.object(so_windows, "all_windows", return_value=[21, 22, 23, 24, 25, 26]), \
         patch.object(so_windows, "asio_windows", return_value=[31]), \
         patch.object(so_windows, "force_foreground", return_value=True):
        yield gui


def test_list_windows_chinh_dau_tien_bo_cua_so_noi_bo(fake_gui):
    entries = so_windows.list_windows()
    assert [e.hwnd for e in entries] == [23, 21, 31]
    assert entries[0].is_main and entries[0].source == "daw"
    assert entries[1].title == "Mic: Ins. 1 - Auto-Tune Pro" and not entries[1].visible
    assert entries[2].source == "asio" and entries[2].visible


def test_show_window_chi_hien_dung_cua_so(fake_gui):
    assert so_windows.show_window(21) is True
    assert fake_gui.shown == [(21, so_windows.SW_SHOW)]
    assert fake_gui.wins[23]["vis"] is False                  # cửa sổ chính vẫn ẩn


def test_show_window_hwnd_chet_tra_false(fake_gui):
    assert so_windows.show_window(99) is False
    assert so_windows.hide_window(99) is False
    assert fake_gui.shown == []


def test_hide_window_chi_an_dung_cua_so(fake_gui):
    fake_gui.wins[21]["vis"] = True
    assert so_windows.hide_window(21) is True
    assert fake_gui.shown == [(21, so_windows.SW_HIDE)]


def test_show_window_tren_ca_app_dang_ghim(fake_gui):
    assert so_windows.show_window(21, above_topmost=True) is True
    assert ("pos", 21, so_windows.HWND_TOPMOST) in fake_gui.shown
    assert ("pos", 21, so_windows.HWND_NOTOPMOST) in fake_gui.shown


def test_show_all_bo_qua_cua_so_noi_bo_va_asio(fake_gui):
    so_windows.show_all(focus_main=False)
    shown = {h for h, _ in fake_gui.shown}
    assert shown == {21, 23, 26}           # không USB Change Listener/IME/tooltip, không ASIO


def test_bang_asio_link_trong_studio_one_khong_phai_cua_so_chinh():
    # Đo máy 1 (Studio One 5, 2026-11-02): ASIO Link Pro mở bảng trong tiến trình
    # Studio One với tiêu đề có chữ "Studio One" — trước đây bị nhận là cửa sổ chính
    # (đóng an toàn gửi WM_CLOSE vào nó, danh sách Cài đặt ghi "(cửa sổ chính)").
    daw.bind({})
    assert so_windows.title_is_main("O Deus ASIO Link Pro 2.4.2.0 - Studio One.exe") is False
    assert so_windows.title_is_main("Studio One - vp") is True


def test_list_windows_bo_cua_so_ngam_juce():
    # Plugin JUCE (Auto-Tune, Waves…) tạo cửa sổ ngầm 133×38 tiêu đề "JUCEWindow",
    # vốn ẩn từ đầu — hiện lên là rác.
    daw.bind({})
    gui = _FakeGui({51: {"title": "Studio One - vp", "vis": False},
                    52: {"title": "JUCEWindow", "cls": "JUCE_551dc4e427", "vis": False,
                         "rect": (0, 0, 133, 38)},
                    53: {"title": "O Deus ASIO Link Pro 2.4.2.0 - Studio One.exe",
                         "cls": "ASIOLINKCLASS36559117", "vis": False}})
    with patch.object(so_windows, "win32_modules", return_value=(gui, MagicMock(), MagicMock())), \
         patch.object(so_windows, "all_windows", return_value=[53, 52, 51]), \
         patch.object(so_windows, "asio_windows", return_value=[]), \
         patch.object(so_windows, "force_foreground", return_value=True):
        entries = so_windows.list_windows()
        assert [(e.hwnd, e.is_main) for e in entries] == [(51, True), (53, False)]
        so_windows.show_all(focus_main=False)
        assert {h for h, _ in gui.shown} == {51, 53}


def test_asio_windows_theo_ten_tien_trinh():
    gui = _FakeGui({41: {"title": "ASIO Link Pro", "vis": True},
                    42: {"title": "ASIO4ALL download - Chrome", "vis": True},
                    43: {"title": "", "vis": False}})
    names = {1: "ASIOLinkPro.exe", 2: "chrome.exe"}
    owner = {41: 1, 42: 2, 43: 1}
    winproc = MagicMock()
    winproc.GetWindowThreadProcessId.side_effect = lambda h: (0, owner[h])
    gui.EnumWindows = lambda cb, extra: [cb(h, extra) for h in (41, 42, 43)]
    fake_psutil = MagicMock()
    fake_psutil.Process.side_effect = lambda pid: MagicMock(**{"name.return_value": names[pid]})
    with patch.object(so_windows, "win32_modules", return_value=(gui, MagicMock(), winproc)), \
         patch.dict("sys.modules", {"psutil": fake_psutil}):
        assert so_windows.asio_windows() == [41]
