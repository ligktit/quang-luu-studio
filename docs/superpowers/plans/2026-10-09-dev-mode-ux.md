# Dev Mode UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kỹ thuật viên setup trọn máy khách bằng Dev Mode mà không phải sửa `ui_config.json` tay: hộp "Quản lý giao diện" (hiện/ẩn, đổi thứ tự, xoá, khôi phục mặc định), xuất/nhập cấu hình, Widget Builder thân thiện (nhãn rõ, ô màu, kiểm tra tức thì, cảnh báo CC trùng, Gửi thử).

**Architecture:** Logic thuần (thao tác danh sách widget, dò CC trùng, kiểm tra màu) nằm ở `core/ui_layout.py`; sao lưu/khôi phục ở `core/devmode_backup.py`; hai thứ này không phụ thuộc Qt. Hộp Quản lý `ui/dialogs/widget_manager.py` sửa trên BẢN SAO của ui_config, chỉ ghi file khi bấm Lưu. `MainDashboard` mở hộp, áp calibration, dựng lại UI. Widget Builder được nâng cấp tại chỗ.

**Tech Stack:** Python 3.13, PySide6, pytest + pytest-qt (Windows `.venv`).

**Spec:** `docs/superpowers/specs/2026-10-09-dev-mode-ux-design.md`

## Global Constraints

- Chạy test bằng Python Windows từ WSL (Python Linux KHÔNG chạy được test UI):
  `cmd.exe /c "D:\Projects\quang-luu-studio\.venv\Scripts\python.exe -m pytest D:\Projects\quang-luu-studio\<đường\dẫn\test> -q -p no:cacheprovider --rootdir=D:\Projects\quang-luu-studio"`
  (dưới đây viết tắt là `PYTEST <đường dẫn>`). Sau khi chạy: `git checkout app_config.json` nếu git báo file này đổi (suite đổi line-ending).
- Widget built-in (id có trong `UiConfigManager._DEFAULT_UI_CONFIG[panel]`) **chỉ ẩn được, không xoá được** — `_merge_new_defaults` sẽ nối lại id thiếu.
- Thứ tự phần tử trong mảng panel của `ui_config.json` = thứ tự hiển thị.
- `calibration_overrides.json` được sao lưu **nguyên file** (không lọc key). Ghi bằng `core.utils.atomic_write_json` (không BOM). Đọc file người dùng bằng `encoding="utf-8-sig"`.
- Định dạng file sao lưu: `format = "quangluu-devmode-backup"`, `format_version = 1`, tên gợi ý `quangluu-giaodien-YYYYMMDD-HHMM.json`; bản .bak ở `<thư mục ui_config.json>/backups/<tên file>.<YYYYmmdd-HHMMSS>.bak`.
- Ô màu nhanh dùng đúng token: `primary, creative, accent, green, orange, pink, deep_purple, blue` (từ `ui.design_tokens.C`).
- Mọi chữ trên UI bằng tiếng Việt; giữ phím `Ctrl+Shift+D` và menu chuột phải Sửa/Ẩn như cũ.
- Không để Qt in `QWindowsWindow::setGeometry` khi đổi trường trong dialog: nhãn có nội dung thay đổi được **dành sẵn chiều cao cố định và luôn visible** (không ẩn/hiện) — bài học commit 49a41ab.

## Review Focus

1. File sao lưu sửa bằng Notepad (có UTF-8 BOM) phải nhập được bình thường → test `test_read_backup_chap_nhan_bom` (Task 2).
2. File sao lưu chỉ có một panel (vd. bản cũ chỉ có `tools`) → sau khôi phục app vẫn có đủ 3 panel nhờ merge mặc định → test `test_restore_thieu_panel_van_du_3_panel` (Task 2).
3. `ui_config.json` sửa tay có phần tử không phải dict / CC dạng chuỗi số trong `midi_cc` → các hàm `ui_layout` bỏ qua, không crash, vẫn dò đúng → test `test_bo_qua_phan_tu_hong` và `test_conflict_midi_cc_dang_chuoi` (Task 1).
4. Đóng hộp Quản lý bằng nút X khi còn thay đổi chưa lưu → phải hỏi, chọn "Không" thì hộp ở lại → test `test_dong_khi_con_thay_doi_hoi_truoc` (Task 5).
5. Gửi thử khi cổng MIDI lỗi (`send_midi` ném lỗi) → báo trong dialog, không crash → test `test_gui_thu_loi_khong_crash` (Task 4).

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `core/ui_layout.py` (mới) | Thao tác thuần trên ui_config: `PANEL_TITLES`, `is_custom`, `index_of`, `move`, `reorder`, `set_hidden`, `delete_custom`, `reset_panel`, `is_valid_color`, `find_cc_conflicts` |
| `core/devmode_backup.py` (mới) | `BackupError`, `default_filename`, `build_backup`, `export_backup`, `read_backup`, `summarize`, `restore_backup` |
| `ui/dialogs/widget_builder.py` (sửa) | Nhãn/bố cục/ô màu, kiểm tra tức thì, cảnh báo CC, Gửi thử |
| `ui/dialogs/widget_manager.py` (mới) | `WidgetManagerDialog` — tab Mixer/Tools/Mode, Lưu/Huỷ, Xuất/Nhập |
| `ui/panels/_dev_buttons.py` (mới) | `build_dev_row` — hàng "+ Thêm…" + "⚙ Quản lý" dùng chung 3 panel |
| `ui/panels/{mixer,tools,mode}.py` (sửa) | Dùng `build_dev_row` |
| `frontend_qt.py` (sửa) | `_on_manage_widgets`, `_after_backup_restore`, `_resend_calibrated_states`; truyền engine/midi_cc/ui_config cho Widget Builder |
| `docs/DEV_MODE_GUIDE.md` (sửa) | Tài liệu tính năng mới |

---

### Task 1: `core/ui_layout.py` — thao tác thuần trên ui_config

**Files:**
- Create: `core/ui_layout.py`
- Test: `tests/core/test_ui_layout.py`

**Interfaces:**
- Consumes: `core.config.UiConfigManager._DEFAULT_UI_CONFIG`
- Produces:
  - `PANEL_TITLES: dict[str, str]` = `{"mixer": "Mixer", "tools": "Tools", "mode": "Mode"}` (giữ thứ tự)
  - `default_ids(panel: str) -> set[str]`
  - `is_custom(panel: str, entry) -> bool`
  - `index_of(entries: list, wid: str) -> int` (-1 nếu không có)
  - `move(entries: list, index: int, delta: int) -> int` (sửa tại chỗ, trả index mới)
  - `reorder(entries: list, ids: list[str]) -> list` (list mới)
  - `set_hidden(entries: list, wid: str, hidden: bool) -> bool`
  - `delete_custom(panel: str, entries: list, wid: str) -> bool`
  - `reset_panel(config: dict, panel: str) -> None`
  - `is_valid_color(text: str, token_names=()) -> bool`
  - `find_cc_conflicts(cc: int, ui_config: dict, midi_cc: dict, exclude_id=None, mode_config=None) -> list[str]`

- [ ] **Step 1: Write the failing tests**

`tests/core/test_ui_layout.py`:

```python
"""Thao tác thuần trên ui_config cho hộp Quản lý giao diện (Dev Mode)."""
import copy

from core import ui_layout
from core.config import UiConfigManager


def _cfg():
    return copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)


def _ids(entries):
    return [e["id"] for e in entries if isinstance(e, dict)]


def test_is_custom_theo_id_mac_dinh():
    assert not ui_layout.is_custom("tools", {"id": "btn_rescan"})
    assert ui_layout.is_custom("tools", {"id": "custom_ab12cd34"})
    # id built-in của panel khác vẫn tính là custom ở panel này
    assert ui_layout.is_custom("mode", {"id": "btn_rescan"})
    assert not ui_layout.is_custom("tools", "hỏng")


def test_move_len_xuong_va_chan_bien():
    entries = _cfg()["tools"]
    first = entries[0]["id"]
    assert ui_layout.move(entries, 0, -1) == 0
    assert entries[0]["id"] == first
    assert ui_layout.move(entries, 0, 1) == 1
    assert entries[1]["id"] == first
    last = len(entries) - 1
    assert ui_layout.move(entries, last, 1) == last
    assert ui_layout.move(entries, 99, 1) == 99  # index ngoài dải: không làm gì


def test_reorder_theo_ids_giu_phan_tu_la_o_cuoi():
    entries = [{"id": "a"}, "hỏng", {"id": "b"}, {"id": "c"}]
    out = ui_layout.reorder(entries, ["c", "a", "b"])
    assert out[:3] == [{"id": "c"}, {"id": "a"}, {"id": "b"}]
    assert out[3] == "hỏng"


def test_set_hidden():
    entries = _cfg()["mixer"]
    assert ui_layout.set_hidden(entries, "mix_reverb", True)
    assert entries[ui_layout.index_of(entries, "mix_reverb")]["hidden"] is True
    assert ui_layout.set_hidden(entries, "mix_reverb", False)
    assert entries[ui_layout.index_of(entries, "mix_reverb")]["hidden"] is False
    assert not ui_layout.set_hidden(entries, "khong_co", True)


def test_delete_custom_tu_choi_built_in():
    entries = _cfg()["tools"] + [{"id": "custom_1", "label": "X", "cc": 60}]
    assert not ui_layout.delete_custom("tools", entries, "btn_rescan")
    assert "btn_rescan" in _ids(entries)
    assert ui_layout.delete_custom("tools", entries, "custom_1")
    assert "custom_1" not in _ids(entries)
    assert not ui_layout.delete_custom("tools", entries, "custom_1")


def test_reset_panel_chi_doi_panel_do():
    cfg = _cfg()
    cfg["tools"] = [{"id": "custom_1"}]
    cfg["mode"][0]["hidden"] = True
    ui_layout.reset_panel(cfg, "tools")
    assert _ids(cfg["tools"]) == _ids(UiConfigManager._DEFAULT_UI_CONFIG["tools"])
    assert cfg["mode"][0]["hidden"] is True
    # bản sao sâu: sửa cfg không làm bẩn mặc định
    cfg["tools"][0]["label"] = "Đổi"
    assert UiConfigManager._DEFAULT_UI_CONFIG["tools"][0]["label"] != "Đổi"


def test_is_valid_color():
    assert ui_layout.is_valid_color("#abc")
    assert ui_layout.is_valid_color("#14B8A6")
    assert ui_layout.is_valid_color(" #14b8a6 ")
    assert not ui_layout.is_valid_color("#14b8a")
    assert not ui_layout.is_valid_color("teal")
    assert ui_layout.is_valid_color("teal", token_names={"teal"})


def test_conflict_custom_va_built_in():
    cfg = _cfg()
    cfg["tools"].append({"id": "custom_1", "label": "Vang HT", "cc": 60})
    midi_cc = {"mix_music": 20, "mode": 30}
    assert ui_layout.find_cc_conflicts(60, cfg, midi_cc) == ["Vang HT (Tools)"]
    # CC built-in dạng tên → hiện nhãn widget, không lặp lại key hệ thống
    assert ui_layout.find_cc_conflicts(20, cfg, midi_cc) == ["Nhạc (Mixer)"]
    assert ui_layout.find_cc_conflicts(30, cfg, midi_cc) == ["CC hệ thống “mode”"]
    assert ui_layout.find_cc_conflicts(99, cfg, midi_cc) == []
    assert ui_layout.find_cc_conflicts(-1, cfg, midi_cc) == []


def test_conflict_loai_chinh_no_va_mode_config():
    cfg = _cfg()
    cfg["tools"].append({"id": "custom_1", "label": "Vang HT", "cc": 60})
    modes = {"Lofi": {"cc": 37, "on_value": 127, "off_value": 0}}
    assert ui_layout.find_cc_conflicts(60, cfg, {}, exclude_id="custom_1") == []
    assert ui_layout.find_cc_conflicts(37, cfg, {}, mode_config=modes) == ["Mode Lofi"]
    # Đang sửa chính nút Lofi → không tự cảnh báo CC mode của nó
    assert ui_layout.find_cc_conflicts(37, cfg, {}, exclude_id="mode_lofi",
                                       mode_config=modes) == []


def test_conflict_midi_cc_dang_chuoi():
    assert ui_layout.find_cc_conflicts(20, {}, {"mix_music": "20"}) == ["CC hệ thống “mix_music”"]


def test_bo_qua_phan_tu_hong():
    cfg = {"mixer": ["hỏng", None, {"id": "custom_1", "label": "A", "cc": True}],
           "tools": "không phải list"}
    assert ui_layout.find_cc_conflicts(1, cfg, {"x": None}) == []
    assert ui_layout.index_of(cfg["mixer"], "custom_1") == 2
    assert not ui_layout.set_hidden(cfg["mixer"], "khong_co", True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\core\test_ui_layout.py`
