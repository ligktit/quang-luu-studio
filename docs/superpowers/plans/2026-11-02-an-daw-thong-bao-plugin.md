# Bỏ khoá kỹ thuật · Cửa sổ cảnh báo Tự sửa âm thanh · Ẩn/hiện từng cửa sổ plugin — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bỏ PIN/phiên kỹ thuật, thay bằng tự ẩn DAW khi mở app (nút hiện/ẩn chuyển vào Cài đặt). Cảnh báo Tự sửa âm thanh hiện trong một cửa sổ riêng. KTV bật/tắt được từng cửa sổ plugin hoặc ASIO mà không hiện cả DAW.

**Architecture:** Module cấu hình mới `core/daw_visibility.py` thay `core/kiosk.py`, gồm cả bước chuyển cấu hình cũ. `core/so_windows.py` có thêm API theo từng cửa sổ (`list_windows`, `show_window`, `hide_window`) và nhận diện công cụ ASIO. Mục "Cửa sổ {DAW}" trong `SettingsDialog` thay mục "Chế độ khách". Dải cảnh báo ở header được thay bằng `ui/dialogs/audio_alert_dialog.py` (non-modal).

**Tech Stack:** Python 3.13, PySide6, pywin32 (win32gui/win32con/win32process), psutil, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-11-02-an-daw-thong-bao-plugin-design.md`

## Global Constraints

- Nhánh mới `feat/an-daw-plugin` tách từ `feat/velopack-installer`, làm trong worktree riêng (superpowers:using-git-worktrees). Cây làm việc gốc có thay đổi chưa commit: không đụng tới, không mang sang.
- Chạy test bằng Python Windows của repo gốc, trỏ vào worktree (`<WT>` = đường dẫn Windows của worktree):
  `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest <WT>\tests\<đường dẫn> -q -p no:cacheprovider --rootdir=<WT>"`.
  Dưới đây gọi tắt là `PYTEST <đường dẫn>`. Chạy xong: `git checkout app_config.json`.
- Mọi chữ hiển thị là tiếng Việt có dấu. Tên DAW lấy từ `daw.active().display_name`, đuôi bản mẫu từ `daw.active().template_extension`.
- Phải chạy được với cả Studio One lẫn Cubase (`daw.active()`).
- Key settings mới: `"daw_windows": {"auto_hide": bool, "restore_template": bool}`. Mặc định khi chưa có: `auto_hide=True`, `restore_template=False`.
- Chuyển cấu hình cũ: `restore_template = tech_lock.enabled AND tech_lock.get("restore_template", True)`, `auto_hide = True`, sau đó **xoá** key `tech_lock`.
- Thay đổi trong mục "Cửa sổ {DAW}" của Cài đặt áp dụng **ngay khi bấm**, không chờ nút Lưu.
- Phần 3 (từng cửa sổ plugin) **phải có trong bản phát hành này**. Nếu spike (Task 5) cho thấy không hiện riêng được cửa sổ owned thì làm phương án dự phòng (Task 8).

## Review Focus

1. **Máy cũ đang bật khoá, settings có `tech_lock` hỏng** (không phải dict, thiếu trường): chuyển cấu hình không được ném lỗi. `restore_template` mặc định False, `auto_hide` True. Có test trong Task 1.
2. **DAW chưa chạy hoặc thiếu pywin32** khi mở Cài đặt: danh sách cửa sổ trống kèm dòng giải thích, nút Hiện/Ẩn tất cả không làm crash. Có test trong Task 7.
3. **HWND chết giữa lúc quét và lúc bấm** (KTV đóng plugin, DAW thoát): `show_window`/`hide_window` trả False, không ném lỗi, danh sách tự quét lại. Có test trong Task 6.
4. **Lượt kiểm tra chạy lại (`"rerun"`) khi cửa sổ cảnh báo đang mở**: cập nhật nội dung, không mở cửa sổ thứ hai. Báo cáo sạch thì đóng cửa sổ. Có test trong Task 4.
5. **Tự sửa âm thanh đóng/mở lại Cubase giữa buổi khi ô tự ẩn đang bật**: DAW mới bật lên phải bị ẩn. Ô đang tắt thì không ẩn. Có test trong Task 2.

---

### Task 1: Module cấu hình `core/daw_visibility.py` + chuyển cấu hình cũ

**Files:**
- Create: `core/daw_visibility.py`
- Test: `tests/core/test_daw_visibility.py`

