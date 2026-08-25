"""
Quang Lưu Studio — Bản mẫu file .song của Studio One.

Vấn đề: khách hàng táy máy chỉnh thông số trong Studio One rồi lưu đè, buổi sau
phần mềm chạy sai. Chống bằng cách khoá tay khách không bao giờ đủ — cứ có một
đường nào đó lọt là hỏng bài mẫu vĩnh viễn.

Cách chắc chắn: kỹ thuật viên **chốt bản mẫu** (snapshot) sau khi tinh chỉnh
xong; mỗi lần app khởi động, file .song được chép đè lại từ bản mẫu **trước khi**
Studio One được mở. Nhờ vậy:
  - Khách chỉnh gì cũng chỉ sống trong phiên đó, buổi sau về nguyên trạng.
  - Lúc thoát app được phép Ctrl+S thoải mái → Studio One không hiện hộp thoại
    "lưu hay không" → đóng sạch → lần sau mở không còn cảnh báo phục hồi.

Vị trí lưu: %APPDATA%\\QuangLuuStudio\\so_template\\
  template.song        — bản mẫu kỹ thuật viên đã chốt
  template.json        — thông tin bản mẫu (nguồn, sha256, thời điểm chốt)
  replaced.song        — bản vừa bị chép đè (phao cứu sinh nếu KTV quên chốt)

Chỉ xử lý **file .song**. Nếu đường dẫn Studio One trỏ tới .exe thì tính năng
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


def is_song_file(path) -> bool:
    return bool(path) and str(path).lower().endswith(".song")


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def has_template() -> bool:
    return os.path.isfile(TEMPLATE_FILE)


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
    meta.setdefault("size", os.path.getsize(TEMPLATE_FILE))
    return meta


def snapshot(song_path):
    """Chốt file .song hiện tại làm bản mẫu.

    Trả dict {"ok": bool, "error": str|None, "sha256": str|None}.
    """
    if not is_song_file(song_path):
        return {"ok": False, "error": "Đường dẫn Studio One không phải file .song",
                "sha256": None}
    if not os.path.isfile(song_path):
        return {"ok": False, "error": f"Không tìm thấy file: {song_path}", "sha256": None}

    try:
        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        tmp = TEMPLATE_FILE + ".tmp"
        shutil.copy2(song_path, tmp)
        os.replace(tmp, TEMPLATE_FILE)
        digest = _sha256(TEMPLATE_FILE)
        meta = {
            "source": os.path.abspath(song_path),
            "sha256": digest,
            "size": os.path.getsize(TEMPLATE_FILE),
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
        return {"restored": False, "reason": "đường dẫn không phải file .song"}

    if so_running is None:
        try:
            from core import so_windows
            so_running = so_windows.is_running()
        except Exception:
            so_running = False
    if so_running:
        log.info("Studio One đang chạy — bỏ qua phục hồi bản mẫu")
        return {"restored": False, "reason": "Studio One đang chạy"}

    try:
        if os.path.isfile(song_path) and _sha256(song_path) == _sha256(TEMPLATE_FILE):
            return {"restored": False, "reason": "đã trùng bản mẫu"}
    except Exception as e:
        log.debug("So sánh bản mẫu lỗi: %s", e)

    try:
        os.makedirs(os.path.dirname(os.path.abspath(song_path)) or ".", exist_ok=True)
        # Giữ lại bản vừa bị đè: nếu KTV chỉnh xong mà quên chốt, còn đường lấy về.
        if os.path.isfile(song_path):
            try:
                shutil.copy2(song_path, REPLACED_FILE)
            except Exception as e:
                log.debug("Không sao lưu được bản bị đè: %s", e)
        tmp = song_path + ".qls_tmp"
        shutil.copy2(TEMPLATE_FILE, tmp)
        os.replace(tmp, song_path)
        log.info("Đã phục hồi bản mẫu .song → %s", song_path)
        return {"restored": True, "reason": "đã phục hồi bản mẫu"}
    except Exception as e:
        log.warning("Phục hồi bản mẫu thất bại: %s", e)
        return {"restored": False, "reason": f"lỗi: {e}"}


def clear():
    """Xoá bản mẫu đã chốt."""
    for path in (TEMPLATE_FILE, TEMPLATE_META):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception as e:
            log.debug("Xoá %s lỗi: %s", path, e)