Expected: FAIL — `ImportError: cannot import name 'ui_layout' from 'core'`

- [ ] **Step 3: Write the implementation**

`core/ui_layout.py`:

```python
"""Thao tác thuần trên ui_config (Dev Mode) — không phụ thuộc Qt để test được.

Widget built-in = id có trong mặc định của panel. UiConfigManager nối lại id
built-in bị thiếu mỗi lần nạp, nên built-in chỉ ẩn được, không xoá được.
"""
import copy
import re

PANEL_TITLES = {"mixer": "Mixer", "tools": "Tools", "mode": "Mode"}

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _defaults():
    from core.config import UiConfigManager
    return UiConfigManager._DEFAULT_UI_CONFIG


def default_ids(panel):
    return {d["id"] for d in _defaults().get(panel, [])}


def is_custom(panel, entry):
    return isinstance(entry, dict) and entry.get("id") not in default_ids(panel)


def index_of(entries, wid):
    for i, e in enumerate(entries):
        if isinstance(e, dict) and e.get("id") == wid:
            return i
    return -1


def move(entries, index, delta):
    """Dời entries[index] đi delta bước (chặn ở hai đầu). Trả index mới."""
    if not 0 <= index < len(entries):
        return index
    new = max(0, min(len(entries) - 1, index + delta))
    if new != index:
        entries.insert(new, entries.pop(index))
    return new


def reorder(entries, ids):
    """Sắp lại theo ids (thứ tự trên danh sách kéo-thả). Phần tử không có
    trong ids (hỏng / không phải dict) giữ ở cuối theo thứ tự cũ."""
    by_id = {}
    for e in entries:
        if isinstance(e, dict) and e.get("id") not in by_id:
            by_id[e.get("id")] = e
    head = [by_id[i] for i in ids if i in by_id]
    used = {id(e) for e in head}
    return head + [e for e in entries if id(e) not in used]


def set_hidden(entries, wid, hidden):
    i = index_of(entries, wid)
    if i < 0:
        return False
    entries[i]["hidden"] = bool(hidden)
    return True


def delete_custom(panel, entries, wid):
    i = index_of(entries, wid)
    if i < 0 or not is_custom(panel, entries[i]):
        return False
    del entries[i]
    return True


def reset_panel(config, panel):
    config[panel] = copy.deepcopy(_defaults().get(panel, []))


def is_valid_color(text, token_names=()):
    text = (text or "").strip()
    return bool(_HEX.match(text)) or text in token_names


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_cc_conflicts(cc, ui_config, midi_cc, exclude_id=None, mode_config=None):
    """Những thứ khác đang gửi trên CC `cc` — để cảnh báo (không chặn) trong
    Widget Builder. Gồm widget trên 3 panel (CC số hoặc tên tra midi_cc),
    CC của mode trong mode_config và key hệ thống trong midi_cc."""
    if cc is None or cc < 0:
        return []
    midi_cc = midi_cc or {}
    hits, used_keys = [], set()
    exclude_label = None
    for panel, title in PANEL_TITLES.items():
        entries = (ui_config or {}).get(panel)
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            if exclude_id is not None and e.get("id") == exclude_id:
                exclude_label = e.get("label")
                continue
            raw = e.get("cc")
            if isinstance(raw, str):
                if _as_int(midi_cc.get(raw)) == cc:
                    hits.append(f"{e.get('label') or raw} ({title})")
                    used_keys.add(raw)
            elif _as_int(raw) == cc:
                hits.append(f"{e.get('label') or e.get('id')} ({title})")
    for label, mcfg in (mode_config or {}).items():
        if label == exclude_label or not isinstance(mcfg, dict):
            continue
        if _as_int(mcfg.get("cc")) == cc:
            hits.append(f"Mode {label}")
    for key, value in midi_cc.items():
        if key not in used_keys and _as_int(value) == cc:
            hits.append(f"CC hệ thống “{key}”")
    return list(dict.fromkeys(hits))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\core\test_ui_layout.py`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add core/ui_layout.py tests/core/test_ui_layout.py
git commit -m "feat(devmode): core/ui_layout — đổi thứ tự/ẩn/xoá widget, dò CC trùng"
```

---

### Task 2: `core/devmode_backup.py` — xuất/nhập cấu hình

**Files:**
- Create: `core/devmode_backup.py`
- Test: `tests/core/test_devmode_backup.py`

**Interfaces:**
- Consumes: `core.ui_layout.PANEL_TITLES`; `core.config.UI_CONFIG_FILE`, `CALIBRATION_OVERRIDES_FILE`, `UiConfigManager.load_ui_config`, `AppConfig.reload` (đọc qua module `core.config` lúc gọi để test monkeypatch được); `core.utils.atomic_write_json`; `core.version.__version__`
- Produces:
  - `class BackupError(Exception)` — thông điệp tiếng Việt hiển thị thẳng cho người dùng
  - `default_filename(now: datetime | None = None) -> str`
  - `build_backup() -> dict`
  - `export_backup(path: str) -> None`
  - `read_backup(path: str) -> dict` (ném `BackupError`)
  - `summarize(backup: dict) -> str`
  - `restore_backup(backup: dict) -> list[str]` (đường dẫn các .bak đã tạo; ném `BackupError`)

- [ ] **Step 1: Write the failing tests**

`tests/core/test_devmode_backup.py`:

```python
"""Xuất/nhập cấu hình Dev Mode (ui_config + calibration_overrides)."""
import json
import os
from datetime import datetime
from unittest.mock import patch

import pytest

import core.config as cfg
from core import devmode_backup as bk


@pytest.fixture
def files(tmp_path, monkeypatch):
    ui = tmp_path / "ui_config.json"
    cal = tmp_path / "calibration_overrides.json"
    monkeypatch.setattr(cfg, "UI_CONFIG_FILE", str(ui))
    monkeypatch.setattr(cfg, "CALIBRATION_OVERRIDES_FILE", str(cal))
    yield ui, cal
    cfg.AppConfig.reload()


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_default_filename():
    assert bk.default_filename(datetime(2026, 10, 9, 14, 5)) == "quangluu-giaodien-20261009-1405.json"


def test_round_trip_giu_key_la_cua_calibration(files, tmp_path):
    ui, cal = files
    layout = cfg.UiConfigManager.load_ui_config()
    layout["tools"][1]["hidden"] = True
    _write(ui, layout)
    _write(cal, {"mode_config": {"Lofi": {"cc": 37}}, "key_la_cua_may_khach": {"x": 1}})

    out = tmp_path / "out" / "sao-luu.json"
    out.parent.mkdir()
    bk.export_backup(str(out))
    data = bk.read_backup(str(out))
    assert data["format"] == "quangluu-devmode-backup"
    assert data["calibration_overrides"]["key_la_cua_may_khach"] == {"x": 1}

    # Đổi máy: xoá cấu hình rồi khôi phục
    os.remove(ui)
    os.remove(cal)
    assert bk.restore_backup(data) == []  # không có file cũ → không có .bak
    assert _read(ui)["tools"][1]["hidden"] is True
    assert _read(cal)["key_la_cua_may_khach"] == {"x": 1}


def test_restore_tao_bak_truoc_khi_ghi(files):
    ui, cal = files
    _write(ui, {"tools": [{"id": "custom_cu"}]})
    _write(cal, {"toggle_invert": {"be": True}})
    backup = {"format": "quangluu-devmode-backup", "format_version": 1,
              "ui_config": {"tools": [{"id": "custom_moi"}]}, "calibration_overrides": {}}
    baks = bk.restore_backup(backup)
    assert len(baks) == 2
    assert all(os.path.dirname(b) == os.path.join(str(ui.parent), "backups") for b in baks)
    names = sorted(os.path.basename(b).split(".")[0] for b in baks)
    assert names == ["calibration_overrides", "ui_config"]
    ui_bak = next(b for b in baks if os.path.basename(b).startswith("ui_config"))
    with open(ui_bak, encoding="utf-8") as f:
        assert json.load(f) == {"tools": [{"id": "custom_cu"}]}
    assert _read(ui) == {"tools": [{"id": "custom_moi"}]}


def test_restore_thieu_panel_van_du_3_panel(files):
    backup = {"format": "quangluu-devmode-backup", "format_version": 1,
              "ui_config": {"tools": [{"id": "custom_1", "label": "X", "cc": 60}]},
              "calibration_overrides": {}}
    bk.restore_backup(backup)
    loaded = cfg.UiConfigManager.load_ui_config()
    assert set(loaded) >= {"mixer", "tools", "mode"}
    assert loaded["mixer"]  # built-in được nối lại
    assert loaded["tools"][0]["id"] == "custom_1"


def test_restore_ghi_loi_tra_lai_nhu_cu(files):
    ui, cal = files
    _write(ui, {"tools": [{"id": "custom_cu"}]})
    _write(cal, {"toggle_invert": {"be": True}})
    backup = {"format": "quangluu-devmode-backup", "format_version": 1,
              "ui_config": {"tools": []}, "calibration_overrides": {"mode_config": {}}}
    real = bk.atomic_write_json
    calls = []

    def flaky(path, data, *a, **k):
        calls.append(path)
        if len(calls) == 2:
            raise OSError("đĩa đầy")
        return real(path, data, *a, **k)

    with patch.object(bk, "atomic_write_json", side_effect=flaky):
        with pytest.raises(bk.BackupError) as ei:
            bk.restore_backup(backup)
    assert "đã trả lại như cũ" in str(ei.value)
    assert _read(ui) == {"tools": [{"id": "custom_cu"}]}
    assert _read(cal) == {"toggle_invert": {"be": True}}


@pytest.mark.parametrize("content, msg", [
    ("{không phải json", "Không đọc được file"),
    (json.dumps({"format": "khac"}), "không phải bản sao lưu"),
    (json.dumps({"format": "quangluu-devmode-backup", "format_version": 2,
                 "ui_config": {"tools": []}}), "bản app mới hơn"),
    (json.dumps({"format": "quangluu-devmode-backup", "format_version": 1,
                 "ui_config": {"khac": []}}), "không có cấu hình giao diện"),
    (json.dumps({"format": "quangluu-devmode-backup", "format_version": 1,
                 "ui_config": {"tools": []}, "calibration_overrides": [1]}), "cân chỉnh MIDI"),
])
def test_read_backup_tu_choi_file_sai(tmp_path, content, msg):
    p = tmp_path / "x.json"
    p.write_text(content, encoding="utf-8")
    with pytest.raises(bk.BackupError) as ei:
        bk.read_backup(str(p))
    assert msg in str(ei.value)


def test_read_backup_chap_nhan_bom(tmp_path):
    p = tmp_path / "x.json"
    data = {"format": "quangluu-devmode-backup", "format_version": 1, "ui_config": {"tools": []}}
    p.write_text(json.dumps(data), encoding="utf-8-sig")
    out = bk.read_backup(str(p))
    assert out["calibration_overrides"] == {}


def test_summarize_dem_widget_an():
    backup = {"app_version": "1.8.0", "exported_at": "2026-10-09T14:30:00",
              "ui_config": {"mixer": [{"id": "a"}, {"id": "b", "hidden": True}],
                            "tools": [{"id": "c"}]},
              "calibration_overrides": {"mode_config": {}, "toggle_invert": {}}}
    text = bk.summarize(backup)
    assert "Mixer: 2 widget (1 ẩn)" in text
    assert "Tools: 1 widget" in text
    assert "Mode" not in text
    assert "2 mục cân chỉnh MIDI" in text
    assert "v1.8.0 lúc 09/10/2026 14:30" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\core\test_devmode_backup.py`
Expected: FAIL — `ImportError: cannot import name 'devmode_backup'`

- [ ] **Step 3: Write the implementation**

`core/devmode_backup.py`:

```python
"""Xuất/nhập toàn bộ cấu hình Dev Mode của một máy khách.

Một file gồm ui_config.json (widget, thứ tự, ẩn) và NGUYÊN calibration_overrides.json
(Bypass, mode_config và các key cân chỉnh riêng của máy — không lọc). Khôi phục
luôn chép hai file hiện có sang thư mục backups/ trước khi ghi đè.
"""
import json
import os
import shutil
from datetime import datetime

