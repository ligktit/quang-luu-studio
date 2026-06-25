"""
tools/download_voice_models.py
==============================
Tải các model giọng nói tiếng Việt OFFLINE cho Quang Lưu Studio:

  1. Vosk VI "lớn" (ASR chính xác hơn)  → models/vosk-vi-large/
  2. Piper voice neural VI (TTS)         → models/piper-vi/
  3. Piper binary (Windows amd64)        → tools/piper/

Chạy:  python tools/download_voice_models.py [--asr] [--tts] [--all]
Không tham số = --all. Idempotent: bỏ qua phần đã có.

Chỉ dùng stdlib (urllib/zipfile/shutil) — không cần cài thêm gì.
Lưu ý: tổng ~160MB, cần mạng. Model nhỏ Vosk (models/vosk-vi/) đã có sẵn trong repo.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS = os.path.join(ROOT, "models")
TOOLS = os.path.join(ROOT, "tools")

VOSK_LARGE_URL = "https://alphacephei.com/vosk/models/vosk-model-vn-0.4.zip"
VOSK_LARGE_DIR = os.path.join(MODELS, "vosk-vi-large")

PIPER_VOICE_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "vi/vi_VN/vais1000/medium/"
)
PIPER_VOICE_FILES = [
    "vi_VN-vais1000-medium.onnx",
    "vi_VN-vais1000-medium.onnx.json",
]
PIPER_VOICE_DIR = os.path.join(MODELS, "piper-vi")

PIPER_BIN_URL = (
    "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/"
    "piper_windows_amd64.zip"
)
PIPER_BIN_DIR = os.path.join(TOOLS, "piper")


def _download(url: str, dest: str):
    """Tải url → dest với thanh tiến trình (throttle: chỉ in khi % đổi)."""
    print(f"  ↓ {url}")
    state = {"pct": -1}

    def _hook(blocks, bs, total):
        if total > 0:
            pct = min(100, blocks * bs * 100 // total)
            if pct != state["pct"]:
                state["pct"] = pct
                mb = blocks * bs // (1024 * 1024)
                sys.stdout.write(f"\r    {pct:3d}%  ({mb}MB)")
                sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, _hook)
    sys.stdout.write("\r    done            \n")


def _extract_zip(zip_path: str, dest_dir: str) -> str:
    """Giải nén zip; trả tên thư mục gốc đầu tiên trong zip (nếu có)."""
    with zipfile.ZipFile(zip_path) as z:
        top = z.namelist()[0].split("/")[0] if z.namelist() else ""
        z.extractall(dest_dir)
    return top


def fetch_vosk_large(force=False):
    if os.path.isdir(VOSK_LARGE_DIR) and not force:
        print("✓ Vosk lớn đã có:", VOSK_LARGE_DIR)
        return
    print("• Tải Vosk VI lớn...")
    os.makedirs(MODELS, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zp = os.path.join(tmp, "vosk-large.zip")
        _download(VOSK_LARGE_URL, zp)
        top = _extract_zip(zp, tmp)  # vosk-model-vn-0.4/
        src = os.path.join(tmp, top)
        if os.path.isdir(VOSK_LARGE_DIR):
            shutil.rmtree(VOSK_LARGE_DIR, ignore_errors=True)
        shutil.move(src, VOSK_LARGE_DIR)
    print("✓ Xong:", VOSK_LARGE_DIR)


def fetch_piper_voice(force=False):
    onnx = os.path.join(PIPER_VOICE_DIR, PIPER_VOICE_FILES[0])
    if os.path.isfile(onnx) and not force:
        print("✓ Piper voice đã có:", PIPER_VOICE_DIR)
        return
    print("• Tải Piper voice VI...")
    os.makedirs(PIPER_VOICE_DIR, exist_ok=True)
    for fn in PIPER_VOICE_FILES:
        _download(PIPER_VOICE_BASE + fn, os.path.join(PIPER_VOICE_DIR, fn))
    print("✓ Xong:", PIPER_VOICE_DIR)


def fetch_piper_binary(force=False):
    exe = os.path.join(PIPER_BIN_DIR, "piper.exe")
    if os.path.isfile(exe) and not force:
        print("✓ Piper binary đã có:", PIPER_BIN_DIR)
        return
    if os.name != "nt":
        print("! Bỏ qua piper binary (script này tải bản Windows; trên OS khác hãy "
              "cài piper từ package manager).")
        return
    print("• Tải Piper binary (Windows)...")
    os.makedirs(TOOLS, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        zp = os.path.join(tmp, "piper.zip")
        _download(PIPER_BIN_URL, zp)
        # Zip giải nén ra thư mục "piper/" → trực tiếp vào tools/.
        _extract_zip(zp, TOOLS)
    if os.path.isfile(exe):
        print("✓ Xong:", PIPER_BIN_DIR)
    else:
        print("! Không tìm thấy piper.exe sau giải nén — kiểm tra lại:", PIPER_BIN_DIR)


def main():
    ap = argparse.ArgumentParser(description="Tải model giọng nói VI offline.")
    ap.add_argument("--asr", action="store_true", help="Chỉ tải Vosk lớn (ASR)")
    ap.add_argument("--tts", action="store_true", help="Chỉ tải Piper voice + binary (TTS)")
    ap.add_argument("--all", action="store_true", help="Tải tất cả (mặc định)")
    ap.add_argument("--force", action="store_true", help="Tải lại dù đã có")
    args = ap.parse_args()

    do_asr = args.asr or args.all or not (args.asr or args.tts)
    do_tts = args.tts or args.all or not (args.asr or args.tts)

    if do_asr:
        fetch_vosk_large(args.force)
    if do_tts:
        fetch_piper_voice(args.force)
        fetch_piper_binary(args.force)
    print("\nHoàn tất. Vào Cài đặt → Trợ năng để chọn bộ đọc Piper / model Vosk lớn.")


if __name__ == "__main__":
    main()
