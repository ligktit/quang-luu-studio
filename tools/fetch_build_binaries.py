"""
Tải các binary phụ trợ vào `binaries/` trước khi đóng gói bộ cài.

Chạy tự động từ build_installer.bat / build_installer_heavy.bat. Không commit
các file này vào git (đã có trong .gitignore) — chúng nặng và thay đổi theo bản.

Gồm 2 thứ, đều phục vụ MỘT mục tiêu: máy khách tải được YouTube mà không cần
tài khoản, không cần cookie, không cần cài thêm gì.

  qjs.exe  — QuickJS-ng, runtime JavaScript để yt-dlp giải "n challenge" của
             YouTube. Bắt buộc từ cuối 2025; thiếu nó thì link tải bị bóp băng
             thông hoặc trả 403. Chỉ ~2MB nên gói được cả vào bản Nhẹ.
             (Deno là mặc định của yt-dlp nhưng nặng ~40MB.)

  ffmpeg/  — ffmpeg + ffprobe bản LGPL shared. Trước đây chỉ setup_all.bat tải
             về %LOCALAPPDATA%; máy nào cài lỗi mạng là mất luôn chấm điểm và dò
             tone. Nay gói thẳng vào bộ cài.

Dùng:  python tools/fetch_build_binaries.py [--skip-ffmpeg] [--force]
"""
import io
import os
import sys
import shutil
import hashlib
import zipfile
import argparse
import subprocess
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(ROOT, "binaries")

# ── QuickJS-ng ───────────────────────────────────────────────────────────────
# Asset của một bản phát hành cố định → ghim được sha256.
QJS_VERSION = "v0.16.1"
QJS_URL = (
    "https://github.com/quickjs-ng/quickjs/releases/download/"
    f"{QJS_VERSION}/qjs-windows-x86_64.exe"
)
QJS_SHA256 = "55a1b69cd4fdb6b0d3f8fdd910d0e89519f5330e408462084140c7b3b964fdae"

# ── ffmpeg ───────────────────────────────────────────────────────────────────
# Asset "latest" của BtbN được build lại liên tục nên KHÔNG ghim sha256 được;
# bù lại script kiểm tra zip hợp lệ + chạy thử `ffmpeg -version`, và in sha256
# ra màn hình để người build ghi lại vào nhật ký phát hành nếu cần.
FFMPEG_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-n9.0-latest-win64-lgpl-shared-9.0.zip"
)
# Không cần cho app — bỏ đi để bộ cài nhẹ bớt.
FFMPEG_SKIP = ("ffplay.exe",)


def _download(url, expected_sha256=None):
    print(f"  tai: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "QuangLuuStudio/build"})
    with urllib.request.urlopen(request, timeout=300) as response:
        payload = response.read()
    digest = hashlib.sha256(payload).hexdigest()
    print(f"  {len(payload)/1048576:.1f} MB  sha256={digest}")
    if expected_sha256 and digest != expected_sha256:
        raise SystemExit(
            f"LOI: sai sha256.\n  mong doi: {expected_sha256}\n  nhan duoc: {digest}"
        )
    return payload


def fetch_qjs(force=False):
    target = os.path.join(BIN_DIR, "qjs.exe")
    if os.path.isfile(target) and not force:
        with open(target, "rb") as handle:
            if hashlib.sha256(handle.read()).hexdigest() == QJS_SHA256:
                print("[qjs] da co, dung phien ban -> bo qua")
                return target
    print(f"[qjs] {QJS_VERSION}")
    payload = _download(QJS_URL, QJS_SHA256)
    os.makedirs(BIN_DIR, exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(payload)
    print(f"[qjs] -> {target}")
    return target


def fetch_ffmpeg(force=False):
    target_dir = os.path.join(BIN_DIR, "ffmpeg")
    exe = os.path.join(target_dir, "ffmpeg.exe")
    if os.path.isfile(exe) and not force:
        print("[ffmpeg] da co -> bo qua (dung --force de tai lai)")
        return target_dir

    print("[ffmpeg] LGPL shared build (BtbN)")
    payload = _download(FFMPEG_URL)

    staging = target_dir + ".new"
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    count = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in archive.namelist():
            parts = name.split("/")
            # Bo cuc: ffmpeg-.../bin/<file>  -> chi lay thu muc bin
            if len(parts) < 3 or parts[-2] != "bin" or not parts[-1]:
                continue
            leaf = parts[-1]
            if leaf in FFMPEG_SKIP:
                continue
            with archive.open(name) as source, \
                    open(os.path.join(staging, leaf), "wb") as handle:
                shutil.copyfileobj(source, handle)
            count += 1

    if not os.path.isfile(os.path.join(staging, "ffmpeg.exe")):
        shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit("LOI: goi ffmpeg khong chua bin/ffmpeg.exe")

    try:
        out = subprocess.run(
            [os.path.join(staging, "ffmpeg.exe"), "-version"],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:200])
        print("  " + (out.stdout.splitlines() or [""])[0])
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit(f"LOI: ffmpeg vua tai khong chay duoc: {exc}")

    shutil.rmtree(target_dir, ignore_errors=True)
    os.replace(staging, target_dir)
    size = sum(
        os.path.getsize(os.path.join(target_dir, f)) for f in os.listdir(target_dir)
    )
    print(f"[ffmpeg] -> {target_dir}  ({count} file, {size/1048576:.1f} MB)")
    return target_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-ffmpeg", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    os.makedirs(BIN_DIR, exist_ok=True)
    fetch_qjs(force=args.force)
    if not args.skip_ffmpeg:
        fetch_ffmpeg(force=args.force)
    print("Xong.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
