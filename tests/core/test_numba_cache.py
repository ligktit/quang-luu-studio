"""Cache numba hỏng → app phải tự chữa, không bắt người dùng xoá tay.

Bối cảnh: nhật ký 15/09/2026 có 22 lần dò tone liên tiếp cùng ném
``UnpicklingError: invalid load key, '\\x00'`` từ ``numba/core/caching.py`` —
một file mục lục cache bị ghi dở nên toàn byte 0x00. numba không tự chữa, nên
máy khách hỏng dò tone vĩnh viễn cho tới khi có người xoá cache bằng tay.

Toàn bộ test dùng **librosa giả**: nạp librosa thật trong pytest làm abort cả
phiên chạy (numba/llvmlite), và cái cần kiểm là lớp chữa của app chứ không phải
librosa. Bộ tự kiểm tra chạy trên máy khách (core/self_check.py) cũng chính là
mấy phép thử này, gói trong exe.
"""

import pickle
import sys
from types import ModuleType

import pytest

from core import numba_cache

LOI_THAT = "invalid load key, '\x00'."


@pytest.fixture
def cache_tam(tmp_path, monkeypatch):
    """Trỏ cache numba vào thư mục tạm — test được phép xoá thoải mái."""
    thu_muc = tmp_path / "numba_cache"
    thu_muc.mkdir()
    monkeypatch.setattr(numba_cache, "cache_dir", lambda: thu_muc)
    return thu_muc


@pytest.fixture
def librosa_gia(monkeypatch):
    """Cắm module librosa giả vào sys.modules (là package, có __path__)."""
    gia = ModuleType("librosa")
    gia.__path__ = []
    gia.load = lambda *a, **k: ([0.0] * 16000, 16000)
    monkeypatch.delitem(sys.modules, "librosa", raising=False)
    monkeypatch.setitem(sys.modules, "librosa", gia)
    return gia


# ── Nhận diện lỗi ─────────────────────────────────────────────────────────────

def test_nhan_ra_loi_cache_hong():
    assert numba_cache.is_corrupt_cache_error(pickle.UnpicklingError(LOI_THAT))


def test_nhan_ra_qua_traceback_numba(tmp_path):
    """Lỗi đi qua numba/core/caching.py là cache hỏng, dù thông báo khác."""
    ma = tmp_path / "caching.py"
    ma.write_text("def doc_cache():\n    raise EOFError('cut ngang')\n", encoding="utf-8")
    khong_gian = {}
    exec(compile(ma.read_text(encoding="utf-8"),
                 str(tmp_path / "numba" / "core" / "caching.py"), "exec"), khong_gian)
    try:
        khong_gian["doc_cache"]()
    except EOFError as exc:
        assert numba_cache.is_corrupt_cache_error(exc)


@pytest.mark.parametrize("loi", [
    ValueError("file âm thanh rỗng"),
    pickle.UnpicklingError("chuyện khác"),
    OSError("mất mạng"),
])
def test_khong_nhan_nham_loi_thuong(loi):
    assert not numba_cache.is_corrupt_cache_error(loi)


# ── Tự chữa ───────────────────────────────────────────────────────────────────

def test_tu_chua_roi_chay_lai(cache_tam):
    """Cache hỏng: xoá cache, chạy lại, và chỉ chạy lại đúng một lần."""
    file_hong = cache_tam / "utils._cabs2-2436.py313.nbi"
    file_hong.write_bytes(b"\x00" * 128)
    dem = []

    def viec():
        dem.append(1)
        if len(dem) == 1:
            raise pickle.UnpicklingError(LOI_THAT)
        return "xong"

    assert numba_cache.run_healing(viec) == "xong"
    assert len(dem) == 2
    assert not file_hong.exists()


def test_hong_lan_hai_thi_chiu_thua(cache_tam):
    """Xoá cache rồi vẫn hỏng → ném lỗi ra, không thử vòng vo mãi."""
    dem = []

    def viec():
        dem.append(1)
        raise pickle.UnpicklingError(LOI_THAT)

    with pytest.raises(pickle.UnpicklingError):
        numba_cache.run_healing(viec)
    assert len(dem) == 2


def test_loi_thuong_khong_lam_xoa_cache(cache_tam):
    """Lỗi vặt (video bị chặn) mà cũng xoá cache thì lần dò tone nào cũng phải
    ngồi chờ numba biên dịch lại."""
    moc = cache_tam / "con_nguyen.nbi"
    moc.write_bytes(b"\x80abc")

    def viec():
        raise ValueError("video bị chặn")

    with pytest.raises(ValueError):
        numba_cache.run_healing(viec)
    assert moc.exists()