**Interfaces:**
- Produces:
  - `bind(settings: dict | None) -> None`
  - `auto_hide() -> bool`, `set_auto_hide(value: bool) -> None`
  - `restore_template_enabled() -> bool`, `set_restore_template(value: bool) -> None`
  - `migrate(settings: dict) -> bool`: hàm thuần, sửa dict tại chỗ, trả True nếu có đổi (để caller lưu).
  - `_write(**patch) -> dict`: vá cả đĩa (`ConfigManager`) lẫn dict đang sống, giống hệt `kiosk._write` (lý do ghi trong docstring `kiosk.bind`).

- [ ] **Step 1: Viết test (fixture giống `tests/core/test_kiosk.py:7-25`, monkeypatch `_write` vá key `daw_windows` của dict sống)**

```python
def test_mac_dinh_khi_chua_co_cau_hinh(isolated_settings):
    assert daw_visibility.auto_hide() is True
    assert daw_visibility.restore_template_enabled() is False

def test_ghi_va_doc_lai(isolated_settings):
    daw_visibility.set_auto_hide(False); daw_visibility.set_restore_template(True)
    assert daw_visibility.auto_hide() is False
    assert daw_visibility.restore_template_enabled() is True

@pytest.mark.parametrize("old, want_restore", [
    ({"enabled": True, "pin_hash": "ab", "pin_salt": "cd"}, True),
    ({"enabled": True, "restore_template": False}, False),
    ({"enabled": False, "restore_template": True}, False),
    ("không phải dict", False),
])
def test_migrate_tu_tech_lock(old, want_restore):
    s = {"tech_lock": old}
    assert daw_visibility.migrate(s) is True
    assert "tech_lock" not in s
    assert s["daw_windows"] == {"auto_hide": True, "restore_template": want_restore}

def test_migrate_khong_dong_khi_da_co_cau_hinh_moi():
    s = {"daw_windows": {"auto_hide": False, "restore_template": True}}
    assert daw_visibility.migrate(s) is False
    assert s["daw_windows"] == {"auto_hide": False, "restore_template": True}

def test_migrate_may_moi_khong_co_gi():
    s = {}
    assert daw_visibility.migrate(s) is True
    assert s["daw_windows"] == {"auto_hide": True, "restore_template": False}

def test_daw_windows_hong_thi_dung_mac_dinh(isolated_settings):
    isolated_settings["daw_windows"] = "rác"
    assert daw_visibility.auto_hide() is True
```

- [ ] **Step 2:** `PYTEST tests\core\test_daw_visibility.py`. Kỳ vọng: FAIL (ImportError).
- [ ] **Step 3:** Viết `core/daw_visibility.py` theo Interfaces. Có `tech_lock` và đồng thời có `daw_windows` hợp lệ: chỉ xoá `tech_lock`, trả True.
- [ ] **Step 4:** `PYTEST tests\core\test_daw_visibility.py`. Kỳ vọng: PASS.
- [ ] **Step 5:** Commit `feat(daw-hide): cấu hình daw_windows + chuyển từ tech_lock`.

---

### Task 2: Dashboard bỏ khoá kỹ thuật, tự ẩn DAW theo `daw_visibility`

**Files:**
- Modify: `frontend_qt.py`
  - khoảng dòng 163-169: bind và migrate;
  - 393-395: shortcut Ctrl+Alt+Shift+T;
  - 513-609: `_apply_kiosk_visibility`, `_kiosk_session_tick`, `_lock_studio_one`, `_toggle_tech_session`;
  - 1516-1567: `_auto_launch_apps`;
  - 3418-3458: `_on_eye_toggle_studio_one`, `_on_toggle_studio_one`;
  - 3862: tab order;
  - 4336-4344: thoát app.
- Modify: `ui/panels/header.py:166-191`: bỏ `_eye_btn`, bỏ `_tech_badge`. Sửa chú thích dòng 143 (Hỗ trợ luôn hiện).
- Modify: `ui/audio_doctor_bridge.py:27-32`: `launch_daw`.
- Modify: `core/so_windows.py`: xoá `HideGuard` (dòng ~468-510) và mọi chú thích nhắc "khoá kỹ thuật".
- Test: `tests/ui/test_startup_template_restore.py`, `tests/ui/test_settings_daw_kind.py:84-86`, `tests/ui/test_exit_close_studio_one.py`, `tests/ui/test_audio_doctor_bridge.py`

