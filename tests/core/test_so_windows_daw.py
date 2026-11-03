# tests/core/test_so_windows_daw.py
"""so_windows nhận diện process/cửa sổ theo hồ sơ DAW đang chọn."""
from unittest.mock import MagicMock, patch

import pytest

from core import daw, so_windows


@pytest.fixture(autouse=True)
def _unbind(tmp_path, monkeypatch):
    daw.bind(None)
    # Ghi nhận "cửa sổ app đã ẩn" lưu ra file — không đụng thư mục dữ liệu thật.
    monkeypatch.setattr(so_windows, "_RECORD_FILE", str(tmp_path / "daw_hidden.json"))
    monkeypatch.setattr(so_windows, "_record_loaded", False)
    so_windows._hidden_by_us.clear()
    yield
    daw.bind(None)
    so_windows._hidden_by_us.clear()


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

    def GetWindow(self, h, cmd):
        return self.wins[h].get("owner", 0)

    def IsWindowEnabled(self, h):
        return self.wins[h].get("enabled", True)


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
    so_windows._hidden_by_us.clear()
    so_windows._pinned_topmost.clear()
    gui = _FakeGui(_CUBASE_WINS)
    with patch.object(so_windows, "win32_modules", return_value=(gui, MagicMock(), MagicMock())), \
         patch.object(so_windows, "all_windows", return_value=[21, 22, 23, 24, 25, 26]), \
         patch.object(so_windows, "asio_windows", return_value=[31]), \
         patch.object(so_windows, "studio_one_pids", return_value={7}), \
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
    # App ghim là cửa sổ topmost: đặt TOPMOST rồi bỏ ngay thì plugin lại nằm dưới
    # app (MSDN: NOTOPMOST = sau mọi cửa sổ topmost). Phải giữ TOPMOST khi hiện.
    assert so_windows.show_window(21, above_topmost=True) is True
    assert ("pos", 21, so_windows.HWND_TOPMOST) in fake_gui.shown
    assert ("pos", 21, so_windows.HWND_NOTOPMOST) not in fake_gui.shown


def test_an_lai_thi_bo_topmost_truoc(fake_gui):
    so_windows.show_window(21, above_topmost=True)
    fake_gui.shown.clear()
    assert so_windows.hide_window(21) is True
    assert fake_gui.shown == [("pos", 21, so_windows.HWND_NOTOPMOST), (21, so_windows.SW_HIDE)]


def test_hide_all_bo_topmost_cua_so_da_ghim(fake_gui):
    so_windows.show_window(21, above_topmost=True)
    fake_gui.shown.clear()
    so_windows.hide_all()
    assert ("pos", 21, so_windows.HWND_NOTOPMOST) in fake_gui.shown


def test_show_all_chi_hien_lai_cua_so_da_an(fake_gui):
    # Đo máy 1: bảng ASIO Link Pro nằm sẵn (ẩn, chưa từng mở) trong tiến trình
    # Studio One; "Hiện tất cả" bật nó lên thành khung trắng. Chỉ hiện lại cái
    # hide_all đã ẩn.
    fake_gui.wins[23]["vis"] = True                 # cửa sổ chính đang hiện
    fake_gui.wins[21]["vis"] = False                # plugin chưa từng hiện
    so_windows.hide_all()
    fake_gui.shown.clear()
    so_windows.show_all(focus_main=False)
    assert {h for h, _ in fake_gui.shown} == {23}


def test_show_all_khong_ghi_nhan_thi_hien_moi_cua_so_hop_le(fake_gui):
    # App mở lại khi DAW đã bị ẩn từ phiên trước: không có ghi nhận nào.
    so_windows._hidden_by_us.clear()
    so_windows.show_all(focus_main=False)
    assert {h for h, _ in fake_gui.shown} == {21, 23, 26}


def test_show_all_luon_hien_cua_so_chinh(fake_gui):
    # App mở lại khi DAW đã ẩn sẵn → KTV bật rồi tắt riêng plugin → "Hiện tất cả"
    # vẫn phải hiện cửa sổ chính, không chỉ plugin.
    so_windows._hidden_by_us.clear()
    so_windows.show_window(21)
    so_windows.hide_window(21)
    fake_gui.shown.clear()
    so_windows.show_all(focus_main=False)
    assert {h for h, _ in fake_gui.shown} == {21, 23}


def test_bam_an_dung_khi_ktv_vua_hien_cua_so():
    # "Không tự ẩn lại": trong lúc hide_when_ready còn bám ẩn (60 s sau khi DAW
    # mở, hoặc sau khi Tự sửa mở lại DAW), KTV bật plugin thì vòng bám phải dừng.
    calls = []

    def fake_sleep(_):
        if len(calls) == 1:
            so_windows.show_window(21)          # KTV bật plugin giữa chừng
    with patch.object(so_windows, "wait_for_main_window", return_value=23), \
         patch.object(so_windows, "hide_all", side_effect=lambda **kw: calls.append(1) or 0), \
         patch.object(so_windows, "win32_modules", return_value=(_FakeGui(_CUBASE_WINS), MagicMock(), MagicMock())), \
         patch.object(so_windows, "force_foreground", return_value=True), \
         patch.object(so_windows.time, "sleep", side_effect=fake_sleep):
        so_windows.hide_when_ready(follow_seconds=2.0).join(timeout=5)
    assert len(calls) == 1


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


