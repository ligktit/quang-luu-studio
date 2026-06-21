"""
Quang Lưu Studio — Shared Utilities
Consolidated: find_ffmpeg(), extract_video_id(), atomic_write_json()
"""
import os
import sys
import re
import json
import tempfile


def atomic_write_json(path, data, indent=4):
    """Ghi JSON an toàn (atomic): ghi ra file tạm cùng thư mục rồi os.replace().

    Tránh hỏng file khi app crash/mất điện giữa chừng — os.replace là atomic
    trên cùng volume (Windows + POSIX).
    """
    path = os.path.abspath(path)
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".tmp_" + os.path.basename(path) + ".",
        dir=dir_name
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        # Dọn file tạm nếu ghi/replace thất bại
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def find_ffmpeg():
    """Tự động tìm đường dẫn ffmpeg (setup_all.bat, WinGet, PATH, hoặc thư mục phổ biến)."""
    import shutil, glob
    # 1. Kiểm tra PATH hiện tại
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return os.path.dirname(ffmpeg_path)
    # 2. Tìm trong %LOCALAPPDATA%\FFmpeg (nơi setup_all.bat cài đặt)
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        local_ffmpeg = os.path.join(local_appdata, "FFmpeg")
        if os.path.isfile(os.path.join(local_ffmpeg, "ffmpeg.exe")):
            return local_ffmpeg
    # 3. Tìm trong WinGet packages
    winget_dir = os.path.join(local_appdata, "Microsoft", "WinGet", "Packages")
    if os.path.isdir(winget_dir):
        matches = glob.glob(os.path.join(winget_dir, "**", "ffmpeg.exe"), recursive=True)
        if matches:
            return os.path.dirname(matches[0])
    # 4. Các thư mục phổ biến trên Windows
    for candidate in [r"C:\ffmpeg\bin", r"C:\Program Files\ffmpeg\bin", r"C:\tools\ffmpeg\bin",
                      os.path.join(local_appdata, "Programs", "FFmpeg", "bin") if local_appdata else ""]:
        if candidate and os.path.isfile(os.path.join(candidate, "ffmpeg.exe")):
            return candidate
    # 5. Tìm ffmpeg.exe cùng thư mục với app (PyInstaller bundle)
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        # Also check parent directory (project root) when running from core/
        parent_dir = os.path.dirname(app_dir)
        if os.path.isfile(os.path.join(parent_dir, "ffmpeg.exe")):
            return parent_dir
    if os.path.isfile(os.path.join(app_dir, "ffmpeg.exe")):
        return app_dir
    return None


def extract_video_id(url):
    """Trích xuất YouTube Video ID từ URL (11 ký tự).
    
    Hỗ trợ: youtube.com/watch?v=, youtu.be/, youtube.com/embed/, youtube.com/shorts/
    """
    if not url:
        return None
    patterns = [
        r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def song_match_key(url):
    """Khóa nhận dạng bài hát / timeline tone của một bài.

    Ưu tiên YouTube video_id (để cùng 1 video nhưng khác định dạng link vẫn
    coi là MỘT bài), fallback về URL nguyên văn cho các nguồn không phải
    YouTube (file local, link /live/, URL khác...). Nhờ vậy MỌI bài hát có
    URL đều lưu được chuỗi tone, không chỉ link YouTube chuẩn.
    """
    return extract_video_id(url) or (url or "").strip()
