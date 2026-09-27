"""Bộ tự kiểm tra cơ chế chữa cache numba — chạy được ngay trên máy khách.

Máy khách không có Python, nhưng file exe thì có sẵn Python bên trong. Nên bộ
kiểm tra này nằm luôn trong app và gọi bằng::

    QuangLuuStudio.exe --tu-kiem-tra        (hoặc bấm đúp kiem_tra_tone.bat)
    QuangLuuStudio.exe --tu-kiem-tra --day-du   (nạp thêm librosa THẬT, chậm hơn)

Mặc định dùng **librosa giả**: không nạp librosa thật, không bắt numba biên dịch,
nên chạy trong vài giây và không kéo theo mấy trăm MB bộ nhớ. Cái cần kiểm là
lớp chữa cache của app (core/numba_cache.py), không phải bản thân librosa.

Các phép thử phá hoại (xoá cache) chạy trên thư mục tạm; cache thật chỉ bị đụng
tới khi phép thử số 8 tìm thấy file hỏng — lúc đó xoá là đang chữa máy.
"""

import os
import pickle
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import ModuleType

from core import numba_cache
from core.logger import get_logger

log = get_logger(__name__)

# Chữ ký y hệt lỗi thật trong nhật ký ngày 15/09/2026.
_LOI_THAT = "invalid load key, '\x00'."


# ── Khung chạy ────────────────────────────────────────────────────────────────

class _KetQua:
    def __init__(self, ten, dat, chi_tiet):
        self.ten, self.dat, self.chi_tiet = ten, dat, chi_tiet


def _chay(ten, ham):
    """Chạy một phép thử, không cho nó làm sập cả bộ kiểm tra."""
    try:
        chi_tiet = ham() or "đạt"
        return _KetQua(ten, True, chi_tiet)
    except AssertionError as exc:
        return _KetQua(ten, False, str(exc) or "không đúng như mong đợi")
    except Exception as exc:
        return _KetQua(ten, False, f"{type(exc).__name__}: {exc}")


class _CacheTam:
    """Tạm trỏ cache numba vào thư mục tạm, để phép thử xoá thoải mái."""

    def __enter__(self):
        self._goc = numba_cache.cache_dir
        self.duong_dan = Path(tempfile.mkdtemp(prefix="qls_kiemtra_numba_"))
        numba_cache.cache_dir = lambda: self.duong_dan
        return self.duong_dan

    def __exit__(self, *exc):
        numba_cache.cache_dir = self._goc
        shutil.rmtree(self.duong_dan, ignore_errors=True)
        return False


def _cam_librosa_gia(ham_load):
    """Cắm module librosa giả vào sys.modules; trả về hàm gỡ ra."""
    cu = {k: v for k, v in sys.modules.items()
          if k == "librosa" or k.startswith("librosa.")}
    for k in cu:
        del sys.modules[k]
    gia = ModuleType("librosa")
    gia.__path__ = []
    gia.load = ham_load
    sys.modules["librosa"] = gia

    def _go():
        for k in [k for k in sys.modules if k == "librosa" or k.startswith("librosa.")]:
            del sys.modules[k]
        sys.modules.update(cu)

    return _go


# ── Các phép thử ──────────────────────────────────────────────────────────────

def _t1_thu_muc_cache_rieng():
    """Cache numba phải nằm trong thư mục dữ liệu app và ghi được."""
    duong_dan = numba_cache.activate_private_cache()
    assert duong_dan, "không đặt được NUMBA_CACHE_DIR (thư mục dữ liệu không ghi được?)"
    assert os.environ.get("NUMBA_CACHE_DIR") == duong_dan, "NUMBA_CACHE_DIR không khớp"
    thu = Path(duong_dan) / "thu_ghi.tmp"
    thu.write_bytes(b"x")
    thu.unlink()
    return duong_dan


def _t2_nhan_dien_loi():
    """Phân biệt đúng lỗi cache hỏng với lỗi thường."""
    hong = pickle.UnpicklingError(_LOI_THAT)
    assert numba_cache.is_corrupt_cache_error(hong), "không nhận ra lỗi cache hỏng"
    assert not numba_cache.is_corrupt_cache_error(ValueError("file âm thanh rỗng")), \
        "nhận nhầm lỗi thường thành lỗi cache"
    assert not numba_cache.is_corrupt_cache_error(pickle.UnpicklingError("chuyện khác")), \
        "nhận nhầm lỗi pickle khác thành lỗi cache"
    return "nhận đúng cả 3 ca"