def test_tien_to_cua_so_chinh_khai_bao_rieng_khong_theo_thu_tu_tu_khoa(monkeypatch):
    # Quy tắc "tiêu đề BẮT ĐẦU bằng tên DAW" không được dựa vào thứ tự
    # main_title_requires: đảo ("project", "cubase") vẫn phải nhận cửa sổ project.
    import dataclasses
    from core.daw import profiles
    prof = dataclasses.replace(profiles.CUBASE, main_title_requires=("project", "cubase"))
    monkeypatch.setattr(so_windows, "_profile", lambda: prof)
    assert so_windows.title_is_main("Cubase Pro Project - mau") is True
    assert so_windows.title_is_main("Project Logical Editor - Cubase") is False


def test_show_all_nho_cua_so_da_an_qua_lan_mo_lai_app(fake_gui):
    # App ẩn DAW, tắt app, mở lại: ghi nhận trong RAM mất nhưng DAW vẫn là tiến
    # trình cũ → "Hiện tất cả" vẫn hiện lại đúng cái đã ẩn, kể cả cửa sổ không tiêu đề.
    fake_gui.wins[22]["vis"] = True
    fake_gui.wins[23]["vis"] = True
    so_windows.hide_all()
    _mo_lai_app()
    fake_gui.shown.clear()
    so_windows.show_all(focus_main=False)
    assert {h for h, _ in fake_gui.shown} == {22, 23}


def test_ghi_nhan_cua_tien_trinh_daw_khac_bi_bo_qua(fake_gui):
    # DAW đã khởi động lại: HWND cũ có thể bị cửa sổ khác dùng lại → bỏ ghi nhận.
    fake_gui.wins[22]["vis"] = True
    so_windows.hide_all()
    _mo_lai_app()
    fake_gui.shown.clear()
    with patch.object(so_windows, "studio_one_pids", return_value={8}):
        so_windows.show_all(focus_main=False)
    assert {h for h, _ in fake_gui.shown} == {21, 23, 26}


def test_asio_windows_khop_mot_phan_ten_tien_trinh():
    # Bản ASIO Link 64-bit / bản cài khác tên exe vẫn là công cụ ASIO.
    gui = _FakeGui({44: {"title": "ASIO Link Pro", "vis": True},
                    45: {"title": "ASIO4ALL v2 Instruction Manual", "vis": True}})
    names = {1: "ASIOLinkPro64.exe", 2: "msedge.exe"}
    owner = {44: 1, 45: 2}
    winproc = MagicMock()
    winproc.GetWindowThreadProcessId.side_effect = lambda h: (0, owner[h])
    gui.EnumWindows = lambda cb, extra: [cb(h, extra) for h in (44, 45)]
    fake_psutil = MagicMock()
    fake_psutil.Process.side_effect = lambda pid: MagicMock(**{"name.return_value": names[pid]})
    with patch.object(so_windows, "win32_modules", return_value=(gui, MagicMock(), winproc)), \
         patch.dict("sys.modules", {"psutil": fake_psutil}):
        assert so_windows.asio_windows() == [44]


def test_hide_all_giu_hop_thoai_dang_cho_tra_loi(fake_gui):
    # DAW đang nạp bài bật hộp thoại (thiếu thiết bị âm thanh, thiếu plugin…):
    # ẩn nó đi thì DAW kẹt chờ một hộp thoại không ai thấy.
    fake_gui.wins[23].update(vis=True, enabled=False)          # cửa sổ chính bị khoá bởi hộp thoại
    fake_gui.wins[27] = {"title": "Studio One", "cls": "#32770", "vis": True}
    fake_gui.wins[28] = {"title": "Audio Device", "vis": True, "owner": 23}
    fake_gui.wins[21]["vis"] = True
    with patch.object(so_windows, "all_windows", return_value=[21, 23, 27, 28]):
        so_windows.hide_all(keep_dialogs=True)
    assert fake_gui.wins[27]["vis"] is True
    assert fake_gui.wins[28]["vis"] is True
    assert fake_gui.wins[21]["vis"] is False
    assert fake_gui.wins[23]["vis"] is False


def test_hide_all_mac_dinh_van_an_ca_hop_thoai(fake_gui):
    # KTV bấm "Ẩn" là ý muốn rõ ràng — ẩn hết như trước.
    fake_gui.wins[27] = {"title": "Studio One", "cls": "#32770", "vis": True}
    with patch.object(so_windows, "all_windows", return_value=[27]):
        so_windows.hide_all()
    assert fake_gui.wins[27]["vis"] is False


def test_bam_an_luc_mo_daw_giu_hop_thoai():
    kwargs = []
    with patch.object(so_windows, "wait_for_main_window", return_value=23), \
         patch.object(so_windows, "hide_all", side_effect=lambda **kw: kwargs.append(kw) or 0), \
         patch.object(so_windows.time, "sleep"):
        so_windows.hide_when_ready(follow_seconds=0.0).join(timeout=5)
    assert kwargs and all(kw.get("keep_dialogs") is True for kw in kwargs)


def _mo_lai_app():
    """Giả lập tắt rồi mở lại app: mọi thứ trong RAM mất, file ghi nhận còn."""
    so_windows._hidden_by_us.clear()
    so_windows._record_loaded = False


def test_mo_lai_app_an_them_khong_lam_mat_ghi_nhan_cu(fake_gui):
    # Đo máy 1: app mở lại, DAW bật thêm một cửa sổ, app ẩn nó → file ghi nhận
    # bị ghi đè chỉ còn cửa sổ mới, plugin đã ẩn từ lần trước bị quên.
    fake_gui.wins[21]["vis"] = True
    fake_gui.wins[23]["vis"] = True
    so_windows.hide_all()
    _mo_lai_app()
    fake_gui.wins[22]["vis"] = True                 # cửa sổ mới mọc lên
    so_windows.hide_all()
    _mo_lai_app()
    fake_gui.shown.clear()
    so_windows.show_all(focus_main=False)
    assert {h for h, _ in fake_gui.shown} == {21, 22, 23}
