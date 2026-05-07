# Plan — Hỗ trợ người khiếm thị sử dụng Quang Lưu Studio

## Context

**Vấn đề:** Quang Lưu Studio (PySide6/Qt desktop app, Windows) hiện không có khả năng tiếp cận (accessibility) cho người khiếm thị:
- Không có `setAccessibleName/Description` → screen reader (NVDA, Narrator) không đọc được nút/slider.
- Không có QShortcut, Tab order rõ ràng, focus indicator → không điều khiển được bằng bàn phím.
- Không có TTS nội bộ → mọi thay đổi trạng thái (tone phát hiện, điểm số, kết nối MIDI) chỉ hiện trực quan.
- Không có high-contrast theme / font lớn → thị lực kém không đọc được.

**Đối tượng:** Hỗ trợ cả 2 nhóm — mù hoàn toàn (TTS + bàn phím + voice command) và thị lực kém (theme phóng to + tương phản cao).

**Kết quả mong đợi:** Người khiếm thị có thể tự kích hoạt app, dò tone, mở YouTube, lưu/mở bài, chấm điểm — mà không cần người sáng mắt hỗ trợ.

**Đã xác nhận từ user:**
- Phạm vi: cả mù hoàn toàn + thị lực kém.
- TTS: dual mode (accessible names cho NVDA + pyttsx3 nội bộ tuỳ chọn).
- Input: bàn phím/hotkey + voice command (giọng nói tiếng Việt). MIDI controller đã có sẵn → tận dụng kèm.

---

## Phạm vi & kiến trúc giải pháp

Module mới gom vào package `core/accessibility/`:

```
core/accessibility/
├── __init__.py
├── speaker.py          # TTS (pyttsx3 + SAPI5) — Vietnamese voice
├── voice_input.py      # Voice command (Vosk offline VI)
├── theme.py            # High contrast / font scale palettes
├── shortcuts.py        # Đăng ký QShortcut tập trung
└── announcer.py        # Service kết nối state changes → speaker
```

Flag bật/tắt trong `app_config.json`:
```json
"accessibility": {
  "tts_enabled": false,
  "tts_voice": "vietnamese",
  "tts_rate": 180,
  "voice_command_enabled": false,
  "voice_command_hotkey": "Ctrl+Space",
  "high_contrast": false,
  "font_scale": 1.0,
  "focus_ring_thick": false,
  "announce_focus": true,
  "announce_state": true
}
```

---

## Các thay đổi cụ thể

### 1. Accessible names cho widget (cho NVDA / Windows Narrator)

**Files chính cần sửa:**
- `ui/panels/header.py` — MIDI dot, browser dot, marquee, tone combobox, scale combobox, settings button, eye button
- `ui/panels/tools.py` — knob ±, value label, mute (mỗi knob có nhãn "Tone Nhạc", "Tone Giọng")
- `ui/panels/mixer.py` — 4 fader (Nhạc/Mic/Vang/Giọng) + 4 mute button
- `ui/panels/mode.py` — 4 mode button + SFX button area
- `ui/panels/bottom_bar.py` — Record, Save, List, Score, Folder
- `ui/dialogs/settings_dialog.py`, `ui/dialogs/songs_list.py`, `ui/dialogs/scoring_report.py`

**Pattern:**
```python
button.setAccessibleName("Dò tone tự động")
button.setAccessibleDescription("Bật/tắt dò tone liên tục từ loopback. Phím tắt Ctrl+D.")
slider.setAccessibleName("Âm lượng nhạc")
```

PainterButton custom (`ui/components/painter_button.py` — nếu có) cần override `accessibleName()` hoặc set qua property thông thường vì kế thừa QPushButton/QWidget.

### 2. TTS engine nội bộ — `core/accessibility/speaker.py`

- Library: **pyttsx3** (offline, SAPI5).
- Init: chọn voice tiếng Việt (Microsoft An / Linh / Mai). Fallback English nếu không có.
- API:
  ```python
  class Speaker:
      def speak(self, text: str, priority: str = "normal"): ...
      def stop(self): ...
      def set_rate(self, rate: int): ...
      def set_voice(self, voice_id: str): ...
  ```
- **Async**: chạy worker thread + queue để tránh block UI. `priority="high"` flush queue (cho thông báo lỗi).
- **Bật/tắt** runtime qua `Ctrl+Shift+V`.

### 3. Announcer — kết nối state → speaker (`core/accessibility/announcer.py`)

Subscribe vào các event hiện có trong `frontend_qt.py` / `backend.py`:

| Event | Câu thông báo |
|---|---|
| Focus change | Đọc `accessibleName` + `accessibleDescription` của widget mới |
| MIDI connect/disconnect | "MIDI đã kết nối" / "Mất kết nối MIDI" |
| Tone detected | "Phát hiện tone Đô trưởng, độ tin cậy 87%" |
| AutoKey segment update | (chỉ khi key đổi) "Chuyển sang Rê thứ" |
| Slider value change | (debounce 300ms) "Nhạc 75%" |
| Mode chọn | "Chế độ Bolero" |
| Recording start/stop | "Bắt đầu ghi" / "Dừng ghi" |
| Score result | "Điểm 92, xuất sắc" |
| Browser open YouTube | "Đã mở YouTube. Đang dò tone." |
| Lỗi / message alert | Đọc text trong `_show_message()` |

