# Integration Notes — Phase 2: Smart Recall

Tài liệu này dành cho **agent chủ** nối Smart Recall vào `frontend_qt.py` /
`ui/dialogs/`. Phần backend (data + preset thuần + test) đã hoàn tất:

- `core/presets.py` — hàm thuần `normalize_preset`, `merge_preset`, `empty_preset`,
  `is_empty_preset`, `normalize_mixer`, hằng `MIXER_KEYS`.
- `core/songs.py` — `add_song(..., preset=None)`, `update_song(..., preset=...)`,
  `SongManager.save_preset(song_id, preset_dict) -> bool`,
  `SongManager.get_preset(song_id) -> dict|None`.
- `tests/test_presets.py` — 18 test (chạy không cần Qt).

Backend được expose qua `backend.SongManager` (alias hiện có), nên trong UI dùng
`backend.SongManager.save_preset(...)` / `backend.SongManager.get_preset(...)`.

---

## 1. Schema preset

```python
{
    "tone":  str | None,            # "C", "Am", "F#m" ... (giống tone_combo)
    "scale": "Major" | "Minor" | None,
    "mixer": { "music": int, "mic": int, "reverb": int, "backing": int },  # field thiếu = không áp
    "mode":  str | None,            # "Dân Ca" | "Lofi" | "Remix" | "Đa Thể Loại"
}
```

`get_preset` luôn trả dict đã normalize (đủ 4 khóa) khi bài có preset, hoặc
`None` khi bài chưa từng lưu preset. `mixer` chỉ chứa các kênh thực sự được lưu.

**Ánh xạ khóa mixer ↔ cc_key UI** (đã xác nhận trong `ui/panels/mixer.py` +
`core/config.py` default ui_config):

| preset key | cc_key (`self._mixer_sliders`) |
|------------|--------------------------------|
| `music`    | `mix_music`                    |
| `mic`      | `mix_mic`                      |
| `reverb`   | `mix_reverb`                   |
| `backing`  | `mix_backing`                  |

Lưu ý: slider lưu **giá trị UI thô** (vd music 0..100, mic/reverb −10..+10,
tone_music −12..+12). `_make_value_changed_callback` (mixer.py) lo việc đổi sang
MIDI khi `slider.valueChanged` fire — nên chỉ cần `slider.setValue(...)` là MIDI
được gửi đúng. **Kênh `tone_music` (cao độ giọng) KHÔNG nằm trong schema preset**
(preset.tone là nốt gốc Auto-Tune, khác với slider dịch giọng). Nếu sau muốn lưu
cả `tone_music` thì thêm khóa mới, đừng nhồi vào 4 khóa hiện tại.

---

## 2. Callback / state đã xác nhận trong `frontend_qt.py`

| Mục | Vị trí | Ghi chú |
|-----|--------|---------|
| `_on_tone_selected(self, value)` | dòng 425 | set `self.current_tone`, gửi MIDI key_root, **khoá replay** (`_lock_replay_for_manual_override`). |
| `_on_scale_selected(self, value)` | dòng 432 | value = `"Major"`/`"Minor"`; gửi MIDI scale_type + sync nút. |
| `_on_mode_selected(self, mode, toggle=False)` | dòng 1618 | `mode` = tên VN; với `toggle=False` luôn **bật** mode (gửi on_value). |
| `self.tone_combo` / `self.scale_combo` | combo QComboBox | set qua `QSignalBlocker` để tránh double-fire (pattern hiện có ở dòng 463-469, 886-891). |
| `self._mixer_sliders` | dict `{cc_key: QSlider}` | dựng trong `ui/panels/mixer.py:build_panel_mixer` (dòng 208). `.value()` để đọc, `.setValue()` để set (kéo theo MIDI). |
| `self.mute_states` | dict `{cc_key: bool}` | dòng 127. |
| `self.current_mode` / `current_tone` / `current_scale` | state | dùng để CAPTURE. |
| `self._require_premium(feature, label) -> bool` | dòng 1102 | gate Premium; trả True nếu được phép. |