**Interfaces:**
- Consumes: Task 1 `daw_visibility.*`.
- Produces:
  - `MainDashboard._on_toggle_studio_one() -> None`: không còn chặn khoá. Settings (Task 3) gọi hàm này.
  - `dashboard._eye_btn` **không còn tồn tại**.
  - `dashboard._support_btn` luôn visible.

- [ ] **Step 1: Sửa test hiện có cho khớp hành vi mới, rồi thêm test mới.** Ở cả ba file test UI, thay mọi `patch("core.kiosk.is_enabled"/"restore_template_enabled"/"is_locked", …)` bằng:
  - `patch("core.daw_visibility.restore_template_enabled", return_value=True)`;
  - `patch("core.daw_visibility.auto_hide", return_value=<giá trị cũ của is_locked>)`.

  Thêm test:

```python
# tests/ui/test_startup_template_restore.py
def test_tu_an_bat_thi_an_khi_daw_dang_chay():   # auto_hide=True, so_running=True, không restore
    ... MainDashboard._auto_launch_apps(self); hide_all.assert_called_once()
def test_tu_an_tat_thi_khong_an():               # auto_hide=False → hide_all/hide_when_ready không được gọi
def test_vua_khoi_chay_thi_an_khi_san_sang():    # auto_launch=True, so_running=False → hide_when_ready.assert_called_once()

# tests/ui/test_audio_doctor_bridge.py
def test_launch_daw_an_khi_tu_an_bat(...):       # patch daw_visibility.auto_hide=True, os.path.exists=True
    assert actions.launch_daw() is True; hide_when_ready.assert_called_once()
def test_launch_daw_khong_an_khi_tu_an_tat(...): hide_when_ready.assert_not_called()

# tests/ui/test_audio_doctor_ui.py (dùng _make_dashboard có sẵn)
def test_header_khong_con_nut_mat_va_ho_tro_luon_hien(qapp, mock_engine, qtbot):
    d = _make_dashboard(qtbot)
    assert getattr(d, "_eye_btn", None) is None
    assert d._support_btn.isVisibleTo(d)
```

- [ ] **Step 2:** Chạy `PYTEST tests\ui\test_startup_template_restore.py tests\ui\test_settings_daw_kind.py tests\ui\test_exit_close_studio_one.py tests\ui\test_audio_doctor_bridge.py tests\ui\test_audio_doctor_ui.py::test_header_khong_con_nut_mat_va_ho_tro_luon_hien`. Kỳ vọng: FAIL.
- [ ] **Step 3: Sửa code.**
  - Lúc khởi tạo: `daw_visibility.bind(self.settings)`. Nếu `daw_visibility.migrate(self.settings)` trả True thì lưu bằng `backend.ConfigManager.save_settings(self.settings)`. Phải chạy trước `_auto_launch_apps`.
  - Xoá hẳn: `_apply_kiosk_visibility`, `_kiosk_session_tick`, `_lock_studio_one`, `_toggle_tech_session`, `_tech_shortcut`, `_kiosk_timer`, `_so_hide_guard`, `_on_eye_toggle_studio_one`, `_studio_one_visible`. Xoá luôn mọi chỗ gọi tới chúng.
  - `_auto_launch_apps`: điều kiện phục hồi bản mẫu đổi thành `daw_visibility.restore_template_enabled()`. Điều kiện ẩn đổi thành `daw_visibility.auto_hide()`. Đổi tiền tố log `[KIOSK]` thành `[DAW-HIDE]`.
  - `_on_toggle_studio_one`: bỏ nhánh `is_locked`.
  - Thoát app: `hide_all()` khi `daw_visibility.auto_hide()`.
  - `launch_daw`: sau `launch_app`, nếu `daw_visibility.auto_hide()` thì gọi `so_windows.hide_when_ready()`.
- [ ] **Step 4:** Chạy lại lệnh ở Step 2. Kỳ vọng: PASS. Thêm `grep -rn "kiosk\|_eye_btn\|tech_badge\|HideGuard" frontend_qt.py ui/panels core/so_windows.py ui/audio_doctor_bridge.py`: kỳ vọng không còn kết quả nào.
- [ ] **Step 5:** Commit `feat(daw-hide): bỏ khoá kỹ thuật trên dashboard, tự ẩn DAW theo cấu hình`.

---

