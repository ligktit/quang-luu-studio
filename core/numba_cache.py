"""Cache biên dịch của numba — để riêng cho app và tự chữa khi hỏng.

librosa dùng numba với ``cache=True``: lần chạy đầu numba biên dịch vài hàm rồi
ghi kết quả ra đĩa (``.nbi`` là mục lục, ``.nbc`` là mã máy). Nếu máy tắt ngang,
mất điện, ổ đầy hay phần mềm diệt virus chen vào đúng lúc đang ghi, file mục lục
còn lại toàn byte 0x00.

numba KHÔNG tự chữa: mỗi lần sau nó đọc lại file hỏng rồi ném
``UnpicklingError: invalid load key, '\\x00'``. Lỗi bật ra ngay lúc nạp
``librosa.util.utils``, tức TRƯỚC khi chạm tới audio, nên mọi lần dò tone đều
hỏng như nhau cho tới khi có người xoá cache bằng tay. Nhật ký ngày 15/09/2026
cho thấy đúng cảnh đó: 22 lần dò tone liên tiếp, cùng một lỗi, người dùng chỉ
thấy "phân tích âm điệu bị lỗi, vui lòng thử lại" và thử lại bao nhiêu cũng vậy.

Hai lớp phòng ở đây:

1. :func:`activate_private_cache` — ép numba ghi cache vào thư mục dữ liệu của
   app. Thư mục cài có thể chỉ đọc (Program Files) và cache chung
   ``%LOCALAPPDATA%\\numba`` thì app không nên đụng vào; cache riêng là thứ app
   có toàn quyền xoá.
2. :func:`sweep_corrupt` — lúc mở app, quét cache và xoá riêng file hỏng. Rẻ
   (chỉ đọc vài file nhỏ, không nạp numba) nên chạy nền được ở mọi lần khởi
   động, chữa trước cả khi người dùng bấm dò tone.
3. :func:`run_healing` — bọc lời gọi librosa đầu tiên của mỗi luồng phân tích
   (``librosa.load`` / ``librosa.resample``, chỗ numba thật sự đọc cache): gặp
   lỗi cache hỏng thì xoá cache rồi gọi lại một lần. Người dùng chỉ thấy lần dò
   tone đó chậm hơn mươi giây (numba biên dịch lại), thay vì hỏng vĩnh viễn.

Cố ý KHÔNG nạp sẵn ``librosa.util.utils`` để bắt lỗi sớm: làm vậy là kéo cả
numba/llvmlite vào bộ nhớ ngay từ lời gọi đầu, trong khi librosa vốn nạp lười.
"""

import os
import pickle
import shutil
from pathlib import Path

from core.logger import get_logger

log = get_logger(__name__)

# Tên thư mục cache nằm trong thư mục dữ liệu app (%APPDATA%/QuangLuuStudio).
_CACHE_DIR_NAME = "numba_cache"

# Lỗi pickle ném ra khi đọc phải file mục lục hỏng.
_UNPICKLE_ERRORS = (pickle.UnpicklingError, EOFError)


def cache_dir() -> Path:
    """Thư mục cache numba của app (tự tạo nếu chưa có)."""
    from core.config import _get_data_dir

    path = Path(_get_data_dir()) / _CACHE_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def activate_private_cache() -> str:
    """Trỏ NUMBA_CACHE_DIR về thư mục riêng của app.

    Phải gọi TRƯỚC lần nạp numba/librosa đầu tiên — numba đọc biến môi trường
    này lúc nạp module. Tôn trọng lựa chọn của người dùng nếu họ đã tự đặt sẵn.
    """
    existing = os.environ.get("NUMBA_CACHE_DIR")
    if existing:
        return existing
    try:
        path = str(cache_dir())
    except Exception as exc:          # ổ đầy / không có quyền ghi
        log.warning("Không đặt được thư mục cache numba riêng: %s", exc)
        return ""
    os.environ["NUMBA_CACHE_DIR"] = path
    return path


def is_corrupt_cache_error(exc: BaseException) -> bool:
    """Lỗi này có phải do file cache numba hỏng không?

    Nhận diện theo hai dấu hiệu, chỉ cần một là đủ: traceback có đi qua
    ``numba/core/caching.py``, hoặc thông báo lỗi mang đúng chữ ký của file
    toàn byte 0x00.
    """
    tb = getattr(exc, "__traceback__", None)
    while tb is not None:
        name = tb.tb_frame.f_code.co_filename.replace("\\", "/").lower()
        if "numba" in name and "caching" in name:
            return True
        tb = tb.tb_next
    return isinstance(exc, _UNPICKLE_ERRORS) and "invalid load key" in str(exc)


def scan_corrupt() -> list:
    """Liệt kê các file mục lục (.nbi) không đọc được trong cache của app.

    Dùng cho bộ tự kiểm tra: soi thẳng trạng thái đĩa, không cần biên dịch gì.
    """
    bad = []
    try:
        files = sorted(cache_dir().rglob("*.nbi"))
    except Exception:
        return bad
    for path in files:
        try:
            with open(path, "rb") as fh:
                pickle.load(fh)        # số hiệu phiên bản
                data = fh.read()
            pickle.loads(data)         # (dấu thời gian, danh sách hàm)
        except Exception as exc:
            bad.append((str(path), f"{type(exc).__name__}: {exc}"))
    return bad


def clear_cache() -> int:
    """Xoá sạch cache numba của app. Trả về số file đã xoá."""
    try:
        path = cache_dir()
        count = sum(1 for _ in path.rglob("*") if _.is_file())
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return count
    except Exception as exc:
        log.warning("Không xoá được cache numba: %s", exc)
        return 0


def run_healing(func, *args, **kwargs):
    """Chạy ``func``; nếu hỏng vì cache numba thì xoá cache rồi chạy lại MỘT lần.

    Chỉ một lần: cache vừa xoá mà vẫn hỏng thì nguyên nhân nằm chỗ khác, thử
    mãi chỉ làm treo luồng dò tone.
    """
    try:
        return func(*args, **kwargs)
    except Exception as exc:
        if not is_corrupt_cache_error(exc):
            raise
        removed = clear_cache()
        log.warning(
            "Cache numba hỏng (%s) — đã xoá %d file, biên dịch lại.", exc, removed
        )
        return func(*args, **kwargs)


def sweep_corrupt() -> int:
    """Quét cache, xoá riêng những file hỏng. Trả về số file đã xoá.

    Rẻ tiền: chỉ đọc vài file mục lục nhỏ, KHÔNG nạp numba/librosa. Chạy nền lúc
    mở app để chữa trước cả khi người dùng bấm dò tone; và vì xoá đúng file hỏng
    chứ không xoá sạch, phần cache còn lành vẫn dùng được (không phải biên dịch
    lại từ đầu).
    """
    hong = scan_corrupt()
    da_xoa = 0
    for duong_dan, ly_do in hong:
        p = Path(duong_dan)
        for f in (p, p.with_suffix(".nbc")):   # mục lục hỏng thì mã máy vô dụng
            try:
                if f.exists():
                    f.unlink()
                    da_xoa += 1
            except OSError as exc:
                log.warning("Không xoá được %s: %s", f.name, exc)
        log.warning("Cache numba hỏng: %s (%s) — đã xoá.", p.name, ly_do)
    return da_xoa
