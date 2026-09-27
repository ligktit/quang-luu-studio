"""Chẩn đoán khâu TẢI AUDIO của dò tone — chạy ngay trên máy khách.

Vì sao cần: khi dò tone hỏng, nhật ký của app gần như không nói gì. Logger
``yt_dlp`` bị ghim ở mức ERROR (core/logger.py) và mọi thông điệp của yt-dlp đi
vào ``log.debug``, nên ở mức INFO ta chỉ thấy một khoảng lặng rồi watchdog 90
giây nổ — không biết thời gian tiêu ở đâu. Máy khách ngày 16/09/2026 treo đúng
kiểu đó: 4 lượt tải liên tiếp, mỗi lượt 90 giây, không một dòng nguyên nhân.

Bộ này chạy ĐÚNG đường tải mà app đi (``ScoringEngine.download_youtube_audio_with_info``),
nhưng bật hết đèn: log yt-dlp đầy đủ, đồng hồ đếm từng chặng, báo ffmpeg nằm ở
đâu và có chạy được không. Chạy bằng chính exe nên máy khách không cần Python::

    QuangLuuStudio.exe --thu-tai [link-youtube]     (hoặc thu_tai_youtube.bat)

Không truyền link thì dùng một video mẫu. Báo cáo in ra màn hình và lưu ở
``%APPDATA%\\QuangLuuStudio\\logs\\thu_tai.txt`` để khách gửi về.
"""

import os
import subprocess
import threading
import time
import traceback
from pathlib import Path

from core.logger import get_logger
from core.self_check import _mo_cua_so_chu

log = get_logger(__name__)

# Video mẫu khi người dùng không đưa link: chính bài đã thất bại trên máy khách
# ngày 16/09/2026, để so sánh được với nhật ký cũ.
_VIDEO_MAU = "https://www.youtube.com/watch?v=QRwlhPUcc50"

# Trần cứng của bộ chẩn đoán. Rộng hơn watchdog 90 giây của app, để thấy được
# "chậm nhưng xong" khác với "treo hẳn".
_TRAN_GIAY = 180

# Nhịp báo còn sống khi tải (giây).
_NHIP_BAO = 5


class _BienBan:
    """Gom mọi dòng vừa in ra màn hình vừa cất vào báo cáo."""

    def __init__(self):
        self.dong = []
        self._khoa = threading.Lock()

    def ghi(self, dong=""):
        with self._khoa:
            self.dong.append(dong)
        try:
            print(dong, flush=True)
        except Exception:
            pass

    def van_ban(self):
        with self._khoa:
            return "\n".join(self.dong)


class _LoggerYtdlp:
    """Hứng log của yt-dlp — thứ mà app bình thường vứt vào debug rồi bỏ quên."""

    def __init__(self, bien_ban, t0):
        self._bb = bien_ban
        self._t0 = t0

    def _ghi(self, muc, thong_diep):
        self._bb.ghi(f"    [{time.time() - self._t0:6.1f}s] {muc} {thong_diep}")

    def debug(self, msg):
        # yt-dlp gửi cả dòng tiến độ vào debug; giữ lại vì đây chính là thứ cho
        # biết nó đang tải hay đang đứng im.
        self._ghi("yt-dlp  ", msg)

    def info(self, msg):
        self._ghi("yt-dlp  ", msg)

    def warning(self, msg):
        self._ghi("yt-dlp !", msg)

    def error(self, msg):
        self._ghi("yt-dlp X", msg)


def _mo_ta_ffmpeg(bb):
    """ffmpeg có thật không, và có chạy được không.

    Quan trọng với khâu tải: thiếu ffmpeg thì yt-dlp không cắt được 45 giây đầu
    mà phải tải NGUYÊN bài — một bài karaoke dài trên đường truyền quán là quá
    thừa để vượt watchdog 90 giây.
    """
    from core.config import FFMPEG_LOCATION

    if not FFMPEG_LOCATION:
        bb.ghi("  ffmpeg      : KHÔNG TÌM THẤY  ← khâu tải 45 giây sẽ phải tải cả bài")
        return False

    bb.ghi(f"  ffmpeg      : {FFMPEG_LOCATION}")
    exe = os.path.join(FFMPEG_LOCATION, "ffmpeg.exe")
    if not os.path.isfile(exe):
        exe = os.path.join(FFMPEG_LOCATION, "ffmpeg")
    try:
        ket_qua = subprocess.run([exe, "-version"], capture_output=True, text=True,
                                 timeout=15, creationflags=_co_khong_hien_cua_so())
        dong_dau = (ket_qua.stdout or ket_qua.stderr or "").splitlines()
        bb.ghi(f"                {dong_dau[0] if dong_dau else '(không có đầu ra)'}")
        return ket_qua.returncode == 0
    except subprocess.TimeoutExpired:
        bb.ghi("                CHẠY THỬ QUÁ 15 GIÂY ← nhiều khả năng bị phần mềm diệt virus chặn")
        return False
    except Exception as exc:
        bb.ghi(f"                KHÔNG CHẠY ĐƯỢC: {type(exc).__name__}: {exc}")
        return False