### Task 3: Mục "Cửa sổ {DAW}" trong Cài đặt (chưa có danh sách) + xoá kiosk

**Files:**
- Modify: `ui/dialogs/settings_dialog.py`: thay `_build_kiosk`, `_refresh_kiosk_ui`, `_kiosk_apply`, `_sync_dashboard_kiosk`, `_on_kiosk_toggled`, `_on_kiosk_unlock`, `_on_kiosk_set_pin` (khoảng dòng 410 và 1017-1190). Giữ `_on_kiosk_snapshot`, đổi tên thành `_on_template_snapshot`.
- Delete: `core/kiosk.py`, `ui/dialogs/tech_unlock.py`, `tests/core/test_kiosk.py`
- Test: `tests/ui/test_settings_daw_windows.py` (mới, dựng dialog như `tests/ui/test_settings_daw_kind.py`)

**Interfaces:**
- Consumes: Task 1 `daw_visibility.*`; Task 2 `dashboard._on_toggle_studio_one()`; `so_windows.any_visible()`.
- Produces (Task 7 thêm danh sách vào đây):
  - `SettingsDialog._build_daw_windows(vl) -> None`
  - `SettingsDialog._refresh_daw_windows_ui() -> None`
  - widget `self._cb_auto_hide`, `self._cb_restore_tpl`, `self._btn_toggle_all`, `self._daw_list_box` (một `QVBoxLayout` trống, để Task 7 điền).

- [ ] **Step 1: Viết test**

```python
def test_muc_cua_so_daw_khong_con_pin(qapp, mock_engine, qtbot):
    dlg = _dialog(qtbot)
    assert not hasattr(dlg, "_btn_kiosk_pin") and not hasattr(dlg, "_cb_kiosk")

def test_tick_tu_an_ghi_ngay(qapp, mock_engine, qtbot):
    dlg = _dialog(qtbot)
    with patch("core.daw_visibility.set_auto_hide") as setter:
        dlg._cb_auto_hide.click()
    setter.assert_called_once_with(False)          # mặc định đang bật

def test_tick_phuc_hoi_ban_mau_ghi_ngay(...):     # tương tự với set_restore_template(True)

def test_nut_hien_an_tat_ca_goi_dashboard_va_doi_chu(qapp, mock_engine, qtbot):
    dlg = _dialog(qtbot)
    with patch("core.so_windows.any_visible", return_value=False):
        dlg._refresh_daw_windows_ui()
    assert dlg._btn_toggle_all.text().startswith("Hiện")
    with patch.object(dlg._dashboard, "_on_toggle_studio_one") as t, \
         patch("core.so_windows.any_visible", return_value=True):
        dlg._btn_toggle_all.click()
    t.assert_called_once()
    assert dlg._btn_toggle_all.text().startswith("Ẩn")
```

- [ ] **Step 2:** `PYTEST tests\ui\test_settings_daw_windows.py`. Kỳ vọng: FAIL.
- [ ] **Step 3: Viết mục mới**
  - Tiêu đề thẻ: `Cửa sổ {name}`.
  - Ô tick `Tự ẩn {name} khi mở app` và ô tick `Phục hồi bản mẫu {ext} mỗi lần khởi động`, cả hai gọi setter ngay khi bấm.
  - Nút `Hiện {name} + plugin` / `Ẩn {name} + plugin`.
  - Giữ nguyên nút `Chốt bản mẫu {ext}`, nhãn thông tin bản mẫu và dòng ghi chú bản mẫu.
  - Bỏ hết chữ "chế độ khách", "khoá", "PIN".
  - Xoá các file trong mục Delete.
- [ ] **Step 4:** Chạy `PYTEST tests\ui\test_settings_daw_windows.py tests\ui\test_settings_daw_kind.py`, kỳ vọng PASS. Chạy `grep -rn "kiosk\|tech_unlock\|tech_lock" --include=*.py .`, kỳ vọng chỉ còn trong `core/daw_visibility.py` (phần migrate) và test của nó.
- [ ] **Step 5:** Commit `feat(daw-hide): mục Cửa sổ DAW trong Cài đặt, xoá khoá kỹ thuật`.

---

### Task 4: Cửa sổ cảnh báo Tự sửa âm thanh

