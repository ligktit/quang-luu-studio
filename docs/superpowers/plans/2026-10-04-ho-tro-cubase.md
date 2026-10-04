# Hỗ trợ Cubase (lớp DAW adapter) — Kế hoạch triển khai

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App chạy được với Cubase (12+) y như với Studio One: mở bài mẫu `.cpr`, ẩn/hiện, đóng không lưu, phục hồi bản mẫu, gửi MIDI đúng giá trị; người dùng chọn DAW trong Cài đặt; Studio One không đổi hành vi.

**Architecture:** Gom mọi thứ "biết Studio One" (từ khoá process/tiêu đề, đuôi file, tên hiển thị, giá trị cân chỉnh riêng) vào một **hồ sơ DAW** bất biến (`core/daw/`), chọn theo `settings["daw_kind"]`. `so_windows`, `_lifecycle`, `so_template`, `mixer`, `AppConfig` hỏi hồ sơ đang chọn thay vì hằng cứng. Cubase nhận lệnh qua script MIDI Remote `cubase/QuangLuu_QuangLuuMIDI.js` (đã đo chạy được trên Cubase 13.0.10), bộ cài chép script vào thư mục Steinberg.

**Tech Stack:** Python 3.13 (Windows), PySide6, pywin32, psutil, mido; pytest chạy bằng Python Windows trong `.venv` (xem lệnh dưới); JavaScript ES5 cho MIDI Remote API v1.

**Spec:** `docs/NGHIEN_CUU_HO_TRO_CUBASE.md` (mục 2, 3 và các số đo ở mục 7).

## Global Constraints

- Chạy test (từ WSL, bắt buộc Python Windows): `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\<test> -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`. Sau khi chạy suite: `git checkout app_config.json` (suite đổi line-ending).
- Studio One phải **không đổi hành vi**: mọi test hiện có trong `tests/core/test_close_studio_one_no_save.py`, `test_so_template.py`, `test_so_ready_watcher.py`, `tests/ui/test_startup_template_restore.py`, `test_exit_close_studio_one.py`, `test_midi_resync_on_so_ready.py`, `tests/test_surface_xml.py` phải xanh sau mỗi task.
- Khoá settings `studio_one_path`, `auto_launch_studio_one`, `auto_close_studio_one`, `studio_one_close_timeout`, `force_kill_studio_one` **giữ nguyên tên** (tránh migration); chỉ thêm `daw_kind` với giá trị `"studio_one"` (mặc định khi thiếu) hoặc `"cubase"`.
- Mặc định khi `daw_kind` thiếu/sai → hồ sơ Studio One.
- Script JS phải là ES5 (không `let/const/=>/template string`), test `tests/test_cubase_script.py` giữ xanh.
- Thứ tự kênh bài mẫu Cubase cố định: 0 Nhac, 1 Mic, 2 Vang, 3 Be; plugin pitch ở insert đầu tiên có plugin của kênh Mic.
- Số đo Cubase 13.0.10 dùng làm hằng: fader 0 dB = CC 100; Pitch Correct tham số 6 = Key, 7 = Scale, 3 = PitchCorrect; Scale: Major tâm 43, Minor tâm 85; Key trùng `key_midi_map` hiện có.
- Chuỗi hiển thị tiếng Việt có dấu; tên file/hàm không dấu như code hiện có.
- Không commit lên `main`: làm trên nhánh `cubase-adapter`; chỉ `git add` đúng file của task (working tree còn thay đổi UI dở của người khác: `ui/design_tokens.py`, `ui/dialogs/widget_builder.py`, `ui/panels/mode.py`, `ui/styles/main.qss`, `ui/components/mode_button.py`, `tests/ui/test_mode_button.py`, `tests/ui/test_qt_warnings.py` — **không đụng**).

## Review Focus

1. `settings.json` cũ không có `daw_kind` → mọi đường (so_windows, template, mixer) phải ra đúng Studio One; test ở Task 1 (`test_thieu_daw_kind_la_studio_one`).
2. Cubase có cửa sổ `Checking Licenses...` và `Cubase Pro` (class `SmtgMain`) trước/ngoài cửa sổ project → `main_windows()` không được nhận chúng; test ở Task 2 (`test_cubase_bo_qua_cua_so_khong_phai_project`).
3. Đường dẫn `.cpr` trong settings nhưng `daw_kind` vẫn là `studio_one` (người dùng quên đổi) → không được coi là file bài, không phục hồi bản mẫu, cảnh báo trong chẩn đoán; test ở Task 4 (`test_cpr_khong_phai_bai_studio_one`).
4. Người dùng đã tự cân chỉnh `scale_midi_map` (file overrides) rồi chuyển sang Cubase → override của người dùng phải thắng mặc định Cubase; test ở Task 6 (`test_override_nguoi_dung_thang_mac_dinh_daw`).
5. Hộp thoại Save của Cubase không phải `#32770`, nút là HWND `Button` nhãn `Don't Save` → `click_no_save` phải bấm đúng nút này bằng lớp win32 theo nhãn; test ở Task 2 (`test_hop_thoai_cubase_bam_nut_dont_save`).

---

### Task 0: Nhánh làm việc

**Files:** không sửa file.

- [ ] **Step 1: Tạo nhánh**

```bash
cd /mnt/d/Projects/quang-luu-studio && git checkout -b cubase-adapter
```

- [ ] **Step 2: Chạy nhanh bộ test nền (chuẩn so sánh)**

Run: lệnh pytest ở Global Constraints với `tests\core\test_close_studio_one_no_save.py tests\core\test_so_template.py tests\core\test_so_ready_watcher.py tests\test_surface_xml.py tests\test_cubase_script.py`
Expected: tất cả PASS (ghi lại số lượng).

---

### Task 1: Gói `core/daw` — hồ sơ DAW và cách chọn

**Files:**
- Create: `core/daw/__init__.py`
- Create: `core/daw/profiles.py`
- Test: `tests/core/test_daw.py`

**Interfaces:**
- Produces:
  - `core.daw.DawProfile` (dataclass frozen) với các trường:
    `kind: str`, `display_name: str`, `process_keywords: tuple[str, ...]`,
    `main_title_requires: tuple[str, ...]` (mọi từ phải có trong tiêu đề, so chữ thường),
    `project_extensions: tuple[str, ...]` (đuôi file mở bằng `os.startfile`),
    `template_extension: str` (`.song` / `.cpr`),
    `file_dialog_filter: str`,
    `fader_unity_cc: int`,
    `calibration: dict` (ghi đè mặc định cho `scale_midi_map`, `scale_values`; rỗng = dùng app_config),
    `remote_install_hint: str` (một dòng hướng dẫn cài phần nhận MIDI).
  - `core.daw.STUDIO_ONE`, `core.daw.CUBASE`, `core.daw.PROFILES: dict[str, DawProfile]`
  - `core.daw.active(settings=None) -> DawProfile`: đọc `settings["daw_kind"]`; `settings=None` → `ConfigManager.load_settings()`; thiếu/sai → `STUDIO_ONE`.
  - `core.daw.bind(settings: dict)`: gắn dict settings sống của app (giống `kiosk.bind`) để `active()` không đọc đĩa mỗi lần.
  - `core.daw.is_project_file(path, profile=None) -> bool`: đuôi là `profile.template_extension`.

- [ ] **Step 1: Viết test**