import core.config as cfg
from core.ui_layout import PANEL_TITLES
from core.utils import atomic_write_json
from core.version import __version__

FORMAT = "quangluu-devmode-backup"
FORMAT_VERSION = 1


class BackupError(Exception):
    """Lỗi xuất/nhập — thông điệp hiện thẳng cho kỹ thuật viên."""


def default_filename(now=None):
    now = now or datetime.now()
    return f"quangluu-giaodien-{now:%Y%m%d-%H%M}.json"


def _read_json(path):
    # utf-8-sig: file mở/lưu bằng Notepad có BOM vẫn đọc được.
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def build_backup():
    calibration = {}
    path = cfg.CALIBRATION_OVERRIDES_FILE
    if os.path.exists(path):
        try:
            data = _read_json(path)
            if isinstance(data, dict):
                calibration = data
        except (OSError, ValueError):
            calibration = {}
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "ui_config": cfg.UiConfigManager.load_ui_config(),
        "calibration_overrides": calibration,
    }


def export_backup(path):
    atomic_write_json(path, build_backup())


def read_backup(path):
    try:
        data = _read_json(path)
    except (OSError, ValueError) as e:
        raise BackupError(f"Không đọc được file: {e}") from e
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise BackupError("File này không phải bản sao lưu giao diện của Quang Lưu Studio.")
    version = data.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise BackupError("File sao lưu thiếu phiên bản định dạng.")
    if version > FORMAT_VERSION:
        raise BackupError("File được tạo bởi bản app mới hơn — hãy cập nhật app rồi nhập lại.")
    ui = data.get("ui_config")
    if not isinstance(ui, dict) or not any(isinstance(ui.get(p), list) for p in PANEL_TITLES):
        raise BackupError("File sao lưu không có cấu hình giao diện (mixer/tools/mode).")
    if not isinstance(data.get("calibration_overrides", {}), dict):
        raise BackupError("Phần cân chỉnh MIDI trong file bị hỏng.")
    data.setdefault("calibration_overrides", {})
    return data


def summarize(backup):
    ui = backup.get("ui_config") or {}
    parts = []
    for panel, title in PANEL_TITLES.items():
        entries = ui.get(panel)
        if not isinstance(entries, list):
            continue
        entries = [e for e in entries if isinstance(e, dict)]
        hidden = sum(1 for e in entries if e.get("hidden"))
        parts.append(f"{title}: {len(entries)} widget" + (f" ({hidden} ẩn)" if hidden else ""))
    parts.append(f"{len(backup.get('calibration_overrides') or {})} mục cân chỉnh MIDI")
    when = backup.get("exported_at") or ""
    try:
        when = datetime.fromisoformat(when).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        pass
    origin = f"Xuất từ v{backup.get('app_version', '?')}" + (f" lúc {when}" if when else "")
    return " · ".join(parts) + "\n" + origin


def _backup_dir():
    return os.path.join(os.path.dirname(os.path.abspath(cfg.UI_CONFIG_FILE)), "backups")