# ── Nạp librosa ───────────────────────────────────────────────────────────────

def test_scoring_nap_duoc_audio(librosa_gia, cache_tam):
    """Đường bình thường: hàm nạp audio của app chạy qua lớp chữa vẫn ra dữ liệu."""
    from core.scoring import ScoringEngine

    may = ScoringEngine()
    assert may.load_audio("bai_hat.wav") is True
    assert may.sample_rate == 16000


def test_scoring_tu_chua_khi_cache_hong(librosa_gia, cache_tam):
    """Dựng lại đúng cảnh trong nhật ký: librosa.load hỏng vì cache numba.

    App phải xoá cache, gọi lại, và lần này thành công — thay vì báo lỗi cho
    người dùng rồi lần nào thử lại cũng hỏng y như vậy.
    """
    from core.scoring import ScoringEngine

    (cache_tam / "utils._cabs2-2436.py313.nbi").write_bytes(b"\x00" * 64)
    dem = []

    def load_hong_lan_dau(*a, **k):
        dem.append(1)
        if len(dem) == 1:
            raise pickle.UnpicklingError(LOI_THAT)
        return ([0.0] * 16000, 16000)

    librosa_gia.load = load_hong_lan_dau

    assert ScoringEngine().load_audio("bai_hat.wav") is True
    assert len(dem) == 2, "chưa gọi lại librosa.load sau khi chữa"
    assert not list(cache_tam.glob("*.nbi")), "cache hỏng vẫn còn"


def test_luong_do_tone_di_qua_lop_chua():
    """_tone.py và scoring.py phải gọi librosa qua run_healing, không gọi thẳng."""
    from core import scoring
    from core.engine import _tone

    assert _tone.run_healing is numba_cache.run_healing
    assert scoring.run_healing is numba_cache.run_healing


def test_khong_nap_numba_som(librosa_gia, cache_tam):
    """Lớp chữa KHÔNG được nạp sẵn librosa.util.utils.

    Nạp sớm là kéo cả numba/llvmlite vào bộ nhớ ngay từ lời gọi đầu, trong khi
    librosa vốn nạp lười — và trong pytest thì numba thật làm abort cả phiên.
    """
    from core.scoring import ScoringEngine

    ScoringEngine().load_audio("bai_hat.wav")
    assert "librosa.util.utils" not in sys.modules
    assert "numba" not in sys.modules


# ── Quét cache thật ───────────────────────────────────────────────────────────

def test_quet_ra_file_hong(cache_tam):
    (cache_tam / "tot.nbi").write_bytes(_nbi_hop_le())
    (cache_tam / "hong.nbi").write_bytes(b"\x00" * 200)

    hong = numba_cache.scan_corrupt()
    assert [n for n, _ in hong] and all("hong.nbi" in n for n, _ in hong)


def test_quet_don_chi_xoa_file_hong(cache_tam):
    """sweep_corrupt xoá file hỏng (và file mã máy đi kèm), giữ nguyên file lành."""
    (cache_tam / "lanh.nbi").write_bytes(_nbi_hop_le())
    (cache_tam / "lanh.nbc").write_bytes(b"ma may")
    (cache_tam / "hong.nbi").write_bytes(b"\x00" * 200)
    (cache_tam / "hong.nbc").write_bytes(b"ma may")

    assert numba_cache.sweep_corrupt() == 2
    assert (cache_tam / "lanh.nbi").exists() and (cache_tam / "lanh.nbc").exists()
    assert not (cache_tam / "hong.nbi").exists() and not (cache_tam / "hong.nbc").exists()


def test_xoa_cache_dem_dung_so_file(cache_tam):
    (cache_tam / "a.nbi").write_bytes(b"\x00")
    (cache_tam / "b.nbc").write_bytes(b"\x00")
    assert numba_cache.clear_cache() == 2
    assert numba_cache.cache_dir().exists()


def _nbi_hop_le():
    """File mục lục đúng chuẩn numba: pickle phiên bản, rồi pickle nội dung."""
    return pickle.dumps("0.60.0") + pickle.dumps((b"stamp", {}))


# ── Bộ tự kiểm tra của máy khách ──────────────────────────────────────────────

def test_bo_tu_kiem_tra_chay_sach():
    """core/self_check.py là thứ chạy trên máy khách — nó phải tự đạt hết."""
    from core import self_check

    ket_qua, so_hong = self_check.chay()
    assert so_hong == 0, "; ".join(f"{k.ten}: {k.chi_tiet}" for k in ket_qua if not k.dat)
    assert len(ket_qua) == 8