```python
# tests/core/test_daw.py
"""Hồ sơ DAW: chọn đúng hồ sơ theo settings, mặc định là Studio One."""
import pytest

from core import daw


@pytest.fixture(autouse=True)
def _unbind():
    daw.bind(None)
    yield
    daw.bind(None)


def test_thieu_daw_kind_la_studio_one():
    assert daw.active({}).kind == "studio_one"
    assert daw.active({"daw_kind": "khong_co"}).kind == "studio_one"
    assert daw.active({"daw_kind": None}).kind == "studio_one"


def test_chon_cubase():
    p = daw.active({"daw_kind": "cubase"})
    assert p.kind == "cubase"
    assert p.display_name == "Cubase"
    assert p.template_extension == ".cpr"
    assert ".cpr" in p.project_extensions
    assert p.process_keywords == ("cubase",)
    assert p.main_title_requires == ("cubase", "project")
    assert p.fader_unity_cc == 100
    assert p.calibration["scale_midi_map"] == {"Major": 43, "Minor": 85}
    assert p.calibration["scale_values"] == {"major": 43, "minor": 85}


def test_studio_one_giu_nguyen_hang_cu():
    p = daw.STUDIO_ONE
    assert p.process_keywords == ("studio one",)
    assert p.main_title_requires == ("studio one",)
    assert p.template_extension == ".song"
    assert ".songversion" in p.project_extensions
    assert p.fader_unity_cc == 76
    assert p.calibration == {}


def test_bind_dung_settings_song():
    live = {"daw_kind": "cubase"}
    daw.bind(live)
    assert daw.active().kind == "cubase"
    live["daw_kind"] = "studio_one"
    assert daw.active().kind == "studio_one"


def test_is_project_file_theo_ho_so():
    assert daw.is_project_file(r"C:\a\b.song", daw.STUDIO_ONE) is True
    assert daw.is_project_file(r"C:\a\b.CPR", daw.CUBASE) is True
    assert daw.is_project_file(r"C:\a\b.cpr", daw.STUDIO_ONE) is False
    assert daw.is_project_file("", daw.CUBASE) is False
    assert daw.is_project_file(None, daw.CUBASE) is False
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\core\test_daw.py`
Expected: FAIL `ModuleNotFoundError: No module named 'core.daw'`

- [ ] **Step 3: Viết `core/daw/profiles.py`**

```python
"""Hồ sơ từng DAW mà app điều khiển được.

Mọi thứ "khác nhau giữa Studio One và Cubase" nằm ở đây, phần còn lại của app
chỉ hỏi `core.daw.active()`. Thêm DAW mới = thêm một DawProfile, không sửa logic.

Số đo Cubase lấy từ docs/NGHIEN_CUU_HO_TRO_CUBASE.md mục 7 (Cubase Pro 13.0.10):
fader 0 dB = CC 100; Pitch Correct: Scale Major 22–63 (tâm 43), Minor 64–105 (tâm 85);
Key trùng key_midi_map hiện có nên không ghi đè.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DawProfile:
    kind: str
    display_name: str
    process_keywords: tuple          # so chữ thường với tên process (chứa là trúng)
    main_title_requires: tuple       # MỌI từ phải có trong tiêu đề cửa sổ chính
    project_extensions: tuple        # đuôi file bài → mở bằng os.startfile
    template_extension: str          # đuôi file bản mẫu (snapshot/restore)
    file_dialog_filter: str
    fader_unity_cc: int              # giá trị CC ứng với fader 0 dB
    calibration: dict = field(default_factory=dict)
    remote_install_hint: str = ""


STUDIO_ONE = DawProfile(
    kind="studio_one",
    display_name="Studio One",
    process_keywords=("studio one",),
    main_title_requires=("studio one",),
    project_extensions=(
        ".song", ".songversion", ".soundset", ".instrument",
        ".multiinstrument", ".pedalboard", ".channel", ".macro", ".fxchain",
    ),
    template_extension=".song",
    file_dialog_filter=(
        "Studio One Files (*.song *.exe);;Song Files (*.song);;"
        "Executable (*.exe);;All Files (*.*)"
    ),
    fader_unity_cc=76,
    calibration={},
    remote_install_hint="Options → External Devices → Add → QuangLuuMIDI (Receive From: QuangLuuMIDI, Send To: QLS_PhanHoi)",
)

CUBASE = DawProfile(
    kind="cubase",
    display_name="Cubase",
    process_keywords=("cubase",),
    # Cubase còn có cửa sổ "Checking Licenses..." và cửa sổ "Cubase Pro"
    # (class SmtgMain) — chỉ cửa sổ project mới có chữ "Project".
    main_title_requires=("cubase", "project"),
    project_extensions=(".cpr",),
    template_extension=".cpr",
    file_dialog_filter=(
        "Cubase Files (*.cpr *.exe);;Cubase Project (*.cpr);;"
        "Executable (*.exe);;All Files (*.*)"
    ),
    fader_unity_cc=100,
    calibration={
        "scale_midi_map": {"Major": 43, "Minor": 85},
        "scale_values": {"major": 43, "minor": 85},
    },
    remote_install_hint="Script MIDI Remote tự nhận khi có cổng QuangLuuMIDI + QLS_PhanHoi (chạy setup_all.bat)",
)

PROFILES = {p.kind: p for p in (STUDIO_ONE, CUBASE)}
DEFAULT_KIND = STUDIO_ONE.kind
```

- [ ] **Step 4: Viết `core/daw/__init__.py`**

```python
"""Chọn hồ sơ DAW đang dùng (Studio One / Cubase) theo settings["daw_kind"]."""
from core.daw.profiles import CUBASE, DEFAULT_KIND, PROFILES, STUDIO_ONE, DawProfile

__all__ = ["DawProfile", "STUDIO_ONE", "CUBASE", "PROFILES", "DEFAULT_KIND",
           "active", "bind", "is_project_file", "kind_of"]

_live_settings = None


def bind(settings):
    """Gắn dict settings sống của app (None = đọc file mỗi lần)."""
    global _live_settings
    _live_settings = settings if isinstance(settings, dict) else None


def kind_of(settings) -> str:
    kind = (settings or {}).get("daw_kind")
    return kind if kind in PROFILES else DEFAULT_KIND


def active(settings=None) -> DawProfile:
    """Hồ sơ DAW đang chọn. Thiếu/sai daw_kind → Studio One."""
    if settings is None:
        if _live_settings is not None:
            settings = _live_settings
        else:
            try:
                from core.config import ConfigManager
                settings = ConfigManager.load_settings() or {}
            except Exception:
                settings = {}
    return PROFILES[kind_of(settings)]


def is_project_file(path, profile=None) -> bool:
    if not path:
        return False
    profile = profile or active()
    return str(path).lower().endswith(profile.template_extension)
```

- [ ] **Step 5: Chạy test, xác nhận PASS**

Run: pytest `tests\core\test_daw.py`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add core/daw/__init__.py core/daw/profiles.py tests/core/test_daw.py
git commit -m "feat(daw): hồ sơ DAW (Studio One / Cubase) chọn theo settings daw_kind"
```

---

### Task 2: `so_windows` theo hồ sơ DAW

**Files:**
- Modify: `core/so_windows.py` (hằng `PROCESS_KEYWORDS`, `MAIN_TITLE_KEYWORD`, hàm `studio_one_pids`, `main_windows`)
- Test: `tests/core/test_so_windows_daw.py`

**Interfaces:**
- Consumes: `core.daw.active()`, `DawProfile.process_keywords`, `.main_title_requires`.
- Produces: `so_windows.process_keywords() -> tuple`, `so_windows.title_is_main(title: str) -> bool`; `studio_one_pids()`, `is_running()`, `main_windows()` giữ nguyên chữ ký (alias `daw_pids = studio_one_pids`).

- [ ] **Step 1: Viết test**

```python
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
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\core\test_so_windows_daw.py`
Expected: FAIL `AttributeError: module 'core.so_windows' has no attribute 'process_keywords'` (test cuối có thể PASS sẵn — vẫn giữ làm chốt chặn).

- [ ] **Step 3: Sửa `core/so_windows.py`**

Thay hai hằng ở đầu file:

```python
# Từ khoá nhận diện lấy theo hồ sơ DAW đang chọn (core.daw). Hai tên cũ giữ lại
# cho code/test cũ còn tham chiếu — chúng chỉ là giá trị của Studio One.
PROCESS_KEYWORDS = ("studio one",)
MAIN_TITLE_KEYWORD = "studio one"