def _co_khong_hien_cua_so():
    """Cờ để tiến trình con không nháy cửa sổ đen (chỉ có trên Windows)."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _moi_truong(bb):
    from core.config import AppConfig
    from core.version import __version__

    bb.ghi("MÔI TRƯỜNG")
    bb.ghi(f"  app         : {__version__}")
    try:
        from core import capabilities
        bb.ghi(f"  biến thể    : {capabilities.describe()}")
    except Exception as exc:
        bb.ghi(f"  biến thể    : không xác định được ({exc})")
    try:
        from core.ytdlp_support import describe_stack
        bb.ghi(f"  ngăn xếp    : {describe_stack()}")
    except Exception as exc:
        bb.ghi(f"  ngăn xếp    : không mô tả được ({exc})")
    co_ffmpeg = _mo_ta_ffmpeg(bb)
    bb.ghi(f"  cookie      : trình duyệt={AppConfig.get('youtube_cookie_browser', 'auto')!r}"
           f" file={AppConfig.get('youtube_cookie_file', '') or '(không)'}")
    bb.ghi()
    return co_ffmpeg


def _chang_metadata(bb, url):
    """Chặng 1: hỏi YouTube thông tin video (không tải dữ liệu nặng)."""
    from core.ytdlp_support import extract_info_with_auth, make_ydl_opts

    bb.ghi("CHẶNG 1 — LẤY THÔNG TIN VIDEO")
    t0 = time.time()
    try:
        opts = make_ydl_opts(skip_download=True, logger=_LoggerYtdlp(bb, t0))
        info = extract_info_with_auth(url, opts, download=False, log_prefix="[THỬ TẢI]")
    except Exception as exc:
        giay = time.time() - t0
        bb.ghi(f"  HỎNG sau {giay:.1f}s: {type(exc).__name__}: {exc}")
        bb.ghi()
        return None, giay
    giay = time.time() - t0
    if info:
        bb.ghi(f"  Tên bài     : {info.get('title', '?')}")
        thoi_luong = info.get("duration")
        if thoi_luong:
            bb.ghi(f"  Thời lượng  : {int(thoi_luong) // 60} phút {int(thoi_luong) % 60} giây")
        bb.ghi(f"  Số định dạng: {len(info.get('formats') or [])}")
    bb.ghi(f"  Xong sau    : {giay:.1f}s")
    bb.ghi()
    return info, giay


def _chang_tai(bb, url):
    """Chặng 2: tải 45 giây đầu — đúng hàm mà luồng dò tone gọi."""
    from core.scoring import ScoringEngine

    bb.ghi(f"CHẶNG 2 — TẢI 45 GIÂY ĐẦU (app cho khâu này 90 giây, ở đây nới tới {_TRAN_GIAY}s)")
    t0 = time.time()
    ket_qua = {}

    def _moc_tien_do(d):
        """Hook của yt-dlp: cho biết đang chảy dữ liệu hay đứng hình."""
        if d.get("status") != "downloading":
            if d.get("status") == "finished":
                bb.ghi(f"    [{time.time() - t0:6.1f}s] tải xong phần dữ liệu, chuyển sang xử lý")
            return
        moc = getattr(_moc_tien_do, "_lan_truoc", 0)
        if time.time() - moc < 2:
            return
        _moc_tien_do._lan_truoc = time.time()
        da_tai = (d.get("downloaded_bytes") or 0) / 1024 / 1024
        toc_do = (d.get("speed") or 0) / 1024
        bb.ghi(f"    [{time.time() - t0:6.1f}s] đã tải {da_tai:.1f} MB, tốc độ {toc_do:.0f} KB/s")

    def _chay():
        may = ScoringEngine()
        try:
            duong_dan, ten = may.download_youtube_audio_with_info(
                url, extra_opts={"logger": _LoggerYtdlp(bb, t0),
                                 "progress_hooks": [_moc_tien_do]})
            ket_qua["duong_dan"] = duong_dan
            ket_qua["ten"] = ten
            if duong_dan and os.path.exists(duong_dan):
                ket_qua["mb"] = os.path.getsize(duong_dan) / 1024 / 1024
        except Exception as exc:
            ket_qua["loi"] = f"{type(exc).__name__}: {exc}"
            ket_qua["vet"] = traceback.format_exc()
        finally:
            try:
                may.cleanup_temp_file()
            except Exception:
                pass

    luong = threading.Thread(target=_chay, daemon=True)
    luong.start()

    while luong.is_alive():
        luong.join(timeout=_NHIP_BAO)
        troi = time.time() - t0
        if not luong.is_alive():
            break
        bb.ghi(f"    [{troi:6.1f}s] … vẫn đang chạy")
        if troi > _TRAN_GIAY:
            bb.ghi(f"  BỎ CUỘC: quá {_TRAN_GIAY} giây vẫn chưa xong.")
            bb.ghi()
            return None, troi

    giay = time.time() - t0
    if ket_qua.get("loi"):
        bb.ghi(f"  HỎNG sau {giay:.1f}s: {ket_qua['loi']}")
        bb.ghi()
        return None, giay
    if not ket_qua.get("duong_dan"):
        bb.ghi(f"  KHÔNG RA FILE sau {giay:.1f}s (yt-dlp nuốt lỗi — xem các dòng yt-dlp ở trên)")
        bb.ghi()
        return None, giay

    bb.ghi(f"  File audio  : {ket_qua.get('mb', 0):.1f} MB")
    bb.ghi(f"  Xong sau    : {giay:.1f}s")
    bb.ghi()
    return ket_qua, giay


def _ket_luan(bb, co_ffmpeg, info, giay_meta, tai, giay_tai):
    bb.ghi("-" * 64)
    if tai and giay_tai <= 90:
        bb.ghi(f"KẾT LUẬN: tải được trong {giay_tai:.1f} giây — khâu tải KHÔNG phải thủ phạm.")
        bb.ghi("          Nếu app vẫn báo lỗi dò tone thì vấn đề nằm ở khâu sau (phân tích),")
        bb.ghi("          hãy chạy kiem_tra_tone.bat và gửi cả hai báo cáo.")
    elif tai:
        bb.ghi(f"KẾT LUẬN: tải ĐƯỢC nhưng mất {giay_tai:.1f} giây, quá hạn 90 giây của app.")
        bb.ghi("          Đường truyền ở máy này quá chậm cho việc tải audio từ YouTube.")
    elif not co_ffmpeg:
        bb.ghi("KẾT LUẬN: KHÔNG có ffmpeg chạy được → yt-dlp phải tải nguyên bài thay vì 45")
        bb.ghi("          giây đầu, nên quá hạn. Cài lại app hoặc gỡ chặn ffmpeg khỏi phần")
        bb.ghi("          mềm diệt virus rồi thử lại.")
    elif info is None:
        bb.ghi(f"KẾT LUẬN: hỏng ngay từ chặng LẤY THÔNG TIN ({giay_meta:.1f}s) — máy này không")
        bb.ghi("          nói chuyện được với YouTube. Nghi mạng, tường lửa, hoặc YouTube đang")
        bb.ghi("          chặn máy/địa chỉ mạng này.")
    else:
        bb.ghi(f"KẾT LUẬN: lấy thông tin OK ({giay_meta:.1f}s) nhưng TẢI thất bại.")
        bb.ghi("          Xem các dòng 'yt-dlp' ở trên để biết YouTube trả lời gì.")
    bb.ghi("-" * 64)


def main(argv=None):
    import sys

    argv = sys.argv if argv is None else argv
    _mo_cua_so_chu()

    url = _VIDEO_MAU
    for tham_so in argv[1:]:
        if tham_so.startswith("http"):
            url = tham_so
            break

    bb = _BienBan()
    bb.ghi("QUANG LƯU STUDIO — THỬ TẢI AUDIO TỪ YOUTUBE")
    bb.ghi(time.strftime("Thời điểm: %d/%m/%Y %H:%M:%S"))
    bb.ghi(f"Link      : {url}")
    bb.ghi("-" * 64)

    ma_thoat = 1
    try:
        co_ffmpeg = _moi_truong(bb)
        info, giay_meta = _chang_metadata(bb, url)
        tai, giay_tai = _chang_tai(bb, url)
        _ket_luan(bb, co_ffmpeg, info, giay_meta, tai, giay_tai)
        ma_thoat = 0 if (tai and giay_tai <= 90) else 1
    except Exception:
        bb.ghi("KHÔNG CHẠY ĐƯỢC BỘ CHẨN ĐOÁN:")
        bb.ghi(traceback.format_exc())

    try:
        from core.config import _get_data_dir
        duong_dan = Path(_get_data_dir()) / "logs" / "thu_tai.txt"
        duong_dan.parent.mkdir(parents=True, exist_ok=True)
        duong_dan.write_text(bb.van_ban(), encoding="utf-8")
        print(f"\nĐã lưu báo cáo: {duong_dan}", flush=True)
    except Exception as exc:
        print(f"\n(Không lưu được báo cáo: {exc})", flush=True)

    log.info("Thử tải: %s", "đạt" if ma_thoat == 0 else "có vấn đề")
    return ma_thoat


if __name__ == "__main__":
    import sys
    sys.exit(main())
