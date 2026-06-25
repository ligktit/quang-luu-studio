# Model giọng nói tiếng Việt (offline)

App có 2 phân hệ giọng nói, mỗi phân hệ giờ hỗ trợ **2 model** để chọn trong
**Cài đặt → Trợ năng**:

## 1. Giọng đọc (TTS — output)
| Bộ đọc | Mô tả | Yêu cầu |
|---|---|---|
| **SAPI5** (mặc định) | Giọng hệ thống Windows (`pyttsx3`). Phụ thuộc máy có giọng vi-VN. | Không |
| **Piper neural** (mới) | Giọng tiếng Việt tự nhiên, chạy offline qua binary `piper`. | `tools/piper/` + `models/piper-vi/*.onnx` |

Code: `core/accessibility/speaker.py` (định tuyến engine) + `core/accessibility/tts_piper.py`
(backend Piper: synth qua subprocess `piper --output-raw`, phát bằng `sounddevice`).
Fail-soft: thiếu binary/voice → tự quay về SAPI.

## 2. Nhận lệnh (ASR — input, Ctrl+Space)
| Model | Mô tả | Thư mục |
|---|---|---|
| **Vosk nhỏ** (mặc định) | Nhẹ, nhanh; đủ cho lệnh ngắn. WER ~15.7%. | `models/vosk-vi/` (có sẵn trong repo) |
| **Vosk lớn** (mới) | Chính xác hơn, nặng hơn. | `models/vosk-vi-large/` |

Code: `core/accessibility/voice_input.py` (`MODEL_DIRS`, `available_variants`, `variant=`).

## Tải model
```bash
python tools/download_voice_models.py        # tải tất cả (~160MB)
python tools/download_voice_models.py --tts   # chỉ Piper (voice + binary)
python tools/download_voice_models.py --asr   # chỉ Vosk lớn
```
Idempotent (bỏ qua phần đã có). Nguồn: alphacephei (Vosk), HuggingFace
`rhasspy/piper-voices` (voice), GitHub `rhasspy/piper` releases (binary Windows).

## Đóng gói (build)
- Build là **onefile** → model KHÔNG nhúng vào exe (tránh phình + giải nén lại mỗi
  lần chạy). Installer (`QuangLuuStudio_Setup.iss`) ship `models/` và `tools/piper/`
  **cạnh exe**; resolver kiểm tra dir(exe) trước, rồi `_MEIPASS`, rồi project root.
- Chạy `tools/download_voice_models.py` **trước khi build** để có model đóng vào installer.
- Model lớn được `.gitignore` (không commit binary nặng vào repo).
