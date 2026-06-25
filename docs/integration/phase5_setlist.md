# Integration Notes — Phase 5: Live Setlist / Auto-Pilot

Tài liệu này dành cho **agent chủ** nối Live Setlist vào `frontend_qt.py`. Phần
backend + UI dialog + controller + test đã hoàn tất (KHÔNG sửa `frontend_qt.py`):

- `core/engine/_setlist.py` — `SetlistController` (thuần, không Qt) + helper
  `tone_already_cached(url)`, `_song_url(song)`.
- `core/engine/__init__.py` — `SystemEngine.make_setlist(songs) -> SetlistController`
  (đã nối sẵn `detect_fn` vào pipeline dò tone engine; cũng export
  `SetlistController`).
- `ui/dialogs/setlist_dialog.py` — `SetlistDialog(parent, on_play=..., make_controller=...)`.
- `tests/test_setlist.py` — 9 test controller (chạy không cần Qt).

---

## 1. SetlistController API (thuần)

```python
ctrl = SetlistController(songs)        # songs: list[dict] có tối thiểu 'url'
ctrl.advance()      -> dict | None     # con trỏ sang bài kế, trả bài đó (lần đầu = bài 0)
ctrl.current()      -> dict | None     # bài đang phát (None khi chưa start)
ctrl.peek_next()    -> dict | None     # bài kế (không di chuyển con trỏ)
ctrl.has_next()     -> bool
ctrl.reset()                           # con trỏ về -1
ctrl.set_songs(new_songs)              # đổi danh sách + reset
ctrl.prefetch_next(detect_fn, on_done=None) -> bool
```

`prefetch_next` BỎ QUA nếu bài kế đã có tone (cache auto hoặc timeline thủ công);
ngược lại chạy `detect_fn(url, on_done=...)` trong daemon thread (fail-soft, chống
trùng URL). `detect_fn` nên ghi kết quả vào `ToneCacheManager` — các hàm dò tone
của engine đã làm điều này.

---

## 2. Hàm dò tone 1-URL để nối `detect_fn`

`SystemEngine.make_setlist` đã nối sẵn `detect_fn` vào:

- **`auto_detect_youtube_timeline(url, on_complete, on_error, on_progress, skip_resolve)`**
  — file `core/engine/_tone.py`, **dòng 690** (`class _ToneMixin`).
  Đây là hàm dò TOÀN BỘ timeline 1 URL. Nó ghi kết quả vào
  `ToneCacheManager.save_tone(url, {...})` (`_tone.py` dòng ~830), cache theo
  `song_match_key` nên khi mở bài thật, `_resolve_tone` (dòng 146) sẽ khớp ngay
  → MIDI được áp tự động.

Lựa chọn thay thế (1 tone, nhanh hơn, cũng ghi cache):
- `detect_tone_from_youtube(url, on_complete, on_error, on_progress)` — `_tone.py`
  **dòng 429**. Dò 30s đầu, lưu qua `_save_tone_to_cache` (dòng 212).

`make_setlist` dùng `auto_detect_youtube_timeline` (timeline đầy đủ tốt hơn cho
buổi live). Nếu integrator muốn prefetch nhẹ hơn, có thể tự dựng controller rồi
truyền `detect_fn` gọi `detect_tone_from_youtube`.

---

## 3. Mở SetlistDialog từ frontend (gate "setlist")

`frontend_qt.py` đã có `self._require_premium(feature, label)` (dòng 1102) và
pattern mở dialog danh sách (`_show_songs_list`, dòng 1734). Thêm method tương tự:

```python
def _show_setlist(self):
    if not self._require_premium("setlist", "Live Setlist / Auto-Pilot"):
        return
    from ui.dialogs.setlist_dialog import SetlistDialog
    SetlistDialog(
        self,
        on_play=self._setlist_play_song,
        make_controller=self.engine.make_setlist,   # nối prefetch tone bài kế
    ).exec()
```

Đăng ký action (vd. trong dict command quanh dòng 2156, cạnh `"open_songs"`):

```python
"open_setlist": self._show_setlist,
```

…và gắn vào menu/nút Premium (kèm badge PRO khi Standard, giống các tính năng
Premium khác).

---

## 4. `on_play` — mở URL + áp preset khi chuyển bài

`SetlistDialog` gọi `on_play(song_dict)` mỗi khi bắt đầu / "Bài kế". Method
frontend cần (a) mở URL YouTube và (b) áp preset Smart Recall:

```python
def _setlist_play_song(self, song):
    url   = song.get("url")
    tone  = song.get("tone", "C")
    title = song.get("title", "")
    if not url:
        return
    # (a) Mở URL — TÁI DÙNG đúng luồng mà SongsListDialog._make_play đang dùng:
    #     ui/dialogs/songs_list.py dòng ~379 gọi self.engine.open_youtube_url(...)
    manual_tl = None
    tl = backend.ManualToneTimeline.load_timeline(url)
    if tl and tl.get("timeline"):
        manual_tl = tl["timeline"]
    self.engine.open_youtube_url(
        url,
        on_video_end_callback=lambda res: None,
        on_tone_detected=lambda result: self._tone_result_signal.emit(result),
        manual_timeline=manual_tl,
    )
    from PySide6.QtCore import QSignalBlocker
    with QSignalBlocker(self.tone_combo):
        self.tone_combo.setCurrentText(tone)
    # (b) Áp preset Smart Recall (Phase 2 — method này do agent Phase 2 cung cấp):
    if hasattr(self, "_apply_song_preset"):
        self._apply_song_preset(song)
```

Ghi chú:
- **`open_youtube_url`** là cách hiện tại mở 1 bài từ `songs_list` —
  `core/engine/_youtube.py` **dòng 311**. Dùng nguyên signature đó.
- **`_apply_song_preset(song)`** do **Phase 2 / agent chủ** thêm (xem
  `docs/integration/phase2_smart_recall.md`). Phase 5 chỉ THAM CHIẾU; gọi qua
  `hasattr` để fail-soft nếu Phase 2 chưa tích hợp.
- Vì tone bài kế đã được prefetch vào cache, `open_youtube_url` →
  `start_youtube_watcher` → `_resolve_tone` sẽ khớp cache và áp MIDI ngay, không
  phải dò lại.

---

## 5. Luồng prefetch (đã tự động trong dialog)

Sau mỗi `advance()` (Start hoặc Bài kế), `SetlistDialog._after_advance` gọi
`controller.prefetch_next(detect_fn, on_done=...)` với `detect_fn` lấy từ
`controller._engine_detect_fn` (do `make_setlist` gắn). Vậy ngay khi đang phát
bài N, tone bài N+1 được dò nền và lưu cache. Card bài có cờ **"✓ tone đã sẵn"**
khi cache đã có (cập nhật ở lần rebuild list kế).

Nếu `make_controller=None` (không truyền), dialog chạy chế độ UI thuần: vẫn
advance/Bài kế gọi `on_play`, nhưng KHÔNG prefetch — fail-soft.