def _t3_tu_chua_khi_cache_hong():
    """Gặp lỗi cache hỏng: xoá cache, chạy lại, và chỉ chạy lại một lần."""
    with _CacheTam() as thu_muc:
        file_hong = thu_muc / "utils._cabs2-2436.py313.nbi"
        file_hong.write_bytes(b"\x00" * 128)

        dem = {"n": 0}

        def _viec():
            dem["n"] += 1
            if dem["n"] == 1:
                raise pickle.UnpicklingError(_LOI_THAT)
            return "xong"

        ket_qua = numba_cache.run_healing(_viec)
        assert ket_qua == "xong", f"không chạy lại được: {ket_qua!r}"
        assert dem["n"] == 2, f"phải chạy đúng 2 lần, thực tế {dem['n']}"
        assert not file_hong.exists(), "file cache hỏng chưa bị xoá"
    return "đã xoá cache hỏng và chạy lại thành công"


def _t4_khong_chua_nham():
    """Lỗi thường phải nổi lên nguyên vẹn và KHÔNG được xoá cache.

    Nếu xoá cache mỗi lần có lỗi vặt (video hỏng, mất mạng), máy khách sẽ phải
    ngồi chờ numba biên dịch lại sau mỗi lần dò tone hụt.
    """
    with _CacheTam() as thu_muc:
        moc = thu_muc / "con_nguyen.nbi"
        moc.write_bytes(b"\x80abc")

        def _viec():
            raise ValueError("video bị chặn")

        try:
            numba_cache.run_healing(_viec)
        except ValueError:
            pass
        else:
            raise AssertionError("lỗi thường đã bị nuốt mất")
        assert moc.exists(), "cache bị xoá oan vì một lỗi không liên quan"
    return "giữ nguyên cache, ném lại lỗi gốc"


def _t5_nap_audio_binh_thuong():
    """Chạy THẬT hàm nạp audio của app (ScoringEngine.load_audio) với librosa giả."""
    from core.scoring import ScoringEngine

    go = _cam_librosa_gia(lambda *a, **k: ([0.0] * 16000, 16000))
    try:
        may = ScoringEngine()
        assert may.load_audio("bai_hat.wav") is True, "nạp audio thất bại"
        assert may.sample_rate == 16000, f"tần số lấy mẫu sai: {may.sample_rate}"
    finally:
        go()
    return "app nạp được audio qua lớp chữa"


def _t6_nap_audio_khi_cache_hong():
    """Cùng hàm đó, nhưng librosa hỏng vì cache numba ở lần gọi đầu.

    Đây là dựng lại đúng cảnh trong nhật ký 15/09/2026. App phải tự xoá cache,
    gọi lại, và lần này thành công — thay vì báo lỗi cho người dùng.
    """
    from core.scoring import ScoringEngine

    dem = {"n": 0}

    def _load_hong_lan_dau(*a, **k):
        dem["n"] += 1
        if dem["n"] == 1:
            raise pickle.UnpicklingError(_LOI_THAT)
        return ([0.0] * 16000, 16000)

    go = _cam_librosa_gia(_load_hong_lan_dau)
    with _CacheTam() as thu_muc:
        try:
            (thu_muc / "utils._localmax-1035.py313.nbi").write_bytes(b"\x00" * 64)
            assert ScoringEngine().load_audio("bai_hat.wav") is True, \
                "app không chữa được, vẫn báo nạp audio thất bại"
            assert dem["n"] == 2, f"phải gọi lại librosa.load đúng 1 lần, thực tế {dem['n']}"
            assert not list(thu_muc.glob("*.nbi")), "cache hỏng vẫn còn"
        finally:
            go()
    return "dựng lại đúng lỗi thật: app tự chữa và nạp được audio"


def _t7_duong_do_tone_co_lop_chua():
    """Luồng dò tone (core/engine/_tone.py) phải đi qua lớp chữa, không gọi thẳng."""
    from core.engine import _tone

    assert getattr(_tone, "run_healing", None) is numba_cache.run_healing, \
        "core/engine/_tone.py không gọi qua run_healing — cache hỏng sẽ lại làm hỏng dò tone"
    from core import scoring
    assert getattr(scoring, "run_healing", None) is numba_cache.run_healing, \
        "core/scoring.py không gọi qua run_healing"
    return "cả luồng dò tone lẫn chấm điểm đều đi qua lớp chữa"


def _t8_quet_cache_that():
    """Soi cache thật trên máy này; thấy file hỏng thì chữa luôn."""
    hong = numba_cache.scan_corrupt()
    tong = sum(1 for _ in numba_cache.cache_dir().rglob("*") if _.is_file())
    if not hong:
        return f"cache thật sạch ({tong} file trong {numba_cache.cache_dir()})"
    danh_sach = "; ".join(f"{Path(p).name} ({loi})" for p, loi in hong[:5])
    da_xoa = numba_cache.clear_cache()
    return (f"TÌM THẤY {len(hong)} file hỏng — đã xoá {da_xoa} file để chữa. "
            f"Lần dò tone kế tiếp sẽ chậm hơn mươi giây. Chi tiết: {danh_sach}")