**Files:**
- Create: `ui/dialogs/audio_alert_dialog.py`
- Modify: `frontend_qt.py:1319-1336` (`_on_audio_doctor_report`)
- Modify: `ui/panels/header.py:61-71` (bỏ `_audio_warn_btn`)
- Test: `tests/ui/test_audio_doctor_ui.py`: thay `test_dai_canh_bao_hien_loi_nang_nhat_va_an_khi_on` (dòng 60-71)

**Interfaces:**
- Produces:
  - `class AudioAlertDialog(QDialog)`: `__init__(self, dashboard)`, non-modal.
    - `set_report(report) -> None` điền danh sách `finding.message` của `report.problems()`.
    - `self.fix_btn` ("Tự sửa"): đóng cửa sổ rồi gọi `dashboard._open_audio_doctor()`.
    - `self.later_btn` ("Để sau"): đóng cửa sổ.
  - `MainDashboard._audio_alert_dialog: AudioAlertDialog | None`
  - `MainDashboard._set_audio_fix_highlight(on: bool) -> None`. Bật thì nút `_func_buttons["Tự sửa âm thanh"]` được `setColor(C["accent"])` và `setActive(True)`. Tắt thì `setColor(C["orange"])` và `setActive(False)`.

- [ ] **Step 1: Viết test** (dùng `_svc`, `_Mic`, `_make_dashboard` có sẵn)

```python
def test_loi_luc_mo_app_bat_cua_so_canh_bao(...):
    rep = svc.run("check", "startup")
    with patch.object(dashboard, "_a11y_speak") as speak:
        dashboard._on_audio_doctor_report(rep, "run")
    dlg = dashboard._audio_alert_dialog
    assert dlg.isVisible() and "Kênh Mic đang tắt" in dlg.accessibleDescription()
    speak.assert_called_once()
    assert not hasattr(dashboard, "_audio_warn_btn")

def test_rerun_cap_nhat_khong_mo_cua_so_thu_hai(...):
    dashboard._on_audio_doctor_report(rep, "run"); first = dashboard._audio_alert_dialog
    dashboard._on_audio_doctor_report(rep, "rerun")
    assert dashboard._audio_alert_dialog is first

def test_bao_cao_sach_dong_cua_so_va_tat_vien(...):
    dashboard._on_audio_doctor_report(rep, "run"); _Mic.fixed = True
    dashboard._on_audio_doctor_report(svc.run("check", "startup"), "rerun")
    assert not dashboard._audio_alert_dialog.isVisible()
    assert dashboard._func_buttons["Tự sửa âm thanh"]._active is False

def test_ket_qua_tu_hop_thoai_khong_bat_canh_bao(...):   # action "button" có lỗi → không mở cửa sổ, nút vẫn sáng
    dashboard._on_audio_doctor_report(rep, "button")
    assert dashboard._audio_alert_dialog is None or not dashboard._audio_alert_dialog.isVisible()
    assert dashboard._func_buttons["Tự sửa âm thanh"]._active is True

def test_bam_tu_sua_dong_canh_bao_va_mo_hop_thoai(...):
    dashboard._on_audio_doctor_report(rep, "run")
    with patch.object(dashboard, "_open_audio_doctor") as op:
        dashboard._audio_alert_dialog.fix_btn.click()
    op.assert_called_once(); assert not dashboard._audio_alert_dialog.isVisible()
```

- [ ] **Step 2:** `PYTEST tests\ui\test_audio_doctor_ui.py`. Kỳ vọng: FAIL.
- [ ] **Step 3: Viết code**
  - Viết `AudioAlertDialog`:
    - nền tối tường minh giống `AudioDoctorDialog` (`C['bg']`, `FONT`);
    - tiêu đề `Phát hiện {N} vấn đề âm thanh`;
    - mỗi lỗi một dòng chữ ≥16px, word-wrap;
    - `accessibleName` là `Cảnh báo âm thanh`, `accessibleDescription` là nối các câu lỗi.
  - Hiện cửa sổ: `show()`, `raise_()`, `activateWindow()`.
  - Logic `_on_audio_doctor_report`:
    - Báo cáo có lỗi và `action in ("run", "rerun")`: tạo hoặc tái dùng cửa sổ, gọi `set_report`, hiện lên.
    - Mọi action: `_set_audio_fix_highlight(bool(problems))`.
    - Không còn lỗi: đóng cửa sổ nếu đang mở.
    - TTS giữ như cũ.
  - Xoá `_audio_warn_btn` ở header.