def _profile():
    from core import daw
    return daw.active()


def process_keywords() -> tuple:
    return tuple(_profile().process_keywords)


def title_is_main(title) -> bool:
    """Tiêu đề này có phải cửa sổ chính của DAW không (mọi từ bắt buộc đều có)."""
    t = (title or "").lower()
    return all(word in t for word in _profile().main_title_requires)
```

Trong `studio_one_pids()` đổi `if any(kw in name for kw in PROCESS_KEYWORDS):` thành `if any(kw in name for kw in process_keywords()):` (lấy `keywords = process_keywords()` một lần trước vòng lặp). Thêm ngay dưới hàm: `daw_pids = studio_one_pids`.

Trong `main_windows()` đổi `if MAIN_TITLE_KEYWORD in (win32gui.GetWindowText(hwnd) or "").lower():` thành `if title_is_main(win32gui.GetWindowText(hwnd)):`. Sửa docstring: `"""Các cửa sổ chính — tiêu đề đạt mọi từ khoá của DAW đang chọn (kể cả đang ẩn)."""`.

Trong các `log.info` của `hide_all`/`show_all`/`HideGuard`/`ReadyWatcher` thay chuỗi `Studio One` bằng `%s` + `_profile().display_name` (ví dụ `log.info("Đã ẩn %d cửa sổ %s", count, _profile().display_name)`).

- [ ] **Step 4: Chạy test mới + test cũ**

Run: pytest `tests\core\test_so_windows_daw.py tests\core\test_close_studio_one_no_save.py tests\core\test_so_ready_watcher.py`
Expected: tất cả PASS

- [ ] **Step 5: Commit**

```bash
git add core/so_windows.py tests/core/test_so_windows_daw.py
git commit -m "refactor(so_windows): từ khoá process/tiêu đề lấy theo hồ sơ DAW"
```

---

### Task 3: `_lifecycle` theo hồ sơ DAW (mở, đóng, tắt cứng)

**Files:**
- Modify: `core/engine/_lifecycle.py` (`STUDIO_ONE_EXTENSIONS`, `send_hotkey`, `launch_app`, `_force_kill_studio_one`)
- Test: `tests/core/test_lifecycle_daw.py`

**Interfaces:**
- Consumes: `core.daw.active().project_extensions`, `so_windows.is_running()`, `so_windows.studio_one_pids()`, `so_windows.title_is_main()`.
- Produces: `_LifecycleMixin.project_extensions() -> tuple` (thay hằng lớp); `_force_kill_studio_one()` giết theo PID từ `so_windows.studio_one_pids()` bằng `psutil.Process(pid).kill()`.

- [ ] **Step 1: Viết test**

```python
# tests/core/test_lifecycle_daw.py
"""launch_app / force kill đi theo hồ sơ DAW, không còn tên exe cứng."""
from unittest.mock import MagicMock, patch

import pytest

from core import daw
from core.engine._lifecycle import _LifecycleMixin


@pytest.fixture(autouse=True)
def _unbind():
    daw.bind(None)
    yield
    daw.bind(None)


def _engine():
    return _LifecycleMixin()


def test_mo_file_cpr_bang_startfile_khi_chon_cubase():
    daw.bind({"daw_kind": "cubase"})
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as startfile, \
         patch("subprocess.Popen") as popen:
        _engine().launch_app(r"D:\QLS\mau.cpr")
    startfile.assert_called_once_with(r"D:\QLS\mau.cpr")
    popen.assert_not_called()


def test_file_song_khi_chon_cubase_khong_phai_bai():
    # Người dùng chọn Cubase nhưng để đường dẫn .song cũ → không startfile,
    # cũng không Popen một file không chạy được.
    daw.bind({"daw_kind": "cubase"})
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as startfile, \
         patch("core.so_windows.is_running", return_value=True), \
         patch("subprocess.Popen") as popen:
        _engine().launch_app(r"D:\bai\mau.song")
    startfile.assert_not_called()
    popen.assert_not_called()


def test_mo_exe_chi_khi_daw_chua_chay():
    daw.bind({"daw_kind": "cubase"})
    with patch("os.path.exists", return_value=True), \
         patch("core.so_windows.is_running", return_value=False), \
         patch("threading.Thread") as thread:
        _engine().launch_app(r"C:\Program Files\Steinberg\Cubase 13\Cubase13.exe")
    thread.assert_called_once()


def test_force_kill_theo_pid_cua_daw():
    daw.bind({"daw_kind": "cubase"})
    proc = MagicMock()
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = proc
    with patch("core.so_windows.studio_one_pids", return_value={4132}), \
         patch("core.engine._lifecycle.psutil", fake_psutil):
        _engine()._force_kill_studio_one()
    fake_psutil.Process.assert_called_once_with(4132)
    proc.kill.assert_called_once()


def test_studio_one_van_dung_duoi_song():
    daw.bind({})
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as startfile:
        _engine().launch_app(r"D:\bai\mau.songversion")
    startfile.assert_called_once()
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\core\test_lifecycle_daw.py`
Expected: FAIL ở `test_mo_file_cpr_bang_startfile_khi_chon_cubase` (Popen được gọi vì `.cpr` không nằm trong `STUDIO_ONE_EXTENSIONS`) và `test_force_kill_theo_pid_cua_daw`.

- [ ] **Step 3: Sửa `core/engine/_lifecycle.py`**

Giữ hằng `STUDIO_ONE_EXTENSIONS` (code cũ có thể tham chiếu) nhưng thêm:

```python
    @staticmethod
    def project_extensions():
        from core import daw
        return tuple(daw.active().project_extensions)
```

`send_hotkey`: đổi điều kiện tìm cửa sổ thành

```python
                from core import so_windows
                if win32gui.IsWindowVisible(h) and so_windows.title_is_main(win32gui.GetWindowText(h)):
```

`launch_app` nhánh không phải web:

```python
            if not os.path.exists(path):
                return
            lower = path.lower()
            if lower.endswith(self.project_extensions()):
                try:
                    os.startfile(path)
                except Exception:
                    pass
            elif lower.endswith(".exe"):
                from core import so_windows
                if not so_windows.is_running():
                    threading.Thread(target=lambda: subprocess.Popen(path), daemon=True).start()
            else:
                print(f"[DAW] Bỏ qua đường dẫn không phải file bài của DAW đang chọn: {path}")
```

`_force_kill_studio_one`:

```python
    def _force_kill_studio_one(self):
        """Tắt cứng mọi process của DAW đang chọn (theo PID, không theo tên exe)."""
        from core import so_windows
        killed = 0
        for pid in so_windows.studio_one_pids():
            try:
                psutil.Process(pid).kill()
                killed += 1
            except Exception as e:
                print(f"[DAW] Không kill được PID {pid}: {e}")
        if killed:
            print(f"[DAW] Force kill {killed} process")
        else:
            print("[DAW] Không tìm thấy process để kill")
