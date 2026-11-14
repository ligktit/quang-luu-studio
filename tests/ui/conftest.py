import pytest


@pytest.fixture(autouse=True)
def _xoa_han_widget_cua_test_truoc():
    """Xoá hẳn widget test trước để lại, trước khi test này chạy.

    pytest-qt đóng widget đã addWidget rồi gọi deleteLater(), nhưng DeferredDelete
    chỉ được xử lý khi event loop chạy — trong pytest gần như không bao giờ. Dashboard
    cũ vì thế sống tiếp (ẩn), timer/animation của chúng vẫn chạy mỗi lần test sau
    processEvents: test thứ n chậm hơn test n-1 ~1,6 s, cả bộ phình theo bình phương
    số dashboard (đo 2026-11-10: test_mixer_mic2.py 12 phút 40 → 6,7 giây).
    """
    from PySide6.QtCore import QCoreApplication, QEvent
    if QCoreApplication.instance() is not None:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    yield