- [ ] **Step 4:** `PYTEST tests\ui\test_audio_doctor_ui.py tests\ui\test_qt_warnings.py`. Kỳ vọng: PASS.
- [ ] **Step 5:** Commit `feat(audio-doctor): cảnh báo lỗi trong cửa sổ riêng thay dải header`.

---

### Task 5: Spike: hiện riêng cửa sổ plugin khi cửa sổ DAW chính đang ẩn (máy dev, thủ công)

**Files:**
- Create (bỏ đi sau spike, không commit): `<scratchpad>/daw_window_spike.py`
- Create: `docs/superpowers/specs/2026-11-02-an-daw-plugin-spike-findings.md`

- [ ] **Step 1:** Viết script nhận tham số `list | hideall | show <hwnd> | hide <hwnd>`. Script dùng `so_windows.all_windows()` và với mỗi HWND in ra: `title`, `class`, `IsWindowVisible`, `GetWindow(h, GW_OWNER)`, `GetParent`, `WS_EX_TOOLWINDOW` / `WS_EX_APPWINDOW`, tên tiến trình. Chạy bằng `.venv` Windows với `daw_kind` tương ứng.
- [ ] **Step 2:** Studio One (bài mẫu có Auto-Tune đang mở):
  1. `list` và ghi lại danh sách;
  2. `hideall`;
  3. `show <hwnd Auto-Tune>`.

  Ghi lại: plugin có hiện không, có nhận chuột và bàn phím (chỉnh Key) không, cửa sổ chính có tự hiện theo không, có hiện trên thanh tác vụ không. Sau đó `hide <hwnd>` và kiểm tra plugin ẩn lại.
- [ ] **Step 3:** Lặp lại Step 2 với Cubase 13 (`D:\QLS\mau.cpr`) và bảng điều khiển ASIO nếu mở được. Quit Cubase qua cửa sổ `SmtgMain`.
- [ ] **Step 4:** Ghi findings: bảng DAW × kết quả, quy tắc lọc cửa sổ đề xuất (theo title/class/owner thực tế), và kết luận cho từng DAW: **cách 1 chạy được** hay **cần dự phòng (Task 8)**. Commit file findings `docs(spike): hiện riêng cửa sổ plugin khi DAW ẩn`.

---

### Task 6: API từng cửa sổ trong `core/so_windows.py` + công cụ ASIO

**Files:**
- Modify: `core/so_windows.py`
- Modify: `frontend_qt.py:3459-~3540`: xoá `_on_toggle_asiolink`. Danh sách tên tiến trình và từ khoá chuyển sang `so_windows`.
- Test: `tests/core/test_so_windows_daw.py` (giả lập `win32gui` bằng MagicMock như `test_main_windows_loc_theo_tieu_de_cubase`)

**Interfaces:**
- Consumes: kết quả lọc của Task 5.
- Produces:
  - `@dataclass(frozen=True) class WindowEntry: hwnd: int; title: str; is_main: bool; visible: bool; source: str  # "daw" | "asio"`
  - `ASIO_PROCESS_NAMES: tuple[str, ...]`, `ASIO_TITLE_KEYWORDS: tuple[str, ...]` (giá trị copy nguyên từ `_on_toggle_asiolink`)
  - `asio_windows() -> list[int]`
  - `list_windows() -> list[WindowEntry]`: cửa sổ DAW trước, trong đó cửa sổ chính đứng đầu; sau đó là cửa sổ ASIO. Đã áp quy tắc lọc của Task 5 (tối thiểu: bỏ title rỗng).
  - `show_window(hwnd: int, above_topmost: bool = False) -> bool`: `SW_SHOW` + `force_foreground`. Nếu `above_topmost` thì thêm `SetWindowPos(hwnd, HWND_TOPMOST, …)` rồi `HWND_NOTOPMOST`, để plugin nổi lên trên app đang "Ghim trên cùng". Trả False nếu `not IsWindow(hwnd)` hoặc gặp lỗi.
  - `hide_window(hwnd: int) -> bool`: `SW_HIDE`. Trả False nếu `not IsWindow(hwnd)` hoặc gặp lỗi.
  - `hide_all` / `show_all` / `any_visible` **chỉ** tính cửa sổ DAW (giữ nguyên).

- [ ] **Step 1: Viết test**

