# Hướng dẫn Build EXE

## ⚠️ Lưu ý quan trọng

**KHÔNG chạy:** `PyInstaller --onefile main.py`

Lý do: PyInstaller sẽ tự động tạo lại file `main.spec` và ghi đè các cấu hình `hiddenimports` đã được thiết lập.

## ✅ Cách build đúng

### Bước 1: Đảm bảo file spec đã có hiddenimports

File `main.spec` phải có:
```python
hiddenimports=[
    'rtmidi',
    'mido.backends.rtmidi',
    'mido.backends.rtmidi.backend',
],
```

### Bước 2: Build từ file spec

```bash
PyInstaller main.spec
```

Hoặc nếu muốn build onefile:

```bash
PyInstaller --onefile main.spec
```

## 🔧 Tạo file spec mới (nếu cần)

Nếu muốn tạo file spec mới với các tùy chọn:

```bash
PyInstaller --onefile --name=main main.py
```

Sau đó chỉnh sửa file `main.spec` để thêm `hiddenimports` như trên, rồi build lại:

```bash
PyInstaller main.spec
```

## 📝 Tóm tắt

- ✅ **ĐÚNG:** `PyInstaller main.spec`
- ❌ **SAI:** `PyInstaller --onefile main.py` (sẽ ghi đè spec file)
