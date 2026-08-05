"""
Test device fingerprint: phải ỔN ĐỊNH suốt đời máy.

Bối cảnh lỗi đã gặp: fingerprint băm cả MAC/hostname/PROCESSOR_IDENTIFIER nên
trôi khi user bật VPN hoặc Windows xoay MAC Wi-Fi → verify trả not_activated →
hết grace 7 ngày → app đá user ra → nhập lại mã thì server báo device_limit vì
bản ghi Device cũ vẫn chiếm slot.

Các test dưới đây khoá hai bảo đảm:
  1. Fingerprint đã dùng được ghi xuống activation.json và LUÔN được dùng lại.
  2. Khi phải tính mới, chỉ dựa vào tín hiệu ổn định (MachineGuid), không dựa
     vào MAC/hostname/biến môi trường.
"""
import hashlib
import json
import os
import platform
import tempfile
import uuid
from contextlib import contextmanager

from core.licensing import device


def _read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@contextmanager
def _machine(guid="GUID-MAY-CUA-KHACH", cache=None):
    """Giả lập một máy: MachineGuid cố định + activation.json riêng."""
    orig_guid_fn, orig_file, orig_cached = (
        device._machine_guid, device.ACTIVATION_FILE, device._cached,
    )
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "activation.json")
    if cache is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    device._machine_guid = lambda: guid
    device.ACTIVATION_FILE = path
    device._cached = None
    try:
        yield path
    finally:
        device._machine_guid = orig_guid_fn
        device.ACTIVATION_FILE = orig_file
        device._cached = orig_cached


def test_fingerprint_reused_from_cache():
    """Đã có fingerprint trong activation.json → dùng lại nguyên văn."""
    known = "a" * 64
    with _machine(cache={"device_fingerprint": known}):
        assert device.get_fingerprint() == known


def test_fingerprint_persisted_on_first_compute():
    """Lần đầu tính xong phải ghi xuống đĩa để lần sau không tính lại."""
    with _machine() as path:
        fp = device.get_fingerprint()
        assert _read(path)["device_fingerprint"] == fp


def test_fingerprint_survives_volatile_signals():
    """Đổi MAC / hostname / PROCESSOR_IDENTIFIER không được đổi fingerprint."""
    with _machine():
        before = device.get_fingerprint()

    os.environ["PROCESSOR_IDENTIFIER"] = "CPU-HOAN-TOAN-KHAC"
    orig_getnode, orig_node = uuid.getnode, platform.node
    uuid.getnode = lambda: 0x00FF11223344
    platform.node = lambda: "TEN-MAY-MOI"
    try:
        with _machine():  # cùng MachineGuid, cache rỗng → buộc tính lại
            after = device.get_fingerprint()
    finally:
        uuid.getnode, platform.node = orig_getnode, orig_node

    assert after == before


def test_fingerprint_is_hex64_and_stable_in_process():
    with _machine():
        fp1 = device.get_fingerprint()
        fp2 = device.get_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 64
        assert all(c in "0123456789abcdef" for c in fp1)


def test_falls_back_to_persisted_install_id_without_machine_guid():
    """Không đọc được registry → dùng install_id tự sinh, vẫn ổn định."""
    with _machine(guid="") as path:
        fp = device.get_fingerprint()
        install_id = _read(path)["install_id"]
        assert install_id
        device._cached = None
        assert device.get_fingerprint() == fp


def test_cache_rejected_when_machine_guid_differs():
    """Copy activation.json sang máy khác → không được mượn fingerprint cũ."""
    stolen = "b" * 64
    guard = hashlib.sha256(b"GUID-MAY-KHAC").hexdigest()
    with _machine(guid="GUID-MAY-CUA-TOI",
                  cache={"device_fingerprint": stolen, "fingerprint_guid": guard}):
        assert device.get_fingerprint() != stolen


def test_legacy_cache_without_guard_is_accepted():
    """Bản cũ chỉ ghi device_fingerprint (chưa có guard) → vẫn phải nhận lại.

    Đây là đường phục hồi cho máy đang bị kẹt device_limit.
    """
    legacy = "c" * 64
    with _machine(cache={"device_fingerprint": legacy, "license_code": "X"}):
        assert device.get_fingerprint() == legacy


def test_cache_accepted_when_registry_unreadable_this_launch():
    """Lần chạy này đọc registry lỗi → vẫn dùng cache, KHÔNG được tự đổi danh tính."""
    known = "d" * 64
    guard = hashlib.sha256(b"GUID-MAY-CUA-KHACH").hexdigest()
    with _machine(guid="", cache={"device_fingerprint": known, "fingerprint_guid": guard}):
        assert device.get_fingerprint() == known


def test_corrupt_cached_value_is_ignored():
    with _machine(cache={"device_fingerprint": "khong-phai-hex"}) as path:
        fp = device.get_fingerprint()
        assert len(fp) == 64
        assert _read(path)["device_fingerprint"] == fp


def test_persisting_fingerprint_keeps_other_keys():
    """Ghi fingerprint không được xoá token/mã license đang có trong file."""
    with _machine(cache={"license_code": "MN47-WD84", "license_token": "jwt"}) as path:
        device.get_fingerprint()
        data = _read(path)
        assert data["license_code"] == "MN47-WD84"
        assert data["license_token"] == "jwt"