**Tích hợp:** install event filter `installEventFilter` trên `QApplication.instance()` để bắt `QEvent.FocusIn`. Các state event khác hook qua signals/callback hiện có (`engine.register_midi_callback`, `on_autokey_update`...).

### 4. Hotkey toàn diện — `core/accessibility/shortcuts.py`

Đăng ký `QShortcut` ở `MainDashboard.__init__`:

| Phím | Hành động |
|---|---|
| `F1` | Đọc help — danh sách phím tắt |
| `F2` | Đọc trạng thái hiện tại (tone, MIDI, mode, mức nhạc/mic) |
| `Ctrl+D` | Toggle Dò tone / AutoKey |
| `Ctrl+R` | Toggle Record |
| `Ctrl+S` | Lưu bài |
| `Ctrl+O` | Mở danh sách bài |
| `Ctrl+P` | Chấm điểm |
| `Ctrl+,` | Settings |
| `Ctrl+Shift+V` | Toggle TTS |
| `Ctrl+Space` | Bật/tắt voice command |
| `Ctrl+H` | Toggle high-contrast theme |
| `Ctrl++` / `Ctrl+-` | Tăng/giảm font scale (0.8 – 1.6) |
| `Alt+1..4` | Focus panel: Header / Tools / Mixer / Mode |
| `[` / `]` | Tone Nhạc -1 / +1 |
| `;` / `'` | Tone Giọng -1 / +1 |
| `1..4` | Toggle mute 4 kênh mixer |
| `↑↓` trên slider focus | ±5% giá trị |

**Tab order** rõ ràng: dùng `setTabOrder(w1, w2)` từ Header → Tools → Mixer → Mode → BottomBar.

**Focus ring**: stylesheet bổ sung khi `focus_ring_thick=True`:
```css
*:focus { outline: 3px solid #FFEB3B; outline-offset: 2px; }
```

### 5. Voice command — `core/accessibility/voice_input.py`

- Library: **Vosk** + `vosk-model-small-vn-0.4` (~40MB, offline). Fallback: `speech_recognition` + Google nếu user bật chế độ online.
- **Trigger**: push-to-talk `Ctrl+Space` (giữ để nói, thả để gửi). Không listen always-on tránh nhiễu.
- **Lệnh hỗ trợ** (intent matcher đơn giản, regex/keyword):
  - "dò tone" / "tự động dò" → toggle AutoKey
  - "ghi âm" / "thu" → record
  - "lưu bài" / "mở bài" / "chấm điểm" → action tương ứng
  - "tăng nhạc/mic/vang/giọng" / "giảm …" → ±5%
  - "chế độ bolero" / "chế độ remix" → chọn mode
  - "mở youtube <từ khoá>" → mở browser tìm
  - "đọc trạng thái" → giống F2
  - "tắt giọng nói" → stop TTS
- Phản hồi qua TTS sau mỗi lệnh: "Đã thực hiện" / "Không hiểu lệnh".

### 6. High-contrast theme + font scale — `core/accessibility/theme.py`

- Hai palette: `default`, `high_contrast` (nền đen, chữ vàng `#FFEB3B`, accent xanh lá `#00FF66`, viền 3px).
- Apply qua `QApplication.setPalette()` + stylesheet override.
- `font_scale` (0.8 – 2.0) nhân vào `QApplication.font().pointSize()`.
- Hot-reload không cần restart — phát signal `theme_changed` để các panel re-style nếu cần.

### 7. Settings dialog — tab "Trợ năng" mới

Trong `ui/dialogs/settings_dialog.py` thêm tab mới:
- Checkbox: Bật TTS / Voice command / High contrast / Focus ring dày / Announce focus / Announce state.
- Combobox: voice TTS (liệt kê SAPI voices).
- Slider: TTS rate (100–250), font scale (80–200%).
- Nút "Test giọng nói" — đọc câu mẫu.
- Nút "Tải Vosk model" — nếu chưa có, tải về `models/vosk-vi/`.

### 8. Tài liệu hướng dẫn

Tạo `docs/ACCESSIBILITY_GUIDE.md`:
- Hướng dẫn cài NVDA + bật add-on tiếng Việt.
- Bảng phím tắt + lệnh giọng nói.
- Layout MIDI controller khuyến nghị (Korg nanoKONTROL2, Akai MPK Mini...) cho người mù — đã map sẵn theo `MIDI_MAPPING_GUIDE.md`.
- Cách kích hoạt từng tính năng trợ năng.

---

## Files quan trọng cần sửa / tạo