```

Trong `close_studio_one_safely` và `_studio_one_save`, đổi tiền tố in `[STUDIO ONE]` thành `[DAW]` và các câu `"Đang đóng Studio One..."`, `"Studio One đã thoát sạch"`, `"Studio One chưa đóng xong..."`, `"Đang lưu bài trong Studio One..."` thành dùng `name = daw.active().display_name` (ví dụ `_p(f"Đang đóng {name}...")`). Lấy `from core import daw` ở đầu hàm.

- [ ] **Step 4: Chạy test**

Run: pytest `tests\core\test_lifecycle_daw.py tests\core\test_close_studio_one_no_save.py tests\ui\test_exit_close_studio_one.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/engine/_lifecycle.py tests/core/test_lifecycle_daw.py
git commit -m "refactor(lifecycle): mở/đóng/tắt cứng theo hồ sơ DAW, bỏ danh sách exe cứng"
```

---

### Task 4: Bản mẫu theo đuôi file của DAW

**Files:**
- Modify: `core/so_template.py`
- Test: `tests/core/test_so_template.py` (thêm test), `tests/core/test_so_template_cubase.py`

**Interfaces:**
- Produces: `so_template.template_file(profile=None) -> str` (`template.song` / `template.cpr` trong `TEMPLATE_DIR`), `replaced_file(profile=None)`; `is_song_file(path)` giờ = `daw.is_project_file(path)`; `has_template()`, `snapshot()`, `restore()` dùng file theo hồ sơ đang chọn. Hằng `TEMPLATE_FILE`, `REPLACED_FILE` **giữ** (test cũ monkeypatch chúng): hàm `template_file()` trả `TEMPLATE_FILE` khi hồ sơ là Studio One, nên test cũ không đổi.

- [ ] **Step 1: Viết test**

```python
# tests/core/test_so_template_cubase.py
"""Bản mẫu .cpr khi chọn Cubase; đường dẫn .cpr không phải bài của Studio One."""
import pytest

from core import daw, so_template


@pytest.fixture(autouse=True)
def temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(so_template, "TEMPLATE_DIR", str(tmp_path / "so_template"))
    monkeypatch.setattr(so_template, "TEMPLATE_FILE", str(tmp_path / "so_template" / "template.song"))
    monkeypatch.setattr(so_template, "TEMPLATE_META", str(tmp_path / "so_template" / "template.json"))
    monkeypatch.setattr(so_template, "REPLACED_FILE", str(tmp_path / "so_template" / "replaced.song"))
    daw.bind(None)
    yield
    daw.bind(None)


def test_cpr_khong_phai_bai_studio_one():
    daw.bind({})
    assert so_template.is_song_file(r"D:\QLS\mau.cpr") is False
    r = so_template.snapshot(r"D:\QLS\mau.cpr")
    assert r["ok"] is False


def test_chot_va_phuc_hoi_cpr(tmp_path):
    daw.bind({"daw_kind": "cubase"})
    cpr = tmp_path / "mau.cpr"
    cpr.write_bytes(b"GOC")
    assert so_template.is_song_file(str(cpr)) is True
    assert so_template.snapshot(str(cpr))["ok"] is True
    assert so_template.template_file().endswith("template.cpr")
    assert so_template.has_template() is True
    cpr.write_bytes(b"KHACH SUA")
    r = so_template.restore(str(cpr), so_running=False)
    assert r["restored"] is True
    assert cpr.read_bytes() == b"GOC"
    assert so_template.replaced_file().endswith("replaced.cpr")


def test_ban_mau_hai_daw_khong_de_nhau(tmp_path):
    song = tmp_path / "a.song"; song.write_bytes(b"S1")
    cpr = tmp_path / "b.cpr"; cpr.write_bytes(b"CB")
    daw.bind({})
    assert so_template.snapshot(str(song))["ok"]
    daw.bind({"daw_kind": "cubase"})
    assert so_template.has_template() is False
    assert so_template.snapshot(str(cpr))["ok"]
    daw.bind({})
    assert so_template.has_template() is True
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\core\test_so_template_cubase.py`
Expected: FAIL (`is_song_file` chấp nhận `.cpr`? không — FAIL ở `snapshot` Cubase vì "không phải file .song" và `template_file` không tồn tại).

- [ ] **Step 3: Sửa `core/so_template.py`**

Thay `is_song_file` và thêm hàm chọn file:

```python
def _profile(profile=None):
    from core import daw
    return profile or daw.active()


def template_file(profile=None) -> str:
    p = _profile(profile)
    if p.kind == "studio_one":
        return TEMPLATE_FILE
    return os.path.join(TEMPLATE_DIR, "template" + p.template_extension)


def replaced_file(profile=None) -> str:
    p = _profile(profile)
    if p.kind == "studio_one":
        return REPLACED_FILE
    return os.path.join(TEMPLATE_DIR, "replaced" + p.template_extension)


def is_song_file(path) -> bool:
    """Đường dẫn có phải file bài của DAW đang chọn không (.song / .cpr)."""
    from core import daw
    return daw.is_project_file(path)
```

Trong `has_template()`, `info()`, `snapshot()`, `restore()`, `clear()`: thay mọi `TEMPLATE_FILE` bằng `template_file()` và `REPLACED_FILE` bằng `replaced_file()`. Thông báo lỗi trong `snapshot` đổi thành `f"Đường dẫn không phải file bài {ext}"` với `ext = _profile().template_extension`; lý do trong `restore` tương tự; `"Studio One đang chạy"` → `f"{_profile().display_name} đang chạy"`.

- [ ] **Step 4: Chạy test**

Run: pytest `tests\core\test_so_template.py tests\core\test_so_template_cubase.py tests\ui\test_startup_template_restore.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/so_template.py tests/core/test_so_template_cubase.py
git commit -m "refactor(so_template): bản mẫu theo đuôi file của DAW đang chọn"
```

---

### Task 5: Fader 0 dB theo DAW (mixer)

**Files:**
- Modify: `ui/panels/mixer.py:60-85` (`_make_value_changed_callback`)
- Test: `tests/ui/test_mixer_unity_daw.py`

**Interfaces:**
- Consumes: `core.daw.active().fader_unity_cc`.
- Produces: hàm thuần `ui.panels.mixer.db_to_midi(db: float, min_v: float, unity: int) -> int`.

- [ ] **Step 1: Viết test**

```python
# tests/ui/test_mixer_unity_daw.py
"""Quy đổi dB → CC: 0 dB rơi đúng điểm unity của DAW (Studio One 76, Cubase 100)."""
from core import daw
from ui.panels.mixer import db_to_midi


def test_studio_one_0db_la_76():
    assert db_to_midi(0.0, -10.0, daw.STUDIO_ONE.fader_unity_cc) == 76
    assert db_to_midi(-10.0, -10.0, 76) == 0
    assert db_to_midi(10.0, -10.0, 76) == 127


def test_cubase_0db_la_100():
    assert db_to_midi(0.0, -10.0, daw.CUBASE.fader_unity_cc) == 100
    assert db_to_midi(-10.0, -10.0, 100) == 0
    assert db_to_midi(10.0, -10.0, 100) == 127
    assert db_to_midi(-5.0, -10.0, 100) == 50


def test_khong_vuot_bien():
    assert db_to_midi(99.0, -10.0, 100) == 127
    assert db_to_midi(-99.0, -10.0, 100) == 0
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\ui\test_mixer_unity_daw.py`
Expected: FAIL `ImportError: cannot import name 'db_to_midi'`

- [ ] **Step 3: Sửa `ui/panels/mixer.py`**

Thêm hàm module-level trước `_make_value_changed_callback`:

```python
def db_to_midi(db, min_v, unity):
    """dB (min_v..0..+10) → CC. 0 dB = `unity` (Studio One 76, Cubase 100), hai đoạn tuyến tính."""
    db = float(db)
    if db <= min_v:
        return 0
    if db <= 0:
        return max(0, min(127, int(round(unity + db * (unity / abs(min_v))))))
    return max(0, min(127, int(round(unity + db * ((127 - unity) / 10.0)))))
```

Trong `cb` thay khối `if cc_key in ["mix_mic", "mix_reverb"]: ... midi = max(0, min(127, midi))` bằng:

```python
        if cc_key in ["mix_mic", "mix_reverb"]:
            from core import daw
            midi = db_to_midi(raw_value, min_v, daw.active().fader_unity_cc)
```

(giữ nguyên nhánh `else`). Cập nhật chú thích: `# 0 dB -> fader_unity_cc của DAW: Studio One 76, Cubase 100 (đo 2026-10-04)`.

- [ ] **Step 4: Chạy test**

