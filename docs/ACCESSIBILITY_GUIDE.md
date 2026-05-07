# Hướng dẫn Trợ năng — Quang Lưu Studio

Tài liệu dành cho người **khiếm thị** (mù hoàn toàn) hoặc **thị lực kém**, và người trợ giúp (gia đình, kỹ thuật viên) thiết lập app cho họ.

---

## 1. Cài đặt nhanh

### Người trợ giúp (làm 1 lần)

1. Cài Quang Lưu Studio như hướng dẫn trong [BUILD.md](../BUILD.md).
2. Cài thêm các package trong `requirements.txt` — `pyttsx3` (TTS) và `vosk` (voice command, tuỳ chọn).
3. **(Tuỳ chọn)** Tải Vosk model tiếng Việt:
   - URL: `https://alphacephei.com/vosk/models` → tìm `vosk-model-small-vn-0.4` (khoảng 40 MB).
   - Giải nén vào: `D:/Projects/LiveStudio/quang-luu-studio/models/vosk-vi/`
     (hoặc thư mục `models/vosk-vi/` cạnh `QuangLuuStudio.exe` nếu là bản build).
4. **(Tuỳ chọn)** Cài voice tiếng Việt cho Windows SAPI5: vào *Settings → Time & Language → Speech → Add voices* → tải Microsoft An / Linh / Mai. Nếu bỏ qua, app sẽ dùng voice tiếng Anh có sẵn.

### Người dùng (sau khi đã cài)

Mở app như bình thường. Vào **Settings (Ctrl+Phẩy) → Tab "Trợ năng"**:

- Tích **"Bật TTS đọc trạng thái"** — app sẽ đọc tên control khi Tab tới và phản hồi mỗi lần thay đổi trạng thái.
- Tích **"Tương phản cao"** nếu thị lực kém — nền đen, chữ vàng, viền focus 3px màu vàng.
- Kéo **"Cỡ chữ"** lên 130–160% nếu cần.
- Tích **"Bật lệnh giọng nói"** nếu đã tải Vosk model.

Bấm **"Lưu thiết lập"**. Cấu hình sẽ được áp dụng ngay, không cần restart.

---

## 2. Bảng phím tắt trợ năng

| Phím | Hành động |
|---|---|
| `F1` | Đọc danh sách phím tắt |
| `F2` | Đọc trạng thái hiện tại (MIDI, tone, mức nhạc/mic, chế độ) |
| `Ctrl+D` | Dò lại tone bài hát đang phát |
| `Ctrl+R` | Bắt đầu / dừng ghi âm |
| `Ctrl+S` | Lưu bài hát đang phát |
| `Ctrl+O` | Mở danh sách bài đã lưu |
| `Ctrl+P` | Chấm điểm |
| `Ctrl+,` | Mở thiết lập |
| `Ctrl+Shift+V` | Bật/tắt giọng đọc TTS |
| `Ctrl+H` | Bật/tắt tương phản cao |
| `Ctrl++` / `Ctrl+=` | Tăng cỡ chữ |
| `Ctrl+-` | Giảm cỡ chữ |
| `Ctrl+0` | Khôi phục cỡ chữ mặc định |
| `[` | Tone Nhạc/Giọng -1 bán cung |
| `]` | Tone Nhạc/Giọng +1 bán cung |
| `;` | Tone Giọng -1 |
| `'` | Tone Giọng +1 |
| `1` / `2` / `3` / `4` | Tắt/bật âm Nhạc / Mic / Vang / Giọng đệm |
| `Tab` / `Shift+Tab` | Di chuyển giữa các điều khiển |
| `Mũi tên` trên slider | Tăng/giảm âm lượng |
| `Space` | Kích hoạt nút đang focus |

---

## 3. Lệnh giọng nói

Giữ phím **(do user cấu hình, mặc định không có hotkey hệ thống — dùng nút "Voice" trong tương lai hoặc gọi qua MIDI controller)**, nói lệnh, thả ra. App sẽ đọc lại "Đã thực hiện" hoặc "Không hiểu lệnh".

Một số lệnh hỗ trợ:

- "dò tone", "tự động dò" → bật dò tone
- "ghi âm" / "thu âm" → bật/tắt ghi âm
- "lưu bài", "chấm điểm", "mở bài"
- "tăng nhạc" / "giảm nhạc" / "tăng mic" / "giảm mic"
- "tắt nhạc" / "tắt mic"
- "chế độ Bolero / Lofi / Remix / Đa thể loại"
- "đọc trạng thái" — đọc MIDI, tone, mức âm hiện tại
- "tắt giọng" — dừng TTS

---

## 4. Khuyến nghị MIDI controller cho người mù

App đã hỗ trợ MIDI Learn (xem [MIDI_MAPPING_GUIDE.md](../MIDI_MAPPING_GUIDE.md)). Một số controller phù hợp vì có nhãn nổi sờ được:

- **Korg nanoKONTROL2** (8 fader + 8 knob + nhiều nút) — dán băng dính nổi để phân biệt.
- **Akai MPK Mini Mk3** — pad lớn dễ chạm.
- **Worlde Easycontrol 9** — fader trượt rõ ràng.

Map nhanh:
- Fader 1–4 → mix_music / mix_mic / mix_reverb / mix_backing.
- Knob 1–2 → tone_music / tone_voice.
- Nút 1–2 → autokey / score_trigger.
- Nút 3–6 → mode_danca / mode_lofi / mode_remix / mode_datheloai.

---

## 5. Dùng cùng NVDA / Windows Narrator

App đã set `accessibleName` + `accessibleDescription` cho mọi control quan trọng. Khi NVDA/Narrator được bật:

- **Tab** qua các điều khiển → screen reader đọc tên + mô tả ngắn.
- **F2** trong app cũng đọc trạng thái — không xung đột với NVDA.

> Nếu dùng NVDA mà vẫn muốn TTS nội bộ của app, vào Settings → Trợ năng → tắt "Đọc tên control khi Tab tới" để tránh nói trùng. Vẫn giữ "Đọc thông báo và thay đổi trạng thái" để app báo khi dò tone xong, MIDI mất kết nối, v.v.

---

## 6. Khắc phục sự cố

| Triệu chứng | Cách xử lý |
|---|---|
| TTS không nói gì | Vào Settings → Trợ năng → bấm "Thử giọng nói". Nếu im lặng, kiểm tra `pyttsx3` đã cài (`pip install pyttsx3`) và Windows có ít nhất 1 voice. |
| TTS đọc không đúng tiếng Việt | Settings → Speech → Add voices → tải Microsoft An / Linh / Mai → quay lại app, chọn voice trong dropdown. |
| Voice command không phản hồi | Kiểm tra (1) Vosk đã cài: `pip install vosk sounddevice`. (2) Model nằm tại `models/vosk-vi/`. (3) Mic được cho phép trong Windows Privacy. |
| App quá to / quá nhỏ | Ctrl++ / Ctrl+- để chỉnh cỡ chữ. Ctrl+0 để reset. |
| Tương phản cao "kém đẹp" | Chỉnh palette trong `core/accessibility/theme.py` — biến `_HIGH_CONTRAST_QSS`. |

---

## 7. Build PyInstaller (cho người package app)

Trong `QuangLuuStudio.spec`, bổ sung vào `hiddenimports`:

```python
hiddenimports = [
    # ... các mục hiện có ...
    # Accessibility
    'pyttsx3', 'pyttsx3.drivers', 'pyttsx3.drivers.sapi5',
    'comtypes', 'comtypes.client',
    # Voice command (chỉ thêm nếu muốn bundle vosk)
    'vosk', 'sounddevice',
]
```

Và nếu muốn bundle Vosk model vào exe (làm tăng kích thước ~40 MB), thêm vào `datas`:

```python
datas = [
    # ... mục hiện có ...
    ('models/vosk-vi', 'models/vosk-vi'),
]
```

> **Lưu ý:** model có thể được giữ ngoài exe (cài thủ công vào thư mục cạnh exe sau khi cài đặt) để giảm size exe. App sẽ tự dò `models/vosk-vi/` cạnh `QuangLuuStudio.exe`.

---

## 8. File liên quan

- `core/accessibility/speaker.py` — TTS engine.
- `core/accessibility/announcer.py` — cầu nối state → TTS.
- `core/accessibility/theme.py` — high-contrast theme.
- `core/accessibility/shortcuts.py` — đăng ký phím tắt.
- `core/accessibility/voice_input.py` — voice command (Vosk).
- `app_config.json` — section `accessibility` lưu cài đặt.