```python
def test_list_windows_chinh_dau_tien_bo_title_rong():
    # all_windows → [21, 22, 23], titles {21:"Auto-Tune Pro", 22:"", 23:"Studio One - mau"}, asio_windows → [31] "ASIO Link Pro"
    entries = so_windows.list_windows()
    assert [e.hwnd for e in entries] == [23, 21, 31]
    assert entries[0].is_main and entries[2].source == "asio"

def test_show_window_hwnd_chet_tra_false():
    win32gui.IsWindow.return_value = False
    assert so_windows.show_window(99) is False; win32gui.ShowWindow.assert_not_called()

def test_hide_window_chi_an_dung_cua_so():
    assert so_windows.hide_window(21) is True
    win32gui.ShowWindow.assert_called_once_with(21, so_windows.SW_HIDE)

def test_show_all_khong_dong_toi_asio():   # patch asio_windows → [31]; ShowWindow không được gọi với 31
```

- [ ] **Step 2:** `PYTEST tests\core\test_so_windows_daw.py`. Kỳ vọng: FAIL.
- [ ] **Step 3:** Cài đặt theo Interfaces. `asio_windows()` dùng `EnumWindows`, khớp tên tiến trình trước rồi đến từ khoá title, giống logic cũ.
- [ ] **Step 4:** `PYTEST tests\core\test_so_windows_daw.py`, kỳ vọng PASS. `grep -n "_on_toggle_asiolink" -r .`, kỳ vọng rỗng.
- [ ] **Step 5:** Commit `feat(daw-hide): ẩn/hiện từng cửa sổ DAW và công cụ ASIO`.

---

### Task 7: Danh sách cửa sổ trong mục "Cửa sổ {DAW}"

**Files:**
- Modify: `ui/dialogs/settings_dialog.py` (`_build_daw_windows`, `_refresh_daw_windows_ui` từ Task 3)
- Test: `tests/ui/test_settings_daw_windows.py`

**Interfaces:**
- Consumes: Task 6 `list_windows`, `show_window`, `hide_window`, `WindowEntry`. Task 3: `self._daw_list_box`, `self._btn_toggle_all`.
- Produces:
  - `self._btn_refresh_windows` ("Làm mới");
  - `self._window_switches: dict[int, QCheckBox]` (hwnd → công tắc; nhãn là title, thêm ` (cửa sổ chính)` nếu `is_main`, thêm ` · ASIO` nếu `source == "asio"`).

- [ ] **Step 1: Viết test**

```python
E = so_windows.WindowEntry
def test_danh_sach_hien_dung_trang_thai(...):
    with patch("core.so_windows.list_windows", return_value=[E(1, "Studio One - mau", True, False, "daw"),
                                                             E(2, "Auto-Tune Pro", False, False, "daw")]):
        dlg._refresh_daw_windows_ui()
    assert "(cửa sổ chính)" in dlg._window_switches[1].text()
    assert dlg._window_switches[2].isChecked() is False

def test_bat_cong_tac_chi_hien_cua_so_do(...):
    with patch("core.so_windows.show_window", return_value=True) as show, patch("core.so_windows.list_windows", ...):
        dlg._window_switches[2].click()
    show.assert_called_once_with(2, above_topmost=False)

def test_hwnd_chet_thi_quet_lai(...):   # show_window → False ⇒ list_windows được gọi lại (call_count tăng), không ném lỗi

def test_daw_chua_chay_danh_sach_trong_co_giai_thich(...):
    with patch("core.so_windows.list_windows", return_value=[]):
        dlg._refresh_daw_windows_ui()
    assert dlg._window_switches == {}   # và có QLabel chứa "chưa chạy" hoặc "không có cửa sổ"

def test_hien_an_tat_ca_cap_nhat_danh_sach(...):   # bấm _btn_toggle_all ⇒ list_windows được gọi lại
```

- [ ] **Step 2:** `PYTEST tests\ui\test_settings_daw_windows.py`. Kỳ vọng: FAIL.
- [ ] **Step 3:** Cài đặt:
  - Mỗi lần refresh: xoá các widget cũ trong `_daw_list_box` rồi dựng lại.
  - Công tắc được bấm gọi `show_window` hoặc `hide_window`. Kết quả trả về False thì toast `Cửa sổ không còn — đã quét lại` và refresh.
  - `_refresh_daw_windows_ui` chạy lúc dựng dialog, khi bấm "Làm mới", và sau khi bấm Hiện/Ẩn tất cả.
  - Gọi `show_window(hwnd, above_topmost=bool(settings.get("always_on_top")))`.