Run: pytest `tests\ui\test_mixer_unity_daw.py`
Expected: 3 passed. Kiểm tra bằng tay: với unity 76, min −10: −5 dB → `round(76 − 38)` = 38 (khớp công thức cũ `76 + (−5)·7.6`); +5 dB → `round(76 + 25.5)` = 102 (cũ: 101.5 → 102).

- [ ] **Step 5: Commit**

```bash
git add ui/panels/mixer.py tests/ui/test_mixer_unity_daw.py
git commit -m "feat(mixer): điểm 0 dB của fader theo DAW (Cubase = CC 100)"
```

---

### Task 6: Bảng scale theo DAW trong `AppConfig`

**Files:**
- Modify: `core/config.py` (`get_scale_values`, `get_scale_midi_map`, thêm `_user_calibration_keys`)
- Test: `tests/core/test_config_daw_calibration.py`

**Interfaces:**
- Consumes: `core.daw.active().calibration`, hằng `CALIBRATION_OVERRIDES_FILE` sẵn có trong config.
- Produces: `AppConfig.get_scale_midi_map()` / `get_scale_values()` trả theo thứ tự ưu tiên: override người dùng (có key trong file overrides) > `profile.calibration[key]` > app_config.

- [ ] **Step 1: Viết test**

```python
# tests/core/test_config_daw_calibration.py
"""Scale map: override người dùng > mặc định của DAW > app_config."""
import json

import pytest

from core import daw
from core.config import AppConfig
import core.config as cfg


@pytest.fixture(autouse=True)
def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(tmp_path / "cal.json"))
    AppConfig._user_calibration_keys.cache_clear() if hasattr(AppConfig._user_calibration_keys, "cache_clear") else None
    daw.bind(None)
    yield
    daw.bind(None)


def test_studio_one_dung_app_config():
    daw.bind({})
    assert AppConfig.get_scale_midi_map()["Major"] == 13
    assert AppConfig.get_scale_values()["major"] == 13


def test_cubase_dung_mac_dinh_ho_so():
    daw.bind({"daw_kind": "cubase"})
    assert AppConfig.get_scale_midi_map() == {"Major": 43, "Minor": 85}
    assert AppConfig.get_scale_values() == {"major": 43, "minor": 85}


def test_override_nguoi_dung_thang_mac_dinh_daw(tmp_path):
    (tmp_path / "cal.json").write_text(json.dumps({"scale_midi_map": {"Major": 50, "Minor": 90}}), encoding="utf-8")
    daw.bind({"daw_kind": "cubase"})
    with_override = AppConfig.load()
    with_override["scale_midi_map"] = {"Major": 50, "Minor": 90}   # như load() đã merge
    assert AppConfig.get_scale_midi_map() == {"Major": 50, "Minor": 90}
    # scale_values không có trong override → vẫn lấy mặc định Cubase
    assert AppConfig.get_scale_values() == {"major": 43, "minor": 85}
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\core\test_config_daw_calibration.py`
Expected: FAIL ở `test_cubase_dung_mac_dinh_ho_so` (trả 13/18).

- [ ] **Step 3: Sửa `core/config.py`**

Thêm vào `class AppConfig` (gần `get_scale_values`):

```python
    @staticmethod
    def _user_calibration_keys():
        """Các key cân chỉnh người dùng đã tự lưu (file overrides). Rỗng nếu chưa có."""
        try:
            if os.path.exists(CALIBRATION_OVERRIDES_FILE):
                with open(CALIBRATION_OVERRIDES_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return set(loaded.keys())
        except Exception:
            pass
        return set()

    @classmethod
    def _daw_calibrated(cls, key, fallback):
        """Ưu tiên: override người dùng > mặc định của DAW đang chọn > app_config."""
        if key in cls._user_calibration_keys():
            return fallback
        try:
            from core import daw
            value = daw.active().calibration.get(key)
        except Exception:
            value = None
        return dict(value) if isinstance(value, dict) else fallback

    @classmethod
    def get_scale_values(cls):
        base = cls.load().get("scale_values", _DEFAULT_APP_CONFIG["scale_values"])
        return cls._daw_calibrated("scale_values", base)

    @classmethod
    def get_scale_midi_map(cls):
        base = cls.load().get("scale_midi_map", _DEFAULT_APP_CONFIG["scale_midi_map"])
        return cls._daw_calibrated("scale_midi_map", base)
```

(Xoá hai định nghĩa cũ của `get_scale_values` / `get_scale_midi_map`.) Trong test fixture bỏ dòng `cache_clear` nếu không dùng lru_cache (không dùng — đọc file mỗi lần, file nhỏ).

- [ ] **Step 4: Chạy test**

Run: pytest `tests\core\test_config_daw_calibration.py tests\core\test_config.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/core/test_config_daw_calibration.py
git commit -m "feat(config): bảng scale lấy theo DAW đang chọn, override người dùng vẫn thắng"
```

---

### Task 7: Gắn `daw.bind`, chọn DAW trong Cài đặt và wizard, chuỗi hiển thị

**Files:**
- Modify: `frontend_qt.py` (sau chỗ `kiosk.bind(self.settings)` lúc khởi tạo; `_auto_launch_apps` dòng ~1207; wizard dòng ~4595, ~4601, ~4666-4672, ~4681; thông báo 466, 488, 513, 3128, 3136, 3140, 3145, 3148, 4030, 4038, 4048, 4084-4085)
- Modify: `ui/dialogs/settings_dialog.py` (380, 387, 393, 397-398, 407, 845, 897, 903, 983, 985, 1014-1015, 1080, 1084, 1730-1731, 1756-1761)
- Modify: `ui/panels/header.py:33,163,164`, `ui/dialogs/shutdown_dialog.py:61,74,82-83,122`, `ui/dialogs/tech_unlock.py:136`
- Test: `tests/ui/test_settings_daw_kind.py`

**Interfaces:**
- Consumes: `core.daw.active()`, `daw.PROFILES`, `daw.bind`.
- Produces: settings key `daw_kind`; combo `self._cmb_daw` trong SettingsDialog (userData = kind); wizard combo `self.daw_combo`.

- [ ] **Step 1: Viết test**

```python
# tests/ui/test_settings_daw_kind.py
"""Cài đặt: chọn DAW ghi vào settings["daw_kind"], nhãn theo DAW đang chọn."""
from unittest.mock import MagicMock, patch

from core import daw
from frontend_qt import MainDashboard


def test_auto_launch_dung_duoi_cpr_khi_cubase():
    self = MagicMock()
    self.settings = {"daw_kind": "cubase", "studio_one_path": r"D:\QLS\mau.cpr",
                     "auto_launch_studio_one": True, "auto_launch_browser": False}
    daw.bind(self.settings)
    try:
        with patch("core.kiosk.is_enabled", return_value=True), \
             patch("core.kiosk.restore_template_enabled", return_value=True), \
             patch("core.kiosk.is_locked", return_value=False), \
             patch("core.so_windows.is_running", return_value=False), \
             patch("core.so_template.has_template", return_value=True), \
             patch("core.so_template.restore", return_value={"restored": True, "reason": ""}) as restore, \
             patch("os.path.exists", return_value=True):
            MainDashboard._auto_launch_apps(self)
        restore.assert_called_once_with(r"D:\QLS\mau.cpr")
        self.engine.launch_app.assert_called_once_with(r"D:\QLS\mau.cpr")
    finally:
        daw.bind(None)


def test_settings_dialog_luu_daw_kind(qtbot, mock_engine):
    # Dùng đúng cách dựng dashboard/dialog của tests/ui/test_settings_save_and_sync.py
    from tests.ui.test_settings_save_and_sync import _make_dashboard, _open_dialog, _save_without_side_effects
    dashboard = _make_dashboard(qtbot, settings={"daw_kind": "studio_one"})
    dlg = _open_dialog(qtbot, dashboard)
    idx = dlg._cmb_daw.findData("cubase")
    assert idx >= 0
    dlg._cmb_daw.setCurrentIndex(idx)
    assert dlg._collect_daw_kind() == "cubase"
    assert dlg._cb_launch_so.text() == "Mở Cubase khi khởi động"
    _save_without_side_effects(dlg)
    assert dashboard.settings["daw_kind"] == "cubase"
```