Combo set giá trị mà muốn **gửi MIDI luôn**: làm theo pattern dòng 463-469 —
chặn signal khi `setCurrentText` rồi gọi `_on_tone_selected/_on_scale_selected`
thủ công (tránh double-fire nhưng vẫn phát MIDI). Đây là cách an toàn nhất.

---

## 3. Snippet dán vào `MainDashboard` (frontend_qt.py)

### 3a. Áp preset khi mở bài

```python
def _apply_song_preset(self, song):
    """Smart Recall (Premium): khôi phục tone/scale/mixer/mode đã lưu của bài.

    Gate Premium ở dòng đầu — Standard mở bài như cũ, không auto-apply.
    Trả None; an toàn nuốt lỗi để không chặn việc phát bài.
    """
    if not song:
        return
    try:
        preset = backend.SongManager.get_preset(song.get("id"))
    except Exception:
        preset = None
    if not preset:
        return  # Bài chưa có preset → không làm gì (tương thích ngược)

    # Chỉ gate khi THỰC SỰ có preset để áp, tránh hiện upsell vô cớ khi mở bài cũ.
    if not self._require_premium("smart_recall", "Smart Recall"):
        return

    from PySide6.QtCore import QSignalBlocker

    # --- Tone + Scale (đi qua combo + callback, phát MIDI giống chọn tay) ---
    tone = preset.get("tone")
    if tone:
        with QSignalBlocker(self.tone_combo):
            self.tone_combo.setCurrentText(tone)
        self._on_tone_selected(tone)

    scale = preset.get("scale")
    if scale and hasattr(self, "scale_combo"):
        with QSignalBlocker(self.scale_combo):
            self.scale_combo.setCurrentText(scale)
        self._on_scale_selected(scale)

    # --- Mixer (setValue kéo theo MIDI qua valueChanged của mixer panel) ---
    mixer = preset.get("mixer") or {}
    key_map = {"music": "mix_music", "mic": "mix_mic",
               "reverb": "mix_reverb", "backing": "mix_backing"}
    for pkey, cc_key in key_map.items():
        if pkey not in mixer:
            continue
        slider = self._mixer_sliders.get(cc_key) if hasattr(self, "_mixer_sliders") else None
        if slider is not None:
            slider.setValue(int(mixer[pkey]))

    # --- Mode (toggle=False ⇒ luôn bật mode đã lưu) ---
    mode = preset.get("mode")
    if mode:
        self._on_mode_selected(mode, toggle=False)

    self._show_message(f"🎚️ Đã khôi phục preset: {song.get('title','')}")
```

### 3b. Capture preset hiện tại từ UI

```python
def _capture_current_preset(self) -> dict:
    """Chụp trạng thái UI hiện tại thành preset dict (đã hợp lệ schema).

    Đọc combo tone/scale, mức 4 slider mixer, và mode đang chọn.
    """
    preset = {
        "tone":  self.tone_combo.currentText() if hasattr(self, "tone_combo") else None,
        "scale": self.scale_combo.currentText() if hasattr(self, "scale_combo") else None,
        "mode":  getattr(self, "current_mode", None),
        "mixer": {},
    }
    key_map = {"mix_music": "music", "mix_mic": "mic",
               "mix_reverb": "reverb", "mix_backing": "backing"}
    sliders = getattr(self, "_mixer_sliders", {})
    for cc_key, pkey in key_map.items():
        slider = sliders.get(cc_key)
        if slider is not None:
            preset["mixer"][pkey] = slider.value()
    return preset
```

`SongManager.save_preset` / `add_song` / `update_song` đã tự `normalize_preset`,
nên không cần normalize ở UI; cứ truyền dict thô từ `_capture_current_preset`.

---

## 4. Vị trí GỌI `_apply_song_preset` trong luồng mở bài

Luồng mở bài đã lưu nằm ở **`ui/dialogs/songs_list.py` → `SongsListDialog._make_play(self, song)`
→ hàm trong `_play()`** (dòng **370-393**). Đây là nơi double-click/nút Play gọi
`engine.open_youtube_url(...)` rồi set `tone_combo`.

