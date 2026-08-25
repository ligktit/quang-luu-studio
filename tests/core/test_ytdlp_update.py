"""Kiểm tra cơ chế nạp bản yt-dlp mới hơn từ thư mục dữ liệu người dùng."""
import io
import json
import os
import sys
import zipfile
import hashlib
from unittest.mock import patch

import pytest

from core import ytdlp_update as U


# ── So sánh phiên bản ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("2026.07.04", (2026, 7, 4)),
    ("2026.7.4", (2026, 7, 4)),
    ("2026.2.4", (2026, 2, 4)),
    ("", ()),
    (None, ()),
])
def test_parse_version(text, expected):
    assert U.parse_version(text) == expected


def test_is_newer():
    assert U.is_newer("2026.07.04", "2026.02.04") is True
    assert U.is_newer("2026.02.04", "2026.07.04") is False
    assert U.is_newer("2026.07.04", "2026.07.04") is False
    # phiên bản không đọc được thì không bao giờ được coi là mới hơn
    assert U.is_newer("khong-biet", "2026.02.04") is False
    assert U.is_newer("2026.07.04", "") is False


# ── Nhận diện thư mục nạp ngoài ──────────────────────────────────────────────

def _make_fake_ytdlp(root, version):
    pkg = os.path.join(root, "yt_dlp")
    os.makedirs(os.path.join(pkg, "extractor", "youtube"), exist_ok=True)
    with open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8") as f:
        f.write("from .version import __version__\n")
    with open(os.path.join(pkg, "version.py"), "w", encoding="utf-8") as f:
        f.write(f'__version__ = "{version}"\n')
    with open(os.path.join(pkg, "YoutubeDL.py"), "w", encoding="utf-8") as f:
        f.write("class YoutubeDL: pass\n")
    return root


def test_read_override_version(tmp_path):
    root = _make_fake_ytdlp(str(tmp_path), "2026.09.01")
    assert U.read_override_version(root) == "2026.09.01"


def test_read_override_version_missing(tmp_path):
    assert U.read_override_version(str(tmp_path)) is None


def test_looks_like_ytdlp_rejects_incomplete(tmp_path):
    pkg = tmp_path / "yt_dlp"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    assert U._looks_like_ytdlp(str(tmp_path)) is False


# ── activate_override ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def restore_meta_path():
    """Cô lập trạng thái nạp ngoài — cả finder lẫn gói yt_dlp đã import.

    `core/ytdlp_support.py` gọi `activate_override()` NGAY lúc import, nên chỉ
    cần một test khác chạm vào module đó (hoặc máy dev có sẵn bản yt-dlp mới
    trong %APPDATA%) là `sys.meta_path` đã mang một `_OverrideFinder` thật và
    `sys.modules` đã có `yt_dlp` — lúc đó các phép đếm ở dưới nhìn thấy đồ của
    người khác và báo đỏ tuỳ theo THỨ TỰ chạy. Dọn trước, trả lại nguyên trạng
    sau, để file này chạy riêng hay chạy chung đều cho cùng một kết quả.
    """
    original = list(sys.meta_path)
    original_active = U.ACTIVE_VERSION
    original_modules = {
        name: mod for name, mod in sys.modules.items()
        if name == "yt_dlp" or name.startswith("yt_dlp.")
    }

    sys.meta_path[:] = [
        f for f in sys.meta_path if not isinstance(f, U._OverrideFinder)
    ]
    for name in original_modules:
        del sys.modules[name]
    U.ACTIVE_VERSION = None

    yield

    sys.meta_path[:] = original
    U.ACTIVE_VERSION = original_active
    for name in [n for n in sys.modules
                 if n == "yt_dlp" or n.startswith("yt_dlp.")]:
        del sys.modules[name]
    sys.modules.update(original_modules)


def _override_finders():
    return [f for f in sys.meta_path if isinstance(f, U._OverrideFinder)]