(Repo không có `tests/__init__.py`, nên **không import** từ file test khác: chép nguyên bốn thứ `A11Y_CFG`, fixture `qapp`, fixture `mock_engine`, hàm `_make_dashboard`, `_open_dialog`, `_save_without_side_effects` từ `tests/ui/test_settings_save_and_sync.py` (dòng 1–90) vào đầu `tests/ui/test_settings_daw_kind.py`, rồi bỏ dòng `from tests.ui... import` trong test trên.)

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\ui\test_settings_daw_kind.py`
Expected: FAIL `AttributeError: _cmb_daw`

- [ ] **Step 3: `frontend_qt.py` — bind và wizard**

Ngay sau dòng `kiosk.bind(self.settings)` (`frontend_qt.py:141`, cùng mức thụt) thêm:

```python
        from core import daw
        daw.bind(self.settings)
```

Trong `_auto_launch_apps`: không đổi logic (đã dùng `so_template.is_song_file`). Đổi các `print("[KIOSK] Đã phục hồi bản mẫu Studio One")` thành `print(f"[KIOSK] Đã phục hồi bản mẫu {daw.active().display_name}")` (thêm `from core import daw` ở đầu hàm).

Wizard (`step1_lbl`): thêm combo trước ô đường dẫn:

```python
        from core import daw as _daw
        step1_lbl = QLabel("🔹 Bước 1:  Phần mềm thu âm (DAW) và đường dẫn bài mẫu")
        ...
        self.daw_combo = QComboBox()
        for p in _daw.PROFILES.values():
            self.daw_combo.addItem(p.display_name, p.kind)
        self.daw_combo.setCurrentIndex(max(0, self.daw_combo.findData(_daw.kind_of(existing))))
        layout.addWidget(self.daw_combo)
```

`_browse_studio_one`: lấy filter từ hồ sơ đang chọn trong combo:

```python
    def _browse_studio_one(self):
        from core import daw
        profile = daw.PROFILES[self.daw_combo.currentData()]
        path, _ = QFileDialog.getOpenFileName(
            self, f"Chọn file bài mẫu hoặc chương trình {profile.display_name}", "",
            profile.file_dialog_filter)
```

`_save_and_continue`: thêm `"daw_kind": self.daw_combo.currentData(),` vào dict settings.

Thông báo người dùng: thay chuỗi cứng bằng `name = daw.active().display_name` tại các dòng liệt kê ở **Files** (ví dụ `f"{name} đang khoá — cần mở khoá kỹ thuật"`, `f"Không tìm thấy {name} đang chạy"`, `f"Đã ẩn {name}"`, `f"Đã hiện {name}"`, `hint=f"{name} còn mở từ phiên trước. Đang đóng lại (không lưu) ..."`).

- [ ] **Step 4: `ui/dialogs/settings_dialog.py`**

Trong `__init__`, ngay trước `self._inp_so = QLineEdit(...)` (dòng ~379) tạo combo (chưa add vào layout — `_build_paths` sẽ đặt nó):

```python
        from core import daw as _daw
        self._cmb_daw = QComboBox()
        for p in _daw.PROFILES.values():
            self._cmb_daw.addItem(p.display_name, p.kind)
        self._cmb_daw.setCurrentIndex(max(0, self._cmb_daw.findData(_daw.kind_of(settings))))
```

Sau khi tạo xong `self._cb_close_so` (sau `setToolTip`, dòng ~400) thêm:

```python
        self._cmb_daw.currentIndexChanged.connect(self._on_daw_changed)
        self._on_daw_changed()
```

Trong `_build_paths(self, vl)` chèn **trước** `so_lbl = QLabel(...)`:

```python
        daw_lbl = QLabel("Phần mềm thu âm (DAW):")
        daw_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(daw_lbl)
        self._cmb_daw.setMinimumHeight(42)
        vl.addWidget(self._cmb_daw)
        self._so_lbl = QLabel("")
        self._so_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(self._so_lbl)
```

và **xoá** ba dòng `so_lbl = QLabel("Studio One (.song hoặc .exe):")`, `so_lbl.setStyleSheet(...)`, `vl.addWidget(so_lbl)` (nhãn giờ do `_on_daw_changed` đặt). Thêm hai phương thức vào class:

```python
    def _collect_daw_kind(self) -> str:
        return self._cmb_daw.currentData() or "studio_one"

    def _on_daw_changed(self, _idx=None):
        from core import daw
        p = daw.PROFILES[self._collect_daw_kind()]
        ext = p.template_extension
        if hasattr(self, "_so_lbl"):
            self._so_lbl.setText(f"{p.display_name} ({ext} hoặc .exe):")
        self._inp_so.setPlaceholderText(f"VD: D:/Songs/BaiMau{ext} hoặc C:/.../{p.display_name}.exe")
        self._cb_launch_so.setText(f"Mở {p.display_name} khi khởi động")
        self._cb_close_so.setText(f"Đóng {p.display_name} khi thoát (không lưu)")
        self._cb_close_so.setToolTip(
            f"Thoát app thì đóng luôn {p.display_name} và KHÔNG lưu bài — chỉnh sửa "
            f"trong phiên bị bỏ. Muốn giữ thì tự Ctrl+S trong {p.display_name} trước khi thoát app.")
```

`_build_paths` chạy bên trong `self._section_card(self._build_paths)` ở dòng ~382, tức TRƯỚC khi `_cb_launch_so` tồn tại — vì vậy `_on_daw_changed()` chỉ được gọi ở vị trí nêu trên (sau `_cb_close_so`), và `hasattr(self, "_so_lbl")` bảo vệ trường hợp gọi sớm.

Trong `_save` (dòng ~1751-1761): thêm `s["daw_kind"] = self._collect_daw_kind()` cạnh `s["auto_launch_studio_one"] = ...`.

`_browse_so` (dòng ~1728-1731): 

```python
        from core import daw
        p = daw.PROFILES[self._collect_daw_kind()]
        path, _ = QFileDialog.getOpenFileName(
            self, f"Chọn file bài mẫu hoặc chương trình {p.display_name}", "", p.file_dialog_filter)
```

Các nhãn còn lại (407, 897, 903, 983, 985, 1014-1015, 1080, 1084): thay "Studio One" bằng `{name}` với `name = daw.active().display_name` lấy ở đầu hàm tương ứng (`from core import daw`). Riêng 1128-1129, 1157 (mic/loopback) đổi "Studio One" → "DAW".

- [ ] **Step 5: header, shutdown_dialog, tech_unlock**

`ui/panels/header.py`: đầu hàm dựng header thêm `from core import daw; name = daw.active().display_name`; dòng 33 `f"Kết nối MIDI với {name}"`, 163 `f"Ẩn/Hiện {name} + Plugin"`, 164 `f"Ẩn hiện {name}"`.
`ui/dialogs/shutdown_dialog.py`: trong `__init__` của `StudioOneShutdownDialog` thêm `from core import daw; name = daw.active().display_name`; 61 `title or f"Đang đóng {name}"`, 74 `title or f"Đang đóng {name} an toàn"`, 82-83 `f"Đang chờ {name} tự thoát. Đừng tắt máy lúc này — tắt ngang sẽ khiến lần mở sau {name} đòi phục hồi phiên."`, 122 `skip_tip or f"Để {name} chạy tiếp và thoát app ngay"`.
`ui/dialogs/tech_unlock.py:136`: `f"Nhập mã PIN kỹ thuật để hiện lại {name}. "` với `name` lấy như trên.

- [ ] **Step 6: Chạy test UI**

Run: pytest `tests\ui\test_settings_daw_kind.py tests\ui\test_startup_template_restore.py tests\ui\test_exit_close_studio_one.py tests\ui\test_midi_resync_on_so_ready.py`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend_qt.py ui/dialogs/settings_dialog.py ui/panels/header.py ui/dialogs/shutdown_dialog.py ui/dialogs/tech_unlock.py tests/ui/test_settings_daw_kind.py
git commit -m "feat(ui): chọn DAW trong Cài đặt/wizard, nhãn theo DAW đang chọn"
```

