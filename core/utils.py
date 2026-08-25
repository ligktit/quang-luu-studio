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
    # 5. Bản đóng gói kèm bộ cài: <app>\ffmpeg\ hoặc ngay cạnh exe.
    #    Đây mới là nguồn CHẮC CHẮN có — 4 nấc trên đều phụ thuộc máy khách đã
    #    cài sẵn ffmpeg ở đâu đó, mà rất nhiều máy thì không.
    for base in _app_search_dirs():
        bundled = os.path.join(base, "ffmpeg")
        if os.path.isfile(os.path.join(bundled, "ffmpeg.exe")):
            return bundled
        if os.path.isfile(os.path.join(base, "ffmpeg.exe")):
            return base
    return None


def _app_search_dirs():
    """Các thư mục để tìm binary đi kèm app: cạnh exe (frozen) / gốc dự án (dev)."""
    if getattr(sys, 'frozen', False):
        return [os.path.dirname(sys.executable)]
    core_dir = os.path.dirname(os.path.abspath(__file__))
    return [os.path.dirname(core_dir), core_dir]


def find_js_runtime():
    """Tìm `qjs.exe` (QuickJS-ng) đi kèm app — runtime JavaScript cho yt-dlp.

    Vì sao cần: từ cuối 2025 yt-dlp phải chạy JavaScript ngoài để giải "n
    challenge" của YouTube. Không có runtime nào thì link tải bị bóp băng thông
    hoặc trả 403, kể cả khi bóc được định dạng. Deno là mặc định của yt-dlp
    nhưng nặng ~40MB; QuickJS-ng chỉ ~2MB nên gói kèm được cả bản Nhẹ.

    Trả đường dẫn tới file, hoặc None nếu không tìm thấy (yt-dlp sẽ tự tìm
    `deno` trên PATH — vẫn dùng được nếu máy khách có sẵn).
    """
    import shutil
    for base in _app_search_dirs():
        for candidate in (os.path.join(base, "qjs.exe"),
                          os.path.join(base, "bin", "qjs.exe")):
            if os.path.isfile(candidate):
                return candidate
    found = shutil.which("qjs")
    return found or None


def extract_video_id(url):
    """Trích xuất YouTube Video ID từ URL (11 ký tự).

    Hỗ trợ: youtube.com/watch?v=, youtu.be/, youtube.com/embed/,
    youtube.com/shorts/, youtube.com/live/

    Với dạng watch?…v=…, chỉ bắt ĐÚNG tham số `v` (ranh giới [?&]v=) để không
    khớp nhầm các tham số nhiễu kết thúc bằng "v" như `ved=…`.
    """
    if not url:
        return None
    patterns = [
        # watch?v=… : YÊU CẦU ranh giới tham số ([?&]v=) để KHÔNG nuốt nhầm
        # các tham số khác kết thúc bằng "v" (vd ved=…&v=…). Trước đây dùng
        # ".*v=" có thể bắt 11 ký tự ngay sau "ved=" thay vì tham số v thật.
        r'youtube\.com/watch\?(?:[^#]*&)?v=([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/live/)([a-zA-Z0-9_-]{11})',
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
