# 🎵 Hướng dẫn MIDI Mapping - QuangLuuMIDI → Studio One 7

## Yêu cầu

- **loopMIDI** (đã cài và tạo port `QuangLuuMIDI`)
- **Studio One 7** Professional
- **Quang Lưu Studio** app

---

## Bước 1: Cài đặt Control Surface

Chạy script install:

```bash
install_surface.bat
```

Hoặc copy thủ công:
```
Từ:  studio_one\QuangLuuMIDI.surface.xml
Đến: %APPDATA%\PreSonus\Studio One 7\User Devices\QuangLuuMIDI\QuangLuuMIDI.surface.xml
```

---

## Bước 2: Thêm Device trong Studio One

1. Mở **Studio One → Options → External Devices**
2. Click **Add...**
3. Chọn **New Control Surface**
4. Đặt tên: `QuangLuuMIDI`
5. **Receive From:** chọn `QuangLuuMIDI` (loopMIDI port)
6. Click **OK**

---

## Bước 3: Mapping Controls

### Cách 1: MIDI Learn (Nhanh)

1. Click chuột phải vào parameter muốn điều khiển (volume fader, plugin knob...)
2. Chọn **"Assign MIDI Control"** hoặc **"MIDI Learn"**
3. Di chuyển slider/nhấn nút trên app Quang Lưu Studio
4. Done! Parameter đã được gán

### Cách 2: Control Link (Chuyên nghiệp)

1. Mở **Control Link** panel (menu View → Control Link)
2. Bật **MIDI Learn** mode
3. Di chuyển control trên app → Studio One detect CC
4. Click vào parameter trong Studio One
5. Hai bên tự động liên kết

---

## Danh sách MIDI CC Controls

### Tone Controls
| Control | CC | Loại | Range | Chức năng |
|---------|-----|------|-------|-----------|
| Tone Nhạc | 10 | Knob | 0-127 | Pitch shift nhạc (-12 đến +12) |
| Tone Giọng | 11 | Knob | 0-127 | Pitch shift giọng (-12 đến +12) |

### Mixer Controls
| Control | CC | Loại | Range | Chức năng |
|---------|-----|------|-------|-----------|
| Mix Nhạc | 20 | Fader | 0-127 | Volume nhạc (0-100%) |
| Mix Mic | 21 | Fader | 0-127 | Volume mic (0-100%) |
| Mix Vang | 22 | Fader | 0-127 | Reverb level (0-100%) |
| Mix Bè | 23 | Fader | 0-127 | Backing vocal (0-100%) |

### Tone Function Buttons
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Dò Tone | 30 | Button | 0/127 | Toggle dò tone |
| Lấy Tone | 31 | Button | 0/127 | Lấy tone hiện tại |
| Tone Auto | 32 | Button | 0/127 | Toggle auto tone |

### Auto-Tune Controls
| Control | CC | Loại | Range | Chức năng |
|---------|-----|------|-------|-----------|
| AutoTune Key | 34 | Knob | 0-127 | Key cho Auto-Tune (C→B) |
| AutoTune Scale | 35 | Button | 0/127 | Scale (0=Major, 127=Minor) |
| Tune On/Off | 36 | Button | 0/127 | Bật/tắt Auto-Tune (0=Off, 127=On) |

### Mixer Function Buttons
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Bè | 40 | Button | 0/127 | Toggle bè |
| Vang | 41 | Button | 0/127 | Toggle vang |
| Nhạc | 42 | Button | 0/127 | Toggle nhạc |
| Fix Méo | 43 | Button | 0/127 | Toggle fix méo |

### Mixer Mute Toggles (Icon buttons bên dưới thanh cuộn)
| Control | CC | Loại | Values | Chức năng |
|---------|-----|------|--------|-----------|
| Mute Nhạc | 50 | Button | 0/127 | Tắt/mở kênh nhạc |
| Mute Mic | 51 | Button | 0/127 | Tắt/mở kênh mic |
| Mute Vang | 52 | Button | 0/127 | Tắt/mở reverb |
| Mute Bè | 53 | Button | 0/127 | Tắt/mở backing vocal |

---

## Troubleshooting

### Studio One không nhận MIDI?
- Kiểm tra **loopMIDI** đang chạy và có port `QuangLuuMIDI`
- Kiểm tra **External Devices** đã chọn đúng MIDI input port
- Thử restart Studio One sau khi thêm device

### Control không xuất hiện trong danh sách?
- Kiểm tra file `.surface.xml` đã nằm đúng thư mục
- Chạy lại `install_surface.bat`
- Restart Studio One

### MIDI Learn không hoạt động?
- Đảm bảo app Quang Lưu Studio đang kết nối MIDI (thanh status hiện "Đã kết nối")
- Thử gửi MIDI CC bằng cách di chuyển slider trong app trước khi MIDI Learn
