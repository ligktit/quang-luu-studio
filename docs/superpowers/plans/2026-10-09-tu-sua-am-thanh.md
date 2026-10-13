# Tự sửa âm thanh — Implementation Plan (giai đoạn 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lúc mở app tự kiểm tra các lỗi âm thanh thường gặp (DAW chưa mở, kênh Mic/Nhạc tắt, loopMIDI, thiết bị phát mặc định, mute Windows/trình duyệt, Cubase Release Driver) và báo; nút "Tự sửa âm thanh" sửa những gì sửa được an toàn rồi kiểm tra lại.

**Architecture:** Gói thuần Python `core/audio_doctor/` (không import Qt): mỗi lỗi là một `Check` với `detect(ctx)`/`fix(ctx)`, `Runner` chạy theo thứ tự phụ thuộc trên luồng nền, mọi thứ bên ngoài (hệ thống, Windows audio, thao tác trên UI) đi qua `DoctorContext` để test được bằng đồ giả. Tầng UI (`ui/audio_doctor_bridge.py`, dialog, dải cảnh báo header) chỉ nối dây và chuyển lời gọi về main thread. MIDI phản hồi từ Cubase (`QLS_PhanHoi`) được nghe thật để biết trạng thái kênh.

**Tech Stack:** Python 3.13, PySide6, mido/python-rtmidi, pycaw ≥ 20260927 (có `AudioUtilities.SetDefaultDevice`), comtypes, psutil, pywin32, pytest + pytest-qt.

**Spec:** `docs/superpowers/specs/2026-10-09-tu-sua-am-thanh-design.md`

## Global Constraints

- Lúc mở app: **chỉ kiểm tra và báo**, không gọi `fix()`.
- Tự sửa chỉ ép **Mic** và **Nhạc** về bật; **Bè / Vang** không bao giờ bị đụng.
- Kiểm tra lúc khởi động: chờ cửa sổ chính DAW + **10 s**, tối đa **180 s** (`audio_doctor_startup_wait_s`, mặc định 180); DAW sẵn sàng muộn hơn → chạy lại **một lần**.
- Không thao tác nào cần quyền Admin trong giai đoạn 1.
- Thiết bị ảo lưu theo **endpoint ID** (`music_playback_device_id`), kèm tên (`music_playback_device_name`) để hiển thị.
- Không bấm hộ hộp thoại của DAW; không tự tắt DAW trừ khi khách đồng ý (Release Driver).
- Sửa file cấu hình của DAW luôn sao lưu `.bak-YYYYmmdd-HHMMSS` trước.
- Chữ hiển thị cho khách: tiếng Việt có dấu; tên DAW lấy từ `daw.active().display_name`.
- Mọi exception trong check → `KHONG_RO` + ghi log, không làm hỏng cả lượt.
- Không gọi widget Qt từ luồng nền — đi qua `UiInvoker` hoặc Qt signal.
- `core/audio_doctor/*` không import PySide6.

## Review Focus

1. **Studio One không gửi phản hồi** → `ch_mic`/`ch_music` phải ra `KHONG_RO` lúc kiểm tra (không bật dải cảnh báo) và "Đã gửi lệnh bật …" khi sửa — test ở Task 6.
2. **Khách chưa chọn thiết bị ảo và máy không có thiết bị nào khớp tên** → không được đặt bừa thiết bị mặc định; ra `CAN_LAM_TAY` chỉ vào Cài đặt — test ở Task 7.
3. **Lượt kiểm tra khởi động đang chạy khi khách bấm Tự sửa** → lượt sửa chờ, không chạy song song (hai lượt cùng mở loopMIDI/DAW) — test ở Task 2.
4. **Khách từ chối đóng Cubase** khi sửa Release Driver → không đóng, không sửa file, ra `CAN_LAM_TAY` có hướng dẫn tay — test ở Task 6.
5. **Phản hồi MIDI từ Cubase làm vòng lặp gửi** (nhận mute → UI gửi lại CC → Cubase phát lại …) → `_on_midi_cc_received` chỉ cập nhật UI, không gửi — test ở Task 3.

## Môi trường

- Làm việc trong worktree `.claude/worktrees/tu-sua-am-thanh` (nhánh `feat/tu-sua-am-thanh`, tách từ HEAD hiện tại của `feat/dev-mode-ux`) — các thay đổi chưa commit của nhánh kia không bị đụng.
- Chạy test (từ WSL) — gọi tắt là **`PYTEST <đường dẫn>`** trong các bước dưới:

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio\.claude\worktrees\tu-sua-am-thanh && D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest <đường dẫn kiểu Windows> -q -p no:cacheprovider"
```

- Sau khi chạy suite rộng: `git checkout app_config.json` (suite đổi line-ending file này).

## File Structure

| File | Trách nhiệm |
|---|---|
| `core/audio_doctor/__init__.py` | `default_checks()`, re-export |
| `core/audio_doctor/model.py` | `Status`, `Finding`, `Check`, nhóm |
| `core/audio_doctor/context.py` | `DoctorContext` + mô tả giao diện `actions` |
| `core/audio_doctor/runner.py` | `Runner`, `RunReport`, `append_log` |
| `core/audio_doctor/startup.py` | `StartupGate` (logic chờ thuần) |
| `core/audio_doctor/service.py` | `AudioDoctorService` (chạy + vòng chờ khởi động) |
| `core/audio_doctor/feedback.py` | `DawFeedback` |
| `core/audio_doctor/system.py` | `SystemProbe` — process, MIDI port, registry, file, cửa sổ DAW |
| `core/audio_doctor/win_audio.py` | `WinAudio` (pycaw), `pick_virtual_device` |
| `core/audio_doctor/checks_bridge.py` | `loopmidi`, `daw_remote` |
| `core/audio_doctor/checks_daw.py` | `daw_running`, `daw_dialog`, `cubase_release_driver`, `ch_mic`, `ch_music` |
| `core/audio_doctor/checks_windows.py` | `win_playback_default`, `win_playback_mute`, `win_mic` |
| `core/audio_doctor/checks_browser.py` | `browser_session`, `yt_player` |
| `core/midi.py`, `core/config.py`, `core/engine/__init__.py`, `core/engine/_midi.py` | cổng phản hồi + `DawFeedback` |
| `core/cdp_monitor.py` | `get_player_state`, `unmute_player` |
| `ui/ui_invoker.py` | `UiInvoker` gọi hàm trên main thread (blocking) |
| `ui/audio_doctor_bridge.py` | `DashboardDoctorActions`, `build_service(dashboard)` |
| `ui/dialogs/audio_doctor_dialog.py` | Hộp thoại Tự sửa |
| `ui/panels/header.py`, `ui/panels/bottom_bar.py`, `ui/panels/mixer.py` | dải cảnh báo, nút, setter mute |
| `frontend_qt.py` | sửa `_sync_midi_states`, chấm MIDI, nối service/dialog/voice |
| `core/accessibility/shortcuts.py`, `core/accessibility/voice_input.py` | Ctrl+Shift+A, lệnh "sửa âm thanh" |
| `ui/dialogs/settings_dialog.py` | ô "Thiết bị đưa nhạc vào DAW" |
| `requirements.txt` | `pycaw>=20260927` |
| `docs/manual/index.html` | mục hướng dẫn |

> Lệch nhỏ so với spec: câu hướng dẫn làm tay nằm ngay trong `Finding.guide` của từng check thay vì `guides.py` riêng (mỗi hướng dẫn chỉ một check dùng — tách file là thừa). Phát hiện "tab Chrome bị tắt tiếng" (mute tab của Chrome) không làm được qua CDP/pycaw → `yt_player` kiểm player YouTube + thẻ `<video>`; mute ứng dụng trình duyệt trong Volume Mixer do `browser_session` lo.

---

### Task 0: Worktree

- [ ] **Step 1: Tạo worktree và nhánh**

```bash
cd /mnt/d/Projects/quang-luu-studio
git worktree add .claude/worktrees/tu-sua-am-thanh -b feat/tu-sua-am-thanh
cd .claude/worktrees/tu-sua-am-thanh && git log --oneline -1
```
Expected: commit spec `docs(spec): thiết kế Tự sửa âm thanh …` ở đầu.

- [ ] **Step 2: Chạy thử test sẵn có để chắc môi trường chạy được từ worktree**

Run: `PYTEST tests\core\test_midi.py`
Expected: PASS.

---

### Task 1: Mô hình + Runner

**Files:**
- Create: `core/audio_doctor/__init__.py`, `core/audio_doctor/model.py`, `core/audio_doctor/context.py`, `core/audio_doctor/runner.py`
- Test: `tests/core/audio_doctor/__init__.py` (rỗng), `tests/core/audio_doctor/test_runner.py`

**Interfaces:**
- Produces:
  - `Status` (str Enum): `OK, LOI, KHONG_RO, BO_QUA, DA_SUA, CAN_LAM_TAY`
  - `Finding(status, message, detail="", fixable=False, guide=())` + helper `ok(msg)`, `loi(msg, fixable=True, guide=(), detail="")`, `khong_ro(msg, detail="")`, `bo_qua(msg)`, `da_sua(msg)`, `can_lam_tay(msg, guide=())`
  - `Check` (base): thuộc tính `id, group, title, requires=(), timeout_s=15.0, fix_timeout_s=30.0, fix_when_unknown=False`; method `applies(ctx)->bool`, `detect(ctx)->Finding`, `fix(ctx)->Finding`
  - `GROUP_ORDER`, `GROUP_TITLES`
  - `DoctorContext` dataclass (xem code)
  - `Runner(checks).run(ctx, mode, source, on_progress=None) -> RunReport`; `mode in ("check","fix")`; `on_progress(check, finding_or_None)` — `None` = đang chạy
  - `RunReport.problems() -> list[tuple[Check, Finding]]`, `RunReport.to_dict() -> dict`, `RunReport.summary() -> str`
  - `append_log(report, path)`

- [ ] **Step 1: Viết test runner (fail)**

`tests/core/audio_doctor/test_runner.py`:

```python
import json
import threading
import time

import pytest

from core.audio_doctor.model import Check, Status, ok, loi, khong_ro, da_sua, can_lam_tay
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.runner import Runner, append_log


def _ctx(**kw):
    return DoctorContext(settings={}, daw=None, system=None, win=None, actions=None, **kw)


class FakeCheck(Check):
    def __init__(self, id, group="bridge", requires=(), detects=None, fix_result=None,
                 fix_when_unknown=False, applies=True, raise_in=None, sleep=0.0):
        self.id, self.group, self.title = id, group, id.upper()
        self.requires = requires
        self._detects = list(detects or [ok("ổn")])
        self._fix_result = fix_result or da_sua("đã sửa")
        self.fix_when_unknown = fix_when_unknown
        self._applies = applies
        self._raise_in = raise_in
        self._sleep = sleep
        self.fix_calls = 0
        self.timeout_s = 0.5

    def applies(self, ctx):
        return self._applies

    def detect(self, ctx):
        if self._raise_in == "detect":
            raise RuntimeError("hỏng")
        if self._sleep:
            time.sleep(self._sleep)
        return self._detects.pop(0) if len(self._detects) > 1 else self._detects[0]

    def fix(self, ctx):
        self.fix_calls += 1
        return self._fix_result


def test_check_mode_khong_bao_gio_goi_fix():
    c = FakeCheck("a", detects=[loi("hỏng")])
    rep = Runner([c]).run(_ctx(), "check", "startup")
    assert c.fix_calls == 0
    assert rep.results["a"].status is Status.LOI