def restore_backup(backup):
    """Ghi đè ui_config.json + calibration_overrides.json từ `backup` (đã qua
    read_backup). Chép file hiện có sang backups/ trước; ghi lỗi giữa chừng thì
    trả lại từ bản chép. Trả danh sách file .bak đã tạo."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    targets = (
        (cfg.UI_CONFIG_FILE, backup["ui_config"]),
        (cfg.CALIBRATION_OVERRIDES_FILE, backup.get("calibration_overrides") or {}),
    )
    saved = []
    try:
        os.makedirs(_backup_dir(), exist_ok=True)
        for target, _ in targets:
            bak = None
            if os.path.exists(target):
                bak = os.path.join(_backup_dir(), f"{os.path.basename(target)}.{stamp}.bak")
                shutil.copy2(target, bak)
            saved.append((target, bak))
    except OSError as e:
        raise BackupError(f"Không sao lưu được cấu hình hiện tại, chưa ghi gì: {e}") from e

    try:
        for target, data in targets:
            atomic_write_json(target, data)
    except Exception as e:
        for target, bak in saved:
            try:
                if bak:
                    shutil.copy2(bak, target)
                elif os.path.exists(target):
                    os.remove(target)
            except OSError:
                pass
        raise BackupError(
            f"Ghi cấu hình lỗi, đã trả lại như cũ (bản sao lưu ở {_backup_dir()}): {e}") from e

    cfg.AppConfig.reload()
    return [bak for _, bak in saved if bak]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\core\test_devmode_backup.py`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add core/devmode_backup.py tests/core/test_devmode_backup.py
git commit -m "feat(devmode): xuất/nhập cấu hình giao diện + cân chỉnh MIDI, tự sao lưu trước khi ghi"
```

---

### Task 3: Widget Builder — nhãn thân thiện, nhóm trường, ô màu, kiểm tra tức thì

**Files:**
- Modify: `ui/dialogs/widget_builder.py` (`__init__`, `_build_fields`, `_build_buttons`, `_on_type_changed`, `_refresh_preview`, `_load_data`, `_on_save`; thêm `_section`, `_validate`, `_update_save_state`)
- Modify: `tests/ui/test_widget_builder_so_values.py` (2 test thêm tên), `tests/ui/test_qt_warnings.py` (đổi loại bằng `findData`)
- Test: `tests/ui/test_widget_builder_form.py`

**Interfaces:**
- Consumes: `core.ui_layout.is_valid_color`
- Produces (Task 4/5 dùng): `type_combo` có data `"slider"`/`"button"` (chữ hiển thị "Thanh trượt"/"Nút"); `type_row: QWidget`; `icon_row: QWidget`; `swatches: dict[str, QPushButton]`; `_validate() -> str | None`; `_update_save_state() -> str | None`; `save_btn` bị disable khi có lỗi; `error_label` luôn visible với chiều cao cố định.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_widget_builder_form.py`:

```python
"""Widget Builder: nhãn thân thiện, ô màu, kiểm tra tức thì."""
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication

from core.config import DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT
from ui.design_tokens import C
from ui.dialogs.widget_builder import WidgetBuilderDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def cfg():
    modes = {k: dict(v) for k, v in DEFAULT_MODE_CONFIG.items()}
    invert = dict(DEFAULT_TOGGLE_INVERT)
    with patch("core.config.AppConfig.get_mode_config", return_value=modes), \
         patch("core.config.AppConfig.get_toggle_invert", return_value=invert):
        yield modes, invert


def _dlg(qtbot, **kw):
    dlg = WidgetBuilderDialog(None, **kw)
    qtbot.addWidget(dlg)
    return dlg


def test_combo_loai_hien_chu_tieng_viet(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    texts = [dlg.type_combo.itemText(i) for i in range(dlg.type_combo.count())]
    assert texts == ["Thanh trượt", "Nút"]
    assert dlg.type_combo.currentData() == "slider"
    assert not dlg.type_row.isHidden()


def test_an_combo_loai_khi_sua_va_o_tools_mode(qapp, qtbot, cfg):
    assert _dlg(qtbot, panel_name="tools", widget_type="button").type_row.isHidden()
    assert _dlg(qtbot, panel_name="mode", widget_type="button").type_row.isHidden()
    entry = {"id": "mix_music", "type": "slider", "label": "Nhạc", "cc": "mix_music",
             "range": [0, 100]}
    assert _dlg(qtbot, panel_name="mixer", widget_type="slider",
                existing_data=entry).type_row.isHidden()


def test_icon_chi_hien_voi_thanh_truot(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    assert not dlg.icon_row.isHidden()
    dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("button"))
    assert dlg.icon_row.isHidden()


def test_bam_o_mau_dien_hex_token(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    assert set(dlg.swatches) == {"primary", "creative", "accent", "green",
                                 "orange", "pink", "deep_purple", "blue"}
    dlg.swatches["green"].click()
    assert dlg.color_input.text() == C["green"]


def test_ten_rong_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    assert not dlg.save_btn.isEnabled()
    assert "tên" in dlg.error_label.text().lower()
    dlg.label_input.setText("Vang HT")
    assert dlg.save_btn.isEnabled()
    assert dlg.error_label.text() == ""


def test_mau_sai_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    dlg.label_input.setText("X")
    dlg.color_input.setText("#12345")
    assert not dlg.save_btn.isEnabled()
    assert "màu" in dlg.error_label.text().lower()
    dlg.color_input.setText("")  # để trống = màu mặc định, hợp lệ
    assert dlg.save_btn.isEnabled()


def test_min_lon_hon_max_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    dlg.label_input.setText("Kênh")
    dlg.min_val.setValue(50)
    dlg.max_val.setValue(10)
    assert not dlg.save_btn.isEnabled()
    assert "min" in dlg.error_label.text().lower()
    dlg._on_save()
    assert dlg.result_data is None


def test_khoang_so_trung_khoa_luu(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    dlg.label_input.setText("X")
    dlg.cc_input.setValue(60)
    dlg.so_type_combo.setCurrentIndex(dlg.so_type_combo.findData("range"))
    dlg.range_min.setValue(5)
    dlg.range_max.setValue(5)
    assert not dlg.save_btn.isEnabled()


def test_luu_ghi_type_theo_data(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider")
    dlg.label_input.setText("Kênh")
    dlg._on_save()
    assert dlg.result_data["type"] == "slider"


def test_nhan_loi_luon_hien_chieu_cao_co_dinh(qapp, qtbot, cfg):
    dlg = _dlg(qtbot, panel_name="tools", widget_type="button")
    h = dlg.error_label.minimumHeight()
    assert h > 0 and not dlg.error_label.isHidden()
    dlg.label_input.setText("X")
    assert not dlg.error_label.isHidden()
    assert dlg.error_label.minimumHeight() == h
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\ui\test_widget_builder_form.py`
Expected: FAIL — `AttributeError: 'WidgetBuilderDialog' object has no attribute 'type_row'` (và các lỗi tương tự)

- [ ] **Step 3: Implement**

Trong `ui/dialogs/widget_builder.py`:

(a) Import + hằng số ở đầu file — thay dòng `from core import so_values` bằng:

```python
from core import so_values, ui_layout
```

và thêm sau hàm `_config()`:

```python
# (data, chữ hiển thị) của combo loại widget.
TYPE_LABELS = (("slider", "Thanh trượt"), ("button", "Nút"))
# Ô màu nhanh — token có thật trong ui/design_tokens.C.
SWATCH_TOKENS = ("primary", "creative", "accent", "green", "orange", "pink", "deep_purple", "blue")
```

(b) Cuối `__init__` — thay hai dòng

```python
        self._load_data()
        self._on_type_changed(self.type_combo.currentText())
```

bằng

```python
        self._load_data()
        self._on_type_changed(self.type_combo.currentData())
        self._update_save_state()
```

(c) Thêm helper ngay sau `_add_row`:

```python
    def _section(self, text, layout=None):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-weight: 700; color: {C['text_muted']}; margin-top: 4px;")
        (layout or self.vl).addWidget(lbl)
        return lbl
```

(d) Thay phần đầu `_build_fields` — từ `# Type` tới hết khối `# --- Slider Specific ---` (tức tới dòng `self.vl.addLayout(self.slider_widget)`, KHÔNG gồm khối CC) bằng nội dung dưới, và đặt khối CC hiện có (từ comment `# CC — giá trị -1 …` tới `self._add_row("MIDI CC:", self.cc_input)`) ngay sau dòng `self._section("MIDI")` như đánh dấu:

```python
    def _build_fields(self):
        # Loại — chỉ chọn được khi THÊM ở Mixer. Sửa thì loại đã cố định;
        # Tools/Mode chỉ có Nút.
        self.type_combo = QComboBox()
        for key, text in TYPE_LABELS:
            self.type_combo.addItem(text, key)
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(self.widget_type)))
        self.type_combo.currentIndexChanged.connect(
            lambda _i: self._on_type_changed(self.type_combo.currentData()))
        self.type_row = QWidget()
        trl = QHBoxLayout(self.type_row)
        trl.setContentsMargins(0, 0, 0, 0)
        tlbl = QLabel("Loại:")
        tlbl.setFixedWidth(100)
        trl.addWidget(tlbl)
        trl.addWidget(self.type_combo)
        self.vl.addWidget(self.type_row)
        self.type_row.setVisible(not self.existing_data and self.panel_name == "mixer")

        self._section("Hiển thị")
        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("Chữ hiện trên nút / kênh")
        self.label_input.textChanged.connect(lambda _t: self._update_save_state())
        self._add_row("Tên:", self.label_input)

        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("#HexColor — để trống = trắng")
        self.color_input.textChanged.connect(lambda _t: self._update_save_state())
        self.color_btn = QPushButton("Chọn màu")
        self.color_btn.clicked.connect(self._pick_color)
        chl = QHBoxLayout()
        lbl = QLabel("Màu sắc:")
        lbl.setFixedWidth(100)
        chl.addWidget(lbl)
        chl.addWidget(self.color_input)
        chl.addWidget(self.color_btn)
        self.vl.addLayout(chl)

        swl = QHBoxLayout()
        pad = QLabel("")
        pad.setFixedWidth(100)
        swl.addWidget(pad)
        self.swatches = {}
        for token in SWATCH_TOKENS:
            b = QPushButton()
            b.setFixedSize(22, 22)
            b.setToolTip(token)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"background-color: {C[token]}; border: 1px solid {C['border']};"
                            " border-radius: 4px;")
            b.clicked.connect(lambda _c=False, tk=token: self.color_input.setText(C[tk]))
            swl.addWidget(b)
            self.swatches[token] = b
        swl.addStretch()
        self.vl.addLayout(swl)

        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("♪, ☉, ≡")
        self.icon_row = QWidget()
        irl = QHBoxLayout(self.icon_row)
        irl.setContentsMargins(0, 0, 0, 0)
        ilbl = QLabel("Icon:")
        ilbl.setFixedWidth(100)
        irl.addWidget(ilbl)
        irl.addWidget(self.icon_input)
        self.vl.addWidget(self.icon_row)

        self._section("MIDI")
        # >>> khối CC hiện có (cc_input QSpinBox -1..127 + _add_row("MIDI CC:", ...)) đặt ở đây <<<

        # --- Slider Specific ---
        self.slider_widget = QVBoxLayout()
        self.slider_widget.setContentsMargins(0, 0, 0, 0)
        self._section("Giá trị", self.slider_widget)

        self.min_val = QSpinBox()
        self.min_val.setRange(-127, 127)
        self.max_val = QSpinBox()
        self.max_val.setRange(-127, 127)
        self.max_val.setValue(100)
        for sb in (self.min_val, self.max_val):
            sb.valueChanged.connect(lambda _v: self._update_save_state())

        hl2 = QHBoxLayout()
        hl2.addWidget(QLabel("Min:"))
        hl2.addWidget(self.min_val)
        hl2.addWidget(QLabel("Max:"))
        hl2.addWidget(self.max_val)
        self.slider_widget.addLayout(hl2)

        self.has_mute_cb = QCheckBox("Có nút Mute")
        self.slider_widget.addWidget(self.has_mute_cb)

        self.vl.addLayout(self.slider_widget)
```

Phần `# --- Button Specific ---` phía sau giữ nguyên.

(e) `_build_buttons` — thay 4 dòng tạo `error_label`:

```python
        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {C['accent']};")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.vl.addWidget(self.error_label)
```

bằng:

```python
        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {C['accent']};")
        self.error_label.setWordWrap(True)
        # Luôn hiện, dành sẵn 2 dòng: ẩn/hiện nhãn đổi cỡ tối thiểu của dialog
        # → Qt in cảnh báo setGeometry (xem value_note).
        self.error_label.ensurePolished()
        self.error_label.setMinimumHeight(self.error_label.fontMetrics().lineSpacing() * 2 + 4)
        self.vl.addWidget(self.error_label)
```

(f) Thay `_on_type_changed`:

```python
    def _on_type_changed(self, t):
        is_slider = t == "slider"
        self._set_layout_visible(self.slider_widget, is_slider)
        self.icon_row.setVisible(is_slider)
        self.button_box.setVisible(not is_slider)
        if not is_slider:
            self._refresh_value_section()
        self._update_save_state()
        self.adjustSize()
```

(g) Thêm hai method ngay sau `_validation_error`:

```python
    def _validate(self):
        """Lý do chưa Lưu được (None = hợp lệ). Chạy mỗi khi một trường đổi."""
        if not self.label_input.text().strip():
            return "Chưa nhập tên."
        color = self.color_input.text().strip()
        if color and not ui_layout.is_valid_color(color, C.keys()):
            return "Màu không hợp lệ — dùng mã #rgb / #rrggbb hoặc bấm một ô màu."
        if self.type_combo.currentData() == "slider":
            if self.min_val.value() >= self.max_val.value():
                return "Min phải nhỏ hơn Max."
            return None
        if self._value_target() is not None:
            return self._validation_error(self._current_spec())
        return None

    def _update_save_state(self):
        if self._loading or not hasattr(self, "save_btn"):
            return None
        err = self._validate()
        self.error_label.setText(err or "")
        self.save_btn.setEnabled(err is None)
        self.save_btn.setToolTip(err or "")
        return err
```

(h) Trong `_refresh_preview` thay hai dòng

```python
        self.error_label.setText(err or "")
        self.error_label.setVisible(bool(err))
```

bằng

```python
        self._update_save_state()
```

(i) `_load_data`: thay `self.type_combo.setCurrentText(d.get("type", "slider"))` bằng

```python
        self.type_combo.setCurrentIndex(max(0, self.type_combo.findData(d.get("type", "slider"))))
```

(j) `_on_save`: thay dòng đầu `t = self.type_combo.currentText()` bằng

```python
        err = self._validate()
        if err:
            self.error_label.setText(err)
            return
        t = self.type_combo.currentData()
```

và xoá khối kiểm tra lỗi spec cũ trong nhánh `else` (nay `_validate` đã chặn):

```python
            if target is not None:
                err = self._validation_error(spec)
                if err:
                    self.error_label.setText(err)
                    self.error_label.setVisible(True)
                    return
```

(k) Sửa test cũ cho khớp:
- `tests/ui/test_widget_builder_so_values.py`: trong `test_nut_moi_phan_tram` và `test_nut_moi_danh_sach`, thêm `dlg.label_input.setText("Nút thử")` ngay sau `qtbot.addWidget(dlg)` (nút mới bắt buộc có tên).
- `tests/ui/test_qt_warnings.py` (`test_widget_builder_doi_kieu_khong_canh_bao_geometry`): thay `dlg.type_combo.setCurrentText("button")` bằng `dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("button"))` và `dlg.type_combo.setCurrentText("slider")` bằng `dlg.type_combo.setCurrentIndex(dlg.type_combo.findData("slider"))`; thêm `dlg.label_input.setText("")` rồi `qtbot.wait(150)` và `dlg.label_input.setText("X")` rồi `qtbot.wait(150)` trước khi đọc `bad` (đổi lỗi tên không được in cảnh báo geometry).

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\ui\test_widget_builder_form.py tests\ui\test_widget_builder_so_values.py tests\ui\test_qt_warnings.py`
Expected: tất cả passed

- [ ] **Step 5: Commit**

```bash
git add ui/dialogs/widget_builder.py tests/ui/test_widget_builder_form.py tests/ui/test_widget_builder_so_values.py tests/ui/test_qt_warnings.py
git commit -m "feat(devmode): Widget Builder — nhãn tiếng Việt, nhóm trường, ô màu, kiểm tra tức thì"
```

---

### Task 4: Widget Builder — cảnh báo CC trùng + Gửi thử

**Files:**
- Modify: `ui/dialogs/widget_builder.py` (`__init__` thêm tham số, khối CC trong `_build_fields`; thêm `_refresh_cc_info`, `_cc_conflicts`, `_test_values`, `_on_test_send`, `_send_quiet`)
- Test: `tests/ui/test_widget_builder_cc.py`

**Interfaces:**
- Consumes: `core.ui_layout.find_cc_conflicts`; `engine.send_midi(cc: int, value: int)`; `core.config.UiConfigManager.load_ui_config`, `AppConfig.get_midi_cc`, `AppConfig.get_mode_config`
- Produces: `WidgetBuilderDialog(parent=None, panel_name="mixer", widget_type="slider", existing_data=None, engine=None, ui_config=None, midi_cc=None)` — `engine` mặc định `getattr(parent, "engine", None)`; thuộc tính `cc_note: QLabel`, `test_btn: QPushButton`, `test_status: QLabel`.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_widget_builder_cc.py`:

```python
"""Widget Builder: cảnh báo CC trùng và nút Gửi thử."""
import copy
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from core.config import DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT, UiConfigManager
from ui.dialogs.widget_builder import WidgetBuilderDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def cfg():
    modes = {k: dict(v) for k, v in DEFAULT_MODE_CONFIG.items()}
    invert = dict(DEFAULT_TOGGLE_INVERT)
    with patch("core.config.AppConfig.get_mode_config", return_value=modes), \
         patch("core.config.AppConfig.get_toggle_invert", return_value=invert):
        yield modes, invert


@pytest.fixture
def layout():
    ui = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    ui["tools"].append({"id": "custom_1", "type": "button", "label": "Vang HT", "cc": 60})
    return ui


def _dlg(qtbot, **kw):
    kw.setdefault("panel_name", "tools")
    kw.setdefault("widget_type", "button")
    kw.setdefault("midi_cc", {"mix_music": 20})
    dlg = WidgetBuilderDialog(None, **kw)
    qtbot.addWidget(dlg)
    dlg.label_input.setText("Nút thử")
    return dlg


def test_canh_bao_cc_trung_khong_chan_luu(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout)
    assert dlg.cc_note.text() == ""
    dlg.cc_input.setValue(60)
    assert "Vang HT (Tools)" in dlg.cc_note.text()
    assert dlg.save_btn.isEnabled()
    dlg.cc_input.setValue(20)
    assert "Nhạc (Mixer)" in dlg.cc_note.text()
    dlg.cc_input.setValue(99)
    assert dlg.cc_note.text() == ""


def test_sua_chinh_no_khong_tu_canh_bao(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout, existing_data=dict(layout["tools"][-1]))
    assert dlg.cc_input.value() == 60
    assert dlg.cc_note.text() == ""


def test_nhan_cc_luon_hien_chieu_cao_co_dinh(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout)
    h = dlg.cc_note.minimumHeight()
    assert h > 0 and not dlg.cc_note.isHidden()
    dlg.cc_input.setValue(60)
    assert dlg.cc_note.minimumHeight() == h and not dlg.cc_note.isHidden()


def test_gui_thu_gui_bat_roi_tat(qapp, qtbot, cfg, layout):
    engine = MagicMock()
    dlg = _dlg(qtbot, ui_config=layout, engine=engine)
    assert not dlg.test_btn.isEnabled()  # CC chưa gán
    dlg.cc_input.setValue(61)
    assert dlg.test_btn.isEnabled()
    dlg.test_btn.click()
    assert engine.send_midi.call_args_list[0].args == (61, 127)
    qtbot.waitUntil(lambda: engine.send_midi.call_count == 2, timeout=2000)
    assert engine.send_midi.call_args_list[1].args == (61, 0)
    assert "61" in dlg.test_status.text()


def test_gui_thu_thanh_truot(qapp, qtbot, cfg, layout):
    engine = MagicMock()
    dlg = _dlg(qtbot, panel_name="mixer", widget_type="slider", ui_config=layout, engine=engine)
    dlg.cc_input.setValue(70)
    dlg.test_btn.click()
    qtbot.waitUntil(lambda: engine.send_midi.call_count == 2, timeout=2000)
    assert [c.args for c in engine.send_midi.call_args_list] == [(70, 64), (70, 0)]


def test_gui_thu_khong_co_engine_thi_khoa(qapp, qtbot, cfg, layout):
    dlg = _dlg(qtbot, ui_config=layout)
    dlg.cc_input.setValue(61)
    assert not dlg.test_btn.isEnabled()


def test_gui_thu_loi_khong_crash(qapp, qtbot, cfg, layout):
    engine = MagicMock()
    engine.send_midi.side_effect = RuntimeError("cổng MIDI đóng")
    dlg = _dlg(qtbot, ui_config=layout, engine=engine)
    dlg.cc_input.setValue(61)
    dlg.test_btn.click()
    qtbot.wait(500)
    assert "cổng MIDI đóng" in dlg.test_status.text()
    assert engine.send_midi.call_count == 1  # lỗi lần BẬT → không hẹn gửi TẮT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\ui\test_widget_builder_cc.py`
Expected: FAIL — `TypeError: WidgetBuilderDialog.__init__() got an unexpected keyword argument 'midi_cc'`

- [ ] **Step 3: Implement**

(a) Import: đổi `from PySide6.QtCore import Qt` thành `from PySide6.QtCore import Qt, QTimer`.

(b) `__init__` — đổi chữ ký và thêm thuộc tính (đặt ngay sau `self._loading = False`):

```python
    def __init__(self, parent=None, panel_name="mixer", widget_type="slider", existing_data=None,
                 engine=None, ui_config=None, midi_cc=None):
        ...
        self._loading = False
        # Gửi thử cần engine; dashboard truyền vào, hoặc lấy từ parent.
        self._engine = engine if engine is not None else getattr(parent, "engine", None)
        self._ui_config = ui_config   # None → đọc ui_config.json lúc cần
        self._midi_cc = midi_cc       # None → AppConfig.get_midi_cc()
```

và trước dòng `self._update_save_state()` cuối `__init__` thêm `self._refresh_cc_info()`.

(c) Khối CC trong `_build_fields` (ngay sau `self._section("MIDI")`) — thay

```python
        self.cc_input.valueChanged.connect(lambda _v: self._refresh_value_section())
        self._add_row("MIDI CC:", self.cc_input)
```

bằng

```python
        self.cc_input.valueChanged.connect(lambda _v: self._refresh_value_section())
        self.cc_input.valueChanged.connect(lambda _v: self._refresh_cc_info())
        self.test_btn = QPushButton("Gửi thử")
        self.test_btn.setToolTip("Gửi giá trị BẬT rồi TẮT trên CC này — dùng để MIDI Learn "
                                 "hoặc kiểm tra trong DAW mà chưa cần Lưu.")
        self.test_btn.clicked.connect(self._on_test_send)
        ccl = QHBoxLayout()
        cclbl = QLabel("MIDI CC:")
        cclbl.setFixedWidth(100)
        ccl.addWidget(cclbl)
        ccl.addWidget(self.cc_input, 1)
        ccl.addWidget(self.test_btn)
        self.vl.addLayout(ccl)

        # Hai nhãn đổi nội dung theo CC: luôn hiện + dành sẵn chiều cao (geometry).
        self.cc_note = QLabel()
        self.cc_note.setWordWrap(True)
        self.cc_note.setStyleSheet(f"color: {C['orange']}; font-size: 11px;")
        self.cc_note.ensurePolished()
        self.cc_note.setMinimumHeight(self.cc_note.fontMetrics().lineSpacing() * 2 + 4)
        self.vl.addWidget(self.cc_note)
        self.test_status = QLabel()
        self.test_status.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px;")
        self.test_status.ensurePolished()
        self.test_status.setMinimumHeight(self.test_status.fontMetrics().lineSpacing() + 2)
        self.vl.addWidget(self.test_status)
```

(d) Thêm các method (đặt sau `_update_save_state`):

```python
    # ── CC: cảnh báo trùng + gửi thử ────────────────────────
    def _current_cc(self):
        return self.cc_input.value() if self.cc_input.isEnabled() else -1

    def _cc_conflicts(self, cc):
        if cc < 0:
            return []
        app_config, _, _ = _config()
        if self._ui_config is None:
            try:
                from core.config import UiConfigManager
                self._ui_config = UiConfigManager.load_ui_config()
            except Exception:
                self._ui_config = {}
        if self._midi_cc is None:
            try:
                self._midi_cc = app_config.get_midi_cc() or {}
            except Exception:
                self._midi_cc = {}
        try:
            modes = app_config.get_mode_config() or {}
        except Exception:
            modes = {}
        return ui_layout.find_cc_conflicts(
            cc, self._ui_config, self._midi_cc,
            exclude_id=(self.existing_data or {}).get("id"), mode_config=modes)

    def _refresh_cc_info(self):
        cc = self._current_cc()
        self.test_btn.setEnabled(self._engine is not None and cc >= 0)
        hits = self._cc_conflicts(cc)
        self.cc_note.setText(f"⚠ CC {cc} đang dùng bởi: {', '.join(hits)}" if hits else "")

    def _test_values(self):
        """(bật, tắt) theo MIDI để gửi thử; None nếu form chưa hợp lệ."""
        if self.type_combo.currentData() == "slider":
            return 64, 0   # giữa dải rồi về mức thấp nhất
        spec = self._current_spec()
        if self._validation_error(spec):
            return None
        return so_values.midi_pair(spec)

    def _on_test_send(self):
        cc = self._current_cc()
        values = self._test_values()
        if self._engine is None or cc < 0:
            return
        if values is None:
            self.test_status.setText("Giá trị chưa hợp lệ — sửa phần Giá trị rồi gửi lại.")
            return
        on, off = int(values[0]), int(values[1])
        try:
            self._engine.send_midi(cc, on)
        except Exception as e:
            self.test_status.setText(f"Gửi lỗi: {e}")
            return
        self.test_status.setText(f"Đã gửi CC {cc} = {on}, sau đó {off}")
        QTimer.singleShot(300, lambda: self._send_quiet(cc, off))

    def _send_quiet(self, cc, value):
        try:
            self._engine.send_midi(cc, value)
        except Exception as e:
            self.test_status.setText(f"Gửi lỗi: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\ui\test_widget_builder_cc.py tests\ui\test_widget_builder_form.py tests\ui\test_widget_builder_so_values.py tests\ui\test_qt_warnings.py`
Expected: tất cả passed

- [ ] **Step 5: Commit**

```bash
git add ui/dialogs/widget_builder.py tests/ui/test_widget_builder_cc.py
git commit -m "feat(devmode): Widget Builder cảnh báo CC trùng và nút Gửi thử"
```

---

### Task 5: Hộp "Quản lý giao diện" — danh sách, ẩn/hiện, thứ tự, sửa/xoá, Lưu/Huỷ

**Files:**
- Create: `ui/dialogs/widget_manager.py`
- Test: `tests/ui/test_widget_manager.py`

**Interfaces:**
- Consumes: `core.ui_layout` (Task 1); `WidgetBuilderDialog(..., engine=, ui_config=, midi_cc=)` (Task 4) với `result_data`, `result_calibration`; `UiConfigManager.load_ui_config/save_ui_config`
- Produces: `WidgetManagerDialog(parent=None, panel_name="mixer", ui_config=None, engine=None, midi_cc=None)` với:
  - `working: dict` (bản sao ui_config), `calibrations: list[dict]`, `restored: bool`, `restored_backups: list[str]`
  - `lists: dict[str, QListWidget]`, `tabs: QTabWidget`, `footer: QHBoxLayout`
  - nút `up_btn, down_btn, edit_btn, delete_btn, add_btn, reset_btn, save_btn, cancel_btn`
  - `current_panel() -> str`, `select(panel, wid)`, `_sync_order(panel)`
  - Lưu thành công → `accept()`; Lưu lỗi → hộp ở lại.

Ghi chú thiết kế: Sửa/Xoá/↑/↓ áp lên **hàng đang chọn** (thanh nút dưới danh sách) thay vì nút trên từng hàng như phác thảo trong spec — giữ được kéo-thả gốc của `QListWidget` và test được; nhấp đúp hàng = Sửa.

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_widget_manager.py`:

```python
"""Hộp Quản lý giao diện (Dev Mode)."""
import copy
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core.config import UiConfigManager
from ui.dialogs.widget_manager import WidgetManagerDialog

YES = QMessageBox.Yes
NO = QMessageBox.No


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def layout():
    ui = copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG)
    ui["tools"].append({"id": "custom_1", "type": "button", "label": "Vang HT", "cc": 60})
    return ui


def _dlg(qtbot, layout, panel="tools"):
    dlg = WidgetManagerDialog(None, panel_name=panel, ui_config=layout, midi_cc={})
    qtbot.addWidget(dlg)
    return dlg


def _ids(dlg, panel):
    lst = dlg.lists[panel]
    return [lst.item(i).data(Qt.UserRole) for i in range(lst.count())]


def test_mo_dung_tab_va_khong_dong_vao_ban_goc(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout, "mode")
    assert dlg.current_panel() == "mode"
    assert _ids(dlg, "tools")[-1] == "custom_1"
    dlg.select("tools", "btn_rescan")
    dlg.down_btn.click()
    assert layout["tools"][1]["id"] == "btn_rescan"  # bản gốc không đổi


def test_len_xuong_doi_thu_tu(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "custom_1")
    dlg.up_btn.click()
    assert _ids(dlg, "tools")[-2] == "custom_1"
    assert [e["id"] for e in dlg.working["tools"]][-2] == "custom_1"
    assert dlg.lists["tools"].currentItem().data(Qt.UserRole) == "custom_1"


def test_keo_tha_dong_bo_thu_tu(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    lst = dlg.lists["tools"]
    item = lst.takeItem(lst.count() - 1)
    lst.insertItem(0, item)
    dlg._sync_order("tools")
    assert dlg.working["tools"][0]["id"] == "custom_1"


def test_bo_tick_la_an(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    item = dlg.lists["tools"].item(1)
    item.setCheckState(Qt.Unchecked)
    assert dlg.working["tools"][1]["hidden"] is True
    item.setCheckState(Qt.Checked)
    assert dlg.working["tools"][1]["hidden"] is False


def test_widget_an_hien_bo_tick(qapp, qtbot, layout):
    layout["mixer"][2]["hidden"] = True
    dlg = _dlg(qtbot, layout, "mixer")
    assert dlg.lists["mixer"].item(2).checkState() == Qt.Unchecked


def test_xoa_chi_cho_widget_tu_them(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "btn_rescan")
    assert not dlg.delete_btn.isEnabled()
    dlg.select("tools", "custom_1")
    assert dlg.delete_btn.isEnabled()
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=YES):
        dlg.delete_btn.click()
    assert "custom_1" not in _ids(dlg, "tools")


def test_xoa_hoi_khong_thi_giu(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "custom_1")
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=NO):
        dlg.delete_btn.click()
    assert "custom_1" in _ids(dlg, "tools")


def test_khoi_phuc_mac_dinh_panel(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=YES):
        dlg.reset_btn.click()
    assert "custom_1" not in _ids(dlg, "tools")
    assert len(_ids(dlg, "tools")) == len(UiConfigManager._DEFAULT_UI_CONFIG["tools"])


def _fake_builder(result, calibration=None):
    inst = MagicMock()
    inst.exec.return_value = QDialog.Accepted
    inst.result_data = result
    inst.result_calibration = calibration
    return MagicMock(return_value=inst)


def test_sua_ghi_vao_ban_sao_va_gom_calibration(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "btn_be")
    new = dict(dlg.working["tools"][4], label="Bè 2")
    fake = _fake_builder(new, {"toggle_invert": {"be": True}})
    with patch("ui.dialogs.widget_manager.WidgetBuilderDialog", fake):
        dlg.edit_btn.click()
    kwargs = fake.call_args.kwargs
    assert kwargs["existing_data"]["id"] == "btn_be"
    assert kwargs["ui_config"] is dlg.working
    assert dlg.working["tools"][4]["label"] == "Bè 2"
    assert dlg.calibrations == [{"toggle_invert": {"be": True}}]


def test_them_noi_cuoi_va_chon(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout, "mixer")
    fake = _fake_builder({"id": "custom_9", "type": "slider", "label": "Kênh", "cc": 70})
    with patch("ui.dialogs.widget_manager.WidgetBuilderDialog", fake):
        dlg.add_btn.click()
    assert fake.call_args.kwargs["widget_type"] == "slider"
    assert _ids(dlg, "mixer")[-1] == "custom_9"
    assert dlg.lists["mixer"].currentItem().data(Qt.UserRole) == "custom_9"


def test_luu_ghi_file_va_accept(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.select("tools", "custom_1")
    dlg.up_btn.click()
    with patch("ui.dialogs.widget_manager.UiConfigManager.save_ui_config",
               return_value=True) as save:
        dlg.save_btn.click()
    save.assert_called_once()
    assert [e["id"] for e in save.call_args.args[0]["tools"]][-2] == "custom_1"
    assert dlg.result() == QDialog.Accepted


def test_luu_loi_thi_o_lai(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    with patch("ui.dialogs.widget_manager.UiConfigManager.save_ui_config", return_value=False), \
         patch("ui.dialogs.widget_manager.QMessageBox.warning") as warn:
        dlg.save_btn.click()
    warn.assert_called_once()
    assert dlg.result() != QDialog.Accepted


def test_huy_khong_ghi_file(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    with patch("ui.dialogs.widget_manager.UiConfigManager.save_ui_config") as save:
        dlg.cancel_btn.click()  # chưa đổi gì → đóng luôn, không hỏi
    save.assert_not_called()
    assert dlg.result() == QDialog.Rejected


def test_dong_khi_con_thay_doi_hoi_truoc(qapp, qtbot, layout):
    dlg = _dlg(qtbot, layout)
    dlg.show()
    dlg.select("tools", "custom_1")
    dlg.up_btn.click()
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=NO) as ask:
        dlg.close()
    ask.assert_called_once()
    assert dlg.isVisible()
    with patch("ui.dialogs.widget_manager.QMessageBox.question", return_value=YES):
        dlg.close()
    assert not dlg.isVisible()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\ui\test_widget_manager.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui.dialogs.widget_manager'`

- [ ] **Step 3: Write the implementation**

`ui/dialogs/widget_manager.py`:

```python
"""Hộp "Quản lý giao diện" của Dev Mode.