---

### Task 8: Script Cubase: gán thẳng CC của app vào tham số plugin

**Files:**
- Modify: `cubase/QuangLuu_QuangLuuMIDI.js`
- Test: `tests/test_cubase_script.py` (thêm test)

**Interfaces:**
- Produces: trong JS, hằng `THAM_SO_PLUGIN = { key_root: 6, scale_type: 7, tone_auto: 3 }` và các knob CC 33/35/40 bind vào `thamSo[idx]`; phần SysEx/log giữ nguyên (dùng cho chẩn đoán).

- [ ] **Step 1: Thêm test**

```python
def test_js_gan_cc_app_vao_tham_so_plugin():
    with open(JS_PATH, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"var THAM_SO_PLUGIN = \{(.*?)\}", src, re.S)
    assert m, "thiếu THAM_SO_PLUGIN"
    idx = {k: int(v) for k, v in re.findall(r"(\w+):\s*(\d+)", m.group(1))}
    assert idx == {"key_root": 6, "scale_type": 7, "tone_auto": 3}
    assert "makeValueBinding(kApp.mSurfaceValue, thamSo[" in src
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\test_cubase_script.py`
Expected: FAIL `thiếu THAM_SO_PLUGIN`

- [ ] **Step 3: Sửa JS**

Sau vòng `for (var pi = 0; pi < SO_THAM_SO; pi++) {...}` thêm:

```javascript
// App gui key_root (CC 33), scale_type (CC 35), tone_auto (CC 40) nhu voi Studio One.
// Chi so tham so cua Steinberg Pitch Correct (do 2026-10-04): 6 Key, 7 Scale, 3 PitchCorrect.
// Dung plugin khac thi doi 3 so nay (xem bang param|i|ten qua SysEx).
var THAM_SO_PLUGIN = { key_root: 6, scale_type: 7, tone_auto: 3 }
var ccTheoKhoa = { key_root: CC.key_root, scale_type: CC.scale_type, tone_auto: CC.tone_auto }
for (var khoa in THAM_SO_PLUGIN) {
    if (!THAM_SO_PLUGIN.hasOwnProperty(khoa)) continue
    var kApp = knobCC(ccTheoKhoa[khoa])
    page.makeValueBinding(kApp.mSurfaceValue, thamSo[THAM_SO_PLUGIN[khoa]])
}
```

Bỏ `CC.tone_auto` khỏi mảng `ccChiLog` (một CC chỉ nên có một knob).

- [ ] **Step 4: Kiểm cú pháp + test**

Run: `node -e "new (require('vm').Script)(require('fs').readFileSync('cubase/QuangLuu_QuangLuuMIDI.js','utf8'))"` rồi pytest `tests\test_cubase_script.py`
Expected: không lỗi; 4 passed

- [ ] **Step 5: Kiểm trên Cubase thật (máy dev đang có Cubase + `D:\QLS\mau.cpr`)**

