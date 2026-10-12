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
    popen(["cmd.exe", "/c", name], cwd=app_dir, creationflags=_NEW_CONSOLE)
    return True


def open_folder(path, opener=None):
    if not os.path.isdir(path):
        return False
    (opener or os.startfile)(path)
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


def build_wipe_command(pid, targets):
    """PowerShell (ẩn): chờ tiến trình `pid` thoát rồi xoá từng thư mục."""
    lit = lambda s: "'" + s.replace("'", "''") + "'"  # noqa: E731 — chuỗi PowerShell nháy đơn
    lines = [f"Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue"]
    lines += [f"Remove-Item -LiteralPath {lit(t)} -Recurse -Force -ErrorAction SilentlyContinue"
              for t in targets]
    enc = base64.b64encode("; ".join(lines).encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", enc]


def schedule_wipe_after_exit(targets, popen=subprocess.Popen, pid=None):
    if not targets:
        return False
    popen(build_wipe_command(pid or os.getpid(), targets), creationflags=_DETACHED, close_fds=True)
    log.warning("Đã hẹn xoá dữ liệu sau khi app thoát: %s", targets)
    return True