def _t9_nap_librosa_that():
    """Tuỳ chọn --day-du: nạp librosa THẬT + numba (chậm, có khi vài chục giây).

    Phép thử duy nhất chạm vào cache numba thật. Nạp qua run_healing đúng như
    app làm, nên cache thật hỏng thì chính phép thử này chữa.
    """
    import importlib

    t0 = time.time()

    def _nap():
        lib = importlib.import_module("librosa")
        importlib.import_module("librosa.util.utils")   # chỗ numba đọc cache
        return lib

    lib = numba_cache.run_healing(_nap)
    assert hasattr(lib, "load"), "librosa thật thiếu hàm load"
    return f"nạp librosa thật + numba mất {time.time() - t0:.1f} giây"


_PHEP_THU = [
    ("1. Thư mục cache riêng của app",          _t1_thu_muc_cache_rieng),
    ("2. Nhận diện lỗi cache hỏng",             _t2_nhan_dien_loi),
    ("3. Tự chữa khi cache hỏng",               _t3_tu_chua_khi_cache_hong),
    ("4. Không xoá cache vì lỗi vặt",           _t4_khong_chua_nham),
    ("5. Nạp audio (librosa giả) bình thường",  _t5_nap_audio_binh_thuong),
    ("6. Nạp audio khi cache hỏng — lỗi thật",  _t6_nap_audio_khi_cache_hong),
    ("7. Đường dò tone có lớp chữa",            _t7_duong_do_tone_co_lop_chua),
    ("8. Quét cache thật trên máy này",         _t8_quet_cache_that),
]


# ── Đầu ra ────────────────────────────────────────────────────────────────────

def _mo_cua_so_chu():
    """Exe dựng ở chế độ không console → xin lại cửa sổ chữ để in kết quả.

    Rồi ép đầu ra sang UTF-8: console Windows mặc định là cp1252/cp437, gặp chữ
    "Lưu" là ném UnicodeEncodeError và nuốt sạch báo cáo.
    """
    # sys.stdout is None = exe không console và người dùng cũng không chuyển
    # hướng đầu ra đi đâu; chỉ khi đó mới được chiếm cửa sổ chữ.
    if os.name == "nt" and getattr(sys, "frozen", False) and sys.stdout is None:
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            if not k32.AttachConsole(-1):      # console của file .bat gọi mình
                k32.AllocConsole()
            k32.SetConsoleOutputCP(65001)
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            sys.stderr = sys.stdout
            return
        except Exception:
            pass
    for luong in (sys.stdout, sys.stderr):
        try:
            luong.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def chay(day_du=False):
    """Chạy hết các phép thử, trả về (danh sách kết quả, số phép hỏng)."""
    phep_thu = list(_PHEP_THU)
    if day_du:
        phep_thu.append(("9. Nạp librosa THẬT qua lớp chữa", _t9_nap_librosa_that))
    ket_qua = [_chay(ten, ham) for ten, ham in phep_thu]
    return ket_qua, sum(1 for k in ket_qua if not k.dat)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    day_du = "--day-du" in argv
    _mo_cua_so_chu()

    dong = ["QUANG LƯU STUDIO — TỰ KIỂM TRA CƠ CHẾ DÒ TONE",
            time.strftime("Thời điểm: %d/%m/%Y %H:%M:%S"),
            f"Thư mục cache: {numba_cache.cache_dir()}",
            "-" * 64]
    try:
        ket_qua, so_hong = chay(day_du=day_du)
    except Exception:
        dong += ["KHÔNG CHẠY ĐƯỢC BỘ KIỂM TRA:", traceback.format_exc()]
        ket_qua, so_hong = [], 1
    for k in ket_qua:
        dong.append(f"[{'ĐẠT ' if k.dat else 'HỎNG'}] {k.ten}")
        dong.append(f"         {k.chi_tiet}")
    dong.append("-" * 64)
    dong.append("TẤT CẢ ĐỀU ĐẠT — cơ chế chữa cache đang hoạt động."
                if so_hong == 0 else
                f"CÓ {so_hong} PHÉP THỬ HỎNG — gửi file báo cáo dưới đây cho kỹ thuật.")
    if not day_du:
        dong.append("(Thêm --day-du để nạp thử librosa thật, chậm hơn nhưng kiểm tận gốc.)")

    bao_cao = "\n".join(dong)
    print(bao_cao)
    log.info("Tự kiểm tra: %d phép hỏng", so_hong)

    try:
        from core.config import _get_data_dir
        duong_dan = Path(_get_data_dir()) / "logs" / "tu_kiem_tra.txt"
        duong_dan.parent.mkdir(parents=True, exist_ok=True)
        duong_dan.write_text(bao_cao, encoding="utf-8")
        print(f"\nĐã lưu báo cáo: {duong_dan}")
    except Exception as exc:
        print(f"\n(Không lưu được báo cáo: {exc})")

    return 0 if so_hong == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
