"""Công cụ mở từ Cài đặt → Công cụ.

Thay các shortcut Start Menu của bộ cài Inno cũ (Velopack chỉ tạo shortcut cho exe
chính) và thêm "Xoá dữ liệu" — gỡ cài đặt Velopack cố ý GIỮ %APPDATA% và Documents.
Không đụng Qt để test được.
"""
import base64
import logging
import os
import subprocess

log = logging.getLogger(__name__)

DATA_FOLDER_NAME = "QuangLuuStudio"
_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
_DETACHED = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def launch_bat(app_dir, name, popen=subprocess.Popen):
    """Mở <app_dir>\\<name> trong cửa sổ console riêng (.bat tự `pause` ở cuối)."""
    if not os.path.isfile(os.path.join(app_dir, name)):
        log.warning("Thiếu %s trong %s", name, app_dir)
        return False
    # Tên .bat đứng riêng + cwd: đường dẫn có ( ) & không làm vỡ dòng lệnh cmd.
    try:
        popen(["cmd.exe", "/c", name], cwd=app_dir, creationflags=_NEW_CONSOLE)
    except OSError:
        log.warning("Không chạy được %s", name, exc_info=True)
        return False
    return True


def open_folder(path, opener=None):
    if not os.path.isdir(path):
        return False
    try:
        (opener or os.startfile)(path)
    except OSError:
        log.warning("Không mở được thư mục %s", path, exc_info=True)
        return False
    return True


def wipe_targets(data_dir, recordings_dir, include_recordings, frozen):
    """Thư mục sẽ xoá. Chỉ bản đóng gói (chạy từ mã nguồn DATA_DIR = gốc repo!), và chỉ
    thư mục tên đúng "QuangLuuStudio" — không bao giờ một thư mục cha/gốc ổ."""
    if not frozen:
        return []
    out = []
    for d in [data_dir] + ([recordings_dir] if include_recordings else []):
        p = os.path.abspath(d or "")
        if os.path.basename(p.rstrip("\\/")) == DATA_FOLDER_NAME and os.path.isdir(p):
            out.append(p)
    return out


WIPE_LOG_NAME = "QuangLuuStudio_xoa_du_lieu.log"
WIPE_ATTEMPTS = 10
WIPE_RETRY_SECONDS = 2


def build_wipe_command(pid, targets):
    """PowerShell (ẩn): chờ tiến trình `pid` thoát rồi xoá từng thư mục.

    Mỗi thư mục thử tối đa WIPE_ATTEMPTS lần, cách nhau WIPE_RETRY_SECONDS giây (Update.exe
    hoặc ffmpeg/yt-dlp con có thể còn giữ file ngay sau khi app thoát). Nếu vẫn còn thì ghi
    một dòng vào %TEMP%\\QuangLuuStudio_xoa_du_lieu.log (ngoài thư mục bị xoá)."""
    lit = lambda s: "'" + s.replace("'", "''") + "'"  # noqa: E731 — chuỗi PowerShell nháy đơn
    lines = [f"Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue",
             f"$log = Join-Path $env:TEMP {lit(WIPE_LOG_NAME)}"]
    for t in targets:
        p = lit(t)
        lines.append(
            "$err = ''; "
            f"for ($i = 0; $i -lt {WIPE_ATTEMPTS}; $i++) {{ "
            f"try {{ Remove-Item -LiteralPath {p} -Recurse -Force -ErrorAction Stop }} "
            "catch { $err = $_.Exception.Message }; "
            f"if (-not (Test-Path -LiteralPath {p})) {{ break }}; "
            f"Start-Sleep -Seconds {WIPE_RETRY_SECONDS} }}; "
            f"if (Test-Path -LiteralPath {p}) {{ "
            f"Add-Content -LiteralPath $log -Value (\"$(Get-Date -Format s) \" + {p} + \" $err\") }}")
    enc = base64.b64encode("\n".join(lines).encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", enc]


def schedule_wipe_after_exit(targets, popen=subprocess.Popen, pid=None):
    if not targets:
        return False
    try:
        popen(build_wipe_command(pid or os.getpid(), targets), creationflags=_DETACHED, close_fds=True)
    except OSError:
        log.warning("Không hẹn được việc xoá dữ liệu", exc_info=True)
        return False
    log.warning("Đã hẹn xoá dữ liệu sau khi app thoát: %s", targets)
    return True
