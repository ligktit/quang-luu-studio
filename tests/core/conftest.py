"""Cấu hình chung cho tests/core."""
import sys
import types

import pytest


def _no_real_audio(*_args, **_kwargs):
    raise RuntimeError("tests/core không được mở thiết bị âm thanh thật")


@pytest.fixture(autouse=True, scope="session")
def _chan_thiet_bi_am_thanh_that():
    """Thay pyaudiowpatch bằng bản giả cho CẢ phiên test.

    Nhiều test chạy luồng dò tone nền; luồng có thể sống lâu hơn test, tới lúc
    mock của test đã gỡ thì nó gọi pyaudiowpatch THẬT (thu loopback từ loa của
    máy chạy test) và thỉnh thoảng làm cả pytest chết vì access violation.
    Test nào cần pyaudiowpatch giả riêng vẫn tự đè bằng patch.dict(sys.modules).
    """
    fake = types.ModuleType("pyaudiowpatch")
    fake.PyAudio = _no_real_audio
    fake.paFloat32 = 1
    fake.paInt16 = 8
    saved = sys.modules.get("pyaudiowpatch")
    sys.modules["pyaudiowpatch"] = fake
    yield
    if saved is not None:
        sys.modules["pyaudiowpatch"] = saved
    else:
        sys.modules.pop("pyaudiowpatch", None)