Hiện/ẩn, đổi thứ tự (kéo-thả hoặc ↑/↓), sửa, xoá (chỉ widget tự thêm) và
khôi phục mặc định từng panel. Mọi thao tác chạy trên BẢN SAO ui_config —
chỉ ghi ui_config.json khi bấm Lưu; Huỷ/đóng thì bỏ hết. Calibration (Bypass,
mode_config) do Widget Builder trả về được gom vào `calibrations` để
MainDashboard áp sau khi Lưu.
"""
import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
)

from core import ui_layout
from core.config import UiConfigManager
from ui import responsive as rp
from ui.design_tokens import C, FONT
from ui.dialogs.widget_builder import WidgetBuilderDialog

ID_ROLE = Qt.UserRole
_PANELS = list(ui_layout.PANEL_TITLES)


class WidgetManagerDialog(QDialog):
    def __init__(self, parent=None, panel_name="mixer", ui_config=None, engine=None, midi_cc=None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý giao diện")
        rp.set_min_width(self, 460)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")

        source = ui_config if ui_config is not None else UiConfigManager.load_ui_config()
        self.working = copy.deepcopy(source)
        self.calibrations = []
        self.restored = False
        self.restored_backups = []
        self._dirty = False
        self._engine = engine
        self._midi_cc = midi_cc
        self._populating = False

        vl = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.lists = {}
        for panel, title in ui_layout.PANEL_TITLES.items():
            lst = QListWidget()
            lst.setDragDropMode(QAbstractItemView.InternalMove)
            lst.setDefaultDropAction(Qt.MoveAction)
            lst.itemChanged.connect(lambda item, p=panel: self._on_item_changed(p, item))
            lst.model().rowsMoved.connect(lambda *_a, p=panel: self._sync_order(p))
            lst.currentRowChanged.connect(lambda _r: self._refresh_buttons())
            lst.itemDoubleClicked.connect(lambda _i: self._edit_selected())
            self.lists[panel] = lst
            self.tabs.addTab(lst, title)
            self._populate(panel)
        vl.addWidget(self.tabs)

        hint = QLabel("Tích để hiện, bỏ tích để ẩn · kéo hoặc ↑/↓ để đổi thứ tự · nhấp đúp để sửa")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px;")
        vl.addWidget(hint)

        row = QHBoxLayout()
        self.up_btn = QPushButton("↑")
        self.down_btn = QPushButton("↓")
        self.edit_btn = QPushButton("Sửa")
        self.delete_btn = QPushButton("Xoá")
        self.add_btn = QPushButton("+ Thêm")
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))
        self.down_btn.clicked.connect(lambda: self._move_selected(1))
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.add_btn.clicked.connect(self._add)
        for b in (self.up_btn, self.down_btn, self.edit_btn, self.delete_btn):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.add_btn)
        vl.addLayout(row)

        self.reset_btn = QPushButton("Khôi phục mặc định panel này")
        self.reset_btn.clicked.connect(self._reset_panel)
        vl.addWidget(self.reset_btn)

        self.footer = QHBoxLayout()
        self.footer.addStretch()
        self.save_btn = QPushButton("Lưu")
        self.save_btn.setStyleSheet(f"background-color: {C['green']}; padding: 5px;")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("Huỷ")
        self.cancel_btn.clicked.connect(self.reject)
        self.footer.addWidget(self.save_btn)
        self.footer.addWidget(self.cancel_btn)
        vl.addLayout(self.footer)

        self.tabs.currentChanged.connect(lambda _i: self._refresh_buttons())
        self.tabs.setCurrentIndex(_PANELS.index(panel_name) if panel_name in _PANELS else 0)
        self._refresh_buttons()

    # ── Truy cập ─────────────────────────────────────────────
    def current_panel(self):
        return _PANELS[self.tabs.currentIndex()]

    def _entries(self, panel):
        entries = self.working.get(panel)
        if not isinstance(entries, list):
            entries = self.working[panel] = []
        return entries

    def _find(self, panel, wid):
        entries = self._entries(panel)
        i = ui_layout.index_of(entries, wid)
        return entries[i] if i >= 0 else None

    def _selected_id(self):
        item = self.lists[self.current_panel()].currentItem()
        return item.data(ID_ROLE) if item else None

    def select(self, panel, wid):
        self.tabs.setCurrentIndex(_PANELS.index(panel))
        lst = self.lists[panel]
        for i in range(lst.count()):
            if lst.item(i).data(ID_ROLE) == wid:
                lst.setCurrentRow(i)
                return

    # ── Vẽ danh sách ─────────────────────────────────────────
    def _row_text(self, panel, entry):
        tag = "" if ui_layout.is_custom(panel, entry) else "có sẵn"
        cc = entry.get("cc")
        if isinstance(cc, int) and not isinstance(cc, bool):
            tag = f"{tag} · CC {cc}" if tag else f"CC {cc}"
        elif not tag:
            tag = "chưa gán CC"
        return f"{entry.get('label') or entry.get('id')}   —   {tag}"

    def _style_item(self, item, hidden):
        item.setForeground(QColor(C["text_muted"] if hidden else C["text"]))

    def _populate(self, panel, select_id=None):
        lst = self.lists[panel]
        self._populating = True
        try:
            lst.clear()
            for e in self._entries(panel):
                if not isinstance(e, dict):
                    continue
                item = QListWidgetItem(self._row_text(panel, e))
                item.setData(ID_ROLE, e.get("id"))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                hidden = bool(e.get("hidden"))
                item.setCheckState(Qt.Unchecked if hidden else Qt.Checked)
                self._style_item(item, hidden)
                lst.addItem(item)
        finally:
            self._populating = False
        if select_id is not None:
            self.select(panel, select_id)

    def _refresh_buttons(self):
        panel = self.current_panel()
        wid = self._selected_id()
        entry = self._find(panel, wid) if wid is not None else None
        for b in (self.up_btn, self.down_btn, self.edit_btn):
            b.setEnabled(entry is not None)
        self.delete_btn.setEnabled(entry is not None and ui_layout.is_custom(panel, entry))

    # ── Thao tác ─────────────────────────────────────────────
    def _on_item_changed(self, panel, item):
        if self._populating:
            return
        wid = item.data(ID_ROLE)
        hidden = item.checkState() != Qt.Checked
        entry = self._find(panel, wid)
        if entry is None or bool(entry.get("hidden")) == hidden:
            return
        ui_layout.set_hidden(self._entries(panel), wid, hidden)
        self._dirty = True
        # Đổi màu chữ cũng phát itemChanged — chặn vòng lặp.
        self._populating = True
        try:
            self._style_item(item, hidden)
        finally:
            self._populating = False

    def _sync_order(self, panel):
        lst = self.lists[panel]
        ids = [lst.item(i).data(ID_ROLE) for i in range(lst.count())]
        self.working[panel] = ui_layout.reorder(self._entries(panel), ids)
        self._dirty = True

    def _move_selected(self, delta):
        panel = self.current_panel()
        wid = self._selected_id()
        if wid is None:
            return
        entries = self._entries(panel)
        idx = ui_layout.index_of(entries, wid)
        if ui_layout.move(entries, idx, delta) != idx:
            self._dirty = True
        self._populate(panel, wid)

    def _builder(self, panel, widget_type, existing=None):
        return WidgetBuilderDialog(self, panel_name=panel, widget_type=widget_type,
                                   existing_data=existing, engine=self._engine,
                                   ui_config=self.working, midi_cc=self._midi_cc)

    def _take_result(self, dlg):
        if dlg.exec() != QDialog.Accepted or not dlg.result_data:
            return None
        if dlg.result_calibration:
            self.calibrations.append(dlg.result_calibration)
        self._dirty = True
        return dlg.result_data

    def _edit_selected(self):
        panel = self.current_panel()
        wid = self._selected_id()
        entry = self._find(panel, wid) if wid is not None else None
        if entry is None:
            return
        data = self._take_result(self._builder(panel, entry.get("type", "button"), entry))
        if data is None:
            return
        entries = self._entries(panel)
        entries[ui_layout.index_of(entries, wid)] = data
        self._populate(panel, wid)

    def _add(self):
        panel = self.current_panel()
        data = self._take_result(self._builder(panel, "slider" if panel == "mixer" else "button"))
        if data is None:
            return
        self._entries(panel).append(data)
        self._populate(panel, data.get("id"))

    def _delete_selected(self):
        panel = self.current_panel()
        wid = self._selected_id()
        entry = self._find(panel, wid) if wid is not None else None
        if entry is None or not ui_layout.is_custom(panel, entry):
            return
        answer = QMessageBox.question(
            self, "Xoá widget",
            f"Xoá “{entry.get('label') or wid}”? Sau khi Lưu sẽ không hoàn tác được.")
        if answer != QMessageBox.Yes:
            return
        ui_layout.delete_custom(panel, self._entries(panel), wid)
        self._dirty = True
        self._populate(panel)
        self._refresh_buttons()

    def _reset_panel(self):
        panel = self.current_panel()
        title = ui_layout.PANEL_TITLES[panel]
        answer = QMessageBox.question(
            self, "Khôi phục mặc định",
            f"Đưa panel {title} về mặc định? Widget tự thêm của panel này sẽ bị xoá.")
        if answer != QMessageBox.Yes:
            return
        ui_layout.reset_panel(self.working, panel)
        self._dirty = True
        self._populate(panel)
        self._refresh_buttons()

    # ── Lưu / đóng ───────────────────────────────────────────
    def _on_save(self):
        if not UiConfigManager.save_ui_config(self.working):
            QMessageBox.warning(self, "Quản lý giao diện",
                                "Không lưu được ui_config.json — thay đổi vẫn còn trong hộp này.")
            return
        self._dirty = False
        self.accept()

    def reject(self):
        # Nút Huỷ, phím Esc và nút X (QDialog.closeEvent gọi reject() và tự
        # bỏ qua sự kiện đóng nếu hộp vẫn hiện) đều đi qua đây.
        if self._dirty and not self.restored:
            answer = QMessageBox.question(self, "Bỏ thay đổi", "Bỏ các thay đổi chưa lưu?")
            if answer != QMessageBox.Yes:
                return
        super().reject()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\ui\test_widget_manager.py`
Expected: 14 passed

- [ ] **Step 5: Commit**

```bash
git add ui/dialogs/widget_manager.py tests/ui/test_widget_manager.py
git commit -m "feat(devmode): hộp Quản lý giao diện — hiện lại widget ẩn, đổi thứ tự, xoá, khôi phục mặc định"
```

---

### Task 6: Xuất/Nhập file trong hộp Quản lý

**Files:**
- Modify: `ui/dialogs/widget_manager.py` (import, nút footer, `_export`, `_import`)
- Test: `tests/ui/test_widget_manager_backup.py`

**Interfaces:**
- Consumes: `core.devmode_backup` (Task 2): `default_filename`, `export_backup`, `read_backup`, `summarize`, `restore_backup`, `BackupError`
- Produces: `export_btn`, `import_btn`; sau khi nhập thành công: `restored = True`, `restored_backups = [...]`, dialog `accept()` (dashboard dựa vào `restored`, KHÔNG lưu `working`).

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_widget_manager_backup.py`:

```python
"""Xuất/Nhập file từ hộp Quản lý giao diện."""
import copy
import pytest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from core import devmode_backup
from core.config import UiConfigManager
from ui.dialogs.widget_manager import WidgetManagerDialog

M = "ui.dialogs.widget_manager"


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def dlg(qapp, qtbot):
    d = WidgetManagerDialog(None, panel_name="tools",
                            ui_config=copy.deepcopy(UiConfigManager._DEFAULT_UI_CONFIG))
    qtbot.addWidget(d)
    return d


def test_xuat_file(dlg):
    with patch(f"{M}.QFileDialog.getSaveFileName", return_value=("D:/x.json", "")) as ask, \
         patch(f"{M}.devmode_backup.export_backup") as export, \
         patch(f"{M}.QMessageBox.information"):
        dlg.export_btn.click()
    assert ask.call_args.args[2].startswith("quangluu-giaodien-")
    export.assert_called_once_with("D:/x.json")


def test_xuat_khi_chua_luu_thi_nhac(dlg):
    dlg.select("tools", "btn_be")
    dlg.up_btn.click()
    with patch(f"{M}.QFileDialog.getSaveFileName") as ask, \
         patch(f"{M}.QMessageBox.information") as info:
        dlg.export_btn.click()
    ask.assert_not_called()
    info.assert_called_once()


def test_nhap_file_xac_nhan_roi_khoi_phuc(dlg):
    backup = {"ui_config": {"tools": []}, "calibration_overrides": {}}
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", return_value=backup), \
         patch(f"{M}.devmode_backup.summarize", return_value="Tools: 0 widget"), \
         patch(f"{M}.devmode_backup.restore_backup", return_value=["a.bak"]) as restore, \
         patch(f"{M}.QMessageBox.question", return_value=QMessageBox.Yes) as ask:
        dlg.import_btn.click()
    assert "Tools: 0 widget" in ask.call_args.args[2]
    assert "sao lưu tự động" in ask.call_args.args[2]
    restore.assert_called_once_with(backup)
    assert dlg.restored and dlg.restored_backups == ["a.bak"]
    assert dlg.result() == QDialog.Accepted


def test_nhap_file_huy_khong_ghi(dlg):
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", return_value={"ui_config": {}}), \
         patch(f"{M}.devmode_backup.summarize", return_value=""), \
         patch(f"{M}.devmode_backup.restore_backup") as restore, \
         patch(f"{M}.QMessageBox.question", return_value=QMessageBox.No):
        dlg.import_btn.click()
    restore.assert_not_called()
    assert not dlg.restored


def test_nhap_file_sai_bao_loi(dlg):
    err = devmode_backup.BackupError("File này không phải bản sao lưu")
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", side_effect=err), \
         patch(f"{M}.devmode_backup.restore_backup") as restore, \
         patch(f"{M}.QMessageBox.warning") as warn:
        dlg.import_btn.click()
    assert "không phải bản sao lưu" in warn.call_args.args[2]
    restore.assert_not_called()


def test_nhap_khi_con_thay_doi_bao_se_bo(dlg):
    dlg.select("tools", "btn_be")
    dlg.up_btn.click()
    with patch(f"{M}.QFileDialog.getOpenFileName", return_value=("D:/x.json", "")), \
         patch(f"{M}.devmode_backup.read_backup", return_value={"ui_config": {}}), \
         patch(f"{M}.devmode_backup.summarize", return_value=""), \
         patch(f"{M}.devmode_backup.restore_backup", return_value=[]), \
         patch(f"{M}.QMessageBox.question", return_value=QMessageBox.Yes) as ask:
        dlg.import_btn.click()
    assert "chưa lưu" in ask.call_args.args[2]
    assert ask.call_count == 1  # accept() sau khi khôi phục không hỏi thêm
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\ui\test_widget_manager_backup.py`
Expected: FAIL — `AttributeError: 'WidgetManagerDialog' object has no attribute 'export_btn'`

- [ ] **Step 3: Implement**

(a) Import trong `ui/dialogs/widget_manager.py`: thêm `QFileDialog` vào khối import `PySide6.QtWidgets`, và đổi `from core import ui_layout` thành `from core import devmode_backup, ui_layout`.

(b) Trong `__init__`, ngay sau `self.footer = QHBoxLayout()` và TRƯỚC `self.footer.addStretch()`, thêm:

```python
        self.export_btn = QPushButton("Xuất file")
        self.export_btn.setToolTip("Lưu giao diện + cân chỉnh MIDI của máy này ra một file .json")
        self.export_btn.clicked.connect(self._export)
        self.import_btn = QPushButton("Nhập file")
        self.import_btn.setToolTip("Nạp giao diện + cân chỉnh MIDI từ file đã xuất")
        self.import_btn.clicked.connect(self._import)
        self.footer.addWidget(self.export_btn)
        self.footer.addWidget(self.import_btn)
```

(c) Thêm hai method (trước phần `# ── Lưu / đóng`):

```python
    # ── Xuất / Nhập ──────────────────────────────────────────
    def _export(self):
        if self._dirty:
            QMessageBox.information(self, "Xuất file",
                                    "Có thay đổi chưa lưu — bấm Lưu trước rồi mới xuất.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất cấu hình giao diện", devmode_backup.default_filename(),
            "Cấu hình (*.json)")
        if not path:
            return
        try:
            devmode_backup.export_backup(path)
        except Exception as e:
            QMessageBox.warning(self, "Xuất file", f"Không xuất được: {e}")
            return
        QMessageBox.information(self, "Xuất file", f"Đã xuất:\n{path}")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Nhập cấu hình giao diện", "", "Cấu hình (*.json)")
        if not path:
            return
        try:
            backup = devmode_backup.read_backup(path)
        except devmode_backup.BackupError as e:
            QMessageBox.warning(self, "Nhập file", str(e))
            return
        text = (f"{devmode_backup.summarize(backup)}\n\n"
                "Cấu hình hiện tại sẽ được sao lưu tự động trước khi ghi đè.")
        if self._dirty:
            text += "\nCác thay đổi chưa lưu trong hộp này sẽ bị bỏ."
        if QMessageBox.question(self, "Nhập cấu hình", text) != QMessageBox.Yes:
            return
        try:
            self.restored_backups = devmode_backup.restore_backup(backup)
        except devmode_backup.BackupError as e:
            QMessageBox.warning(self, "Nhập file", str(e))
            return
        self.restored = True
        self.accept()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\ui\test_widget_manager_backup.py tests\ui\test_widget_manager.py`
Expected: tất cả passed

- [ ] **Step 5: Commit**

```bash
git add ui/dialogs/widget_manager.py tests/ui/test_widget_manager_backup.py
git commit -m "feat(devmode): Xuất/Nhập file cấu hình trong hộp Quản lý giao diện"
```

---

### Task 7: Nối vào dashboard + nút "⚙ Quản lý" trên 3 panel

**Files:**
- Create: `ui/panels/_dev_buttons.py`
- Modify: `ui/panels/mixer.py:229-237`, `ui/panels/tools.py:264-271`, `ui/panels/mode.py:109-116` (khối `# --- Dev Mode Add Button ---`)
- Modify: `frontend_qt.py` — `_on_add_widget`, `_on_edit_widget`, `_apply_widget_calibration` (khoảng dòng 603-660); thêm `_resend_calibrated_states`, `_on_manage_widgets`, `_after_backup_restore`
- Test: `tests/ui/test_dev_mode_manage.py`

**Interfaces:**
- Consumes: `WidgetManagerDialog` (Task 5/6): `exec()`, `restored`, `calibrations`; `WidgetBuilderDialog(..., engine=, ui_config=, midi_cc=)` (Task 4)
- Produces:
  - `build_dev_row(dashboard, panel_name: str, add_text: str, widget_type: str, extra_style: str = "") -> QHBoxLayout`
  - `MainDashboard._on_manage_widgets(panel_name: str) -> None`
  - `MainDashboard._resend_calibrated_states(modes, toggles) -> None` (iterables tên mode / key toggle)
  - `MainDashboard._after_backup_restore() -> None`

- [ ] **Step 1: Write the failing tests**

`tests/ui/test_dev_mode_manage.py`:

```python
"""Nút ⚙ Quản lý trên panel + luồng lưu/nhập ở MainDashboard."""
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QWidget

from ui.panels._dev_buttons import build_dev_row


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_hang_nut_dev_goi_dung_ham(qapp, qtbot):
    dash = MagicMock()
    host = QWidget()
    qtbot.addWidget(host)
    host.setLayout(build_dev_row(dash, "tools", "+ Thêm Nút", "button"))
    buttons = {b.text(): b for b in host.findChildren(QPushButton)}
    assert set(buttons) == {"+ Thêm Nút", "⚙ Quản lý"}
    buttons["+ Thêm Nút"].click()
    dash._on_add_widget.assert_called_once_with("tools", "button")
    buttons["⚙ Quản lý"].click()
    dash._on_manage_widgets.assert_called_once_with("tools")


# ── MainDashboard ──────────────────────────────────────────────
from frontend_qt import MainDashboard  # noqa: E402


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


@pytest.fixture
def dashboard(qapp, mock_engine, qtbot):
    base = {"studio_one_path": "", "auto_close_studio_one": False}
    with patch("frontend_qt.backend.SongManager.load_songs", return_value=[]), \
         patch("frontend_qt.backend.ActivationManager.is_activated", return_value=True), \
         patch("frontend_qt.backend.ActivationManager.needs_activation", return_value=False), \
         patch("frontend_qt.QTimer.start"):
        d = MainDashboard(base)
        qtbot.addWidget(d)
        if d._so_ready_watcher is not None:
            d._so_ready_watcher.stop()
        yield d


def _fake_manager(result, restored=False, calibrations=()):
    inst = MagicMock()
    inst.exec.return_value = result
    inst.restored = restored
    inst.calibrations = list(calibrations)
    return MagicMock(return_value=inst)


def test_dev_mode_co_nut_quan_ly_tren_3_panel(dashboard):
    dashboard.is_dev_mode = True
    dashboard.refresh_ui()
    manage = [b for b in dashboard.findChildren(QPushButton) if b.text() == "⚙ Quản lý"]
    assert len(manage) == 3


def test_luu_trong_hop_quan_ly_ap_calibration_va_ve_lai(dashboard):
    fake = _fake_manager(QDialog.Accepted, calibrations=[{"toggle_invert": {"be": True}}])
    with patch("ui.dialogs.widget_manager.WidgetManagerDialog", fake), \
         patch.object(dashboard, "_apply_widget_calibration") as apply_cal, \
         patch.object(dashboard, "refresh_ui") as refresh:
        dashboard._on_manage_widgets("tools")
    kwargs = fake.call_args.kwargs
    assert kwargs["panel_name"] == "tools"
    assert kwargs["engine"] is dashboard.engine
    apply_cal.assert_called_once_with({"toggle_invert": {"be": True}})
    refresh.assert_called_once()


def test_huy_hop_quan_ly_khong_lam_gi(dashboard):
    fake = _fake_manager(QDialog.Rejected)
    with patch("ui.dialogs.widget_manager.WidgetManagerDialog", fake), \
         patch.object(dashboard, "refresh_ui") as refresh:
        dashboard._on_manage_widgets("mixer")
    refresh.assert_not_called()


def test_nhap_file_xong_nap_lai_va_gui_lai_trang_thai(dashboard):
    fake = _fake_manager(QDialog.Accepted, restored=True)
    with patch("ui.dialogs.widget_manager.WidgetManagerDialog", fake), \
         patch.object(dashboard, "_apply_widget_calibration") as apply_cal, \
         patch.object(dashboard, "refresh_ui") as refresh, \
         patch.object(dashboard, "_resend_calibrated_states") as resend:
        dashboard._on_manage_widgets("mode")
    apply_cal.assert_not_called()  # file nhập đã ghi calibration — không ghi lại
    refresh.assert_called_once()
    modes, toggles = resend.call_args.args
    assert set(toggles) == {"tone_auto", "fix_meo", "be", "tat_on"}
    assert set(modes) == set(dashboard.mode_states)


def test_them_widget_truyen_engine_cho_builder(dashboard):
    inst = MagicMock()
    inst.exec.return_value = QDialog.Rejected
    fake = MagicMock(return_value=inst)
    with patch("ui.dialogs.widget_builder.WidgetBuilderDialog", fake):
        dashboard._on_add_widget("tools", "button")
    kwargs = fake.call_args.kwargs
    assert kwargs["engine"] is dashboard.engine
    assert kwargs["midi_cc"] is dashboard.MIDI_CC
    assert "tools" in kwargs["ui_config"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTEST tests\ui\test_dev_mode_manage.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'ui.panels._dev_buttons'`

- [ ] **Step 3: Implement**

(a) `ui/panels/_dev_buttons.py`:

```python
"""Hàng nút Dev Mode cuối mỗi panel: "+ Thêm…" và "⚙ Quản lý"."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton

from ui.design_tokens import C


def build_dev_row(dashboard, panel_name, add_text, widget_type, extra_style=""):
    style = (f"background-color: transparent; border: 1px dashed {C['teal']};"
             f" color: {C['teal']};{extra_style}")
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)

    add_btn = QPushButton(add_text)
    add_btn.setStyleSheet(style)
    add_btn.setCursor(Qt.PointingHandCursor)
    add_btn.clicked.connect(lambda: dashboard._on_add_widget(panel_name, widget_type))

    manage_btn = QPushButton("⚙ Quản lý")
    manage_btn.setStyleSheet(style)
    manage_btn.setCursor(Qt.PointingHandCursor)
    manage_btn.setToolTip("Hiện lại widget đã ẩn, đổi thứ tự, xoá, xuất/nhập cấu hình")
    manage_btn.clicked.connect(lambda: dashboard._on_manage_widgets(panel_name))

    row.addWidget(add_btn, 1)
    row.addWidget(manage_btn)
    return row
```

(b) `ui/panels/mixer.py` — thay khối

```python
    # --- Dev Mode Add Button ---
    if getattr(dashboard, "is_dev_mode", False):
        # KHÔNG import Qt cục bộ ở đây — sẽ shadow import module-level
        # và gây UnboundLocalError ở block context-menu phía trên.
        from PySide6.QtWidgets import QPushButton
        add_btn = QPushButton("+ Thêm")
        add_btn.setStyleSheet(f"background-color: transparent; border: 1px dashed {C['teal']}; color: {C['teal']};")
        add_btn.setCursor(Qt.PointingHandCursor)
        add_btn.clicked.connect(lambda: dashboard._on_add_widget("mixer", "slider"))
        vl.addWidget(add_btn)