- [ ] **Step 4:** `PYTEST tests\ui\test_settings_daw_windows.py`. Kỳ vọng: PASS.
- [ ] **Step 5:** Commit `feat(daw-hide): danh sách cửa sổ plugin/ASIO bật tắt riêng trong Cài đặt`.

---

### Task 8 (chỉ làm nếu Task 5 kết luận cần dự phòng cho ít nhất một DAW): hiện cửa sổ chính ngoài màn hình

**Files:**
- Modify: `core/so_windows.py`
- Modify: `core/daw.py` (hồ sơ DAW nào cần thì thêm cờ `owned_plugin_needs_offscreen_main: bool`)
- Test: `tests/core/test_so_windows_daw.py`

**Interfaces:**
- Produces:
  - `show_window(hwnd)`: nếu hồ sơ DAW đang chọn có cờ trên và hwnd không phải cửa sổ chính, thì trước khi hiện plugin phải đưa cửa sổ chính ra ngoài màn hình. Cụ thể: lưu `GetWindowRect` của cửa sổ chính vào biến module `_offscreen: dict[int, tuple]`, thêm `WS_EX_TOOLWINDOW` để bỏ khỏi thanh tác vụ, `SetWindowPos` tới (-32000, -32000), rồi `SW_SHOWNOACTIVATE`.
  - `is_effectively_visible(hwnd) -> bool`: `IsWindowVisible(hwnd) and hwnd not in _offscreen`. Dùng hàm này trong `any_visible`, `list_windows().visible` và `hide_all`.
  - `hide_all()` / `hide_window(main)` / `show_all()`: trả cửa sổ chính về vị trí và style cũ, xoá khỏi `_offscreen`, sau đó mới ẩn hoặc hiện như thường.

- [ ] **Step 1:** Viết test:
  - `test_offscreen_main_van_tinh_la_an` (`any_visible()` False khi chỉ có main nằm trong `_offscreen`);
  - `test_show_all_tra_vi_tri_cu` (SetWindowPos được gọi lại với rect đã lưu);
  - `test_dao_khong_offscreen_voi_daw_khong_co_co`.
- [ ] **Step 2:** Chạy `PYTEST tests\core\test_so_windows_daw.py`, kỳ vọng FAIL.
- [ ] **Step 3:** Cài đặt.
- [ ] **Step 4:** Chạy lại, kỳ vọng PASS. Lặp lại Task 5 Step 2/3 bằng app thật. Ghi thêm vào findings: DAW có lưu vị trí ngoài màn hình vào bài hoặc layout không (đóng DAW có lưu rồi mở lại, xem cửa sổ chính nằm đâu).
- [ ] **Step 5:** Commit `feat(daw-hide): dự phòng hiện plugin bằng cửa sổ chính ngoài màn hình`.

---

### Task 9: Chạy toàn bộ test + kiểm thử trên máy dev

- [ ] **Step 1:** Chạy toàn suite ở chế độ nền (>10 phút), bỏ `tests/test_recorder_worker_e2e.py`. Kỳ vọng: không có test đỏ mới so với `feat/velopack-installer`. Sau đó `git checkout app_config.json` và đặt lại `daw_kind`, `auto_launch_studio_one`, `studio_one_path` trong `settings.json`.
- [ ] **Step 2: Kiểm tay** bằng app chạy từ source trong worktree (chép `activation.json` từ gốc repo). Làm với cả Studio One và Cubase:
  1. `settings.json` có `tech_lock` bật khoá → mở app: DAW tự ẩn, `tech_lock` biến mất, ô phục hồi bản mẫu đang tick.
  2. Header không còn nút mắt, nút Hỗ trợ có mặt. Ctrl+Alt+Shift+T không làm gì.
  3. Cài đặt → Hiện tất cả / Ẩn tất cả hoạt động.
  4. Trong danh sách bật riêng Auto-Tune: chỉnh được Key, DAW chính không lộ. Tắt thì ẩn lại.
  5. Tắt mic trong DAW rồi mở lại app: cửa sổ cảnh báo hiện lên nổi trên DAW. Bấm "Tự sửa" → hộp thoại sửa chạy. Nút thanh dưới hết sáng.
  6. Cubase: Tự sửa đóng/mở lại Cubase → Cubase mới bật lên vẫn bị ẩn.
- [ ] **Step 3:** Ghi kết quả kiểm tay vào cuối file findings rồi commit.