**Tạo mới:**
- `core/accessibility/__init__.py`
- `core/accessibility/speaker.py`
- `core/accessibility/voice_input.py`
- `core/accessibility/theme.py`
- `core/accessibility/shortcuts.py`
- `core/accessibility/announcer.py`
- `docs/ACCESSIBILITY_GUIDE.md`
- `docs/ACCESSIBILITY_PLAN.md` (bản plan này)

**Sửa:**
- `frontend_qt.py` — khởi tạo `Announcer`, `Speaker`, `VoiceInput`, đăng ký shortcut, install focus event filter, hook state callbacks.
- `ui/panels/header.py`, `tools.py`, `mixer.py`, `mode.py`, `bottom_bar.py` — `setAccessibleName/Description` + `setTabOrder`.
- `ui/dialogs/settings_dialog.py` — thêm tab "Trợ năng".
- `ui/dialogs/songs_list.py`, `scoring_report.py` — accessible names + announce on open.
- `app_config.json` — thêm section `accessibility` với defaults.
- `core/config_manager.py` (hoặc tương đương) — load/save accessibility config.
- `requirements.txt` — thêm `pyttsx3>=2.90`, `vosk>=0.3.45`, `sounddevice>=0.4.6`.
- `QuangLuuStudio.spec` — bundle Vosk model + pyttsx3 hidden imports (`pyttsx3.drivers.sapi5`).

**Tận dụng/Tham khảo (không sửa logic):**
- `frontend_qt.py:757-767` `_show_message()` — hook để TTS đọc message.
- `core/system_engine.py` (backend) `register_midi_callback` — hook MIDI event.
- `MIDI_MAPPING_GUIDE.md` — tham chiếu mapping vật lý.
- `sfx/` — tận dụng `sfx_applause.wav` / `sfx_cheer.wav` làm audio cue khi đạt điểm cao.

---

## Triển khai theo giai đoạn (incremental)

**Phase 1 — Nền tảng (1-2 ngày):**
1. Thêm `setAccessibleName/Description` cho mọi widget tương tác.
2. Thiết lập Tab order + focus ring rõ ràng.
3. Đăng ký bộ QShortcut tối thiểu (F1, F2, Ctrl+D/R/S/O/P, +/- tone, mute 1-4).
4. Thêm tab "Trợ năng" cơ bản trong settings.

→ NVDA/Narrator đọc được; điều khiển bằng bàn phím tốt.

**Phase 2 — TTS nội bộ (1 ngày):**
5. `Speaker` + `Announcer` cho focus/state events.
6. Toggle Ctrl+Shift+V.

**Phase 3 — High contrast / font scale (0.5 ngày):**
7. `theme.py` + hot-reload.
8. Phím Ctrl+H, Ctrl++/-.

**Phase 4 — Voice command (1-2 ngày):**
9. `voice_input.py` + Vosk model loader + intent matcher.
10. Push-to-talk Ctrl+Space + phản hồi TTS.

**Phase 5 — Tài liệu + build (0.5 ngày):**
11. `ACCESSIBILITY_GUIDE.md`.
12. Cập nhật spec build (bundle model + hidden imports).

---

## Verification (cách kiểm thử end-to-end)

**Bằng bàn phím (mô phỏng người mù):**
1. Mở app, không chạm chuột.
2. Tab qua tất cả control — focus ring phải hiển thị; nếu bật TTS → mỗi lần Tab nghe tên control.
3. Ctrl+D → nghe "Bắt đầu dò tone tự động". Sau 5s nghe "Phát hiện Đô trưởng".
4. Ctrl+S → dialog lưu bài → nhập tên → Enter → nghe "Đã lưu".
5. Ctrl+P → flow chấm điểm → nghe điểm cuối.

**Bằng NVDA (đảm bảo accessible names hoạt động):**
1. Cài NVDA, bật, mở app.
2. Tab qua các control — NVDA đọc accessibleName.
3. Vào dialog Settings tab Trợ năng → NVDA đọc tên các checkbox.

**Voice command:**
1. Bật "Voice command" trong Settings.
2. Giữ Ctrl+Space, nói "dò tone" → thả → app toggle AutoKey + TTS phản hồi.
3. Thử "tăng nhạc", "chế độ bolero", "đọc trạng thái".

**Thị lực kém:**
1. Ctrl+H → app chuyển nền đen chữ vàng tương phản cao.
2. Ctrl++ vài lần → font tăng dần, layout không vỡ.
3. Tab → focus ring 3px màu vàng.

**Unit/integration tests** (`tests/`):
- `tests/test_accessibility_speaker.py` — mock SAPI, kiểm tra queue + priority.
- `tests/test_accessibility_announcer.py` — feed mock event, assert speaker called với câu đúng.
- `tests/test_voice_intent.py` — input text → match action đúng.
- `tests/test_shortcuts.py` — mỗi QShortcut trigger đúng slot.

**Build:**
- `PyInstaller QuangLuuStudio.spec` → exe khởi động bình thường, không lỗi import pyttsx3/vosk.
- Test trên máy chỉ có voice English (fallback) và máy có Microsoft An (đọc tiếng Việt chuẩn).