```

bằng

```python
    # --- Dev Mode: + Thêm / ⚙ Quản lý ---
    if getattr(dashboard, "is_dev_mode", False):
        # KHÔNG import Qt cục bộ ở đây — sẽ shadow import module-level
        # và gây UnboundLocalError ở block context-menu phía trên.
        from ui.panels._dev_buttons import build_dev_row
        vl.addLayout(build_dev_row(dashboard, "mixer", "+ Thêm", "slider"))
```

(c) `ui/panels/tools.py` — thay khối `# --- Dev Mode Add Button ---` (tạo `add_btn` "+ Thêm Nút" rồi `panel.body_layout.addWidget(add_btn)`) bằng

```python
    # --- Dev Mode: + Thêm Nút / ⚙ Quản lý ---
    if getattr(dashboard, "is_dev_mode", False):
        from ui.panels._dev_buttons import build_dev_row
        panel.body_layout.addLayout(build_dev_row(dashboard, "tools", "+ Thêm Nút", "button"))
```

(d) `ui/panels/mode.py` — thay khối `# --- Dev Mode Add Button ---` (tạo `add_btn` "+ Thêm Mode" rồi `vl.addWidget(add_btn)`) bằng

```python
    # --- Dev Mode: + Thêm Mode / ⚙ Quản lý ---
    if getattr(dashboard, "is_dev_mode", False):
        from ui.panels._dev_buttons import build_dev_row
        vl.addLayout(build_dev_row(dashboard, "mode", "+ Thêm Mode", "button", " margin-top: 5px;"))
```