def test_activate_override_skips_older(tmp_path):
    root = _make_fake_ytdlp(str(tmp_path), "2020.01.01")
    assert U.activate_override(root) is None
    assert _override_finders() == []
    assert U.active_version() == U.BUNDLED_YTDLP_VERSION


def test_activate_override_skips_missing(tmp_path):
    assert U.activate_override(str(tmp_path / "khong-co")) is None
    assert _override_finders() == []


def test_activate_override_installs_finder(tmp_path):
    newer = "9999.01.01"
    root = _make_fake_ytdlp(str(tmp_path), newer)
    with patch.dict(sys.modules):
        sys.modules.pop("yt_dlp", None)
        assert U.activate_override(root) == newer
        assert len(_override_finders()) == 1
        assert sys.meta_path[0] is _override_finders()[0]
        assert U.active_version() == newer


def test_activate_override_is_idempotent(tmp_path):
    root = _make_fake_ytdlp(str(tmp_path), "9999.01.01")
    with patch.dict(sys.modules):
        sys.modules.pop("yt_dlp", None)
        U.activate_override(root)
        U.activate_override(root)
        assert len(_override_finders()) == 1


def test_activate_override_bails_if_already_imported(tmp_path):
    root = _make_fake_ytdlp(str(tmp_path), "9999.01.01")
    with patch.dict(sys.modules, {"yt_dlp": object()}):
        assert U.activate_override(root) is None
        assert _override_finders() == []


def test_finder_ignores_other_modules(tmp_path):
    root = _make_fake_ytdlp(str(tmp_path), "9999.01.01")
    finder = U._OverrideFinder(root)
    assert finder.find_spec("requests") is None
    assert finder.find_spec("yt_dlpx") is None
    spec = finder.find_spec("yt_dlp")
    assert spec is not None
    assert os.path.normcase(root) in os.path.normcase(spec.origin)


def test_finder_loads_real_package(tmp_path):
    """Bản nạp ngoài phải thắng cả gói yt_dlp cài sẵn trong site-packages."""
    root = _make_fake_ytdlp(str(tmp_path), "9999.01.01")
    with patch.dict(sys.modules):
        for name in [n for n in sys.modules if n == "yt_dlp" or n.startswith("yt_dlp.")]:
            sys.modules.pop(name)
        U.activate_override(root)
        import yt_dlp
        assert yt_dlp.__version__ == "9999.01.01"
        assert os.path.normcase(root) in os.path.normcase(yt_dlp.__file__)


# ── Tải bản mới ──────────────────────────────────────────────────────────────

def _fake_wheel_bytes(version):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("yt_dlp/__init__.py", "from .version import __version__\n")
        archive.writestr("yt_dlp/version.py", f'__version__ = "{version}"\n')
        archive.writestr("yt_dlp/YoutubeDL.py", "class YoutubeDL: pass\n")
        archive.writestr("yt_dlp/extractor/youtube/__init__.py", "")
        archive.writestr("yt_dlp-1.dist-info/METADATA", "Name: yt-dlp\n")
    return buffer.getvalue()


def _patch_download(monkeypatch, version, payload, digest=None):
    metadata = {
        "info": {"version": version},
        "urls": [{
            "packagetype": "bdist_wheel",
            "filename": f"yt_dlp-{version}-py3-none-any.whl",
            "url": "https://example.invalid/yt_dlp.whl",
            "digests": {"sha256": digest if digest is not None else hashlib.sha256(payload).hexdigest()},
        }],
    }
    monkeypatch.setattr(U, "_fetch_pypi_metadata", lambda timeout=20: metadata)

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return payload

    monkeypatch.setattr(U.urllib.request, "urlopen", lambda *a, **k: _Response())


def test_download_override_installs(tmp_path, monkeypatch):
    payload = _fake_wheel_bytes("9999.01.01")
    _patch_download(monkeypatch, "9999.01.01", payload)
    monkeypatch.setattr(U, "STAMP_FILE", str(tmp_path / "stamp.json"))

    target = str(tmp_path / "ytdlp")
    assert U.download_override(target) == "9999.01.01"
    assert U.read_override_version(target) == "9999.01.01"
    # chỉ giải nén gói yt_dlp, không lôi theo dist-info
    assert os.listdir(target) == ["yt_dlp"]


