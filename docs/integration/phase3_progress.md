# Phase 3 — Bảng tiến bộ luyện hát (scoring history) — Integration notes

File mới (đã tạo, KHÔNG cần agent chủ sửa):
- `core/score_history.py` — `ScoreHistory.add/load/summary/recent` (file `score_history.json` trong `DATA_DIR`, atomic write, fail-soft, cap 500 entry).
- `ui/dialogs/progress_dialog.py` — `ProgressDialog(QDialog)` (QtCharts nếu có, fallback QPainter; nếu chưa có dữ liệu → "Chưa có dữ liệu chấm điểm").
- `tests/test_score_history.py` — 11 test, chạy không cần Qt.

Agent chủ chỉ cần chèn 2 đoạn dưới vào `frontend_qt.py`.

---

## 1. Ghi điểm sau mỗi lần chấm

Trong `frontend_qt.py`, callback `on_score_ready(result)` bên trong `_on_score()`
(khoảng dòng 1067–1074). Đoạn hiện tại:

```python
def on_score_ready(result):
    # Reset UI
    self._score_btn_reset_signal.emit()

    if "error" in result:
        self._message_signal.emit(f"Lỗi chấm điểm: {result['error']}", True)
    else:
        self._score_report_signal.emit(result)
```

Sửa nhánh `else` thành (chỉ thêm phần ghi lịch sử — gọi trước khi emit signal):

```python
def on_score_ready(result):
    # Reset UI
    self._score_btn_reset_signal.emit()

    if "error" in result:
        self._message_signal.emit(f"Lỗi chấm điểm: {result['error']}", True)
    else:
        # Phase 3 — lưu lịch sử chấm điểm (Premium "progress").
        # Score đã gate premium ở đầu _on_score nên chỉ chạy cho Premium.
        # Fail-soft: ScoreHistory.add nuốt mọi lỗi, không làm vỡ luồng.
        try:
            from core.score_history import ScoreHistory
            ScoreHistory.add(
                result,
                song_title=getattr(self, "current_title", "") or "",
                url=getattr(self.engine, "current_youtube_url", "") or "",
            )
        except Exception as e:
            print(f"[PROGRESS] save history error: {e}")
        self._score_report_signal.emit(result)
```

Nguồn `song_title` / `url` (đã xác minh trong frontend_qt.py):
- `self.current_title` — set ở `_on_tone_detected` (dòng ~887) khi engine trả title.
- `self.engine.current_youtube_url` — dùng sẵn ở `_on_save` (dòng 1241).

`ScoreHistory.add` tự map khóa thật từ `result`:
- `overall` ← `result["total_score"]`
- `pitch`   ← TB của `pitch_intonation` & `pitch_stability` (lấy giá trị > 0)
- `rhythm`  ← `result["rhythm_score"]`
- `tone`    ← `result["key_conformity"]` (đúng tông)

---

## 2. Nút mở Bảng tiến bộ (gate "progress")

Thêm 1 callback mở dialog (đặt cạnh `_show_scoring_report`, ~dòng 1097):

```python
def _show_progress_dialog(self):
    if not self._require_premium("progress", "Bảng tiến bộ luyện hát"):
        return
    from ui.dialogs.progress_dialog import ProgressDialog
    ProgressDialog(self).exec()
```

Vị trí nút đề xuất (chọn 1):

**A. Header bar** (`ui/panels/header.py`, cạnh `_settings_btn` / `_eye_btn`, dòng ~95–116)
— gọn nhất, dùng `PainterButton` sẵn có:

```python
dashboard._progress_btn = PainterButton(
    icon="chart",            # hoặc emoji/text "📈" tuỳ API PainterButton hiện dùng
    size=...,                # khớp các nút header khác
)
dashboard._progress_btn.setToolTip("Bảng tiến bộ luyện hát (Premium)")
dashboard._progress_btn.setAccessibleName("Mở bảng tiến bộ")
dashboard._progress_btn.setCursor(Qt.PointingHandCursor)
dashboard._progress_btn.clicked.connect(dashboard._show_progress_dialog)
layout.addWidget(dashboard._progress_btn)
```

**B. Songs list dialog** (`ui/dialogs/songs_list.py`) — nếu muốn đặt trong khu
"thư viện bài". Thêm 1 `QPushButton("📈 Tiến bộ")` ở thanh nút trên cùng,
`clicked.connect` về `parent._show_progress_dialog` (truyền dashboard làm parent).

Gợi ý: theo Phase plan, đặt ở **header bar** (A) để luôn truy cập được, đồng nhất
với nút Settings. Nếu agent chủ thêm badge "PRO" cho nút Premium (Phase 0), gắn
badge lên `_progress_btn` khi `not entitlements.is_premium()` để upsell (không ẩn).

---

## Verify

```bash
python -c "import core.score_history; print('ok')"
python -m pytest tests/test_score_history.py -q      # 11 passed
```

Smoke (Premium): chấm 2–3 lần → mở Bảng tiến bộ → thấy các mốc + đường biểu đồ
+ thẻ TB/Cao nhất + xu hướng. Standard bấm nút → dialog upsell (qua `_require_premium`).