(e) `frontend_qt.py` — trong `_on_add_widget` thay dòng tạo dialog bằng:

```python
        dialog = WidgetBuilderDialog(self, panel_name=panel_name, widget_type=widget_type,
                                     **self._builder_context())
```

trong `_on_edit_widget`:

```python
        dialog = WidgetBuilderDialog(self, panel_name=panel_name,
                                     widget_type=widget_data.get("type", "slider"),
                                     existing_data=widget_data, **self._builder_context())
```

và thêm ngay trước `_on_add_widget`:

```python
    def _builder_context(self):
        """Tham số chung cho Widget Builder: Gửi thử + cảnh báo CC trùng."""
        return {"engine": self.engine, "midi_cc": self.MIDI_CC,
                "ui_config": backend.UiConfigManager.load_ui_config()}

    def _on_manage_widgets(self, panel_name):
        from ui.dialogs.widget_manager import WidgetManagerDialog
        dialog = WidgetManagerDialog(self, panel_name=panel_name, engine=self.engine,
                                     midi_cc=self.MIDI_CC)
        result = dialog.exec()
        if dialog.restored:
            self._after_backup_restore()
            return
        if result != QDialog.Accepted:
            return
        # Hộp đã tự ghi ui_config.json khi Lưu; còn calibration thì áp ở đây.
        for calibration in dialog.calibrations:
            self._apply_widget_calibration(calibration)
        self.refresh_ui()

    def _after_backup_restore(self):
        """Vừa nhập file cấu hình: nạp lại config, vẽ lại, bắn lại trạng thái
        mode/toggle theo cân chỉnh mới (như _apply_widget_calibration)."""
        backend.AppConfig.reload()
        self.refresh_ui()
        self._resend_calibrated_states(list(self.mode_states),
                                       ("tone_auto", "fix_meo", "be", "tat_on"))
        self._show_message("Đã nhập cấu hình giao diện")
```

(f) `frontend_qt.py` — tách phần gửi lại trong `_apply_widget_calibration`. Thay toàn bộ đoạn từ `for mode in calibration.get("mode_config", {}):` tới hết method (dòng `self.engine.send_midi(int(MIDI_CC.get(key)), val)`) bằng:

```python
        self._resend_calibrated_states(calibration.get("mode_config", {}),
                                       calibration.get("toggle_invert", {}))

    def _resend_calibrated_states(self, modes, toggles):
        """Bắn lại trạng thái hiện tại của các mode / nút Bypass vừa đổi cân chỉnh —
        không thì DAW giữ giá trị theo chiều cũ, đèn trên app ngược cho tới lần bấm sau."""
        for mode in modes:
            self._set_mode(mode, self.mode_states.get(mode, False))

        states = {
            "tone_auto": ("tune_state", True),
            "fix_meo": ("fix_meo_state", False),
            "be": ("be_state", False),
            "tat_on": ("tat_on_state", False),
        }
        for key in toggles:
            if key not in states:
                continue
            attr, default = states[key]
            on_value = 127
            if key == "fix_meo":
                mode_map = backend.AppConfig.get_mode_midi_map()
                on_value = int(mode_map.get("Fix Méo", 127)) if isinstance(mode_map, dict) else 127
            val = self._toggle_value(key, getattr(self, attr, default), on_value=on_value)
            self.engine.send_midi(int(MIDI_CC.get(key)), val)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTEST tests\ui\test_dev_mode_manage.py tests\ui\test_pin_and_widget_calibration.py tests\ui\test_tools_panel.py`
Expected: tất cả passed (test calibration cũ xác nhận refactor không đổi hành vi)

- [ ] **Step 5: Commit**

```bash
git add ui/panels/_dev_buttons.py ui/panels/mixer.py ui/panels/tools.py ui/panels/mode.py frontend_qt.py tests/ui/test_dev_mode_manage.py
git commit -m "feat(devmode): nút ⚙ Quản lý trên 3 panel, áp calibration/nhập file từ dashboard"
```

---

### Task 8: Tài liệu + chạy toàn bộ test liên quan

**Files:**
- Modify: `docs/DEV_MODE_GUIDE.md`

**Interfaces:**
- Consumes: hành vi của Task 1–7.
- Produces: tài liệu cập nhật.

- [ ] **Step 1: Cập nhật `docs/DEV_MODE_GUIDE.md`**

- Dòng "Ngày viết": thêm `· cập nhật 2026-10-09 (hộp Quản lý giao diện, Xuất/Nhập, Gửi thử)`.
- Mục 1, bảng panel: cột "Thêm gì" thêm **`⚙ Quản lý`** cạnh `+ Thêm…` cho cả 3 panel.
- Mục 2: thay bảng "Trường chung" bằng bố cục mới — **Loại** (Thanh trượt / Nút; chỉ hiện khi thêm ở Mixer), nhóm **Hiển thị** (Tên, Màu sắc + hàng ô màu nhanh, Icon cho thanh trượt), nhóm **MIDI** (MIDI CC; dòng cảnh báo vàng "⚠ CC n đang dùng bởi: …" — chỉ cảnh báo, vẫn Lưu được; nút **Gửi thử** gửi BẬT rồi TẮT sau ~0,3 s, thanh trượt gửi 64 rồi 0, dùng để MIDI Learn mà chưa cần Lưu). Thêm câu: nút **Lưu** bị khoá kèm lý do màu đỏ khi tên trống, màu sai, Min ≥ Max, khoảng số Từ = Đến, danh sách < 2 mục.
- Mục 3: thêm tiểu mục **Hộp Quản lý giao diện** — tab Mixer/Tools/Mode; tích = hiện, bỏ tích = ẩn; kéo hoặc ↑/↓ đổi thứ tự; nhấp đúp hoặc **Sửa**; **Xoá** chỉ với widget tự thêm (nút có sẵn chỉ ẩn được); **Khôi phục mặc định panel này**; mọi thay đổi chỉ ghi khi bấm **Lưu**, **Huỷ**/đóng sẽ hỏi nếu còn thay đổi. Xoá dòng "Hiện lại widget đã ẩn: chưa có UI — mở ui_config.json…".
- Thêm mục mới **Xuất / Nhập cấu hình** (sau mục 4): file `quangluu-giaodien-YYYYMMDD-HHMM.json` gồm `ui_config` + nguyên `calibration_overrides.json`; Nhập hiện tóm tắt và hỏi trước; bản cũ tự chép vào `<thư mục ui_config.json>/backups/*.bak`; file hỏng / bản app mới hơn thì báo lỗi, không ghi gì.
- Mục 5 (quy trình setup): bước 5 thay "backup file ui_config.json của khách (copy ra ngoài)" bằng "⚙ Quản lý → **Xuất file**, cất file .json để cài lại nhanh (máy mới: ⚙ Quản lý → **Nhập file**)"; bước 4 thêm "dùng **Gửi thử** trong Widget Builder".
- Mục 6: xoá hạn chế số 2 (chưa có UI hiện lại widget ẩn), đánh số lại.
- Dòng "Các file liên quan" cuối: thêm `ui/dialogs/widget_manager.py`, `ui/panels/_dev_buttons.py`, `core/ui_layout.py`, `core/devmode_backup.py`.

- [ ] **Step 2: Chạy toàn bộ test Dev Mode + lân cận**

Run: `PYTEST tests\core\test_ui_layout.py tests\core\test_devmode_backup.py tests\core\test_config.py tests\ui\test_widget_builder_form.py tests\ui\test_widget_builder_cc.py tests\ui\test_widget_builder_so_values.py tests\ui\test_widget_manager.py tests\ui\test_widget_manager_backup.py tests\ui\test_dev_mode_manage.py tests\ui\test_pin_and_widget_calibration.py tests\ui\test_tools_panel.py tests\ui\test_qt_warnings.py tests\ui\test_main_window_logic.py`
Expected: tất cả passed. (`test_main_window_logic` chậm, vài phút — không phải treo.) Sau đó `git checkout app_config.json` nếu git báo đổi.

- [ ] **Step 3: Chạy thử app thật (kiểm tra bằng mắt)**

Run: `cmd.exe /c "cd /d D:\Projects\quang-luu-studio && .venv\Scripts\python.exe main.py"` → `Ctrl+Shift+D` → bấm "⚙ Quản lý" ở Tools: bỏ tích một nút, kéo đổi thứ tự, Lưu → dashboard đổi đúng; mở lại, tích lại → hiện lại. Xuất file, Nhập lại chính file đó → thông báo "Đã nhập cấu hình giao diện", thư mục `backups/` có .bak. Mở "+ Thêm Nút": Lưu bị khoá khi tên trống; gõ CC đã dùng → dòng cảnh báo vàng.

- [ ] **Step 4: Commit**

```bash
git add docs/DEV_MODE_GUIDE.md
git commit -m "docs(devmode): hộp Quản lý giao diện, Xuất/Nhập, cảnh báo CC, Gửi thử"
```
