"""
Quang Lưu Studio — Bản mẫu file .song của Studio One.

Vấn đề: khách hàng táy máy chỉnh thông số trong Studio One rồi lưu đè, buổi sau
phần mềm chạy sai. Chống bằng cách khoá tay khách không bao giờ đủ — cứ có một
đường nào đó lọt là hỏng bài mẫu vĩnh viễn.

Cách chắc chắn: kỹ thuật viên **chốt bản mẫu** (snapshot) sau khi tinh chỉnh
xong; mỗi lần app khởi động, file .song được chép đè lại từ bản mẫu **trước khi**
Studio One được mở. Nhờ vậy:
  - Khách chỉnh gì cũng chỉ sống trong phiên đó, buổi sau về nguyên trạng.
  - Lúc thoát app không cần lưu gì cả: hộp thoại "lưu hay không" của Studio One
    được trả lời bằng nút "Don't Save" (xem close_studio_one_safely). Có bản mẫu
    ở đây còn mở thêm nước cuối `fallback_save` cho luồng thoát — hụt nút đó thì
    lưu cũng vô hại vì bản mẫu chép đè ngay lần khởi động sau.

Vị trí lưu: %APPDATA%\\QuangLuuStudio\\so_template\\
  template.song        — bản mẫu kỹ thuật viên đã chốt (Cubase: template.cpr)
  template.json        — thông tin bản mẫu (nguồn, sha256, thời điểm chốt)
  replaced.song        — bản vừa bị chép đè (phao cứu sinh nếu KTV quên chốt)
                         (Cubase: replaced.cpr)

Chỉ xử lý **file bài của DAW đang chọn** (đuôi file theo hồ sơ DAW: .song cho
Studio One, .cpr cho Cubase; mỗi DAW có bản mẫu riêng). Nếu đường dẫn Studio One trỏ tới .exe thì tính năng
này không áp dụng (không có file bài để phục hồi).
"""
import hashlib
import json
import logging
import os
import shutil
import time

from core.config import DATA_DIR

log = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(DATA_DIR, "so_template")
TEMPLATE_FILE = os.path.join(TEMPLATE_DIR, "template.song")
TEMPLATE_META = os.path.join(TEMPLATE_DIR, "template.json")
REPLACED_FILE = os.path.join(TEMPLATE_DIR, "replaced.song")


def _profile(profile=None):
    from core import daw
    return profile or daw.active()


def template_file(profile=None) -> str:
    p = _profile(profile)
    if p.kind == "studio_one":
        return TEMPLATE_FILE
    return os.path.join(TEMPLATE_DIR, "template" + p.template_extension)


def replaced_file(profile=None) -> str:
    p = _profile(profile)
    if p.kind == "studio_one":
        return REPLACED_FILE
    return os.path.join(TEMPLATE_DIR, "replaced" + p.template_extension)


def is_song_file(path) -> bool:
    """Đường dẫn có phải file bài của DAW đang chọn không (.song / .cpr)."""
    from core import daw
    return daw.is_project_file(path)


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def has_template() -> bool:
    return os.path.isfile(template_file())


def info():
    """Thông tin bản mẫu đã chốt, hoặc None."""
    if not has_template():
        return None
    meta = {}
    try:
        with open(TEMPLATE_META, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        pass
    meta.setdefault("size", os.path.getsize(template_file()))
    return meta


def snapshot(song_path):
    """Chốt file .song hiện tại làm bản mẫu.

    Trả dict {"ok": bool, "error": str|None, "sha256": str|None}.
    """
    if not is_song_file(song_path):
        return {"ok": False, "error": f"Đường dẫn không phải file bài {_profile().template_extension}",
                "sha256": None}
    if not os.path.isfile(song_path):
        return {"ok": False, "error": f"Không tìm thấy file: {song_path}", "sha256": None}

    try:
        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        tmp = template_file() + ".tmp"
        shutil.copy2(song_path, tmp)
        os.replace(tmp, template_file())
        digest = _sha256(template_file())
        meta = {
            "source": os.path.abspath(song_path),
            "sha256": digest,
            "size": os.path.getsize(template_file()),
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(TEMPLATE_META, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        log.info("Đã chốt bản mẫu .song từ %s (sha %s...)", song_path, digest[:12])
        return {"ok": True, "error": None, "sha256": digest}
    except Exception as e:
        log.warning("Chốt bản mẫu thất bại: %s", e)
        return {"ok": False, "error": str(e), "sha256": None}


def restore(song_path, so_running=None):
    """Chép đè bản mẫu lên file .song đang dùng.

    Bỏ qua (không phải lỗi) khi: chưa chốt bản mẫu, đường dẫn không phải .song,
    nội dung đã trùng bản mẫu, hoặc Studio One đang chạy (ghi đè lúc đó sẽ hỏng
    file đang mở).

    Trả dict {"restored": bool, "reason": str}.
    """
    if not has_template():
        return {"restored": False, "reason": "chưa chốt bản mẫu"}
    if not is_song_file(song_path):
        return {"restored": False, "reason": f"đường dẫn không phải file bài {_profile().template_extension}"}

    if so_running is None:
        try:
            from core import so_windows
            so_running = so_windows.is_running()
        except Exception:
            so_running = False
    if so_running:
        log.info("%s đang chạy — bỏ qua phục hồi bản mẫu", _profile().display_name)
        return {"restored": False, "reason": f"{_profile().display_name} đang chạy"}

    try:
        if os.path.isfile(song_path) and _sha256(song_path) == _sha256(template_file()):
            return {"restored": False, "reason": "đã trùng bản mẫu"}
    except Exception as e:
        log.debug("So sánh bản mẫu lỗi: %s", e)

    try:
        os.makedirs(os.path.dirname(os.path.abspath(song_path)) or ".", exist_ok=True)
        # Giữ lại bản vừa bị đè: nếu KTV chỉnh xong mà quên chốt, còn đường lấy về.
        if os.path.isfile(song_path):
            try:
                shutil.copy2(song_path, replaced_file())
            except Exception as e:
                log.debug("Không sao lưu được bản bị đè: %s", e)
        tmp = song_path + ".qls_tmp"
        shutil.copy2(template_file(), tmp)
        os.replace(tmp, song_path)
        log.info("Đã phục hồi bản mẫu .song → %s", song_path)
        return {"restored": True, "reason": "đã phục hồi bản mẫu"}
    except Exception as e:
        log.warning("Phục hồi bản mẫu thất bại: %s", e)
        return {"restored": False, "reason": f"lỗi: {e}"}


def clear():
    """Xoá bản mẫu đã chốt."""
    for path in (template_file(), TEMPLATE_META):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception as e:
            log.debug("Xoá %s lỗi: %s", path, e)