Chép script: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools\tham_do_cubase\ThamDoCubase.ps1 -CaiScript -NoPause`. Trong Cubase bấm Reload Scripts (hoặc mở lại Cubase). Chạy `.venv\Scripts\python.exe tools\tham_do_cubase\nghe_phan_hoi.py 8` và song song gửi `CC 33 = 23` (D), `CC 35 = 43` (Major) bằng `tools\tham_do_cubase\quet_tham_so.py`-style script hoặc mido; kỳ vọng nhận `SYSEX loai=4 disp|6|D|` và `disp|7|Major|`.
Expected: hai dòng SysEx trên xuất hiện.

- [ ] **Step 6: Commit**

```bash
git add cubase/QuangLuu_QuangLuuMIDI.js tests/test_cubase_script.py
git commit -m "feat(cubase): CC 33/35/40 của app gán thẳng vào Key/Scale/PitchCorrect"
```

---

### Task 9: Bộ cài, đóng gói và chẩn đoán cho Cubase

**Files:**
- Modify: `setup_all.bat` (sau `:skip_surface`)
- Modify: `QuangLuuStudio_Setup.iss` (sau khối `Studio One Surface files`)
- Modify: `QuangLuuStudio.spec` (`datas`)
- Modify: `tools/chan_doan/QLS_ChanDoan.ps1` (sau Section "Studio One đã cài")
- Test: `tests/test_packaging_cubase.py`

**Interfaces:**
- Produces: thư mục cài `{app}\cubase\QuangLuu_QuangLuuMIDI.js`; script chép tới `%USERPROFILE%\Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\`.

- [ ] **Step 1: Viết test**

```python
# tests/test_packaging_cubase.py
"""Script Cubase phải đi theo bộ cài và bản đóng gói, như surface.xml của Studio One."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8", errors="replace") as f:
        return f.read()


def test_iss_chep_script_cubase():
    assert 'Source: "cubase\\QuangLuu_QuangLuuMIDI.js"; DestDir: "{app}\\cubase"' in _read("QuangLuuStudio_Setup.iss")


def test_spec_dong_goi_thu_muc_cubase():
    assert "('cubase', 'cubase')" in _read("QuangLuuStudio.spec")


def test_setup_all_cai_script_cubase():
    bat = _read("setup_all.bat")
    assert "MIDI Remote\\Driver Scripts\\Local\\QuangLuu\\QuangLuuMIDI" in bat
    assert "QuangLuu_QuangLuuMIDI.js" in bat


def test_chan_doan_kiem_cubase():
    ps = _read(os.path.join("tools", "chan_doan", "QLS_ChanDoan.ps1"))
    assert "ReleaseHardware" in ps
    assert "QuangLuu_QuangLuuMIDI.js" in ps
```

- [ ] **Step 2: Chạy test, xác nhận FAIL**

Run: pytest `tests\test_packaging_cubase.py`
Expected: 4 failed

- [ ] **Step 3: `setup_all.bat`** — chèn sau nhãn `:skip_surface` và dòng `echo.`:

```bat
REM ============================================
REM  BƯỚC 2b: Script MIDI Remote cho Cubase (12+)
REM ============================================
echo ----------------------------------------
echo  Buoc 2b: Script MIDI Remote cho Cubase
echo ----------------------------------------
set "CB_FOUND="
for /d %%D in ("%ProgramFiles%\Steinberg\Cubase*") do set "CB_FOUND=%%~fD"
if "!CB_FOUND!"=="" (
    echo [INFO] Khong thay Cubase trong Program Files - bo qua ^(chi can khi dung Cubase^).
    goto :skip_cubase
)
echo [OK] Tim thay !CB_FOUND!
set "CB_DST=%USERPROFILE%\Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI"
if not exist "!CB_DST!" mkdir "!CB_DST!"
copy /Y "%~dp0cubase\QuangLuu_QuangLuuMIDI.js" "!CB_DST!\" >nul
if exist "!CB_DST!\QuangLuu_QuangLuuMIDI.js" (
    echo [OK] Da chep QuangLuu_QuangLuuMIDI.js
    echo [QUAN TRONG] Mo lai Cubase ^(hoac MIDI Remote ^> Reload Scripts^). Cubase tu nhan khi co du 2 cong MIDI.
    echo [LUU Y] Studio ^> Studio Setup ^> Audio System: TAT "Release Driver when Application is in Background".
) else (
    echo [ERROR] Copy script Cubase that bai!
)
:skip_cubase
echo.
```

- [ ] **Step 4: `QuangLuuStudio_Setup.iss`** — sau hai dòng `studio_one\...` thêm:

```ini
; Cubase MIDI Remote script (chép vào Documents\Steinberg\... bởi setup_all.bat)
Source: "cubase\QuangLuu_QuangLuuMIDI.js"; DestDir: "{app}\cubase"; Flags: ignoreversion
```

Đổi mô tả `[Run]`: `Description: "Cài đặt loopMIDI, cổng MIDI và phần nhận MIDI cho Studio One / Cubase"`.

- [ ] **Step 5: `QuangLuuStudio.spec`** — sau `('studio_one', 'studio_one'),` thêm `('cubase', 'cubase'),`.

- [ ] **Step 6: `tools/chan_doan/QLS_ChanDoan.ps1`** — sau khối `Safe "Studio One đã cài" {...}` thêm:

```powershell
Safe "Cubase đã cài" {
    $found = @(Get-ChildItem -LiteralPath (Join-Path $env:ProgramFiles "Steinberg") -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Cubase*" })
    if ($found.Count -eq 0) { Chk "Cubase đã cài" "INFO" "không thấy (chỉ cần khi dùng Cubase)"; return }
    Chk "Cubase đã cài" "OK" (($found | ForEach-Object { $_.Name }) -join ", ")
    $dst = Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js"
    if (-not (Test-Path -LiteralPath $dst)) {
        Chk "Script MIDI Remote Cubase" "FAIL" "chưa chép" "Cubase không nhận nút bấm từ app. Chạy setup_all.bat rồi mở lại Cubase."
    } else {
        $src = Join-Path $script:AppRoot "cubase\QuangLuu_QuangLuuMIDI.js"
        if ((Test-Path -LiteralPath $src) -and ((Get-FileHash $src).Hash -ne (Get-FileHash $dst).Hash)) {
            Chk "Script MIDI Remote Cubase" "WARN" "khác bản đi kèm app" "Chạy setup_all.bat rồi Reload Scripts trong Cubase."
        } else { Chk "Script MIDI Remote Cubase" "OK" "đã chép, đúng bản" }
    }
    foreach ($pd in Get-ChildItem -LiteralPath (Join-Path $env:APPDATA "Steinberg") -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Cubase*" }) {
        $def = Join-Path $pd.FullName "Defaults.xml"
        if (-not (Test-Path -LiteralPath $def)) { continue }
        $m = Select-String -LiteralPath $def -Pattern 'name="ReleaseHardware" value="(\d)"' | Select-Object -First 1
        if ($m -and $m.Matches[0].Groups[1].Value -eq "1") {
            Chk ("Release Driver (" + $pd.Name + ")") "FAIL" "đang BẬT" "App ẩn cửa sổ Cubase nên Cubase luôn ở nền → bật cờ này là mất tiếng. Studio Setup → Audio System → tắt 'Release Driver when Application is in Background'."
        } elseif ($m) { Chk ("Release Driver (" + $pd.Name + ")") "OK" "đang tắt" }
    }
}
```

(Kiểm `Safe`/`Chk` có đúng chữ ký đang dùng trong file — xem các khối lân cận; `Chk` nhận (tên, trạng thái, chi tiết, [gợi ý]).)

- [ ] **Step 7: Chạy test + kiểm cú pháp PowerShell**

Run: pytest `tests\test_packaging_cubase.py`; rồi `powershell.exe -NoProfile -Command '$e=$null; [void][System.Management.Automation.PSParser]::Tokenize((Get-Content -Raw "D:\Projects\quang-luu-studio\tools\chan_doan\QLS_ChanDoan.ps1"), [ref]$e); $e.Count'`
Expected: 4 passed; `0`.

- [ ] **Step 8: Commit**

```bash
git add setup_all.bat QuangLuuStudio_Setup.iss QuangLuuStudio.spec tools/chan_doan/QLS_ChanDoan.ps1 tests/test_packaging_cubase.py
git commit -m "build: cài script MIDI Remote cho Cubase, đóng gói thư mục cubase, chẩn đoán Cubase"
```

---

### Task 10: Chạy thử đầu-cuối trên máy dev và tài liệu

**Files:**
- Modify: `docs/NGHIEN_CUU_HO_TRO_CUBASE.md` (mục 7: trạng thái các giai đoạn), `docs/KIOSK_MODE_GUIDE.md` (một đoạn: chọn DAW, Cubase tắt Release Driver), `docs/manual/index.html` (câu nhắc chọn DAW ở phần Cài đặt)

- [ ] **Step 1: Chạy toàn bộ test liên quan**

Run: pytest `tests\core\test_daw.py tests\core\test_so_windows_daw.py tests\core\test_lifecycle_daw.py tests\core\test_so_template.py tests\core\test_so_template_cubase.py tests\core\test_config_daw_calibration.py tests\core\test_close_studio_one_no_save.py tests\core\test_so_ready_watcher.py tests\ui\test_mixer_unity_daw.py tests\ui\test_settings_daw_kind.py tests\ui\test_startup_template_restore.py tests\ui\test_exit_close_studio_one.py tests\ui\test_midi_resync_on_so_ready.py tests\test_surface_xml.py tests\test_cubase_script.py tests\test_packaging_cubase.py`
Expected: tất cả PASS. Sau đó `git checkout app_config.json`.

- [ ] **Step 2: Chạy app với Cubase (máy dev)**

Đặt trong `%APPDATA%\QuangLuuStudio\settings.json`: `"daw_kind": "cubase"`, `"studio_one_path": "D:\\QLS\\mau.cpr"`, `"auto_launch_studio_one": true`, `"auto_close_studio_one": true`. Đóng Cubase nếu đang mở. Chạy `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe main.py"`. Kiểm:
  - Cubase mở thẳng bài `mau.cpr`, không Hub.
  - Bấm nút mắt: Cubase ẩn/hiện (cả cửa sổ `Cubase Pro` class SmtgMain).
  - Kéo fader Mic về 0 trên app → Cubase hiện 0.00 dB (dùng `tools\tham_do_cubase\nghe_phan_hoi.py` thấy `CC 21 = 100`).
  - Đổi tone/scale trên app → SysEx `disp|6|<Key>|`, `disp|7|Major|`.
  - Thoát app → hộp thoại "Đang đóng Cubase" → Cubase thoát, không còn process.
Expected: cả 5 ý đúng. Ghi kết quả vào docs (bước 3).

- [ ] **Step 3: Tài liệu**

`docs/NGHIEN_CUU_HO_TRO_CUBASE.md`: thêm mục `## 8. Trạng thái triển khai` liệt kê Task 1–9 đã xong, link kế hoạch này, kết quả chạy thử bước 2. `docs/KIOSK_MODE_GUIDE.md`: thêm đoạn "Dùng với Cubase: Cài đặt → Phần mềm thu âm → Cubase; đường dẫn là file `.cpr` bài mẫu; trong Cubase tắt *Release Driver when Application is in Background*; bản mẫu chốt là `template.cpr`." `docs/manual/index.html`: một câu tương tự ở phần Cài đặt.

- [ ] **Step 4: Commit**

```bash
git add docs/NGHIEN_CUU_HO_TRO_CUBASE.md docs/KIOSK_MODE_GUIDE.md docs/manual/index.html
git commit -m "docs: hướng dẫn dùng app với Cubase, trạng thái triển khai"
```

---

## Ngoài phạm vi (ghi để không lạc)

- Nghe phản hồi `QLS_PhanHoi` (ping/tên kênh) làm mốc "sẵn sàng" thay cho `ReadySchedule` hẹn giờ — làm chung cho cả hai DAW theo `docs/PLAN_SO_READY_HANDSHAKE.md`.
- Đổi tên khoá settings `studio_one_path` → `daw_project_path` (cần migration).
- Hồ sơ cân chỉnh theo DAW cho `key_midi_map`/`mode_config` (Cubase hiện trùng Studio One nên chưa cần).
