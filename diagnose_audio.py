"""
Quang Lưu Studio — Audio Device Diagnostics
Liệt kê toàn bộ thiết bị âm thanh, host API, và kiểm tra khả năng loopback.
Chạy: python diagnose_audio.py
"""
import sys

try:
    import pyaudiowpatch as pyaudio
except ImportError:
    print("❌ pyaudiowpatch chưa được cài. Chạy: pip install pyaudiowpatch")
    sys.exit(1)

print("=" * 65)
print("  Quang Lưu Studio — Audio Device Diagnostics")
print("=" * 65)

pa = pyaudio.PyAudio()

# ── 1. Host APIs ──────────────────────────────────────────────────
print("\n📡 HOST APIs:")
api_count = pa.get_host_api_count()
for i in range(api_count):
    info = pa.get_host_api_info_by_index(i)
    print(f"  [{i}] {info['name']!r:35s} "
          f"defaultInput={info.get('defaultInputDevice', -1)} "
          f"defaultOutput={info.get('defaultOutputDevice', -1)}")

# ── 2. Tất cả devices ────────────────────────────────────────────
print("\n🎛️  ALL DEVICES:")
print(f"{'Idx':<4} {'Name':<42} {'API':<18} {'In':>3} {'Out':>3} {'Rate':>7} {'Loopback'}")
print("-" * 90)

wasapi_idx = None
asio_idx = None
all_devs = []

for i in range(api_count):
    api = pa.get_host_api_info_by_index(i)
    name_lower = api["name"].lower()
    if "wasapi" in name_lower:
        wasapi_idx = i
    if "asio" in name_lower:
        asio_idx = i

for i in range(pa.get_device_count()):
    try:
        d = pa.get_device_info_by_index(i)
        api_info = pa.get_host_api_info_by_index(d["hostApi"])
        api_name = api_info["name"]
        is_lb = d.get("isLoopbackDevice", False)
        print(f"  {i:<3} {d['name'][:40]:<42} {api_name[:18]:<18} "
              f"{d['maxInputChannels']:>3} {d['maxOutputChannels']:>3} "
              f"{int(d['defaultSampleRate']):>7} {'✅ LOOPBACK' if is_lb else ''}")
        all_devs.append(d)
    except Exception as e:
        print(f"  {i:<3} ERROR: {e}")

# ── 3. Kiểm tra WASAPI Loopback cụ thể ──────────────────────────
print("\n🔍 WASAPI LOOPBACK DEVICES:")
if wasapi_idx is None:
    print("  ❌ Không tìm thấy WASAPI host API! Driver âm thanh có vấn đề.")
else:
    loopbacks_found = []
    for d in all_devs:
        if d.get("isLoopbackDevice", False) and d["hostApi"] == wasapi_idx:
            loopbacks_found.append(d)
            print(f"  ✅ [{d['index']}] {d['name']!r}  rate={int(d['defaultSampleRate'])}  ch={d['maxInputChannels']}")

    if not loopbacks_found:
        print("  ❌ Không có WASAPI loopback device nào!")
        print()
        print("  ⚠️  Nguyên nhân thường gặp:")
        print("  - ASIO driver (như ASIOVADPRO) chiếm exclusive mode → WASAPI bị bypass")
        print("  - Trong Device Manager, WASAPI loopback bị tắt")
        print("  - Không có audio đang phát (một số driver tắt loopback khi không có audio)")

    # Thử dùng API helper của pyaudiowpatch
    print("\n  📋 Thử pyaudiowpatch helper API:")
    try:
        gen = list(pa.get_loopback_device_info_generator())
        if gen:
            for d in gen:
                print(f"  ✅ [generator] [{d['index']}] {d['name']!r}  rate={int(d['defaultSampleRate'])}")
        else:
            print("  ❌ get_loopback_device_info_generator() trả về rỗng")
    except AttributeError:
        print("  ⚠️  Phiên bản pyaudiowpatch không có get_loopback_device_info_generator()")
    except Exception as e:
        print(f"  ❌ Lỗi: {e}")

    # Thử lấy loopback analogue của default output
    print("\n  📋 Thử get_wasapi_loopback_analogue_by_index():")
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default_out_idx = wasapi_info.get("defaultOutputDevice", -1)
        if default_out_idx >= 0:
            default_out = pa.get_device_info_by_index(default_out_idx)
            print(f"  Default output: [{default_out_idx}] {default_out['name']!r}")
            analogue = pa.get_wasapi_loopback_analogue_by_index(default_out_idx)
            if analogue:
                print(f"  ✅ Loopback analogue: [{analogue['index']}] {analogue['name']!r}")
            else:
                print("  ❌ Không tìm được loopback analogue cho default output")
        else:
            print("  ❌ Không có default output device")
    except AttributeError:
        print("  ⚠️  Phiên bản pyaudiowpatch không có get_wasapi_loopback_analogue_by_index()")
    except Exception as e:
        print(f"  ❌ Lỗi: {e}")

# ── 4. ASIO ──────────────────────────────────────────────────────
print("\n🎵 ASIO STATUS:")
if asio_idx is None:
    print("  ℹ️  Không tìm thấy ASIO host API.")
    print("  ℹ️  pyaudiowpatch prebuilt wheel KHÔNG hỗ trợ ASIO.")
else:
    print(f"  ⚠️  ASIO host API tìm thấy (index={asio_idx}).")
    print("  ⚠️  ASIO chiếm exclusive mode → WASAPI Loopback sẽ KHÔNG hoạt động!")
    print("  ⚠️  Cần tắt ASIO exclusive mode hoặc dùng virtual cable thay thế.")

# ── 5. Default devices ───────────────────────────────────────────
print("\n🎧 DEFAULT DEVICES:")
try:
    di = pa.get_default_input_device_info()
    print(f"  Default Input : [{di['index']}] {di['name']!r}"
          f"  ch={di['maxInputChannels']}  rate={int(di['defaultSampleRate'])}")
except Exception as e:
    print(f"  Default Input : ❌ {e}")

try:
    do = pa.get_default_output_device_info()
    print(f"  Default Output: [{do['index']}] {do['name']!r}"
          f"  ch={do['maxOutputChannels']}  rate={int(do['defaultSampleRate'])}")
except Exception as e:
    print(f"  Default Output: ❌ {e}")

pa.terminate()

print()
print("=" * 65)
print("  Nếu không có WASAPI Loopback, xem hướng dẫn sửa ở trên.")
print("=" * 65)