def test_fix_thanh_cong_thi_ra_DA_SUA():
    c = FakeCheck("a", detects=[loi("hỏng"), ok("ổn rồi")], fix_result=da_sua("Đã bật"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert c.fix_calls == 1
    assert rep.results["a"].status is Status.DA_SUA
    assert rep.results["a"].message == "Đã bật"


def test_fix_xong_van_loi_thi_CAN_LAM_TAY_kem_huong_dan():
    c = FakeCheck("a", detects=[loi("hỏng", guide=("bước 1",))], fix_result=da_sua("x"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    f = rep.results["a"]
    assert f.status is Status.CAN_LAM_TAY
    assert f.guide == ("bước 1",)


def test_fix_tra_CAN_LAM_TAY_duoc_giu_du_detect_lai_ok():
    c = FakeCheck("a", detects=[loi("cũ"), ok("ổn")], fix_result=can_lam_tay("Khởi động lại DAW"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert rep.results["a"].status is Status.CAN_LAM_TAY
    assert rep.results["a"].message == "Khởi động lại DAW"


def test_loi_khong_sua_duoc_thanh_CAN_LAM_TAY_khi_fix():
    c = FakeCheck("a", detects=[loi("thiếu", fixable=False)])
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert c.fix_calls == 0
    assert rep.results["a"].status is Status.CAN_LAM_TAY


def test_khong_ro_co_fix_when_unknown_giu_ket_qua_fix():
    # Studio One không báo trạng thái: detect lại vẫn KHONG_RO → giữ "đã gửi lệnh".
    c = FakeCheck("a", detects=[khong_ro("không biết")], fix_when_unknown=True,
                  fix_result=da_sua("Đã gửi lệnh bật"))
    rep = Runner([c]).run(_ctx(), "fix", "button")
    assert rep.results["a"].status is Status.DA_SUA
    assert rep.results["a"].message == "Đã gửi lệnh bật"


def test_phu_thuoc_loi_thi_bo_qua():
    a = FakeCheck("a", detects=[loi("hỏng")])
    b = FakeCheck("b", requires=("a",))
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert rep.results["b"].status is Status.BO_QUA
    assert "A" in rep.results["b"].message


def test_phu_thuoc_khong_ro_khong_chan():
    a = FakeCheck("a", detects=[khong_ro("?")])
    b = FakeCheck("b", requires=("a",))
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert rep.results["b"].status is Status.OK


def test_check_khong_ap_dung_thi_khong_co_trong_ket_qua():
    rep = Runner([FakeCheck("a", applies=False)]).run(_ctx(), "check", "startup")
    assert "a" not in rep.results


def test_exception_va_timeout_thanh_KHONG_RO():
    a = FakeCheck("a", raise_in="detect")
    b = FakeCheck("b", sleep=2.0)
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert rep.results["a"].status is Status.KHONG_RO
    assert "hỏng" in rep.results["a"].detail
    assert rep.results["b"].status is Status.KHONG_RO


def test_thu_tu_theo_nhom_va_bao_tien_do():
    seen = []
    w = FakeCheck("w", group="windows")
    b = FakeCheck("b", group="bridge")
    Runner([w, b]).run(_ctx(), "check", "startup",
                       on_progress=lambda c, f: seen.append((c.id, f is None)))
    assert seen == [("b", True), ("b", False), ("w", True), ("w", False)]


def test_requires_phai_dung_truoc():
    with pytest.raises(ValueError):
        Runner([FakeCheck("b", requires=("a",)), FakeCheck("a", group="windows")])


def test_hai_luot_khong_chay_song_song():
    active = []
    peak = []

    class Slow(FakeCheck):
        def detect(self, ctx):
            active.append(1)
            peak.append(len(active))
            time.sleep(0.2)
            active.pop()
            return ok("ổn")

    r = Runner([Slow("a")])
    t = threading.Thread(target=r.run, args=(_ctx(), "check", "startup"))
    t.start()
    r.run(_ctx(), "fix", "button")
    t.join()
    assert max(peak) == 1


def test_problems_va_log(tmp_path):
    a = FakeCheck("a", detects=[loi("Mic tắt")])
    b = FakeCheck("b")
    rep = Runner([a, b]).run(_ctx(), "check", "startup")
    assert [c.id for c, _ in rep.problems()] == ["a"]
    assert "Mic tắt" in rep.summary()
    p = tmp_path / "logs" / "audio_doctor.log"
    append_log(rep, p)
    row = json.loads(p.read_text(encoding="utf-8").splitlines()[0])
    assert row["source"] == "startup" and row["results"]["a"]["status"] == "loi"
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_runner.py`
Expected: FAIL — `ModuleNotFoundError: core.audio_doctor`.

- [ ] **Step 3: Viết `model.py`**

```python
"""Mô hình chung của Tự sửa âm thanh: trạng thái, kết quả, mục kiểm tra."""
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    OK = "ok"
    LOI = "loi"
    KHONG_RO = "khong_ro"
    BO_QUA = "bo_qua"
    DA_SUA = "da_sua"
    CAN_LAM_TAY = "can_lam_tay"


# Mục phụ thuộc mang một trong các trạng thái này thì mục sau bỏ qua.
# KHONG_RO không chặn: "không biết" không có nghĩa là hỏng.
BLOCKING = frozenset({Status.LOI, Status.CAN_LAM_TAY, Status.BO_QUA})

# Thứ tự sửa: cầu nối → phần mềm thu âm → Windows → trình duyệt.
GROUP_ORDER = ("bridge", "daw", "windows", "browser")
GROUP_TITLES = {
    "bridge": "Cầu nối MIDI",
    "daw": "Phần mềm thu âm",
    "windows": "Windows",
    "browser": "Trình duyệt",
}


@dataclass(frozen=True)
class Finding:
    status: Status
    message: str
    detail: str = ""
    fixable: bool = False
    guide: tuple = field(default_factory=tuple)


def ok(message):
    return Finding(Status.OK, message)


def loi(message, fixable=True, guide=(), detail=""):
    return Finding(Status.LOI, message, detail=detail, fixable=fixable, guide=tuple(guide))


def khong_ro(message, detail=""):
    return Finding(Status.KHONG_RO, message, detail=detail)


def bo_qua(message):
    return Finding(Status.BO_QUA, message)


def da_sua(message):
    return Finding(Status.DA_SUA, message)


def can_lam_tay(message, guide=()):
    return Finding(Status.CAN_LAM_TAY, message, guide=tuple(guide))


class Check:
    """Một mục kiểm tra. Lớp con đặt thuộc tính và viết detect/fix.

    detect() không được thay đổi gì trên máy. fix() chỉ được gọi khi detect()
    ra LOI có fixable=True (hoặc KHONG_RO khi fix_when_unknown=True).
    """
    id = ""
    group = "bridge"
    title = ""
    requires = ()
    timeout_s = 15.0
    fix_timeout_s = 30.0
    fix_when_unknown = False

    def applies(self, ctx) -> bool:
        return True

    def detect(self, ctx) -> Finding:
        raise NotImplementedError

    def fix(self, ctx) -> Finding:
        raise NotImplementedError
```

- [ ] **Step 4: Viết `context.py`**

```python
"""Mọi thứ một Check được phép chạm tới — gom vào một chỗ để test bằng đồ giả."""
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class DoctorContext:
    """
    actions — đối tượng thao tác trên app (tầng UI cài đặt, xem
    ui/audio_doctor_bridge.DashboardDoctorActions). Các method:
        launch_daw() -> bool
        reconnect_midi() -> bool
        sync_midi() -> None
        close_daw() -> bool
        app_mic_state() -> Optional[tuple[bool, float]]     # (muted, mức dB)
        ensure_app_mic_on() -> None
        app_music_state() -> Optional[tuple[bool, int]]     # (muted, % âm lượng)
        ensure_app_music_on() -> None
        player_state() -> Optional[dict]   # {"muted": bool|None, "volume": int|None}; None = không có player
        unmute_player() -> bool
        save_setting(key, value) -> None
    """
    settings: dict
    daw: Any                      # core.daw.DawProfile
    system: Any                   # core.audio_doctor.system.SystemProbe
    win: Any                      # core.audio_doctor.win_audio.WinAudio
    actions: Any
    feedback: Any = None          # core.audio_doctor.feedback.DawFeedback
    send_cc: Callable[[int, int], bool] = lambda cc, value: False
    midi_cc: dict = field(default_factory=dict)
    midi_port: str = "QuangLuuMIDI"
    feedback_port: str = "QLS_PhanHoi"
    ask: Callable[[str], bool] = lambda question: False
    sleep: Callable[[float], None] = time.sleep
    daw_wait_s: float = 180.0
```

- [ ] **Step 5: Viết `runner.py`**

```python
"""Chạy các Check theo thứ tự phụ thuộc, ở chế độ chỉ kiểm tra hoặc sửa."""
import json
import os
import threading
import time
import traceback
from dataclasses import dataclass, field, replace

from core.audio_doctor.model import (
    BLOCKING, GROUP_ORDER, Finding, Status, bo_qua, khong_ro,
)


def _order(checks):
    ordered = sorted(checks, key=lambda c: GROUP_ORDER.index(c.group))
    seen = set()
    for c in ordered:
        missing = [r for r in c.requires if r not in seen]
        if missing:
            raise ValueError(f"Check {c.id!r} cần {missing} chạy trước")
        seen.add(c.id)
    return ordered


def _call_with_timeout(fn, timeout):
    box = {}

    def target():
        try:
            box["v"] = fn()
        except BaseException as e:  # noqa: BLE001 — chuyển nguyên về luồng gọi
            box["e"] = e

    t = threading.Thread(target=target, daemon=True, name="audio-doctor-call")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"quá {timeout:.0f} s")
    if "e" in box:
        raise box["e"]
    return box["v"]


@dataclass
class RunReport:
    source: str
    mode: str
    started: float
    checks: list = field(default_factory=list)
    results: dict = field(default_factory=dict)

    def problems(self):
        return [(c, self.results[c.id]) for c in self.checks
                if c.id in self.results
                and self.results[c.id].status in (Status.LOI, Status.CAN_LAM_TAY)]

    def summary(self) -> str:
        lines = []
        for c in self.checks:
            f = self.results.get(c.id)
            if f is not None:
                lines.append(f"[{f.status.value}] {c.title}: {f.message}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started)),
            "source": self.source,
            "mode": self.mode,
            "results": {cid: {"status": f.status.value, "message": f.message, "detail": f.detail}
                        for cid, f in self.results.items()},
        }


def append_log(report, path):
    try:
        os.makedirs(os.path.dirname(str(path)), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[AUDIO DOCTOR] Không ghi được nhật ký: {e}")


class Runner:
    def __init__(self, checks):
        self._checks = _order(list(checks))
        # Một lượt tại một thời điểm: bấm Tự sửa giữa lúc lượt khởi động đang
        # chạy thì chờ lượt kia xong, không để hai lượt cùng mở loopMIDI/DAW.
        self._lock = threading.Lock()

    @property
    def checks(self):
        return list(self._checks)

    def run(self, ctx, mode, source, on_progress=None) -> RunReport:
        assert mode in ("check", "fix")
        with self._lock:
            return self._run(ctx, mode, source, on_progress)

    def _emit(self, on_progress, check, finding):
        if on_progress is None:
            return
        try:
            on_progress(check, finding)
        except Exception as e:
            print(f"[AUDIO DOCTOR] on_progress lỗi: {e}")

    def _safe(self, fn, timeout, what):
        try:
            result = _call_with_timeout(fn, timeout)
            if not isinstance(result, Finding):
                return khong_ro("Không kiểm tra được", detail=f"{what} trả {result!r}")
            return result
        except TimeoutError as e:
            return khong_ro("Kiểm tra quá lâu, bỏ qua", detail=f"{what}: {e}")
        except Exception:
            return khong_ro("Không kiểm tra được", detail=traceback.format_exc())

    def _run(self, ctx, mode, source, on_progress):
        report = RunReport(source=source, mode=mode, started=time.time())
        titles = {c.id: c.title for c in self._checks}
        for c in self._checks:
            try:
                if not c.applies(ctx):
                    continue
            except Exception:
                continue
            report.checks.append(c)
            blocked = [r for r in c.requires
                       if r in report.results and report.results[r].status in BLOCKING]
            if blocked:
                f = bo_qua("Chờ sửa «" + "», «".join(titles[r] for r in blocked) + "» trước")
                report.results[c.id] = f
                self._emit(on_progress, c, f)
                continue
            self._emit(on_progress, c, None)
            f = self._safe(lambda: c.detect(ctx), c.timeout_s, f"{c.id}.detect")
            if mode == "fix":
                f = self._fix(c, ctx, f)
            report.results[c.id] = f
            self._emit(on_progress, c, f)
        return report

    def _fix(self, c, ctx, f):
        wants = ((f.status is Status.LOI and f.fixable)
                 or (f.status is Status.KHONG_RO and c.fix_when_unknown))
        if not wants:
            if f.status is Status.LOI:
                return replace(f, status=Status.CAN_LAM_TAY)
            return f
        fixed = self._safe(lambda: c.fix(ctx), c.fix_timeout_s, f"{c.id}.fix")
        if fixed.status is Status.CAN_LAM_TAY:
            return fixed
        again = self._safe(lambda: c.detect(ctx), c.timeout_s, f"{c.id}.detect")
        if again.status is Status.OK:
            msg = fixed.message if fixed.status is Status.DA_SUA else again.message
            return Finding(Status.DA_SUA, msg)
        if again.status is Status.KHONG_RO and fixed.status is Status.DA_SUA:
            return fixed
        guide = again.guide or f.guide or fixed.guide
        detail = "\n".join(x for x in (fixed.detail, again.detail) if x)
        return Finding(Status.CAN_LAM_TAY, again.message, detail=detail, guide=guide)
```

- [ ] **Step 6: Viết `__init__.py` tạm**

```python
"""Tự sửa âm thanh — chẩn đoán và sửa lỗi âm thanh thường gặp."""
```

(Task 9 bổ sung `default_checks()`.)

- [ ] **Step 7: Chạy test**

Run: `PYTEST tests\core\audio_doctor\test_runner.py`
Expected: PASS (13 test).

- [ ] **Step 8: Commit**

```bash
git add core/audio_doctor tests/core/audio_doctor
git commit -m "feat(audio-doctor): mô hình Check/Finding và Runner theo thứ tự phụ thuộc"
```

---

### Task 2: StartupGate + AudioDoctorService

**Files:**
- Create: `core/audio_doctor/startup.py`, `core/audio_doctor/service.py`
- Test: `tests/core/audio_doctor/test_startup.py`

**Interfaces:**
- Consumes: `Runner`, `RunReport`, `append_log` (Task 1)
- Produces:
  - `StartupGate(wait_s=180.0, settle_s=10.0, start=0.0).update(now, daw_ready) -> Optional[str]` trả `"run"` / `"rerun"` / `None`; thuộc tính `done`
  - `AudioDoctorService(ctx_factory, checks, log_path=None)`; `.run(mode, source, ask=None, on_progress=None) -> RunReport`; `.startup_loop(on_report, is_daw_ready, wait_s=180.0, poll_s=3.0, now=time.monotonic, sleep=time.sleep, max_s=3600.0)`; `.start_startup_watch(**same kwargs) -> Thread`; `.stop()`; `.last_report`
  - `ctx_factory(ask) -> DoctorContext`

- [ ] **Step 1: Viết test (fail)**

`tests/core/audio_doctor/test_startup.py`:

```python
from core.audio_doctor.model import Check, ok, loi
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.startup import StartupGate
from core.audio_doctor.service import AudioDoctorService


def test_cho_daw_san_sang_cong_10s():
    g = StartupGate(wait_s=180, settle_s=10, start=0)
    assert g.update(5, False) is None
    assert g.update(30, True) is None      # vừa thấy cửa sổ chính
    assert g.update(39, True) is None
    assert g.update(40, True) == "run"
    assert g.done


def test_het_180s_van_chay_roi_chay_lai_mot_lan_khi_daw_xong():
    g = StartupGate(wait_s=180, settle_s=10, start=0)
    assert g.update(179, False) is None
    assert g.update(180, False) == "run"
    assert not g.done
    assert g.update(200, True) is None
    assert g.update(210, True) == "rerun"
    assert g.update(300, True) is None
    assert g.done


def test_cua_so_chinh_bien_mat_thi_dem_lai():
    g = StartupGate(wait_s=180, settle_s=10, start=0)
    g.update(10, True)
    g.update(15, False)                     # hộp thoại che / đóng project
    assert g.update(21, True) is None
    assert g.update(31, True) == "run"


class _C(Check):
    id, group, title = "a", "bridge", "A"

    def detect(self, ctx):
        return loi("hỏng")


def _svc(tmp_path):
    ctx = lambda ask=None: DoctorContext(settings={}, daw=None, system=None, win=None, actions=None)
    return AudioDoctorService(ctx, [_C()], log_path=tmp_path / "audio_doctor.log")


def test_startup_loop_chay_check_va_bao_ket_qua(tmp_path):
    svc = _svc(tmp_path)
    t = [0.0]
    got = []
    ready = iter([False, True, True, True, True, True])
    svc.startup_loop(
        on_report=lambda rep, act: got.append((act, rep.mode, rep.source)),
        is_daw_ready=lambda: next(ready, True),
        wait_s=180, poll_s=5, now=lambda: t[0],
        sleep=lambda s: t.__setitem__(0, t[0] + s),
    )
    assert got == [("run", "check", "startup")]
    assert (tmp_path / "audio_doctor.log").exists()


def test_startup_loop_dung_khi_stop(tmp_path):
    svc = _svc(tmp_path)
    t = [0.0]
    got = []

    def sleep(s):
        t[0] += s
        if t[0] > 20:
            svc.stop()

    svc.startup_loop(on_report=lambda r, a: got.append(a), is_daw_ready=lambda: False,
                     wait_s=180, poll_s=5, now=lambda: t[0], sleep=sleep)
    assert got == []


def test_run_luu_last_report(tmp_path):
    svc = _svc(tmp_path)
    rep = svc.run("check", "button")
    assert svc.last_report is rep
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_startup.py`
Expected: FAIL — `ModuleNotFoundError: core.audio_doctor.startup`.

- [ ] **Step 3: Viết `startup.py`**

```python
"""Quyết định lúc nào chạy lượt kiểm tra khởi động — logic thuần, đồng hồ do ngoài đưa vào."""


class StartupGate:
    """
    - "run": cửa sổ chính DAW đã đứng yên `settle_s` giây, hoặc đã chờ đủ `wait_s`.
    - "rerun": lần "run" xảy ra do hết giờ chờ, sau đó DAW mới sẵn sàng → chạy lại
      MỘT lần để gỡ cảnh báo "chưa mở xong" nếu mọi thứ đã ổn.
    """

    def __init__(self, wait_s=180.0, settle_s=10.0, start=0.0):
        self.wait_s = float(wait_s)
        self.settle_s = float(settle_s)
        self.start = float(start)
        self._ready_since = None
        self._ran = False
        self._ran_ready = False

    @property
    def done(self) -> bool:
        return self._ran and self._ran_ready

    def update(self, now, daw_ready):
        if daw_ready:
            if self._ready_since is None:
                self._ready_since = now
        else:
            self._ready_since = None
        settled = self._ready_since is not None and now - self._ready_since >= self.settle_s
        if not self._ran:
            if settled:
                self._ran = self._ran_ready = True
                return "run"
            if now - self.start >= self.wait_s:
                self._ran = True
                return "run"
            return None
        if not self._ran_ready and settled:
            self._ran_ready = True
            return "rerun"
        return None
```

- [ ] **Step 4: Viết `service.py`**

```python
"""Ghép Runner với vòng chờ khởi động và nhật ký. Không biết gì về Qt."""
import threading
import time

from core.audio_doctor.runner import Runner, append_log
from core.audio_doctor.startup import StartupGate


class AudioDoctorService:
    def __init__(self, ctx_factory, checks, log_path=None):
        self._ctx_factory = ctx_factory
        self.runner = Runner(checks)
        self._log_path = log_path
        self._stop = threading.Event()
        self.last_report = None

    def stop(self):
        self._stop.set()

    def run(self, mode, source, ask=None, on_progress=None):
        ctx = self._ctx_factory(ask=ask)
        report = self.runner.run(ctx, mode, source, on_progress=on_progress)
        self.last_report = report
        if self._log_path:
            append_log(report, self._log_path)
        return report

    def startup_loop(self, on_report, is_daw_ready, wait_s=180.0, poll_s=3.0,
                     now=time.monotonic, sleep=time.sleep, max_s=3600.0):
        start = now()
        gate = StartupGate(wait_s=wait_s, settle_s=10.0, start=start)
        while not self._stop.is_set() and not gate.done and now() - start < max_s:
            try:
                ready = bool(is_daw_ready())
            except Exception:
                ready = False
            action = gate.update(now(), ready)
            if action:
                report = self.run("check", "startup")
                try:
                    on_report(report, action)
                except Exception as e:
                    print(f"[AUDIO DOCTOR] on_report lỗi: {e}")
                if gate.done:
                    break
            sleep(poll_s)

    def start_startup_watch(self, **kwargs):
        t = threading.Thread(target=self.startup_loop, kwargs=kwargs, daemon=True,
                             name="audio-doctor-startup")
        t.start()
        return t
```

- [ ] **Step 5: Chạy test**

Run: `PYTEST tests\core\audio_doctor`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/audio_doctor/startup.py core/audio_doctor/service.py tests/core/audio_doctor/test_startup.py
git commit -m "feat(audio-doctor): chờ DAW sẵn sàng (tối đa 180 s) rồi kiểm tra, chạy lại một lần khi DAW xong muộn"
```

---

### Task 3: Nghe phản hồi MIDI từ DAW (`QLS_PhanHoi`) + DawFeedback

**Files:**
- Create: `core/audio_doctor/feedback.py`
- Modify: `core/config.py:552` (thêm `MIDI_FEEDBACK_PORT_NAME`), `core/midi.py` (`start_listening` mở cổng phản hồi, thêm `ensure_listening`), `core/engine/__init__.py:45` (tạo `daw_feedback`), `core/engine/_midi.py` (`_handle_midi_in`, `connect_midi`)
- Test: `tests/core/audio_doctor/test_feedback.py`, `tests/core/test_midi.py` (thêm), `tests/ui/test_midi_resync_on_so_ready.py` (thêm test vòng lặp)

**Interfaces:**
- Produces:
  - `MIDI_FEEDBACK_PORT_NAME` trong `core.config` (mặc định `"QLS_PhanHoi"`, đọc `app_config.json` khoá `midi_feedback_port_name`)
  - `MidiHandler.start_listening(port_name=MIDI_FEEDBACK_PORT_NAME) -> bool`, `MidiHandler.ensure_listening() -> bool`
  - `ChannelState(muted: Optional[bool], fader: Optional[int], ts: float)`
  - `DawFeedback(midi_cc, clock=time.monotonic)`: `.on_cc(cc, value) -> bool`, `.get(group) -> Optional[ChannelState]`, `.wait_for(group, pred, timeout) -> bool`; nhóm: `"nhac","mic","vang","be"`
  - `SystemEngine.daw_feedback`

- [ ] **Step 1: Test DawFeedback (fail)**

`tests/core/audio_doctor/test_feedback.py`:

```python
import threading
import time

from core.audio_doctor.feedback import DawFeedback

CC = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
      "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53}


def test_mute_va_fader_theo_nhom():
    fb = DawFeedback(CC, clock=lambda: 7.0)
    assert fb.get("mic") is None
    assert fb.on_cc(51, 127) is True
    assert fb.on_cc(21, 100) is True
    st = fb.get("mic")
    assert st.muted is True and st.fader == 100 and st.ts == 7.0
    fb.on_cc(51, 0)
    assert fb.get("mic").muted is False


def test_cc_khong_lien_quan_bi_bo_qua():
    fb = DawFeedback(CC)
    assert fb.on_cc(49, 5) is False     # echo ping
    assert fb.on_cc(60, 3) is False     # độ dài tên kênh
    assert fb.get("nhac") is None


def test_wait_for_tra_true_khi_trang_thai_toi():
    fb = DawFeedback(CC)
    fb.on_cc(50, 127)
    threading.Timer(0.05, lambda: fb.on_cc(50, 0)).start()
    assert fb.wait_for("nhac", lambda s: s.muted is False, timeout=1.0) is True


def test_wait_for_het_gio():
    fb = DawFeedback(CC)
    t0 = time.monotonic()
    assert fb.wait_for("mic", lambda s: s.muted is False, timeout=0.1) is False
    assert time.monotonic() - t0 < 1.0
```

- [ ] **Step 2: Test MidiHandler mở cổng phản hồi (fail)** — thêm vào cuối `tests/core/test_midi.py`:

```python
def test_start_listening_mo_cong_phan_hoi(mock_mido):
    mock_mido.get_input_names.return_value = ["QuangLuuMIDI 0", "QLS_PhanHoi 1"]
    handler = MidiHandler()
    try:
        assert handler.start_listening() is True
        mock_mido.open_input.assert_called_once_with("QLS_PhanHoi 1")
    finally:
        handler.stop_listening()


def test_ensure_listening_mo_lai_khi_inport_mat(mock_mido):
    mock_mido.get_input_names.return_value = ["QLS_PhanHoi"]
    handler = MidiHandler()
    try:
        assert handler.ensure_listening() is True
        assert handler.ensure_listening() is True          # đang nghe → không mở lại
        assert mock_mido.open_input.call_count == 1
        handler.inport = None                              # loopMIDI khởi động lại
        assert handler.ensure_listening() is True
        assert mock_mido.open_input.call_count == 2
    finally:
        handler.stop_listening()
```

- [ ] **Step 3: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_feedback.py tests\core\test_midi.py`
Expected: FAIL (`ModuleNotFoundError`, `open_input` gọi với `"QuangLuuMIDI 0"`, không có `ensure_listening`).

- [ ] **Step 4: Viết `feedback.py`**

```python
"""Trạng thái kênh mà DAW báo về qua cổng phản hồi (QLS_PhanHoi).

Cubase (script MIDI Remote) phát CC 20–23 (fader) và CC 50–53 (mute) mỗi khi
kênh đổi. Studio One không phát gì → get() luôn None.
"""
import threading
import time
from dataclasses import dataclass
from typing import Optional

GROUPS = ("nhac", "mic", "vang", "be")
_FADER_KEYS = {"nhac": "mix_music", "mic": "mix_mic", "vang": "mix_reverb", "be": "mix_backing"}
_MUTE_KEYS = {"nhac": "mute_music", "mic": "mute_mic", "vang": "mute_reverb", "be": "mute_backing"}
_DEFAULTS = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
             "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53}


@dataclass(frozen=True)
class ChannelState:
    muted: Optional[bool]
    fader: Optional[int]
    ts: float


class DawFeedback:
    def __init__(self, midi_cc, clock=time.monotonic):
        def cc(key):
            return int((midi_cc or {}).get(key, _DEFAULTS[key]))
        self._fader = {cc(_FADER_KEYS[g]): g for g in GROUPS}
        self._mute = {cc(_MUTE_KEYS[g]): g for g in GROUPS}
        self._clock = clock
        self._state = {}
        self._cond = threading.Condition()

    def on_cc(self, cc, value) -> bool:
        cc, value = int(cc), int(value)
        with self._cond:
            if cc in self._mute:
                g = self._mute[cc]
                old = self._state.get(g)
                self._state[g] = ChannelState(value >= 64, old.fader if old else None, self._clock())
            elif cc in self._fader:
                g = self._fader[cc]
                old = self._state.get(g)
                self._state[g] = ChannelState(old.muted if old else None, value, self._clock())
            else:
                return False
            self._cond.notify_all()
            return True

    def get(self, group) -> Optional[ChannelState]:
        with self._cond:
            return self._state.get(group)

    def wait_for(self, group, pred, timeout) -> bool:
        def satisfied():
            st = self._state.get(group)
            return st is not None and bool(pred(st))
        with self._cond:
            return self._cond.wait_for(satisfied, timeout=timeout)
```

- [ ] **Step 5: `core/config.py` — thêm ngay dưới dòng 552**

```python
# Cổng DAW → app (Cubase script / Studio One readyPing gửi về đây). Khác cổng gửi.
MIDI_FEEDBACK_PORT_NAME = AppConfig.get("midi_feedback_port_name", "QLS_PhanHoi")
```

- [ ] **Step 6: `core/midi.py`** — đổi import và `start_listening`, thêm `ensure_listening`:

```python
from core.config import MIDI_PORT_NAME, MIDI_FEEDBACK_PORT_NAME
```

Thay chữ ký và vòng tìm cổng của `start_listening`:

```python
    def start_listening(self, port_name=MIDI_FEEDBACK_PORT_NAME):
        """Bắt đầu lắng nghe cổng PHẢN HỒI của DAW (QLS_PhanHoi) ở thread nền.

        Không nghe cổng gửi (QuangLuuMIDI): trên đó chỉ có lệnh của chính app.
        """
        import mido
        if self._is_listening:
            return True
        try:
            if self.inport:
                try:
                    self.inport.close()
                except Exception:
                    pass
                self.inport = None

            available = mido.get_input_names()
            for name in available:
                if port_name in name:
                    self.inport = mido.open_input(name)
                    self._is_listening = True
                    self._connect_in_warned = False
                    self._listen_thread = threading.Thread(
                        target=self._listen_loop, daemon=True
                    )
                    self._listen_thread.start()
                    print(f"Kết nối MIDI In thành công: {name}")
                    return True
            if not self._connect_in_warned:
                print(f"Không tìm thấy MIDI input port '{port_name}'")
                self._connect_in_warned = True
            return False
        except Exception as e:
            if not self._connect_in_warned:
                print(f"Lỗi kết nối MIDI In: {e}")
                self._connect_in_warned = True
            return False

    def ensure_listening(self):
        """Đang nghe thì thôi; mất inport (loopMIDI khởi động lại) thì mở lại."""
        if self._is_listening and self.inport is not None:
            return True
        self.stop_listening()
        return self.start_listening()
```

- [ ] **Step 7: Engine** — `core/engine/__init__.py` sau `self.midi_handler.on_cc_received = self._handle_midi_in`:

```python
        # Trạng thái kênh DAW báo về (Cubase) — Tự sửa âm thanh đọc ở đây.
        from core.audio_doctor.feedback import DawFeedback
        from core.config import AppConfig as _AC
        self.daw_feedback = DawFeedback(_AC.get("midi_cc", {}) or {})
```

`core/engine/_midi.py`:

```python
    def _handle_midi_in(self, cc, value):
        fb = getattr(self, "daw_feedback", None)
        if fb is not None:
            try:
                fb.on_cc(cc, value)
            except Exception as e:
                print(f"[MIDI IN] DawFeedback lỗi: {e}")
        if self.on_midi_cc_callback:
            self.on_midi_cc_callback(cc, value)
```

Trong `connect_midi`, ngay sau `result = self.midi_handler.connect()`:

```python
        if result:
            # Nghe phản hồi DAW cùng lúc với mở cổng gửi; reconnect cũng mở lại.
            try:
                self.midi_handler.ensure_listening()
            except Exception as e:
                print(f"[MIDI IN] Không mở được cổng phản hồi: {e}")
```

- [ ] **Step 8: Test chống vòng lặp phía UI** — thêm vào `tests/ui/test_midi_resync_on_so_ready.py`:

```python
def test_phan_hoi_mute_tu_daw_chi_cap_nhat_ui_khong_gui_lai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    mock_engine.send_midi.reset_mock()
    dashboard._on_midi_cc_received(51, 127)      # Cubase báo Mic đang mute
    assert dashboard.mute_states["mix_mic"] is True
    assert dashboard._mixer_channels["mix_mic"].is_muted() is True
    mock_engine.send_midi.assert_not_called()
```

- [ ] **Step 9: Chạy test**

Run: `PYTEST tests\core\audio_doctor tests\core\test_midi.py tests\core\test_engine.py tests\ui\test_midi_resync_on_so_ready.py`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add core/audio_doctor/feedback.py core/config.py core/midi.py core/engine tests/core/audio_doctor/test_feedback.py tests/core/test_midi.py tests/ui/test_midi_resync_on_so_ready.py
git commit -m "feat(midi): nghe cổng phản hồi QLS_PhanHoi, lưu trạng thái kênh DAW báo về (DawFeedback)"
```

---

### Task 4: Hai lỗi sẵn có — đồng bộ mute Mic/Bè và chấm MIDI

**Files:**
- Modify: `frontend_qt.py:1123-1136` (`_sync_midi_states`), `frontend_qt.py:1192-1213` (`_update_midi_status`)
- Test: `tests/ui/test_midi_resync_on_so_ready.py`

**Interfaces:**
- Produces: `MainDashboard._daw_running_cached() -> bool` (cache 5 s, dùng lại ở Task 10)

- [ ] **Step 1: Test (fail)** — thêm:

```python
def test_dong_bo_gui_lai_mute_mic_va_be(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dashboard.mute_states["mix_mic"] = True
    dashboard.mute_states["mix_backing"] = False
    mock_engine.send_midi.reset_mock()
    dashboard._sync_midi_states()
    sent = [c.args for c in mock_engine.send_midi.call_args_list]
    assert (51, 127) in sent
    assert (53, 0) in sent


def test_cham_midi_vang_khi_cong_mo_ma_daw_chua_chay(qapp, mock_engine, qtbot):
    from ui.design_tokens import C
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    mock_engine.is_midi_connected.return_value = True
    mock_engine.get_midi_port_name.return_value = "QuangLuuMIDI"
    dashboard._has_synced_initial_midi = True
    with patch("core.so_windows.is_running", return_value=False):
        dashboard._daw_running_at = None
        dashboard._update_midi_status()
    assert C["orange"] in dashboard._midi_dot.styleSheet()
    assert "chưa chạy" in dashboard._midi_dot.toolTip()
    with patch("core.so_windows.is_running", return_value=True):
        dashboard._daw_running_at = None
        dashboard._update_midi_status()
    assert C["teal"] in dashboard._midi_dot.styleSheet()
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\ui\test_midi_resync_on_so_ready.py`
Expected: 2 test mới FAIL.

- [ ] **Step 3: `_sync_midi_states`** — thay bước 4 bằng vòng cho cả ba kênh có mute trong DAW (Nhạc không nằm đây: thanh Nhạc chỉ điều khiển YouTube):

```python
            # 4. Mute Mic / Vang / Bè theo đúng nút trên app. Thiếu Mic/Bè thì
            # DAW mở lại giữ trạng thái mute của bản mẫu — khách thấy nút Mic
            # sáng mà không có tiếng.
            mute_cc_keys = (("mix_mic", "mute_mic", 51),
                            ("mix_reverb", "mute_reverb", 52),
                            ("mix_backing", "mute_backing", 53))
            multi_cc_map = {}
            try:
                multi_cc_map = backend.AppConfig.get_mute_multi_cc()
            except Exception as e:
                print(f"[MIDI SYNC] Multi CC sync error: {e}")
            for key, cc_name, cc_default in mute_cc_keys:
                is_muted = self.mute_states.get(key, False)
                cc = int(MIDI_CC.get(cc_name, cc_default))
                self.engine.send_midi(cc, 127 if is_muted else 0)
                print(f"[MUTE] Đồng bộ {key} -> {'MUTED' if is_muted else 'ACTIVE'} (CC {cc})")
                for entry in multi_cc_map.get(key, []):
                    try:
                        val = int(entry["on_value"]) if is_muted else int(entry["off_value"])
                        self.engine.send_midi(int(entry["cc"]), val)
                    except Exception as e:
                        print(f"[MIDI SYNC] Multi CC {key} lỗi: {e}")
```

- [ ] **Step 4: `_update_midi_status`** — thêm helper và thay nhánh `connected`:

```python
    def _daw_running_cached(self) -> bool:
        """so_windows.is_running() quét process — gọi tối đa 5 s/lần từ timer UI."""
        import time as _t
        from core import so_windows
        now = _t.monotonic()
        at = getattr(self, "_daw_running_at", None)
        if at is None or now - at > 5.0:
            try:
                self._daw_running_val = bool(so_windows.is_running())
            except Exception:
                self._daw_running_val = False
            self._daw_running_at = now
        return self._daw_running_val
```

Trong `_update_midi_status`, thay khối `try: name = ... except: pass` trong nhánh `connected` bằng:

```python
            from core import daw
            daw_name = daw.active().display_name
            if not self._daw_running_cached():
                self._midi_dot.setStyleSheet(f"color: {C['orange']}; font-size: 10px;")
                self._midi_dot.setToolTip(f"Cổng MIDI đã mở nhưng {daw_name} chưa chạy")
            else:
                try:
                    name = self.engine.get_midi_port_name()
                    color = C['teal'] if "QuangLuuMIDI" in name else C['accent']
                except Exception:
                    color = C['teal']
                self._midi_dot.setStyleSheet(f"color: {color}; font-size: 10px;")
                self._midi_dot.setToolTip(f"Đã kết nối {daw_name}")
```

và nhánh `else` (không kết nối) thêm `self._midi_dot.setToolTip("Chưa mở được cổng MIDI (loopMIDI)")`.

- [ ] **Step 5: Chạy test**

Run: `PYTEST tests\ui\test_midi_resync_on_so_ready.py tests\ui\test_main_window_logic.py`
Expected: PASS. (test_main_window_logic chạy lâu — xem ghi chú môi trường.)

- [ ] **Step 6: Commit**

```bash
git add frontend_qt.py tests/ui/test_midi_resync_on_so_ready.py
git commit -m "fix(midi): đồng bộ lại mute Mic/Bè khi DAW sẵn sàng; chấm MIDI vàng khi DAW chưa chạy"
```

---

### Task 5: SystemProbe + WinAudio (lớp bọc hệ thống)

**Files:**
- Create: `core/audio_doctor/system.py`, `core/audio_doctor/win_audio.py`
- Modify: `requirements.txt` (`pycaw>=20260927`)
- Test: `tests/core/audio_doctor/test_win_audio.py`, `tests/core/audio_doctor/test_system.py`

**Interfaces:**
- Produces `SystemProbe` (mọi method không ném lỗi ra ngoài trừ khi ghi chú):
  - `process_running(exe) -> bool`, `kill_process(exe) -> None`, `start_process(path) -> None`
  - `midi_ports() -> tuple[list[str], list[str]]` (outputs, inputs)
  - `find_loopmidi_exe() -> Optional[str]`
  - `reg_get(root, key, name) -> Optional[str]`, `reg_set(root, key, name, value) -> None` (ném OSError), `reg_names(root, key) -> list[str]`; `root in ("HKCU","HKLM")`
  - `appdata() -> str`, `documents() -> str`, `glob_dirs(pattern) -> list[str]`
  - `exists(path)`, `read_text(path) -> str`, `write_text(path, text)`, `sha256(path) -> Optional[str]`, `copy(src, dst)`, `backup(path) -> str`
  - `bundled(rel) -> Optional[str]` (file đi kèm app dưới `APP_DIR`)
  - `daw_running() -> bool`, `daw_main_window() -> bool`, `wait_daw_main_window(timeout) -> bool`, `daw_dialogs() -> list[tuple[int, str]]`, `focus_window(hwnd) -> None`
- Produces `WinAudio`:
  - `available() -> bool`
  - `render_devices() -> list[Device]` (`Device(id, name)`, chỉ thiết bị đang bật)
  - `default_render_ids() -> tuple[Optional[str], Optional[str]]` (console, multimedia)
  - `set_default_render(dev_id) -> None`
  - `default_capture_id() -> Optional[str]`
  - `endpoint_state(dev_id) -> tuple[bool, float]` (muted, %)
  - `set_endpoint(dev_id, muted=False, volume_pct=None) -> None`
  - `browser_sessions(names) -> list[tuple[str, bool, float]]`, `unmute_browser_sessions(names, volume_pct=100.0) -> int`
  - `name_of(dev_id) -> Optional[str]`
- `pick_virtual_device(devices) -> Optional[Device]`
- `BROWSER_PROCESS_NAMES` (dùng lại tuple của engine)

- [ ] **Step 1: Test phần thuần (fail)**

`tests/core/audio_doctor/test_win_audio.py`:

```python
from core.audio_doctor.win_audio import Device, pick_virtual_device


def test_chon_thiet_bi_ao_theo_ten():
    devs = [Device("1", "Speakers (Realtek)"), Device("2", "CABLE Input (VB-Audio Virtual Cable)"),
            Device("3", "ASIOVADPRO Out")]
    assert pick_virtual_device(devs).id == "3"     # ASIOVADPRO ưu tiên hơn VB-Cable


def test_khong_co_thiet_bi_ao():
    assert pick_virtual_device([Device("1", "Speakers (Realtek)")]) is None
```

`tests/core/audio_doctor/test_system.py`:

```python
import os

from core.audio_doctor.system import SystemProbe


def test_backup_va_ghi_giu_nguyen_byte(tmp_path):
    p = tmp_path / "Defaults.xml"
    raw = '<x name="ReleaseHardware" value="1"/>\r\n\u00e9'.encode("utf-8")
    p.write_bytes(raw)
    s = SystemProbe()
    text = s.read_text(str(p))
    bak = s.backup(str(p))
    assert os.path.basename(bak).startswith("Defaults.xml.bak-")
    s.write_text(str(p), text.replace('value="1"', 'value="0"'))
    assert p.read_bytes() == raw.replace(b'value="1"', b'value="0"')
    assert open(bak, "rb").read() == raw


def test_sha256_va_copy(tmp_path):
    src = tmp_path / "a.js"
    src.write_text("x", encoding="utf-8")
    dst = tmp_path / "sub" / "dir" / "a.js"
    s = SystemProbe()
    s.copy(str(src), str(dst))
    assert s.sha256(str(src)) == s.sha256(str(dst))
    assert s.sha256(str(tmp_path / "khong_co")) is None
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_win_audio.py tests\core\audio_doctor\test_system.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Viết `win_audio.py`**

```python
"""Đọc/đặt thiết bị âm thanh Windows qua pycaw (Core Audio).

Mọi method tự CoInitialize cho luồng đang gọi: Runner chạy check trên luồng nền.
pycaw/comtypes thiếu → available() False, các check Windows ra KHONG_RO.
"""
import re
from dataclasses import dataclass
from typing import Optional

# Tên tiến trình trình duyệt — cùng danh sách engine dùng cho thanh Nhạc.
BROWSER_PROCESS_NAMES = (
    "chrome.exe", "msedge.exe", "opera.exe", "firefox.exe",
    "brave.exe", "vivaldi.exe", "chromium.exe",
)

# Thứ tự = độ ưu tiên khi đề xuất thiết bị ảo đưa nhạc vào DAW.
_VIRTUAL_PATTERNS = (r"asiovad", r"vb-audio|cable", r"virtual")


@dataclass(frozen=True)
class Device:
    id: str
    name: str


def pick_virtual_device(devices) -> Optional[Device]:
    for pat in _VIRTUAL_PATTERNS:
        for d in devices:
            if re.search(pat, d.name or "", re.IGNORECASE):
                return d
    return None


def _co_init():
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass


class WinAudio:
    def available(self) -> bool:
        try:
            import comtypes  # noqa: F401
            from pycaw.pycaw import AudioUtilities  # noqa: F401
            return True
        except Exception:
            return False

    # ── thiết bị ─────────────────────────────────────────────────────────────
    def _enum(self):
        _co_init()
        from pycaw.pycaw import AudioUtilities
        return AudioUtilities.GetDeviceEnumerator()

    def render_devices(self):
        _co_init()
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import EDataFlow, DEVICE_STATE
        out = []
        for d in AudioUtilities.GetAllDevices(EDataFlow.eRender.value, DEVICE_STATE.ACTIVE.value):
            if d is not None and d.id:
                out.append(Device(d.id, d.FriendlyName or d.id))
        return out

    def name_of(self, dev_id) -> Optional[str]:
        for d in self.render_devices():
            if d.id == dev_id:
                return d.name
        return None

    def _default_id(self, flow, role):
        try:
            return self._enum().GetDefaultAudioEndpoint(flow, role).GetId()
        except Exception:
            return None

    def default_render_ids(self):
        from pycaw.constants import EDataFlow, ERole
        return (self._default_id(EDataFlow.eRender.value, ERole.eConsole.value),
                self._default_id(EDataFlow.eRender.value, ERole.eMultimedia.value))

    def default_capture_id(self):
        from pycaw.constants import EDataFlow, ERole
        return self._default_id(EDataFlow.eCapture.value, ERole.eConsole.value)

    def set_default_render(self, dev_id) -> None:
        _co_init()
        from pycaw.pycaw import AudioUtilities
        from pycaw.constants import ERole
        AudioUtilities.SetDefaultDevice(dev_id, roles=[ERole.eConsole, ERole.eMultimedia])

    def _volume(self, dev_id):
        from pycaw.pycaw import AudioUtilities
        dev = self._enum().GetDevice(dev_id)
        return AudioUtilities.CreateDevice(dev).EndpointVolume

    def endpoint_state(self, dev_id):
        vol = self._volume(dev_id)
        return bool(vol.GetMute()), float(vol.GetMasterVolumeLevelScalar()) * 100.0

    def set_endpoint(self, dev_id, muted=False, volume_pct=None) -> None:
        vol = self._volume(dev_id)
        vol.SetMute(1 if muted else 0, None)
        if volume_pct is not None:
            vol.SetMasterVolumeLevelScalar(max(0.0, min(100.0, float(volume_pct))) / 100.0, None)

    # ── session trình duyệt (Volume Mixer) ──────────────────────────────────
    def _browser_session_volumes(self, names):
        _co_init()
        from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
        names = {n.lower() for n in names}
        for s in AudioUtilities.GetAllSessions():
            try:
                proc = s.Process
                if proc is None or proc.name().lower() not in names:
                    continue
                yield proc.name(), s._ctl.QueryInterface(ISimpleAudioVolume)
            except Exception:
                continue

    def browser_sessions(self, names=BROWSER_PROCESS_NAMES):
        return [(n, bool(v.GetMute()), float(v.GetMasterVolume()) * 100.0)
                for n, v in self._browser_session_volumes(names)]

    def unmute_browser_sessions(self, names=BROWSER_PROCESS_NAMES, volume_pct=100.0) -> int:
        n = 0
        for _, v in self._browser_session_volumes(names):
            v.SetMute(0, None)
            v.SetMasterVolume(float(volume_pct) / 100.0, None)
            n += 1
        return n
```

> Khi viết xong, kiểm tra tên hằng trong `pycaw.constants` của bản trong `.venv` (`EDataFlow`, `ERole`, `DEVICE_STATE.ACTIVE`): `D:\Projects\quang-luu-studio\.venv\Lib\site-packages\pycaw\constants.py`. Nếu khác, sửa theo đúng tên ở đó.

- [ ] **Step 4: Viết `system.py`**

```python
"""Cổng ra hệ thống cho các Check: process, cổng MIDI, registry, file, cửa sổ DAW.

Tách riêng để test check bằng đồ giả; bản thật dưới đây gọi Windows thật.
"""
import glob
import hashlib
import os
import shutil
import subprocess
import time
from typing import Optional

_LOOPMIDI_REL = os.path.join("Tobias Erichsen", "loopMIDI", "loopMIDI.exe")


class SystemProbe:
    # ── process ─────────────────────────────────────────────────────────────
    def process_running(self, exe) -> bool:
        try:
            import psutil
            exe = exe.lower()
            return any((p.info.get("name") or "").lower() == exe
                       for p in psutil.process_iter(["name"]))
        except Exception:
            return False

    def kill_process(self, exe) -> None:
        try:
            import psutil
            for p in psutil.process_iter(["name"]):
                if (p.info.get("name") or "").lower() == exe.lower():
                    p.kill()
        except Exception as e:
            print(f"[AUDIO DOCTOR] Không dừng được {exe}: {e}")

    def start_process(self, path) -> None:
        subprocess.Popen([path], close_fds=True)

    # ── MIDI ────────────────────────────────────────────────────────────────
    def midi_ports(self):
        try:
            import mido
            return list(mido.get_output_names()), list(mido.get_input_names())
        except Exception:
            return [], []

    def find_loopmidi_exe(self) -> Optional[str]:
        roots = [os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
        for r in roots:
            p = os.path.join(r, _LOOPMIDI_REL)
            if r and os.path.isfile(p):
                return p
        return None

    # ── registry ────────────────────────────────────────────────────────────
    @staticmethod
    def _root(root):
        import winreg
        return {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}[root]

    def reg_get(self, root, key, name) -> Optional[str]:
        try:
            import winreg
            with winreg.OpenKey(self._root(root), key) as k:
                return str(winreg.QueryValueEx(k, name)[0])
        except Exception:
            return None

    def reg_set(self, root, key, name, value) -> None:
        import winreg
        with winreg.CreateKeyEx(self._root(root), key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, str(value))

    def reg_names(self, root, key):
        try:
            import winreg
            out = []
            with winreg.OpenKey(self._root(root), key) as k:
                i = 0
                while True:
                    try:
                        out.append(winreg.EnumValue(k, i)[0])
                    except OSError:
                        break
                    i += 1
            return out
        except Exception:
            return []

    # ── thư mục / file ──────────────────────────────────────────────────────
    def appdata(self) -> str:
        return os.environ.get("APPDATA", os.path.expanduser("~"))

    def documents(self) -> str:
        try:
            from win32com.shell import shell, shellcon
            return shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
        except Exception:
            return os.path.join(os.path.expanduser("~"), "Documents")

    def glob_dirs(self, pattern):
        return sorted(p for p in glob.glob(pattern) if os.path.isdir(p))

    def exists(self, path) -> bool:
        return bool(path) and os.path.exists(path)

    def read_text(self, path) -> str:
        # surrogateescape + newline="" → ghi lại đúng từng byte cũ, chỉ đổi chỗ sửa.
        with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            return fh.read()

    def write_text(self, path, text) -> None:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
            fh.write(text)

    def sha256(self, path) -> Optional[str]:
        try:
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            return None

    def copy(self, src, dst) -> None:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)

    def backup(self, path) -> str:
        dst = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copyfile(path, dst)
        return dst

    def bundled(self, rel) -> Optional[str]:
        from core.config import APP_DIR
        p = os.path.join(APP_DIR, rel)
        return p if os.path.isfile(p) else None

    # ── cửa sổ DAW ──────────────────────────────────────────────────────────
    def daw_running(self) -> bool:
        from core import so_windows
        return so_windows.is_running()

    def daw_main_window(self) -> bool:
        from core import so_windows
        return bool(so_windows.main_windows())

    def wait_daw_main_window(self, timeout) -> bool:
        from core import so_windows
        return so_windows.wait_for_main_window(timeout=timeout) is not None

    def daw_dialogs(self):
        """Cửa sổ ĐANG HIỆN, có tiêu đề, thuộc DAW nhưng không phải cửa sổ chính."""
        from core import so_windows
        mods = so_windows.win32_modules()
        if not mods:
            return []
        win32gui = mods[0]
        mains = set(so_windows.main_windows())
        out = []
        for hwnd in so_windows.all_windows():
            try:
                if hwnd in mains or not win32gui.IsWindowVisible(hwnd):
                    continue
                title = win32gui.GetWindowText(hwnd).strip()
                if title:
                    out.append((hwnd, title))
            except Exception:
                continue
        return out

    def focus_window(self, hwnd) -> None:
        from core import so_windows
        so_windows.force_foreground(hwnd)
```

- [ ] **Step 5: `requirements.txt`** — đổi `pycaw>=20240210` thành `pycaw>=20260927` (bản có `AudioUtilities.SetDefaultDevice`, đang cài trong `.venv`).

- [ ] **Step 6: Chạy test**

Run: `PYTEST tests\core\audio_doctor`
Expected: PASS.

- [ ] **Step 7: Kiểm tra nhanh trên máy thật (không phải test tự động)**

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio\.claude\worktrees\tu-sua-am-thanh && D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -c "from core.audio_doctor.win_audio import WinAudio as W; w=W(); print(w.available(), w.default_render_ids(), [d.name for d in w.render_devices()][:5], w.browser_sessions())""
```
Expected: in ra True, ID mặc định, danh sách tên thiết bị — không exception.

- [ ] **Step 8: Commit**

```bash
git add core/audio_doctor/system.py core/audio_doctor/win_audio.py requirements.txt tests/core/audio_doctor/test_win_audio.py tests/core/audio_doctor/test_system.py
git commit -m "feat(audio-doctor): lớp bọc hệ thống (process, MIDI, registry, cửa sổ DAW) và Windows audio (pycaw)"
```

---

### Task 6: Check cầu nối và DAW

**Files:**
- Create: `core/audio_doctor/checks_bridge.py`, `core/audio_doctor/checks_daw.py`
- Test: `tests/core/audio_doctor/fakes.py`, `tests/core/audio_doctor/test_checks_bridge.py`, `tests/core/audio_doctor/test_checks_daw.py`

**Interfaces:**
- Consumes: `Check`, helpers (Task 1), `DoctorContext`, `DawFeedback`/`ChannelState` (Task 3), method `SystemProbe` (Task 5)
- Produces: lớp `LoopMidiCheck` (`loopmidi`), `DawRemoteCheck` (`daw_remote`), `DawRunningCheck` (`daw_running`), `DawDialogCheck` (`daw_dialog`), `CubaseReleaseDriverCheck` (`cubase_release_driver`), `MicChannelCheck` (`ch_mic`), `MusicChannelCheck` (`ch_music`); hằng `LOOPMIDI_PORTS_KEY`, `FADER_LOW_CC = 20`, `MIC_LOW_DB = -40.0`

- [ ] **Step 1: Đồ giả dùng chung** — `tests/core/audio_doctor/fakes.py`:

```python
"""Đồ giả cho test check: hệ thống, Windows audio, thao tác app."""
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.feedback import DawFeedback
from core.daw import CUBASE, STUDIO_ONE

CC = {"mix_music": 20, "mix_mic": 21, "mix_reverb": 22, "mix_backing": 23,
      "mute_music": 50, "mute_mic": 51, "mute_reverb": 52, "mute_backing": 53}


class FakeSystem:
    def __init__(self):
        self.procs = set()
        self.outs, self.ins = [], []
        self.loopmidi_exe = r"C:\Program Files\Tobias Erichsen\loopMIDI\loopMIDI.exe"
        self.reg = {}                 # (root, key, name) -> value
        self.files = {}               # path -> text
        self.dirs = []
        self.bundle = {}              # rel -> path
        self.running = False
        self.main_window = False
        self.dialogs = []
        self.focused = []
        self.started = []
        self.killed = []
        self.backups = []
        self.on_start = None          # callback khi start_process

    def process_running(self, exe): return exe.lower() in self.procs
    def kill_process(self, exe): self.killed.append(exe); self.procs.discard(exe.lower())
    def start_process(self, path):
        self.started.append(path)
        if self.on_start:
            self.on_start(path)
    def midi_ports(self): return list(self.outs), list(self.ins)
    def find_loopmidi_exe(self): return self.loopmidi_exe
    def reg_get(self, root, key, name): return self.reg.get((root, key, name))
    def reg_set(self, root, key, name, value): self.reg[(root, key, name)] = value
    def reg_names(self, root, key): return [n for (r, k, n) in self.reg if r == root and k == key]
    def appdata(self): return r"C:\U\AppData\Roaming"
    def documents(self): return r"C:\U\Documents"
    def glob_dirs(self, pattern):
        import fnmatch
        return [d for d in self.dirs if fnmatch.fnmatch(d.lower(), pattern.lower())]
    def exists(self, path): return path in self.files
    def read_text(self, path): return self.files[path]
    def write_text(self, path, text): self.files[path] = text
    def sha256(self, path): return None if path not in self.files else str(hash(self.files[path]))
    def copy(self, src, dst): self.files[dst] = self.files[src]
    def backup(self, path):
        self.backups.append(path)
        return path + ".bak"
    def bundled(self, rel): return self.bundle.get(rel)
    def daw_running(self): return self.running
    def daw_main_window(self): return self.main_window
    def wait_daw_main_window(self, timeout): return self.main_window
    def daw_dialogs(self): return list(self.dialogs)
    def focus_window(self, hwnd): self.focused.append(hwnd)


class FakeWin:
    def __init__(self):
        self.ok = True
        self.devices = []
        self.defaults = (None, None)
        self.capture = None
        self.state = {}               # id -> (muted, pct)
        self.sessions = []            # (name, muted, pct)
        self.set_default_calls = []

    def available(self): return self.ok
    def render_devices(self): return list(self.devices)
    def name_of(self, dev_id): return next((d.name for d in self.devices if d.id == dev_id), None)
    def default_render_ids(self): return self.defaults
    def default_capture_id(self): return self.capture
    def set_default_render(self, dev_id):
        self.set_default_calls.append(dev_id)
        self.defaults = (dev_id, dev_id)
    def endpoint_state(self, dev_id): return self.state[dev_id]
    def set_endpoint(self, dev_id, muted=False, volume_pct=None):
        old = self.state.get(dev_id, (False, 100.0))
        self.state[dev_id] = (muted, old[1] if volume_pct is None else volume_pct)
    def browser_sessions(self, names=()): return list(self.sessions)
    def unmute_browser_sessions(self, names=(), volume_pct=100.0):
        self.sessions = [(n, False, volume_pct) for n, _, _ in self.sessions]
        return len(self.sessions)


class FakeActions:
    def __init__(self):
        self.calls = []
        self.launch_ok = True
        self.close_ok = True
        self.mic = (False, 0.0)
        self.music = (False, 80)
        self.player = None
        self.settings_saved = {}
        self.on_launch = None

    def launch_daw(self):
        self.calls.append("launch_daw")
        if self.on_launch:
            self.on_launch()
        return self.launch_ok
    def reconnect_midi(self): self.calls.append("reconnect_midi"); return True
    def sync_midi(self): self.calls.append("sync_midi")
    def close_daw(self): self.calls.append("close_daw"); return self.close_ok
    def app_mic_state(self): return self.mic
    def ensure_app_mic_on(self):
        self.calls.append("ensure_app_mic_on")
        self.mic = (False, self.mic[1] if self.mic[1] > -40 else 0.0)
    def app_music_state(self): return self.music
    def ensure_app_music_on(self): self.calls.append("ensure_app_music_on"); self.music = (False, max(self.music[1], 80))
    def player_state(self): return self.player
    def unmute_player(self):
        self.calls.append("unmute_player")
        if self.player:
            self.player = {"muted": False, "volume": max(self.player.get("volume") or 0, 80)}
        return True
    def save_setting(self, key, value): self.settings_saved[key] = value


def make_ctx(daw=STUDIO_ONE, settings=None, answers=None, **kw):
    system, win, actions = FakeSystem(), FakeWin(), FakeActions()
    sent = []
    asked = []
    answers = list(answers or [])

    def ask(q):
        asked.append(q)
        return answers.pop(0) if answers else False

    ctx = DoctorContext(
        settings=settings if settings is not None else {},
        daw=daw, system=system, win=win, actions=actions,
        feedback=DawFeedback(CC), send_cc=lambda cc, v: sent.append((cc, v)) or True,
        midi_cc=dict(CC), ask=ask, sleep=lambda s: None, **kw)
    ctx.sent, ctx.asked = sent, asked
    return ctx
```

> `DoctorContext` là dataclass thường (không `slots`), gắn thêm thuộc tính `sent/asked` cho test là hợp lệ.

- [ ] **Step 2: Test check cầu nối (fail)** — `tests/core/audio_doctor/test_checks_bridge.py`:

```python
from core.audio_doctor.checks_bridge import LoopMidiCheck, DawRemoteCheck, LOOPMIDI_PORTS_KEY
from core.audio_doctor.model import Status
from core.daw import CUBASE, STUDIO_ONE
from tests.core.audio_doctor.fakes import make_ctx


def test_loopmidi_du_cong_la_ok():
    ctx = make_ctx()
    ctx.system.outs, ctx.system.ins = ["QuangLuuMIDI 1"], ["QLS_PhanHoi 2"]
    assert LoopMidiCheck().detect(ctx).status is Status.OK


def test_loopmidi_chua_cai_khong_sua_duoc():
    ctx = make_ctx()
    ctx.system.loopmidi_exe = None
    f = LoopMidiCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable
    assert "setup_all.bat" in " ".join(f.guide)


def test_loopmidi_tat_thi_bat_len_va_noi_lai_midi():
    ctx = make_ctx()
    s = ctx.system
    s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QuangLuuMIDI")] = "QuangLuuMIDI"
    s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QLS_PhanHoi")] = "QLS_PhanHoi"

    def started(path):
        s.procs.add("loopmidi.exe")
        s.outs, s.ins = ["QuangLuuMIDI"], ["QLS_PhanHoi"]
    s.on_start = started
    c = LoopMidiCheck()
    assert c.detect(ctx).fixable
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA
    assert s.started == [s.loopmidi_exe] and s.killed == []
    assert "reconnect_midi" in ctx.actions.calls


def test_loopmidi_thieu_cong_thi_ghi_registry_va_khoi_dong_lai():
    ctx = make_ctx()
    s = ctx.system
    s.procs.add("loopmidi.exe")
    s.outs = ["QuangLuuMIDI"]
    s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QuangLuuMIDI")] = "QuangLuuMIDI"
    s.on_start = lambda p: (s.procs.add("loopmidi.exe"), setattr(s, "ins", ["QLS_PhanHoi"]))
    f = LoopMidiCheck().fix(ctx)
    assert s.reg[("HKCU", LOOPMIDI_PORTS_KEY, "QLS_PhanHoi")] == "QLS_PhanHoi"
    assert s.killed == ["loopMIDI.exe"]
    assert f.status is Status.DA_SUA


def test_loopmidi_khong_len_cong_thi_can_lam_tay():
    ctx = make_ctx()
    f = LoopMidiCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY


SO_DIR = r"C:\U\AppData\Roaming\PreSonus\Studio One 6"
SO_SURF = SO_DIR + r"\User Devices\QuangLuuMIDI\QuangLuuMIDI.surface.xml"
SO_INFO = SO_DIR + r"\User Devices\QuangLuuMIDI\deviceinfo.xml"
CB_JS = (r"C:\U\Documents\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local"
         r"\QuangLuu\QuangLuuMIDI\QuangLuu_QuangLuuMIDI.js")


def _so_bundle(ctx):
    s = ctx.system
    s.bundle = {"studio_one/QuangLuuMIDI.surface.xml": "SRC_SURF", "studio_one/deviceinfo.xml": "SRC_INFO",
                "cubase/QuangLuu_QuangLuuMIDI.js": "SRC_JS"}
    s.files.update({"SRC_SURF": "surf v2", "SRC_INFO": "info", "SRC_JS": "js v2"})
    s.dirs = [SO_DIR]


def test_surface_so_cu_thi_chep_lai_va_nhac_khoi_dong_lai_khi_dang_chay():
    ctx = make_ctx(STUDIO_ONE)
    _so_bundle(ctx)
    ctx.system.files.update({SO_SURF: "surf v1", SO_INFO: "info"})
    ctx.system.running = True
    c = DawRemoteCheck()
    assert c.detect(ctx).status is Status.LOI
    f = c.fix(ctx)
    assert ctx.system.files[SO_SURF] == "surf v2"
    assert f.status is Status.CAN_LAM_TAY and "Khởi động lại Studio One" in f.message
    assert c.detect(ctx).status is Status.OK


def test_script_cubase_thieu_thi_chep_khi_cubase_dang_dong():
    ctx = make_ctx(CUBASE)
    _so_bundle(ctx)
    c = DawRemoteCheck()
    assert c.detect(ctx).status is Status.LOI
    assert c.fix(ctx).status is Status.DA_SUA
    assert ctx.system.files[CB_JS] == "js v2"


def test_so_chua_tung_chay_thi_khong_ro():
    ctx = make_ctx(STUDIO_ONE)
    _so_bundle(ctx)
    ctx.system.dirs = []
    assert DawRemoteCheck().detect(ctx).status is Status.KHONG_RO
```

- [ ] **Step 3: Test check DAW (fail)** — `tests/core/audio_doctor/test_checks_daw.py`:

```python
from core.audio_doctor.checks_daw import (
    DawRunningCheck, DawDialogCheck, CubaseReleaseDriverCheck, MicChannelCheck, MusicChannelCheck,
)
from core.audio_doctor.model import Status
from core.daw import CUBASE, STUDIO_ONE
from tests.core.audio_doctor.fakes import make_ctx

SONG = r"D:\QLS\mau.song"


def test_daw_dang_chay_co_cua_so_chinh():
    ctx = make_ctx(settings={"studio_one_path": SONG})
    ctx.system.running = ctx.system.main_window = True
    assert DawRunningCheck().detect(ctx).status is Status.OK


def test_chua_dat_duong_dan_thi_khong_sua_duoc():
    ctx = make_ctx(settings={})
    f = DawRunningCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable
    assert "Cài đặt" in " ".join(f.guide)


def test_mo_daw_roi_dong_bo_midi():
    ctx = make_ctx(settings={"studio_one_path": SONG})
    ctx.system.files[SONG] = ""
    ctx.actions.on_launch = lambda: (setattr(ctx.system, "running", True),
                                     setattr(ctx.system, "main_window", True))
    c = DawRunningCheck()
    assert c.detect(ctx).fixable
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA
    assert ctx.actions.calls == ["launch_daw", "sync_midi"]


def test_daw_mo_khong_xong_thi_can_lam_tay():
    ctx = make_ctx(settings={"studio_one_path": SONG})
    ctx.system.files[SONG] = ""
    ctx.actions.on_launch = lambda: setattr(ctx.system, "running", True)
    assert DawRunningCheck().fix(ctx).status is Status.CAN_LAM_TAY


def test_hop_thoai_chan_thi_dua_len_truoc_khong_bam_ho():
    ctx = make_ctx()
    ctx.system.running = True
    ctx.system.dialogs = [(42, "Audio Device Setup")]
    c = DawDialogCheck()
    f = c.detect(ctx)
    assert f.status is Status.LOI and "Audio Device Setup" in f.message
    g = c.fix(ctx)
    assert g.status is Status.CAN_LAM_TAY and ctx.system.focused == [42]


def test_khong_co_hop_thoai():
    ctx = make_ctx()
    ctx.system.running = ctx.system.main_window = True
    assert DawDialogCheck().detect(ctx).status is Status.OK


DEF = r"C:\U\AppData\Roaming\Steinberg\Cubase 13_64\Defaults.xml"


def _cubase_prefs(ctx, value):
    ctx.system.dirs = [r"C:\U\AppData\Roaming\Steinberg\Cubase 13_64"]
    ctx.system.files[DEF] = f'<a><int name="ReleaseHardware" value="{value}"/></a>'


def test_release_driver_chi_ap_dung_cubase():
    assert not CubaseReleaseDriverCheck().applies(make_ctx(STUDIO_ONE))
    assert CubaseReleaseDriverCheck().applies(make_ctx(CUBASE))


def test_release_driver_bat_khi_cubase_dong_thi_sua_va_sao_luu():
    ctx = make_ctx(CUBASE)
    _cubase_prefs(ctx, 1)
    c = CubaseReleaseDriverCheck()
    assert c.detect(ctx).status is Status.LOI
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA
    assert 'value="0"' in ctx.system.files[DEF]
    assert ctx.system.backups == [DEF]
    assert ctx.actions.calls == []


def test_release_driver_khach_tu_choi_dong_cubase():
    ctx = make_ctx(CUBASE, answers=[False])
    _cubase_prefs(ctx, 1)
    ctx.system.running = True
    f = CubaseReleaseDriverCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY
    assert 'value="1"' in ctx.system.files[DEF]
    assert "close_daw" not in ctx.actions.calls
    assert ctx.asked and "Cubase" in ctx.asked[0]


def test_release_driver_khach_dong_y_thi_dong_sua_mo_lai():
    ctx = make_ctx(CUBASE, answers=[True])
    _cubase_prefs(ctx, 1)
    ctx.system.running = True
    ctx.actions.close_ok = True
    f = CubaseReleaseDriverCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert ctx.actions.calls == ["close_daw", "launch_daw"]


def test_release_driver_tat_la_ok():
    ctx = make_ctx(CUBASE)
    _cubase_prefs(ctx, 0)
    assert CubaseReleaseDriverCheck().detect(ctx).status is Status.OK


def test_kenh_mic_studio_one_khong_ro_nhung_van_gui_lenh():
    ctx = make_ctx(STUDIO_ONE)
    c = MicChannelCheck()
    assert c.fix_when_unknown
    assert c.detect(ctx).status is Status.KHONG_RO
    f = c.fix(ctx)
    assert f.status is Status.DA_SUA and "gửi lệnh" in f.message
    assert "ensure_app_mic_on" in ctx.actions.calls
    assert (51, 0) in ctx.sent


def test_kenh_mic_app_dang_tat_la_loi_ca_voi_studio_one():
    ctx = make_ctx(STUDIO_ONE)
    ctx.actions.mic = (True, 0.0)
    assert MicChannelCheck().detect(ctx).status is Status.LOI


def test_kenh_mic_cubase_bao_mute():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 127)
    ctx.feedback.on_cc(21, 100)
    f = MicChannelCheck().detect(ctx)
    assert f.status is Status.LOI and "Cubase" in f.message


def test_kenh_mic_cubase_xac_nhan_sau_khi_sua():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 127)
    ctx.send_cc = lambda cc, v: (ctx.sent.append((cc, v)), ctx.feedback.on_cc(cc, v))[1] or True
    f = MicChannelCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert MicChannelCheck().detect(ctx).status is Status.OK


def test_kenh_mic_cubase_khong_xac_nhan_thi_can_lam_tay():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(51, 127)
    f = MicChannelCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY


def test_kenh_nhac_fader_qua_thap_cubase():
    ctx = make_ctx(CUBASE)
    ctx.feedback.on_cc(50, 0)
    ctx.feedback.on_cc(20, 5)
    assert MusicChannelCheck().detect(ctx).status is Status.LOI


def test_kenh_nhac_sua_gui_bo_mute_va_fader_0db():
    ctx = make_ctx(CUBASE)
    MusicChannelCheck().fix(ctx)
    assert (50, 0) in ctx.sent and (20, CUBASE.fader_unity_cc) in ctx.sent


def test_kenh_khong_dung_be_va_vang():
    ctx = make_ctx(CUBASE)
    MicChannelCheck().fix(ctx)
    MusicChannelCheck().fix(ctx)
    assert not [cc for cc, _ in ctx.sent if cc in (22, 23, 52, 53)]
```

- [ ] **Step 4: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_checks_bridge.py tests\core\audio_doctor\test_checks_daw.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 5: Viết `checks_bridge.py`**

```python
"""Cầu nối app ↔ DAW: loopMIDI và bản điều khiển (surface SO / script Cubase)."""
import os

from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, can_lam_tay

LOOPMIDI_PORTS_KEY = r"Software\Tobias Erichsen\loopMIDI\Ports"
_LOOPMIDI_EXE = "loopMIDI.exe"


class LoopMidiCheck(Check):
    id, group, title = "loopmidi", "bridge", "Cổng MIDI (loopMIDI)"
    timeout_s = 10.0
    fix_timeout_s = 40.0

    def _missing(self, ctx):
        outs, ins = ctx.system.midi_ports()
        missing = []
        if not any(ctx.midi_port in n for n in outs):
            missing.append(ctx.midi_port)
        if not any(ctx.feedback_port in n for n in ins):
            missing.append(ctx.feedback_port)
        return missing

    def detect(self, ctx):
        missing = self._missing(ctx)
        if not missing:
            return ok("loopMIDI đang chạy, đủ cổng gửi và cổng phản hồi")
        if not ctx.system.find_loopmidi_exe():
            return loi("Máy chưa cài loopMIDI — nút bấm trên app không tới được phần mềm thu âm",
                       fixable=False,
                       guide=("Mở thư mục cài đặt app và chạy setup_all.bat.",
                              "Làm xong thì mở lại app."))
        if not ctx.system.process_running(_LOOPMIDI_EXE):
            return loi("loopMIDI chưa chạy — nút bấm trên app không tới được phần mềm thu âm")
        return loi("loopMIDI thiếu cổng: " + ", ".join(missing))

    def fix(self, ctx):
        s = ctx.system
        exe = s.find_loopmidi_exe()
        if not exe:
            return can_lam_tay("Máy chưa cài loopMIDI", guide=("Chạy setup_all.bat trong thư mục cài đặt app.",))
        names = set(s.reg_names("HKCU", LOOPMIDI_PORTS_KEY))
        added = False
        for port in (ctx.midi_port, ctx.feedback_port):
            if port not in names:
                s.reg_set("HKCU", LOOPMIDI_PORTS_KEY, port, port)
                added = True
        # loopMIDI chỉ đọc danh sách cổng lúc khởi động.
        if added and s.process_running(_LOOPMIDI_EXE):
            s.kill_process(_LOOPMIDI_EXE)
            ctx.sleep(2)
        if not s.process_running(_LOOPMIDI_EXE):
            s.start_process(exe)
        for _ in range(10):
            if not self._missing(ctx):
                break
            ctx.sleep(1)
        if self._missing(ctx):
            return can_lam_tay("Đã mở loopMIDI nhưng chưa thấy đủ cổng",
                               guide=("Mở loopMIDI, gõ tên cổng QuangLuuMIDI vào ô 'New port-name' rồi bấm +.",
                                      "Làm tương tự với QLS_PhanHoi.",))
        ctx.actions.reconnect_midi()
        return da_sua("Đã bật loopMIDI và nối lại MIDI")


class DawRemoteCheck(Check):
    id, group, title = "daw_remote", "bridge", "Bản điều khiển trong phần mềm thu âm"

    def _pairs(self, ctx):
        """[(nguồn đi kèm app, đích trên máy)] cho DAW đang chọn; None = chưa xác định được."""
        s = ctx.system
        if ctx.daw.kind == "cubase":
            dst = os.path.join(s.documents(), "Steinberg", "Cubase", "MIDI Remote", "Driver Scripts",
                               "Local", "QuangLuu", "QuangLuuMIDI", "QuangLuu_QuangLuuMIDI.js")
            return [("cubase/QuangLuu_QuangLuuMIDI.js", dst)]
        dirs = s.glob_dirs(os.path.join(s.appdata(), "PreSonus", "Studio One*"))
        if not dirs:
            return None
        pairs = []
        for d in dirs:
            base = os.path.join(d, "User Devices", "QuangLuuMIDI")
            pairs.append(("studio_one/QuangLuuMIDI.surface.xml", os.path.join(base, "QuangLuuMIDI.surface.xml")))
            pairs.append(("studio_one/deviceinfo.xml", os.path.join(base, "deviceinfo.xml")))
        return pairs

    def _stale(self, ctx, pairs):
        s = ctx.system
        out = []
        for rel, dst in pairs:
            src = s.bundled(rel)
            if src is None:
                continue
            if not s.exists(dst) or s.sha256(dst) != s.sha256(src):
                out.append((src, dst))
        return out

    def detect(self, ctx):
        name = ctx.daw.display_name
        pairs = self._pairs(ctx)
        if pairs is None:
            return khong_ro(f"{name} chưa chạy lần nào trên máy này")
        if not any(ctx.system.bundled(rel) for rel, _ in pairs):
            return khong_ro("Không thấy bản điều khiển đi kèm app")
        if self._stale(ctx, pairs):
            return loi(f"Bản điều khiển trong {name} chưa cài hoặc đã cũ — nút mới trên app sẽ không ăn")
        return ok(f"Bản điều khiển trong {name} đúng bản đi kèm app")

    def fix(self, ctx):
        name = ctx.daw.display_name
        for src, dst in self._stale(ctx, self._pairs(ctx) or []):
            ctx.system.copy(src, dst)
        if ctx.system.daw_running():
            return can_lam_tay(f"Đã chép bản mới — Khởi động lại {name} để nạp",
                               guide=(f"Lưu bài rồi tắt {name}, sau đó mở lại.",))
        return da_sua(f"Đã cài bản điều khiển mới cho {name}")
```

- [ ] **Step 6: Viết `checks_daw.py`**

```python
"""Phần mềm thu âm: đang chạy chưa, có hộp thoại chặn không, Release Driver, kênh Mic/Nhạc."""
import os
import re

from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, can_lam_tay

FADER_LOW_CC = 20          # fader thấp hơn mức này coi như kéo hết
MIC_LOW_DB = -40.0         # thanh Mic trên app thấp hơn mức này coi như tắt
_RELEASE_RE = re.compile(r'(name="ReleaseHardware"\s+value=")(\d)(")')


class DawRunningCheck(Check):
    id, group, title = "daw_running", "daw", "Phần mềm thu âm đang chạy"
    timeout_s = 10.0
    fix_timeout_s = 200.0

    def detect(self, ctx):
        name = ctx.daw.display_name
        s = ctx.system
        if s.daw_main_window():
            return ok(f"{name} đang chạy")
        if s.daw_running():
            return loi(f"{name} đang mở nhưng chưa xong (còn nạp bài hoặc đang chờ hộp thoại)")
        path = (ctx.settings or {}).get("studio_one_path", "")
        if not path or not s.exists(path):
            return loi(f"Chưa mở {name}, và app chưa biết mở file nào",
                       fixable=False,
                       guide=("Bấm ⚙ Cài đặt → mục phần mềm thu âm → chọn file bài mẫu hoặc file .exe.",
                              f"Hoặc tự mở {name}."))
        return loi(f"Chưa mở {name}")

    def fix(self, ctx):
        name = ctx.daw.display_name
        s = ctx.system
        if not s.daw_running() and not ctx.actions.launch_daw():
            return can_lam_tay(f"Không mở được {name}", guide=(f"Tự mở {name} từ biểu tượng trên màn hình.",))
        if not s.wait_daw_main_window(ctx.daw_wait_s):
            return can_lam_tay(f"{name} chưa mở xong sau {int(ctx.daw_wait_s // 60)} phút",
                               guide=(f"Xem {name} có đang hỏi gì không (hộp thoại) và trả lời.",))
        ctx.actions.sync_midi()
        return da_sua(f"Đã mở {name}")


class DawDialogCheck(Check):
    id, group, title = "daw_dialog", "daw", "Hộp thoại đang chờ"

    def detect(self, ctx):
        s = ctx.system
        if not s.daw_running() or s.daw_main_window():
            return ok("Không có hộp thoại nào đang chờ")
        dialogs = s.daw_dialogs()
        if not dialogs:
            return khong_ro(f"{ctx.daw.display_name} đang khởi động")
        title = dialogs[0][1]
        return loi(f"{ctx.daw.display_name} đang hỏi: «{title}» — trả lời hộp thoại này",
                   guide=("Đọc hộp thoại vừa hiện lên và chọn đúng (thường là OK / Đồng ý).",
                          "Không chắc thì bấm «Gửi cho kỹ thuật» bên dưới."))

    def fix(self, ctx):
        dialogs = ctx.system.daw_dialogs()
        if dialogs:
            ctx.system.focus_window(dialogs[0][0])
            return can_lam_tay(f"{ctx.daw.display_name} đang hỏi: «{dialogs[0][1]}» — trả lời hộp thoại này",
                               guide=("Hộp thoại đã được đưa lên trước màn hình.",))
        return da_sua("Hộp thoại đã đóng")


class CubaseReleaseDriverCheck(Check):
    id, group, title = "cubase_release_driver", "daw", "Cubase giữ card âm thanh khi chạy nền"
    fix_timeout_s = 200.0

    _GUIDE = ("Trong Cubase: Studio → Studio Setup → Audio System.",
              "Bỏ dấu «Release Driver when Application is in Background» rồi bấm OK.")

    def applies(self, ctx):
        return getattr(ctx.daw, "kind", "") == "cubase"

    def _files(self, ctx):
        s = ctx.system
        out = []
        for d in s.glob_dirs(os.path.join(s.appdata(), "Steinberg", "Cubase*")):
            f = os.path.join(d, "Defaults.xml")
            if s.exists(f):
                out.append(f)
        return out

    def _on(self, ctx):
        out = []
        for f in self._files(ctx):
            m = _RELEASE_RE.search(ctx.system.read_text(f))
            if m and m.group(2) == "1":
                out.append(f)
        return out

    def detect(self, ctx):
        if not self._files(ctx):
            return khong_ro("Không đọc được cấu hình Cubase")
        if self._on(ctx):
            return loi("Cubase đang bật «Release Driver when Application is in Background» — "
                       "app ẩn Cubase nên sẽ mất tiếng", guide=self._GUIDE)
        return ok("Cubase giữ card âm thanh cả khi chạy nền")

    def fix(self, ctx):
        s = ctx.system
        was_running = s.daw_running()
        if was_running:
            if not ctx.ask("Cần đóng Cubase để tắt «Release Driver when Application is in Background». "
                           "Đóng Cubase ngay?"):
                return can_lam_tay("Chưa sửa — cần đóng Cubase trước", guide=self._GUIDE)
            if not ctx.actions.close_daw():
                return can_lam_tay("Không đóng được Cubase", guide=self._GUIDE)
        for f in self._on(ctx):
            s.backup(f)
            s.write_text(f, _RELEASE_RE.sub(r"\g<1>0\g<3>", s.read_text(f)))
        if was_running:
            ctx.actions.launch_daw()
        return da_sua("Đã tắt «Release Driver when Application is in Background»")


class _ChannelCheck(Check):
    group = "daw"
    requires = ("loopmidi", "daw_running")
    fix_when_unknown = True
    fix_timeout_s = 15.0
    fb_group = ""
    label = ""

    def _app_problem(self, ctx):
        return None

    def _send_on(self, ctx):
        raise NotImplementedError

    def detect(self, ctx):
        name = ctx.daw.display_name
        problem = self._app_problem(ctx)
        if problem:
            return loi(problem)
        st = ctx.feedback.get(self.fb_group) if (ctx.feedback and ctx.daw.kind == "cubase") else None
        if st is None or st.muted is None:
            if ctx.daw.kind == "cubase":
                return khong_ro(f"Chưa nhận được trạng thái kênh {self.label} từ Cubase")
            return khong_ro(f"{name} không báo lại trạng thái kênh {self.label}")
        if st.muted:
            return loi(f"Kênh {self.label} đang tắt (mute) trong {name}")
        if st.fader is not None and st.fader < FADER_LOW_CC:
            return loi(f"Fader kênh {self.label} trong {name} gần như kéo hết")
        return ok(f"Kênh {self.label} đang bật")

    def fix(self, ctx):
        name = ctx.daw.display_name
        self._send_on(ctx)
        if ctx.daw.kind == "cubase" and ctx.feedback is not None:
            if ctx.feedback.wait_for(self.fb_group, lambda s: s.muted is False, timeout=2.0):
                return da_sua(f"Đã bật kênh {self.label}")
            return can_lam_tay(f"Đã gửi lệnh bật kênh {self.label} nhưng Cubase chưa xác nhận",
                               guide=(f"Trong Cubase, xem track {self.label}: bỏ nút M (mute), kéo fader lên.",))
        return da_sua(f"Đã gửi lệnh bật kênh {self.label} ({name} không báo lại — "
                      f"nếu vẫn im, kiểm tra track {self.label} trong {name})")


class MicChannelCheck(_ChannelCheck):
    id, title = "ch_mic", "Kênh Mic"
    fb_group, label = "mic", "Mic"

    def _app_problem(self, ctx):
        st = ctx.actions.app_mic_state()
        if st is None:
            return None
        muted, level = st
        if muted:
            return "Kênh Mic đang tắt trên app"
        if level <= MIC_LOW_DB:
            return "Thanh Mic trên app đang kéo hết"
        return None

    def _send_on(self, ctx):
        ctx.actions.ensure_app_mic_on()
        ctx.send_cc(int(ctx.midi_cc.get("mute_mic", 51)), 0)


class MusicChannelCheck(_ChannelCheck):
    id, title = "ch_music", "Kênh Nhạc"
    fb_group, label = "nhac", "Nhạc"

    def _send_on(self, ctx):
        ctx.send_cc(int(ctx.midi_cc.get("mute_music", 50)), 0)
        ctx.send_cc(int(ctx.midi_cc.get("mix_music", 20)), int(ctx.daw.fader_unity_cc))
```

- [ ] **Step 7: Chạy test**

Run: `PYTEST tests\core\audio_doctor`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add core/audio_doctor/checks_bridge.py core/audio_doctor/checks_daw.py tests/core/audio_doctor
git commit -m "feat(audio-doctor): kiểm tra/sửa loopMIDI, bản điều khiển DAW, DAW đang chạy, hộp thoại, Release Driver, kênh Mic/Nhạc"
```

---

### Task 7: Check Windows và trình duyệt

**Files:**
- Create: `core/audio_doctor/checks_windows.py`, `core/audio_doctor/checks_browser.py`
- Test: `tests/core/audio_doctor/test_checks_windows.py`

**Interfaces:**
- Consumes: `Device`, `pick_virtual_device`, `BROWSER_PROCESS_NAMES` (Task 5); fakes (Task 6)
- Produces: `WinPlaybackDefaultCheck` (`win_playback_default`), `WinPlaybackMuteCheck` (`win_playback_mute`), `WinMicCheck` (`win_mic`), `BrowserSessionCheck` (`browser_session`), `YtPlayerCheck` (`yt_player`); `MIC_CONSENT_KEY`

- [ ] **Step 1: Test (fail)** — `tests/core/audio_doctor/test_checks_windows.py`:

```python
from core.audio_doctor.checks_windows import (
    WinPlaybackDefaultCheck, WinPlaybackMuteCheck, WinMicCheck, MIC_CONSENT_KEY,
)
from core.audio_doctor.checks_browser import BrowserSessionCheck, YtPlayerCheck
from core.audio_doctor.model import Status
from core.audio_doctor.win_audio import Device
from tests.core.audio_doctor.fakes import make_ctx

VAD = Device("{vad}", "ASIOVADPRO Out")
SPK = Device("{spk}", "Speakers (Realtek)")


def _ctx(settings=None, answers=None):
    ctx = make_ctx(settings=settings if settings is not None else {}, answers=answers)
    ctx.win.devices = [SPK, VAD]
    return ctx


def test_mac_dinh_dung_thiet_bi_ao():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.defaults = ("{vad}", "{vad}")
    assert WinPlaybackDefaultCheck().detect(ctx).status is Status.OK


def test_mac_dinh_nhay_sang_loa_thi_dat_lai():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.defaults = ("{spk}", "{spk}")
    c = WinPlaybackDefaultCheck()
    f = c.detect(ctx)
    assert f.status is Status.LOI and "Speakers (Realtek)" in f.message
    assert c.fix(ctx).status is Status.DA_SUA
    assert ctx.win.set_default_calls == ["{vad}"]


def test_thiet_bi_ao_bien_mat_khong_sua_duoc():
    ctx = _ctx({"music_playback_device_id": "{gone}", "music_playback_device_name": "VB-Cable"})
    ctx.win.defaults = ("{spk}", "{spk}")
    f = WinPlaybackDefaultCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable and "VB-Cable" in f.message


def test_chua_chon_thiet_bi_thi_khong_ro_luc_kiem_tra():
    c = WinPlaybackDefaultCheck()
    assert c.fix_when_unknown
    assert c.detect(_ctx()).status is Status.KHONG_RO


def test_chua_chon_thiet_bi_de_xuat_va_hoi_khach():
    ctx = _ctx(answers=[True])
    ctx.win.defaults = ("{spk}", "{spk}")
    f = WinPlaybackDefaultCheck().fix(ctx)
    assert f.status is Status.DA_SUA
    assert "ASIOVADPRO" in ctx.asked[0]
    assert ctx.actions.settings_saved == {"music_playback_device_id": "{vad}",
                                          "music_playback_device_name": "ASIOVADPRO Out"}
    assert ctx.win.set_default_calls == ["{vad}"]


def test_khong_co_thiet_bi_nao_khop_ten_thi_khong_dat_bua():
    ctx = make_ctx(answers=[True])
    ctx.win.devices = [SPK]
    f = WinPlaybackDefaultCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY
    assert ctx.win.set_default_calls == [] and ctx.asked == []
    assert "Cài đặt" in " ".join(f.guide)


def test_khach_tu_choi_de_xuat():
    ctx = _ctx(answers=[False])
    f = WinPlaybackDefaultCheck().fix(ctx)
    assert f.status is Status.CAN_LAM_TAY and ctx.win.set_default_calls == []


def test_pycaw_thieu_thi_khong_ro():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.ok = False
    assert WinPlaybackDefaultCheck().detect(ctx).status is Status.KHONG_RO


def test_thiet_bi_ao_bi_mute():
    ctx = _ctx({"music_playback_device_id": "{vad}"})
    ctx.win.state["{vad}"] = (True, 100.0)
    c = WinPlaybackMuteCheck()
    assert c.detect(ctx).status is Status.LOI
    c.fix(ctx)
    assert ctx.win.state["{vad}"] == (False, 100.0)


def test_khong_chon_thiet_bi_thi_kiem_loa_mac_dinh():
    ctx = _ctx()
    ctx.win.defaults = ("{spk}", "{spk}")
    ctx.win.state["{spk}"] = (False, 2.0)
    assert WinPlaybackMuteCheck().detect(ctx).status is Status.LOI


def test_mic_bi_chan_trong_quyen_rieng_tu_va_mute():
    ctx = _ctx()
    ctx.system.reg[("HKCU", MIC_CONSENT_KEY + r"\NonPackaged", "Value")] = "Deny"
    ctx.win.capture = "{mic}"
    ctx.win.state["{mic}"] = (True, 80.0)
    c = WinMicCheck()
    f = c.detect(ctx)
    assert f.status is Status.LOI and f.fixable
    assert c.fix(ctx).status is Status.DA_SUA
    assert ctx.system.reg[("HKCU", MIC_CONSENT_KEY + r"\NonPackaged", "Value")] == "Allow"
    assert ctx.win.state["{mic}"][0] is False


def test_mic_bi_chan_toan_may_can_ky_thuat():
    ctx = _ctx()
    ctx.system.reg[("HKLM", MIC_CONSENT_KEY, "Value")] = "Deny"
    f = WinMicCheck().detect(ctx)
    assert f.status is Status.LOI and not f.fixable


def test_trinh_duyet_bi_mute_trong_volume_mixer():
    ctx = _ctx()
    ctx.win.sessions = [("chrome.exe", True, 100.0)]
    c = BrowserSessionCheck()
    assert c.detect(ctx).status is Status.LOI
    c.fix(ctx)
    assert ctx.win.sessions == [("chrome.exe", False, 100.0)]


def test_trinh_duyet_chua_phat_thi_bo_qua():
    assert BrowserSessionCheck().detect(_ctx()).status is Status.BO_QUA


def test_player_youtube():
    ctx = _ctx()
    c = YtPlayerCheck()
    assert c.detect(ctx).status is Status.BO_QUA            # chưa có player
    ctx.actions.player = {"muted": True, "volume": 50}
    assert c.detect(ctx).status is Status.LOI
    c.fix(ctx)
    assert c.detect(ctx).status is Status.OK


def test_thanh_nhac_tren_app_dang_tat():
    ctx = _ctx()
    ctx.actions.player = {"muted": None, "volume": None}   # player nhúng: không đọc được
    ctx.actions.music = (True, 80)
    f = YtPlayerCheck().detect(ctx)
    assert f.status is Status.LOI and "Nhạc" in f.message
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_checks_windows.py`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Viết `checks_windows.py`**

```python
"""Windows: thiết bị phát mặc định, mute thiết bị ảo, mic + quyền micro."""
from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, can_lam_tay
from core.audio_doctor.win_audio import pick_virtual_device

MIC_CONSENT_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
LOW_PCT = 5.0
_PICK_GUIDE = ("Bấm ⚙ Cài đặt → tab Âm thanh → «Thiết bị đưa nhạc vào DAW» → chọn thiết bị ảo "
               "(ASIOVADPRO / VB-Cable) mà track Nhạc trong phần mềm thu âm đang nhận.",)


def _target(ctx):
    s = ctx.settings or {}
    return s.get("music_playback_device_id") or None, s.get("music_playback_device_name") or ""


class WinPlaybackDefaultCheck(Check):
    id, group, title = "win_playback_default", "windows", "Thiết bị phát mặc định"
    fix_when_unknown = True

    def detect(self, ctx):
        if not ctx.win.available():
            return khong_ro("Không đọc được thiết bị âm thanh Windows")
        target, saved_name = _target(ctx)
        if not target:
            return khong_ro("Chưa chọn thiết bị đưa nhạc vào DAW")
        devices = ctx.win.render_devices()
        names = {d.id: d.name for d in devices}
        if target not in names:
            return loi(f"Không thấy thiết bị «{saved_name or target}» — card ảo bị gỡ hoặc đang tắt",
                       fixable=False,
                       guide=("Mở Control Panel → Sound → tab Playback, chuột phải → «Show Disabled Devices», "
                              "bật lại thiết bị ảo.", "Không thấy thì cài lại ASIOVADPRO / VB-Cable."))
        cur = ctx.win.default_render_ids()
        if all(c == target for c in cur):
            return ok(f"Nhạc đang phát ra «{names[target]}»")
        cur_name = names.get(cur[1] or cur[0] or "", "thiết bị khác")
        return loi(f"Windows đang phát ra «{cur_name}» thay vì «{names[target]}» — nhạc không vào DAW")

    def fix(self, ctx):
        target, _ = _target(ctx)
        if not target:
            cand = pick_virtual_device(ctx.win.render_devices())
            if cand is None:
                return can_lam_tay("Không tìm thấy thiết bị ảo đưa nhạc vào DAW", guide=_PICK_GUIDE)
            if not ctx.ask(f"Nhạc YouTube đi vào phần mềm thu âm qua thiết bị «{cand.name}» phải không?"):
                return can_lam_tay("Chưa chọn thiết bị đưa nhạc vào DAW", guide=_PICK_GUIDE)
            ctx.actions.save_setting("music_playback_device_id", cand.id)
            ctx.actions.save_setting("music_playback_device_name", cand.name)
            ctx.settings["music_playback_device_id"] = cand.id
            ctx.settings["music_playback_device_name"] = cand.name
            target = cand.id
        ctx.win.set_default_render(target)
        return da_sua(f"Đã đặt «{ctx.win.name_of(target) or target}» làm thiết bị phát mặc định")


class WinPlaybackMuteCheck(Check):
    id, group, title = "win_playback_mute", "windows", "Âm lượng thiết bị phát"
    requires = ("win_playback_default",)

    def _dev(self, ctx):
        target, _ = _target(ctx)
        if target:
            return target
        cur = ctx.win.default_render_ids()
        return cur[1] or cur[0]

    def detect(self, ctx):
        if not ctx.win.available():
            return khong_ro("Không đọc được thiết bị âm thanh Windows")
        dev = self._dev(ctx)
        if not dev:
            return khong_ro("Không có thiết bị phát mặc định")
        muted, pct = ctx.win.endpoint_state(dev)
        name = ctx.win.name_of(dev) or "thiết bị phát"
        if muted:
            return loi(f"«{name}» đang bị tắt tiếng trong Windows")
        if pct < LOW_PCT:
            return loi(f"Âm lượng «{name}» trong Windows gần như bằng 0")
        return ok(f"«{name}» đang mở tiếng ({pct:.0f}%)")

    def fix(self, ctx):
        dev = self._dev(ctx)
        ctx.win.set_endpoint(dev, muted=False, volume_pct=100.0)
        return da_sua(f"Đã bật tiếng «{ctx.win.name_of(dev) or 'thiết bị phát'}» lên 100%")


class WinMicCheck(Check):
    id, group, title = "win_mic", "windows", "Micro trong Windows"

    _KEYS = (MIC_CONSENT_KEY, MIC_CONSENT_KEY + r"\NonPackaged")

    def detect(self, ctx):
        s = ctx.system
        if s.reg_get("HKLM", MIC_CONSENT_KEY, "Value") == "Deny":
            return loi("Windows đang chặn micro cho toàn máy — cần kỹ thuật mở", fixable=False,
                       guide=("Bấm «Gửi cho kỹ thuật» bên dưới.",))
        problems = []
        if any(s.reg_get("HKCU", k, "Value") == "Deny" for k in self._KEYS):
            problems.append("Windows đang chặn quyền dùng micro")
        if ctx.win.available():
            cap = ctx.win.default_capture_id()
            if cap and ctx.win.endpoint_state(cap)[0]:
                problems.append("Micro bị tắt tiếng trong Windows")
        if problems:
            return loi("; ".join(problems))
        return ok("Micro không bị Windows chặn")

    def fix(self, ctx):
        for k in self._KEYS:
            if ctx.system.reg_get("HKCU", k, "Value") == "Deny":
                ctx.system.reg_set("HKCU", k, "Value", "Allow")
        if ctx.win.available():
            cap = ctx.win.default_capture_id()
            if cap:
                ctx.win.set_endpoint(cap, muted=False)
        return da_sua("Đã mở quyền micro và bật tiếng micro trong Windows")
```

- [ ] **Step 4: Viết `checks_browser.py`**

```python
"""Trình duyệt: Volume Mixer của Windows và trình phát YouTube."""
from core.audio_doctor.model import Check, ok, loi, khong_ro, da_sua, bo_qua
from core.audio_doctor.win_audio import BROWSER_PROCESS_NAMES

LOW_PCT = 5.0


class BrowserSessionCheck(Check):
    id, group, title = "browser_session", "browser", "Trình duyệt trong Volume Mixer"
    requires = ("win_playback_default",)

    def detect(self, ctx):
        if not ctx.win.available():
            return khong_ro("Không đọc được Volume Mixer")
        sessions = ctx.win.browser_sessions(BROWSER_PROCESS_NAMES)
        if not sessions:
            return bo_qua("Trình duyệt chưa phát âm thanh")
        bad = [n for n, muted, pct in sessions if muted or pct < LOW_PCT]
        if bad:
            return loi(f"Trình duyệt ({bad[0]}) bị tắt tiếng trong Volume Mixer của Windows")
        return ok("Trình duyệt mở tiếng trong Volume Mixer")

    def fix(self, ctx):
        ctx.win.unmute_browser_sessions(BROWSER_PROCESS_NAMES, volume_pct=100.0)
        return da_sua("Đã bật tiếng trình duyệt trong Volume Mixer")


class YtPlayerCheck(Check):
    id, group, title = "yt_player", "browser", "Trình phát YouTube"

    def detect(self, ctx):
        player = ctx.actions.player_state()
        if player is None:
            return bo_qua("Chưa có trình phát YouTube")
        app = ctx.actions.app_music_state()
        if app is not None and (app[0] or app[1] < LOW_PCT):
            return loi("Thanh Nhạc trên app đang tắt")
        if player.get("muted") or (player.get("volume") is not None and player["volume"] <= 0):
            return loi("Trình phát YouTube đang tắt tiếng")
        return ok("Trình phát YouTube đang mở tiếng")

    def fix(self, ctx):
        ctx.actions.ensure_app_music_on()
        ctx.actions.unmute_player()
        return da_sua("Đã bật tiếng nhạc YouTube")
```

- [ ] **Step 5: Chạy test**

Run: `PYTEST tests\core\audio_doctor`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add core/audio_doctor/checks_windows.py core/audio_doctor/checks_browser.py tests/core/audio_doctor/test_checks_windows.py
git commit -m "feat(audio-doctor): kiểm tra/sửa thiết bị phát mặc định, mute Windows, quyền micro, Volume Mixer, player YouTube"
```

---

### Task 8: CDP — đọc/bỏ tắt tiếng player YouTube

**Files:**
- Modify: `core/cdp_monitor.py` (sau `set_player_volume`, dòng ~266)
- Test: `tests/core/audio_doctor/test_cdp_player.py`

**Interfaces:**
- Produces: `CDPYouTubeMonitor.get_player_state() -> Optional[dict]` (`{"muted": bool, "volume": int}`), `CDPYouTubeMonitor.unmute_player() -> bool`

- [ ] **Step 1: Test (fail)**

```python
from unittest.mock import patch

from core.cdp_monitor import CDPYouTubeMonitor


def _mon():
    m = CDPYouTubeMonitor.__new__(CDPYouTubeMonitor)
    m.is_connected = True
    return m


def test_get_player_state():
    m = _mon()
    with patch.object(CDPYouTubeMonitor, "_evaluate_js", return_value={"muted": True, "volume": 30}) as ev:
        assert m.get_player_state() == {"muted": True, "volume": 30}
    assert "isMuted" in ev.call_args.args[0]


def test_khong_ket_noi_thi_none():
    m = _mon()
    m.is_connected = False
    assert m.get_player_state() is None
    assert m.unmute_player() is False


def test_unmute_player():
    m = _mon()
    with patch.object(CDPYouTubeMonitor, "_evaluate_js", return_value=True) as ev:
        assert m.unmute_player() is True
    assert "unMute" in ev.call_args.args[0] and "muted = false" in ev.call_args.args[0]
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_cdp_player.py`
Expected: FAIL — `AttributeError: get_player_state`.

- [ ] **Step 3: Thêm vào `CDPYouTubeMonitor`**

```python
    def get_player_state(self):
        """{"muted", "volume"} của player YouTube (tính cả thẻ <video> bị muted); None nếu không có."""
        if not self.is_connected:
            return None
        script = """
        (function() {
            var p = document.querySelector('#movie_player');
            if (!p || typeof p.isMuted !== 'function') return null;
            var v = document.querySelector('video');
            return {muted: p.isMuted() || !!(v && v.muted), volume: p.getVolume()};
        })();
        """
        state = self._evaluate_js(script)
        return state if isinstance(state, dict) else None

    def unmute_player(self):
        """Bỏ tắt tiếng player YouTube (cả nút loa của player lẫn thẻ <video>)."""
        if not self.is_connected:
            return False
        script = """
        (function() {
            var p = document.querySelector('#movie_player');
            if (p && typeof p.unMute === 'function') p.unMute();
            var v = document.querySelector('video');
            if (v) v.muted = false;
            return !!(p || v);
        })();
        """
        return bool(self._evaluate_js(script))
```

- [ ] **Step 4: Chạy test**

Run: `PYTEST tests\core\audio_doctor\test_cdp_player.py tests\core\test_cdp_cookies.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add core/cdp_monitor.py tests/core/audio_doctor/test_cdp_player.py
git commit -m "feat(cdp): đọc trạng thái tắt tiếng và bỏ tắt tiếng player YouTube"
```

---

### Task 9: Danh sách check mặc định + cầu nối dashboard

**Files:**
- Modify: `core/audio_doctor/__init__.py`
- Create: `ui/ui_invoker.py`, `ui/audio_doctor_bridge.py`
- Modify: `ui/panels/mixer.py` (đăng ký `dashboard._mixer_mute_setters`)
- Test: `tests/core/audio_doctor/test_default_checks.py`, `tests/ui/test_audio_doctor_bridge.py`

**Interfaces:**
- Consumes: mọi check (Task 6–7), `AudioDoctorService` (Task 2), `SystemProbe`/`WinAudio` (Task 5), `DawFeedback` qua `engine.daw_feedback` (Task 3), `get_player_state`/`unmute_player` (Task 8)
- Produces:
  - `core.audio_doctor.default_checks() -> list[Check]` (12 check, đúng thứ tự spec)
  - `UiInvoker(parent).call(fn, *args)` — chạy `fn` trên thread của `UiInvoker`, chặn tới khi xong, trả kết quả / ném lại exception
  - `DashboardDoctorActions(dashboard, invoker)` cài đặt toàn bộ `actions` của `DoctorContext`
  - `build_service(dashboard) -> AudioDoctorService`
  - `dashboard._mixer_mute_setters: dict[cc_key, Callable[[bool], None]]`

- [ ] **Step 1: Test danh sách (fail)** — `tests/core/audio_doctor/test_default_checks.py`:

```python
from core.audio_doctor import default_checks
from core.audio_doctor.runner import Runner


def test_du_12_muc_dung_thu_tu():
    ids = [c.id for c in Runner(default_checks()).checks]
    assert ids == ["loopmidi", "daw_remote", "daw_running", "daw_dialog", "cubase_release_driver",
                   "ch_mic", "ch_music", "win_playback_default", "win_playback_mute", "win_mic",
                   "browser_session", "yt_player"]
```

- [ ] **Step 2: `core/audio_doctor/__init__.py`**

```python
"""Tự sửa âm thanh — chẩn đoán và sửa lỗi âm thanh thường gặp."""
from core.audio_doctor.checks_bridge import LoopMidiCheck, DawRemoteCheck
from core.audio_doctor.checks_daw import (
    DawRunningCheck, DawDialogCheck, CubaseReleaseDriverCheck, MicChannelCheck, MusicChannelCheck,
)
from core.audio_doctor.checks_windows import WinPlaybackDefaultCheck, WinPlaybackMuteCheck, WinMicCheck
from core.audio_doctor.checks_browser import BrowserSessionCheck, YtPlayerCheck


def default_checks():
    return [
        LoopMidiCheck(), DawRemoteCheck(),
        DawRunningCheck(), DawDialogCheck(), CubaseReleaseDriverCheck(),
        MicChannelCheck(), MusicChannelCheck(),
        WinPlaybackDefaultCheck(), WinPlaybackMuteCheck(), WinMicCheck(),
        BrowserSessionCheck(), YtPlayerCheck(),
    ]
```

- [ ] **Step 3: Test cầu nối (fail)** — `tests/ui/test_audio_doctor_bridge.py`:

```python
import threading
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _make_dashboard(qtbot):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        return dashboard

from ui.ui_invoker import UiInvoker


def test_invoker_chay_tren_main_thread(qapp, qtbot):
    inv = UiInvoker()
    main = threading.get_ident()
    seen = {}

    def worker():
        seen["tid"] = inv.call(threading.get_ident)
        try:
            inv.call(lambda: 1 / 0)
        except ZeroDivisionError:
            seen["raised"] = True

    t = threading.Thread(target=worker)
    t.start()
    qtbot.waitUntil(lambda: not t.is_alive(), timeout=3000)
    assert seen == {"tid": main, "raised": True}
    assert inv.call(lambda: 5) == 5          # gọi ngay trên main thread không treo


def _actions(dashboard):
    from ui.audio_doctor_bridge import DashboardDoctorActions
    return DashboardDoctorActions(dashboard, UiInvoker(dashboard))


def test_bat_mic_tren_app_bo_mute_va_nang_muc(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    acts = _actions(dashboard)
    dashboard._mixer_mute_setters["mix_mic"](True)
    dashboard._mixer_sliders["mix_mic"].setValue(dashboard._mixer_sliders["mix_mic"].minimum())
    assert acts.app_mic_state()[0] is True
    mock_engine.send_midi.reset_mock()
    acts.ensure_app_mic_on()
    muted, level = acts.app_mic_state()
    assert muted is False and level > -40
    assert dashboard._mixer_channels["mix_mic"].is_muted() is False
    assert (51, 0) in [c.args for c in mock_engine.send_midi.call_args_list]


def test_khong_dung_be_va_vang(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dashboard._mixer_mute_setters["mix_backing"](True)
    acts = _actions(dashboard)
    acts.ensure_app_mic_on()
    acts.ensure_app_music_on()
    assert dashboard.mute_states["mix_backing"] is True


def test_build_service_tao_context(qapp, mock_engine, qtbot):
    from ui.audio_doctor_bridge import build_service
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    svc = build_service(dashboard)
    ctx = svc._ctx_factory(ask=None)
    assert ctx.feedback is mock_engine.daw_feedback
    assert ctx.daw.kind in ("studio_one", "cubase")
    assert ctx.ask("?") is False
```

- [ ] **Step 4: Chạy, xác nhận fail**

Run: `PYTEST tests\core\audio_doctor\test_default_checks.py tests\ui\test_audio_doctor_bridge.py`
Expected: FAIL (thiếu module / `_mixer_mute_setters`).

- [ ] **Step 5: `ui/ui_invoker.py`**

```python
"""Gọi một hàm trên thread của QObject (thường là main thread) và chờ kết quả."""
from PySide6.QtCore import QObject, QThread, Qt, Signal


class UiInvoker(QObject):
    _job = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job.connect(self._run, Qt.BlockingQueuedConnection)

    @staticmethod
    def _run(job):
        job()

    def call(self, fn, *args):
        # Đang ở đúng thread thì gọi thẳng — BlockingQueued trên cùng thread là treo.
        if QThread.currentThread() == self.thread():
            return fn(*args)
        box = {}

        def job():
            try:
                box["v"] = fn(*args)
            except BaseException as e:  # noqa: BLE001
                box["e"] = e

        self._job.emit(job)
        if "e" in box:
            raise box["e"]
        return box.get("v")
```

- [ ] **Step 6: `ui/panels/mixer.py`** — trong `build_panel_mixer`, cạnh `dashboard._mixer_senders = {}` thêm `dashboard._mixer_mute_setters = {}`; trong vòng, sau khối `if ch["has_mute"]: ch_view.mute_btn.clicked.connect(...)`:

```python
        if ch["has_mute"]:
            # Đặt mute theo giá trị (không lật) — Tự sửa âm thanh và các đường
            # tự động dùng; đi cùng đường gửi CC với nút bấm.
            def _set_muted(muted, channel_view=ch_view, cc_key=ch["cc"], val_range=ch["range"]):
                if channel_view.is_muted() != bool(muted):
                    channel_view.toggle_mute()
                _make_mute_callback(dashboard, cc_key, mute_cc_map, val_range)(bool(muted))
            dashboard._mixer_mute_setters[ch["cc"]] = _set_muted
```

- [ ] **Step 7: `ui/audio_doctor_bridge.py`**

```python
"""Nối AudioDoctorService với MainDashboard: thao tác trên app + dựng DoctorContext."""
import os

import backend
from core import daw
from core.audio_doctor import default_checks
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.service import AudioDoctorService
from core.audio_doctor.system import SystemProbe
from core.audio_doctor.win_audio import WinAudio
from core.config import DATA_DIR, MIDI_FEEDBACK_PORT_NAME, MIDI_PORT_NAME
from ui.ui_invoker import UiInvoker

MIC_KEY = "mix_mic"
MUSIC_KEY = "mix_music"
MIC_LOW_DB = -40.0
MUSIC_MIN_PCT = 5
MUSIC_RESTORE_PCT = 80


class DashboardDoctorActions:
    def __init__(self, dashboard, invoker):
        self._d = dashboard
        self._inv = invoker

    # ── DAW / MIDI ──────────────────────────────────────────────────────────
    def launch_daw(self):
        path = (self._d.settings or {}).get("studio_one_path", "")
        if not path or not os.path.exists(path):
            return False
        self._d.engine.launch_app(path)
        return True

    def reconnect_midi(self):
        eng = self._d.engine
        eng.midi_handler.stop_listening()
        ok = bool(eng.connect_midi())
        eng.midi_handler.ensure_listening()
        return ok

    def sync_midi(self):
        self._inv.call(self._d._sync_midi_states)

    def close_daw(self):
        res = self._d.engine.close_studio_one_safely(save=True) or {}
        return res.get("status") in ("closed", "not_running")

    # ── kênh trên app ───────────────────────────────────────────────────────
    def _slider(self, key):
        return (getattr(self._d, "_mixer_sliders", None) or {}).get(key)

    def app_mic_state(self):
        def read():
            sl = self._slider(MIC_KEY)
            if sl is None:
                return None
            return bool(self._d.mute_states.get(MIC_KEY, False)), float(sl.value())
        return self._inv.call(read)

    def ensure_app_mic_on(self):
        def do():
            sl = self._slider(MIC_KEY)
            setter = (getattr(self._d, "_mixer_mute_setters", None) or {}).get(MIC_KEY)
            if sl is None:
                return
            if setter is not None and self._d.mute_states.get(MIC_KEY, False):
                setter(False)
            if sl.value() <= MIC_LOW_DB:
                sl.setValue(0)              # valueChanged → gửi CC mức Mic
            else:
                send = (getattr(self._d, "_mixer_senders", None) or {}).get(MIC_KEY)
                if send:
                    send(sl.value())        # DAW có thể đang lệch mức với app
        self._inv.call(do)

    def app_music_state(self):
        def read():
            ch = (getattr(self._d, "_mixer_channels", None) or {}).get(MUSIC_KEY)
            sl = self._slider(MUSIC_KEY)
            if ch is None or sl is None or not ch.is_available():
                return None
            return bool(self._d.mute_states.get(MUSIC_KEY, False)), int(sl.value())
        return self._inv.call(read)

    def ensure_app_music_on(self):
        def do():
            sl = self._slider(MUSIC_KEY)
            setter = (getattr(self._d, "_mixer_mute_setters", None) or {}).get(MUSIC_KEY)
            if sl is None:
                return
            if setter is not None and self._d.mute_states.get(MUSIC_KEY, False):
                setter(False)
            if sl.value() < MUSIC_MIN_PCT:
                sl.setValue(MUSIC_RESTORE_PCT)
        self._inv.call(do)

    # ── player YouTube ──────────────────────────────────────────────────────
    def player_state(self):
        eng = self._d.engine
        cdp = getattr(eng, "cdp_monitor", None)
        if cdp is not None and getattr(cdp, "is_connected", False):
            return cdp.get_player_state() or {"muted": None, "volume": None}
        if getattr(eng, "embedded_volume_callback", None) is not None:
            return {"muted": None, "volume": None}
        return None

    def unmute_player(self):
        cdp = getattr(self._d.engine, "cdp_monitor", None)
        if cdp is not None and getattr(cdp, "is_connected", False):
            return bool(cdp.unmute_player())
        return False

    # ── settings ────────────────────────────────────────────────────────────
    def save_setting(self, key, value):
        def do():
            self._d.settings[key] = value
            backend.ConfigManager.save_settings(self._d.settings)
        self._inv.call(do)


def build_service(dashboard):
    invoker = UiInvoker(dashboard)
    actions = DashboardDoctorActions(dashboard, invoker)
    system, win = SystemProbe(), WinAudio()

    def ctx_factory(ask=None):
        eng = dashboard.engine
        return DoctorContext(
            settings=dashboard.settings,
            daw=daw.active(),
            system=system,
            win=win,
            actions=actions,
            feedback=getattr(eng, "daw_feedback", None),
            send_cc=lambda cc, v: bool(eng.send_midi(int(cc), int(v))),
            midi_cc=dict(dashboard.MIDI_CC),
            midi_port=MIDI_PORT_NAME,
            feedback_port=MIDI_FEEDBACK_PORT_NAME,
            ask=ask or (lambda q: False),
        )

    return AudioDoctorService(ctx_factory, default_checks(),
                              log_path=os.path.join(DATA_DIR, "logs", "audio_doctor.log"))
```

> Kiểm tra trước khi viết: `dashboard.MIDI_CC` có tồn tại (mixer.py dùng `dashboard.MIDI_CC`) và thang của thanh Mic là dB (`db_to_midi(raw_value, …)` trong mixer.py) — nếu khác, chỉnh `MIC_LOW_DB`/`sl.setValue(0)` cho khớp.

- [ ] **Step 8: Chạy test**

Run: `PYTEST tests\core\audio_doctor tests\ui\test_audio_doctor_bridge.py tests\ui\test_mixer_unity_daw.py tests\ui\test_mixer_music_youtube.py`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add core/audio_doctor/__init__.py ui/ui_invoker.py ui/audio_doctor_bridge.py ui/panels/mixer.py tests/core/audio_doctor/test_default_checks.py tests/ui/test_audio_doctor_bridge.py
git commit -m "feat(audio-doctor): danh sách check mặc định và cầu nối thao tác trên dashboard"
```

---

### Task 10: Hộp thoại, dải cảnh báo, nút, phím tắt, lệnh giọng nói, kiểm tra lúc khởi động

**Files:**
- Create: `ui/dialogs/audio_doctor_dialog.py`
- Modify: `ui/panels/header.py` (dải cảnh báo), `ui/panels/bottom_bar.py` (nút), `frontend_qt.py` (signal, service, `_open_audio_doctor`, `_on_audio_doctor_report`, voice action, dừng service khi đóng), `core/accessibility/shortcuts.py`, `core/accessibility/voice_input.py`, `QuangLuuStudio.spec` (hiddenimports `ui.dialogs.audio_doctor_dialog` nếu spec liệt kê từng dialog)
- Test: `tests/ui/test_audio_doctor_ui.py`, `tests/core/test_accessibility.py` (thêm intent)

**Interfaces:**
- Consumes: `build_service` (Task 9), `RunReport.problems()/summary()`, `Status`, `GROUP_TITLES`
- Produces:
  - `AudioDoctorDialog(dashboard, service, auto_fix=True)`; signal nội bộ `_progress(object, object)`, `_finished(object)`; method `start(mode)`; thuộc tính `rows: dict[check_id, _Row]`
  - `MainDashboard._audio_doctor` (service), `_audio_warn_btn`, `_audio_doctor_report_signal = Signal(object, str)`, `_open_audio_doctor()`, `_on_audio_doctor_report(report, action)`
  - intent `"fix_audio"`

- [ ] **Step 1: Test UI (fail)** — `tests/ui/test_audio_doctor_ui.py`:

```python
from unittest.mock import MagicMock, patch

import pytest

from frontend_qt import MainDashboard


@pytest.fixture
def mock_engine():
    with patch("frontend_qt.backend.SystemEngine") as mock_eng:
        eng = mock_eng.return_value
        eng.current_youtube_url = "http://yt.com"
        eng.tone_detection_active = False
        eng.autokey_active = False
        eng._tone_session = MagicMock()
        eng._tone_session.is_active = False
        yield eng


def _make_dashboard(qtbot):
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        dashboard = MainDashboard()
        qtbot.addWidget(dashboard)
        return dashboard

from core.audio_doctor.model import Check, Status, loi, ok, da_sua
from core.audio_doctor.context import DoctorContext
from core.audio_doctor.service import AudioDoctorService


class _Mic(Check):
    id, group, title = "ch_mic", "daw", "Kênh Mic"
    fixed = False

    def detect(self, ctx):
        return ok("Kênh Mic đang bật") if _Mic.fixed else loi("Kênh Mic đang tắt trong Cubase")

    def fix(self, ctx):
        _Mic.fixed = True
        return da_sua("Đã bật kênh Mic")


class _Ok(Check):
    id, group, title = "loopmidi", "bridge", "Cổng MIDI"

    def detect(self, ctx):
        return ok("ổn")


def _svc(tmp_path):
    _Mic.fixed = False
    ctx = lambda ask=None: DoctorContext(settings={}, daw=None, system=None, win=None, actions=None)
    return AudioDoctorService(ctx, [_Ok(), _Mic()], log_path=tmp_path / "a.log")


def test_dai_canh_bao_hien_loi_nang_nhat_va_an_khi_on(qapp, mock_engine, qtbot, tmp_path):
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    svc = _svc(tmp_path)
    rep = svc.run("check", "startup")
    with patch.object(dashboard, "_a11y_speak") as speak:
        dashboard._on_audio_doctor_report(rep, "run")
    assert dashboard._audio_warn_btn.isVisibleTo(dashboard)
    assert "Kênh Mic đang tắt" in dashboard._audio_warn_btn.text()
    speak.assert_called_once()
    _Mic.fixed = True
    dashboard._on_audio_doctor_report(svc.run("check", "startup"), "rerun")
    assert not dashboard._audio_warn_btn.isVisibleTo(dashboard)


def test_hop_thoai_tu_sua_va_hien_trang_thai(qapp, mock_engine, qtbot, tmp_path):
    from ui.dialogs.audio_doctor_dialog import AudioDoctorDialog
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    dlg = AudioDoctorDialog(dashboard, _svc(tmp_path), auto_fix=False)
    qtbot.addWidget(dlg)
    with qtbot.waitSignal(dlg._finished, timeout=5000):
        dlg.start("fix")
    assert dlg.rows["ch_mic"].status is Status.DA_SUA
    assert "Đã bật kênh Mic" in dlg.rows["ch_mic"].msg_label.text()
    assert dlg.rows["loopmidi"].status is Status.OK
    assert "Đã sửa 1" in dlg.summary_label.text()


def test_nut_va_phim_tat_mo_hop_thoai(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot)
    dashboard._so_ready_watcher.stop()
    assert "Tự sửa âm thanh" in dashboard._func_buttons["Tự sửa âm thanh"].toolTip()
    from core.accessibility import shortcuts
    assert any(k == "Ctrl+Shift+A" and t == "_open_audio_doctor" for k, t, _ in shortcuts._DEFAULT_BINDINGS)
```

Thêm vào `tests/core/test_accessibility.py`:

```python
def test_intent_sua_am_thanh():
    from core.accessibility.voice_input import match_intent
    for text in ("sửa âm thanh", "sua am thanh", "mất tiếng rồi"):
        assert match_intent(text).name == "fix_audio"
```

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\ui\test_audio_doctor_ui.py tests\core\test_accessibility.py`
Expected: FAIL.

- [ ] **Step 3: `ui/dialogs/audio_doctor_dialog.py`**

```python
"""Hộp thoại Tự sửa âm thanh: danh sách mục theo nhóm, trạng thái từng mục, hướng dẫn làm tay."""
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from core.audio_doctor.model import GROUP_ORDER, GROUP_TITLES, Status
from ui.design_tokens import C
from ui.ui_invoker import UiInvoker

_ICON = {
    None: ("…", C["muted"] if "muted" in C else "#94A3B8"),
    Status.OK: ("✓", C["green"]),
    Status.DA_SUA: ("✓", C["green"]),
    Status.LOI: ("✗", C["accent"]),
    Status.CAN_LAM_TAY: ("!", C["orange"]),
    Status.KHONG_RO: ("?", "#94A3B8"),
    Status.BO_QUA: ("–", "#94A3B8"),
}


class _Row(QWidget):
    def __init__(self, check, parent=None):
        super().__init__(parent)
        self.check = check
        self.status = None
        self.finding = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        top = QHBoxLayout()
        self.icon = QLabel("·")
        self.icon.setFixedWidth(18)
        title = QLabel(f"<b>{check.title}</b>")
        self.msg_label = QLabel("")
        self.msg_label.setWordWrap(True)
        self.guide_btn = QToolButton(text="Hướng dẫn")
        self.guide_btn.setCheckable(True)
        self.guide_btn.hide()
        top.addWidget(self.icon)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.guide_btn)
        lay.addLayout(top)
        lay.addWidget(self.msg_label)
        self.guide_label = QLabel("")
        self.guide_label.setWordWrap(True)
        self.guide_label.hide()
        lay.addWidget(self.guide_label)
        self.guide_btn.toggled.connect(self.guide_label.setVisible)

    def set_finding(self, finding):
        self.finding = finding
        self.status = None if finding is None else finding.status
        glyph, color = _ICON[self.status]
        self.icon.setText(glyph)
        self.icon.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.msg_label.setText("Đang kiểm tra…" if finding is None else finding.message)
        self.setAccessibleName(f"{self.check.title}: {self.msg_label.text()}")
        guide = () if finding is None else finding.guide
        self.guide_label.setText("\n".join(f"{i}. {s}" for i, s in enumerate(guide, 1)))
        self.guide_btn.setVisible(bool(guide) and self.status is Status.CAN_LAM_TAY)


class AudioDoctorDialog(QDialog):
    _progress = Signal(object, object)
    _finished = Signal(object)

    def __init__(self, dashboard, service, auto_fix=True):
        super().__init__(dashboard)
        self._dashboard = dashboard
        self._service = service
        self._invoker = UiInvoker(self)
        self._running = False
        self.report = None
        self.setWindowTitle("Tự sửa âm thanh")
        self.setMinimumWidth(520)
        root = QVBoxLayout(self)
        self.summary_label = QLabel("Đang kiểm tra…")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        body = QWidget()
        bl = QVBoxLayout(body)
        self.rows = {}
        checks = service.runner.checks
        for group in GROUP_ORDER:
            members = [c for c in checks if c.group == group]
            if not members:
                continue
            head = QLabel(GROUP_TITLES[group])
            head.setStyleSheet("font-weight: bold; margin-top: 6px;")
            bl.addWidget(head)
            for c in members:
                row = _Row(c)
                row.hide()                   # chỉ hiện mục áp dụng cho máy này
                self.rows[c.id] = row
                bl.addWidget(row)
        bl.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        btns = QHBoxLayout()
        self.fix_btn = QPushButton("Tự sửa lại")
        self.check_btn = QPushButton("Kiểm tra lại")
        self.send_btn = QPushButton("Gửi cho kỹ thuật")
        close_btn = QPushButton("Đóng")
        for b in (self.fix_btn, self.check_btn, self.send_btn):
            btns.addWidget(b)
        btns.addStretch()
        btns.addWidget(close_btn)
        root.addLayout(btns)
        self.fix_btn.clicked.connect(lambda: self.start("fix"))
        self.check_btn.clicked.connect(lambda: self.start("check"))
        self.send_btn.clicked.connect(self._send_to_support)
        close_btn.clicked.connect(self.close)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        if auto_fix:
            self.start("fix")

    # ── chạy ────────────────────────────────────────────────────────────────
    def start(self, mode):
        if self._running:
            return
        self._running = True
        for b in (self.fix_btn, self.check_btn, self.send_btn):
            b.setEnabled(False)
        self.summary_label.setText("Đang sửa…" if mode == "fix" else "Đang kiểm tra…")

        def work():
            rep = self._service.run(mode, "button", ask=self._ask,
                                    on_progress=lambda c, f: self._progress.emit(c, f))
            self._finished.emit(rep)

        threading.Thread(target=work, daemon=True, name="audio-doctor-run").start()

    def _ask(self, question):
        return self._invoker.call(
            lambda: QMessageBox.question(self, "Tự sửa âm thanh", question)
            == QMessageBox.StandardButton.Yes)

    def _on_progress(self, check, finding):
        row = self.rows.get(check.id)
        if row is None:
            return
        row.show()
        row.set_finding(finding)
        if finding is not None and finding.status in (Status.DA_SUA, Status.CAN_LAM_TAY):
            self._speak(f"{check.title}: {finding.message}")

    def _on_finished(self, report):
        self._running = False
        self.report = report
        for b in (self.fix_btn, self.check_btn, self.send_btn):
            b.setEnabled(True)
        res = report.results.values()
        fixed = sum(1 for f in res if f.status is Status.DA_SUA)
        manual = [f for f in res if f.status in (Status.CAN_LAM_TAY, Status.LOI)]
        if not manual:
            text = f"Đã sửa {fixed} mục. Âm thanh đã sẵn sàng." if fixed else "Mọi thứ đều ổn."
        else:
            text = (f"Đã sửa {fixed} mục. Còn {len(manual)} mục cần làm tay — "
                    "bấm «Hướng dẫn» ở từng mục, hoặc «Gửi cho kỹ thuật».")
        self.summary_label.setText(text)
        self._speak(text)
        cb = getattr(self._dashboard, "_on_audio_doctor_report", None)
        if cb:
            cb(report, "button")

    def _speak(self, text):
        speak = getattr(self._dashboard, "_a11y_speak", None)
        if speak:
            try:
                speak(text)
            except Exception:
                pass

    def _send_to_support(self):
        if self.report is None:
            return
        rep = self.report
        n = len(rep.problems())

        def work():
            from core import support
            res = support.submit("loi", f"Tự sửa âm thanh: còn {n} mục cần làm tay",
                                 rep.summary(), include_logs=True)
            self._dashboard._message_signal.emit(res.get("message") or "Đã gửi cho kỹ thuật",
                                                 not res.get("ok") and not res.get("queued"))

        threading.Thread(target=work, daemon=True).start()
```

> Kiểm tra `ui/design_tokens.C` có khoá `green`, `accent`, `orange` (đã dùng trong frontend_qt) — đúng. Khoá `muted` có thể không có: biểu thức trên tự lùi về `#94A3B8`.

- [ ] **Step 4: Header — dải cảnh báo** (`ui/panels/header.py`, ngay trước `layout.addWidget(dashboard._marquee_widget, 1)`):

```python
    # Dải cảnh báo Tự sửa âm thanh — chỉ hiện khi lượt kiểm tra thấy lỗi.
    from PySide6.QtWidgets import QPushButton
    dashboard._audio_warn_btn = QPushButton("")
    dashboard._audio_warn_btn.setFlat(True)
    dashboard._audio_warn_btn.setCursor(Qt.PointingHandCursor)
    dashboard._audio_warn_btn.setStyleSheet(
        f"QPushButton {{ color: {C['orange']}; border: 1px solid {C['orange']};"
        f" border-radius: 8px; padding: 2px 8px; font-weight: 600; }}")
    dashboard._audio_warn_btn.setAccessibleName("Cảnh báo âm thanh — bấm để tự sửa")
    dashboard._audio_warn_btn.clicked.connect(dashboard._open_audio_doctor)
    dashboard._audio_warn_btn.hide()
    layout.addWidget(dashboard._audio_warn_btn)
```

(Thêm `from PySide6.QtCore import Qt` / `from ui.design_tokens import C` ở đầu file nếu chưa có.)

- [ ] **Step 5: Bottom bar — nút** (`ui/panels/bottom_bar.py`, sau nút Thư mục, import thêm `SVG_WRENCH`):

```python
    btn_fix = PainterButton(
        "", color=C["orange"], height=34, radius=8,
        font_size=10, svg_content=SVG_WRENCH, svg_size=18, fixed_width=38,
    )
    btn_fix.setToolTip("Tự sửa âm thanh · Ctrl+Shift+A")
    btn_fix.setAccessibleName("Tự sửa âm thanh")
    btn_fix.setAccessibleDescription("Kiểm tra và tự sửa khi mất tiếng mic hoặc nhạc")
    btn_fix.clicked.connect(dashboard._open_audio_doctor)
    bar_layout.addWidget(btn_fix)
    dashboard._func_buttons["Tự sửa âm thanh"] = btn_fix
```

Chế độ khách: nút nằm ở bottom bar (không bị dựng lại/ẩn khi khoá). Kiểm tra `frontend_qt.py` quanh dòng 505 (`locked = kiosk.is_locked()`) — nếu có danh sách nút bị khoá, **không** thêm "Tự sửa âm thanh" vào đó.

- [ ] **Step 6: `frontend_qt.py`**

Khai báo signal cạnh các signal khác (dòng ~133):

```python
    _audio_doctor_report_signal = Signal(object, str)   # (RunReport, "run"/"rerun"/"button")
```

Trong `__init__`, sau `self._so_ready_signal.connect(self._on_studio_one_ready)`:

```python
        # Tự sửa âm thanh: lúc mở app chỉ KIỂM TRA (chờ DAW sẵn sàng) rồi báo.
        self._audio_doctor_report_signal.connect(self._on_audio_doctor_report)
        self._audio_doctor_speak_next = True
        try:
            from ui.audio_doctor_bridge import build_service
            self._audio_doctor = build_service(self)
        except Exception as e:
            print(f"[AUDIO DOCTOR] Không khởi tạo được: {e}")
            self._audio_doctor = None
        self._audio_doctor_timer = QTimer(self)
        self._audio_doctor_timer.setSingleShot(True)
        self._audio_doctor_timer.timeout.connect(self._start_audio_doctor_watch)
        self._audio_doctor_timer.start(1000)
```

Thêm method:

```python
    def _start_audio_doctor_watch(self):
        if self._audio_doctor is None:
            return
        from core import so_windows
        wait_s = float(self.settings.get("audio_doctor_startup_wait_s", 180) or 180)
        self._audio_doctor.start_startup_watch(
            on_report=lambda rep, act: self._audio_doctor_report_signal.emit(rep, act),
            is_daw_ready=lambda: bool(so_windows.main_windows()),
            wait_s=wait_s,
        )

    def _open_audio_doctor(self):
        if self._audio_doctor is None:
            self._show_message("Không mở được Tự sửa âm thanh", is_error=True)
            return
        from ui.dialogs.audio_doctor_dialog import AudioDoctorDialog
        dlg = getattr(self, "_audio_doctor_dialog", None)
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            return
        self._audio_doctor_dialog = AudioDoctorDialog(self, self._audio_doctor, auto_fix=True)
        self._audio_doctor_dialog.show()

    def _on_audio_doctor_report(self, report, action):
        """Cập nhật dải cảnh báo header. Chỉ đọc TTS ở lượt khởi động đầu tiên."""
        problems = report.problems()
        btn = getattr(self, "_audio_warn_btn", None)
        if btn is None:
            return
        if not problems:
            btn.hide()
            return
        _, first = problems[0]
        extra = f" · +{len(problems) - 1} vấn đề khác" if len(problems) > 1 else ""
        btn.setText(f"⚠ {first.message}{extra} · Bấm để tự sửa")
        btn.setToolTip("\n".join(f"• {f.message}" for _, f in problems))
        btn.show()
        if action == "run" and self._audio_doctor_speak_next:
            self._audio_doctor_speak_next = False
            self._a11y_speak(f"Có {len(problems)} vấn đề âm thanh. {first.message}. "
                             "Nhấn Control Shift A để tự sửa.")
```

Trong đường đóng app (tìm `closeEvent` của MainDashboard, chỗ `_so_ready_watcher.stop()`), thêm:

```python
        if getattr(self, "_audio_doctor", None) is not None:
            self._audio_doctor.stop()
```

Trong `_a11y_on_voice_intent`, thêm vào dict `actions`: `"fix_audio": self._open_audio_doctor,`

- [ ] **Step 7: Phím tắt** — `core/accessibility/shortcuts.py`, thêm vào `_DEFAULT_BINDINGS` (sau `Ctrl+,`):

```python
    ("Ctrl+Shift+A", "_open_audio_doctor",      "Tự sửa âm thanh"),
```

- [ ] **Step 8: Lệnh giọng nói** — `core/accessibility/voice_input.py`, thêm vào `_KEYWORD_INTENTS` (trước `mute_music`):

```python
    ("fix_audio",         ["sửa âm thanh", "sua am thanh", "sửa tiếng", "sua tieng",
                           "mất tiếng", "mat tieng", "tự sửa", "không có tiếng"]),
```

Nếu `test_intent_sua_am_thanh` cho "mất tiếng rồi" ra intent khác (do fuzzy match), chạy lại test sẵn có của voice_input để chắc không phá intent cũ và điều chỉnh cụm từ (không đổi thuật toán match).

- [ ] **Step 9: Đóng gói** — `QuangLuuStudio.spec` liệt kê từng dialog trong `hiddenimports` (dòng 73–82): thêm `'ui.dialogs.audio_doctor_dialog'` (import lazy) cạnh `'ui.dialogs.setlist_dialog'`.

- [ ] **Step 10: Chạy test**

Run: `PYTEST tests\ui\test_audio_doctor_ui.py tests\ui\test_audio_doctor_bridge.py tests\core\test_accessibility.py tests\ui\test_midi_resync_on_so_ready.py tests\ui\test_qt_warnings.py`
Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add ui/dialogs/audio_doctor_dialog.py ui/panels/header.py ui/panels/bottom_bar.py frontend_qt.py core/accessibility QuangLuuStudio.spec tests/ui/test_audio_doctor_ui.py tests/core/test_accessibility.py
git commit -m "feat(audio-doctor): hộp thoại Tự sửa âm thanh, cảnh báo trên header, nút + Ctrl+Shift+A + lệnh giọng nói, kiểm tra lúc mở app"
```

---

### Task 11: Cài đặt — chọn thiết bị đưa nhạc vào DAW

**Files:**
- Modify: `ui/dialogs/settings_dialog.py` (`_create_audio_combos` → thêm combo, `_build_audio`, phần lưu ~1824)
- Test: `tests/ui/test_settings_music_device.py`

**Interfaces:**
- Consumes: `WinAudio.render_devices()`, `pick_virtual_device` (Task 5)
- Produces: settings `music_playback_device_id`, `music_playback_device_name`; widget `SettingsDialog._combo_music_dev`

- [ ] **Step 1: Test (fail)** — `tests/ui/test_settings_music_device.py`, dùng lại đúng cách dựng dialog của `tests/ui/test_settings_save_and_sync.py` (chép 4 helper `mock_engine`, `_make_dashboard`, `_open_dialog`, `_save_without_side_effects` cùng import `A11Y_CFG`/`SettingsDialog`/`MainDashboard` từ file đó sang file mới — không import chéo module test):

```python
from unittest.mock import patch

from core.audio_doctor.win_audio import Device

# … 4 helper chép từ test_settings_save_and_sync.py …

DEVICES = [Device("{spk}", "Speakers (Realtek)"), Device("{vad}", "ASIOVADPRO Out")]


def test_combo_liet_ke_thiet_bi_va_luu_id(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, settings={"music_playback_device_id": "{vad}"})
    with patch("core.audio_doctor.win_audio.WinAudio.render_devices", return_value=DEVICES):
        dlg = _open_dialog(qtbot, dashboard)
    combo = dlg._combo_music_dev
    assert combo.currentData() == "{vad}"
    combo.setCurrentIndex(combo.findData("{spk}"))
    _save_without_side_effects(dlg)
    assert dashboard.settings["music_playback_device_id"] == "{spk}"
    assert dashboard.settings["music_playback_device_name"] == "Speakers (Realtek)"


def test_thiet_bi_da_luu_khong_con_tren_may_van_giu(qapp, mock_engine, qtbot):
    dashboard = _make_dashboard(qtbot, settings={"music_playback_device_id": "{gone}",
                                                 "music_playback_device_name": "VB-Cable"})
    with patch("core.audio_doctor.win_audio.WinAudio.render_devices", return_value=DEVICES):
        dlg = _open_dialog(qtbot, dashboard)
    assert dlg._combo_music_dev.currentData() == "{gone}"
    assert "không thấy" in dlg._combo_music_dev.currentText()
    _save_without_side_effects(dlg)
    assert dashboard.settings["music_playback_device_name"] == "VB-Cable"
```

> Nếu `_save()` ghi vào một bản sao settings rồi mới gán lại cho dashboard, đọc đúng chỗ nó ghi (xem cuối `_save`).

- [ ] **Step 2: Chạy, xác nhận fail**

Run: `PYTEST tests\ui\test_settings_music_device.py`
Expected: FAIL — không có `_combo_music_dev`.

- [ ] **Step 3: Code**

Thêm method mới cạnh `_create_audio_combos`:

```python
    def _create_music_device_combo(self, settings):
        from PySide6.QtWidgets import QComboBox
        from core.audio_doctor.win_audio import WinAudio
        combo = QComboBox()
        combo.setStyleSheet(self._combo_qss)
        combo.addItem("(chưa chọn)", None)
        saved_id = settings.get("music_playback_device_id")
        saved_name = settings.get("music_playback_device_name", "")
        try:
            devices = WinAudio().render_devices()
        except Exception as e:
            print(f"[SETTINGS] Không liệt kê được thiết bị phát: {e}")
            devices = []
        for d in devices:
            combo.addItem(d.name, d.id)
        if saved_id and combo.findData(saved_id) < 0:
            combo.addItem(f"{saved_name or saved_id} (không thấy trên máy)", saved_id)
        idx = combo.findData(saved_id) if saved_id else 0
        combo.setCurrentIndex(max(0, idx))
        return combo
```

Gọi nó ở chỗ dựng `self._combo_lb, self._combo_mic` (cùng `settings`): `self._combo_music_dev = self._create_music_device_combo(settings)`.

Trong `_build_audio`, sau khối "Nguồn nhạc" + hint:

```python
        dev_lbl = QLabel("Thiết bị đưa nhạc vào DAW (Tự sửa âm thanh đặt lại về đây):")
        dev_lbl.setStyleSheet(self._field_label_qss())
        vl.addWidget(dev_lbl)
        vl.addWidget(self._combo_music_dev)
```

Trong phần lưu (cạnh `s["record_mic_device"] = ...`):

```python
        dev_id = self._combo_music_dev.currentData()
        if dev_id:
            s["music_playback_device_id"] = dev_id
            s["music_playback_device_name"] = self._combo_music_dev.currentText().replace(
                " (không thấy trên máy)", "")
        else:
            s.pop("music_playback_device_id", None)
            s.pop("music_playback_device_name", None)
```

- [ ] **Step 4: Chạy test**

Run: `PYTEST tests\ui\test_settings_music_device.py tests\ui\test_settings_save_and_sync.py tests\ui\test_settings_daw_kind.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ui/dialogs/settings_dialog.py tests/ui/test_settings_music_device.py
git commit -m "feat(settings): chọn thiết bị đưa nhạc vào DAW cho Tự sửa âm thanh"
```

---

### Task 12: Tài liệu + kiểm tra toàn bộ + chạy thử thật

**Files:**
- Modify: `docs/manual/index.html` (mục mới "Tự sửa âm thanh"), `PROJECT_CONTEXT.md` (thêm `core/audio_doctor/` vào bảng module)
- Create: `docs/superpowers/plans/2026-10-09-tu-sua-am-thanh-checklist.md` (checklist thử tay)

- [ ] **Step 1: Manual** — thêm mục sau "Thiết lập hệ thống", cùng kiểu HTML các mục khác:

```html
<h3>Tự sửa âm thanh</h3>
<p>Mất tiếng mic hoặc nhạc? Bấm nút cờ lê ở thanh dưới (hoặc <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>A</kbd>,
hoặc giữ <kbd>Ctrl</kbd>+<kbd>Space</kbd> và nói "sửa âm thanh"). App tự:</p>
<ul>
  <li>bật loopMIDI và tạo đủ cổng nếu thiếu;</li>
  <li>mở Studio One / Cubase nếu chưa mở, rồi đồng bộ lại toàn bộ nút;</li>
  <li>bật kênh Mic và kênh Nhạc (Bè và Vang giữ nguyên như bạn đang chỉnh);</li>
  <li>đặt lại thiết bị phát mặc định của Windows về thiết bị đưa nhạc vào DAW, bỏ tắt tiếng loa, micro, trình duyệt và trình phát YouTube;</li>
  <li>với Cubase: tắt «Release Driver when Application is in Background» (sẽ hỏi trước khi đóng Cubase).</li>
</ul>
<p>Mỗi lần mở app, phần mềm cũng tự <b>kiểm tra</b> (không sửa) sau khi Studio One/Cubase mở xong; có vấn đề sẽ hiện dải vàng trên cùng — bấm vào để tự sửa. Mục nào cần làm tay có nút «Hướng dẫn»; không tự làm được thì bấm «Gửi cho kỹ thuật».</p>
<p>Lần đầu, chọn thiết bị đưa nhạc vào DAW ở ⚙ Cài đặt → Âm thanh (thường là ASIOVADPRO hoặc VB-Cable).</p>
```

- [ ] **Step 2: Checklist thử tay** — viết file checklist:

```markdown
# Checklist thử tay — Tự sửa âm thanh (máy dev Cubase 13 + mau.cpr; lặp lại trên máy SO)

Chuẩn bị: app bản worktree, Cubase đóng, loopMIDI đang chạy.

1. Cài đặt → Âm thanh: chọn thiết bị ảo. Đóng app.
2. Gây lỗi: tắt loopMIDI; đổi Default playback sang loa thật; mute Chrome trong Volume Mixer;
   bật Release Driver trong Cubase (Studio Setup) rồi thoát Cubase; mute Mic trên app trước khi đóng.
3. Mở app (auto_launch_studio_one = bật). Chờ Cubase mở xong + 10 s.
   Kỳ vọng: dải vàng hiện, TTS đọc một câu; nhật ký `%APPDATA%\QuangLuuStudio\logs\audio_doctor.log` có dòng source=startup.
4. Bấm dải vàng → hộp thoại tự sửa. Kỳ vọng: hỏi đóng Cubase (Release Driver) → Có;
   loopMIDI lên, Cubase mở lại, Mic + Nhạc bật, default playback về thiết bị ảo, Chrome hết mute.
   Kết thúc: "Đã sửa N mục…", không mục đỏ.
5. Hát thử: có tiếng mic + nhạc. Bè/Vang giữ đúng trạng thái trước đó.
6. Trong Cubase tự mute track Mic → nút Mic trên app chuyển sang tắt trong ≤ 1 s (phản hồi QLS_PhanHoi).
7. Studio One: lặp 2–5; kênh Mic/Nhạc báo "đã gửi lệnh bật".
8. Tắt mạng / máy chậm: Cubase mở > 3 phút → dải vàng "chưa mở xong", sau khi Cubase lên thì dải tự ẩn (rerun).
```

- [ ] **Step 3: Chạy toàn bộ test (nền, > 10 phút)**

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio\.claude\worktrees\tu-sua-am-thanh && D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --ignore=tests\test_recorder_worker_e2e.py"
```
Expected: không test nào hỏng mới so với `feat/dev-mode-ux` (so với lần chạy trên nhánh gốc nếu có test đỏ sẵn). Sau đó `git checkout app_config.json`.

- [ ] **Step 4: Chạy app thật, mở hộp thoại** (theo checklist mục 3–4 trên máy dev Cubase)

```
cmd.exe /c "cd /d D:\Projects\quang-luu-studio\.claude\worktrees\tu-sua-am-thanh && D:\Projects\quang-luu-studio\.venv\Scripts\python.exe main.py"
```

- [ ] **Step 5: Commit**

```bash
git add docs/manual/index.html PROJECT_CONTEXT.md docs/superpowers/plans/2026-10-09-tu-sua-am-thanh-checklist.md
git commit -m "docs: hướng dẫn Tự sửa âm thanh và checklist thử tay"
```