def test_download_override_rejects_bad_hash(tmp_path, monkeypatch):
    payload = _fake_wheel_bytes("9999.01.01")
    _patch_download(monkeypatch, "9999.01.01", payload, digest="00" * 32)
    monkeypatch.setattr(U, "STAMP_FILE", str(tmp_path / "stamp.json"))

    target = str(tmp_path / "ytdlp")
    assert U.download_override(target) is None
    assert not os.path.exists(target)


def test_download_override_skips_when_current(tmp_path, monkeypatch):
    target = _make_fake_ytdlp(str(tmp_path / "ytdlp"), "9999.02.02")
    payload = _fake_wheel_bytes("9999.01.01")
    _patch_download(monkeypatch, "9999.01.01", payload)

    assert U.download_override(target) is None
    assert U.read_override_version(target) == "9999.02.02"


def test_download_override_keeps_old_on_failure(tmp_path, monkeypatch):
    target = _make_fake_ytdlp(str(tmp_path / "ytdlp"), "2020.01.01")
    payload = b"khong phai zip"
    _patch_download(monkeypatch, "9999.01.01", payload)
    monkeypatch.setattr(U, "STAMP_FILE", str(tmp_path / "stamp.json"))

    assert U.download_override(target) is None
    assert U.read_override_version(target) == "2020.01.01"


def test_python_ok():
    assert U._python_ok(None) is True
    assert U._python_ok(">=3.9") is True
    assert U._python_ok(">=99.0") is False
    assert U._python_ok("linh tinh") is True


def test_download_override_skips_wheel_needing_newer_python(tmp_path, monkeypatch):
    payload = _fake_wheel_bytes("9999.01.01")
    _patch_download(monkeypatch, "9999.01.01", payload)
    metadata_urls = U._fetch_pypi_metadata()["urls"]
    metadata_urls[0]["requires_python"] = ">=99.0"
    monkeypatch.setattr(U, "STAMP_FILE", str(tmp_path / "stamp.json"))

    target = str(tmp_path / "ytdlp")
    assert U.download_override(target) is None
    assert not os.path.exists(target)


# ── Hẹn giờ kiểm tra ─────────────────────────────────────────────────────────

def test_should_check_now_respects_config(tmp_path, monkeypatch):
    monkeypatch.setattr(U, "STAMP_FILE", str(tmp_path / "stamp.json"))
    with patch.object(U.AppConfig, "get", return_value=False):
        assert U.should_check_now() is False


def test_should_check_now_interval(tmp_path, monkeypatch):
    stamp = tmp_path / "stamp.json"
    monkeypatch.setattr(U, "STAMP_FILE", str(stamp))
    with patch.object(U.AppConfig, "get", return_value=True):
        assert U.should_check_now(now=1_000_000) is True   # chưa từng kiểm tra
        stamp.write_text(json.dumps({"last_check": 1_000_000}), encoding="utf-8")
        assert U.should_check_now(now=1_000_100) is False
        assert U.should_check_now(now=1_000_000 + U.AUTO_UPDATE_INTERVAL_SEC) is True


def test_maybe_auto_update_marks_stamp_before_download(tmp_path, monkeypatch):
    stamp = tmp_path / "stamp.json"
    monkeypatch.setattr(U, "STAMP_FILE", str(stamp))
    monkeypatch.setattr(U, "should_check_now", lambda: True)

    def _boom(*args, **kwargs):
        raise OSError("mat mang")

    monkeypatch.setattr(U, "download_override", _boom)
    assert U.maybe_auto_update() is None
    # đã ghi mốc thời gian → lần mở app kế tiếp không thử lại ngay
    assert json.loads(stamp.read_text(encoding="utf-8")).get("last_check")