Chèn lời gọi **ngay sau** block set `tone_combo` (sau dòng 387, trước
`self.close()` ở dòng 392):

```python
# ... sau khi set tone_combo (dòng 386-387) ...
self._dashboard._apply_song_preset(song)   # ← Smart Recall (tự gate Premium)
```

Lưu ý thứ tự: `_apply_song_preset` set lại `tone_combo` theo `preset.tone` (nếu
có) → sẽ **đè** giá trị `song.tone` vừa set ở dòng 386-387. Đó là hành vi mong
muốn (preset ưu tiên hơn tone mặc định của bài). Với bài Standard / bài không có
preset thì `_apply_song_preset` return sớm, giữ nguyên `song.tone`.

> Có một nhánh phát bài thứ hai trong `frontend_qt.py` không? Đã kiểm tra: việc
> mở bài đã lưu chỉ đi qua `SongsListDialog._make_play`. Nút save chính
> (`_process_quick_save`, dòng ~1333) là LƯU bài, không phát. Nên chỉ cần chèn 1
> chỗ ở `_make_play`.

---

## 5. Nút "Lưu preset bài"

Khuyến nghị đặt ở **`ui/dialogs/songs_list.py`**, trong menu ngữ cảnh của mỗi bài
(`_make_menu`, dòng 395-435) — cạnh "Sửa thông tin" / "Sửa chuỗi tone". Lý do:
menu đó đã có sẵn `song` và `self._dashboard`, không cần thêm widget vào card.

```python
# Trong _make_menu(...), thêm sau act_tone (dòng ~412):
act_preset = QAction("🎚️  Lưu preset hiện tại vào bài", menu)
act_preset.triggered.connect(lambda: self._save_preset_for(song))
menu.addAction(act_preset)
```

```python
# Method mới trong SongsListDialog:
def _save_preset_for(self, song):
    dash = self._dashboard
    # Gate Premium trước khi chụp/ghi.
    if not dash._require_premium("smart_recall", "Smart Recall"):
        return
    preset = dash._capture_current_preset()
    if backend.SongManager.save_preset(song.get("id"), preset):
        dash._show_message("✅ Đã lưu preset cho bài hát")
        self._refresh_data()
        self._rebuild_list()
    else:
        dash._show_message("⚠️ Không lưu được preset", is_error=True)
```

(Phương án thay thế: nút trong `ui/dialogs/edit_song.py`. Nhưng edit_song tập
trung vào chuỗi tone timeline; đặt ở menu songs_list gọn và đúng ngữ cảnh hơn.)

---

## 6. Checklist verify (theo plan)

1. Premium: chỉnh tone/scale/mixer/mode → menu bài → "Lưu preset hiện tại" →
   mở bài khác → quay lại bài cũ (Play) → giá trị tự khôi phục, MIDI CC gửi đúng.
2. Standard: mở bài có preset → KHÔNG auto-apply, hiện upsell khi bấm "Lưu preset"
   (vì `_apply_song_preset` gate sau khi phát hiện có preset — cân nhắc bỏ upsell
   ở luồng mở để Standard mở bài im lặng; nếu muốn vậy, đổi `_apply_song_preset`
   dùng `entitlements.has_feature("smart_recall")` trực tiếp thay vì
   `_require_premium`, return im lặng khi False).
3. Bài cũ (chưa có preset) mở bình thường, không lỗi.

> Gợi ý: ở bước mở bài, để tránh quấy rầy Standard bằng dialog upsell, có thể
> thay `self._require_premium(...)` trong `_apply_song_preset` bằng:
> ```python
> from core import entitlements
> if not entitlements.has_feature("smart_recall"):
>     return
> ```
> và CHỈ dùng `_require_premium` ở nút **Lưu preset** (hành động chủ động của
> user thì upsell là hợp lý). Quyết định cuối thuộc agent chủ.
