"""core/support.py — kênh hỗ trợ hai chiều phía client.

Không đụng mạng thật: mọi test đều thay _post bằng hàm giả.
"""
import json

import pytest

from core import support

FP = "fingerprint-may-test-0001"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Mỗi test: fingerprint cố định, server có cấu hình, hàng đợi trong tmp."""
    monkeypatch.setattr(support, "_fingerprint", lambda: FP)
    monkeypatch.setattr(support, "_server_base", lambda: "https://example.test")
    monkeypatch.setattr(support, "_queue_path", lambda: tmp_path / "support_queue.json")
    monkeypatch.setattr(support, "_log_tail", lambda *a, **k: "log giả")
    monkeypatch.setattr(support, "_device_context", lambda: {
        "hostname": "MAY-QUAN", "os": "Windows 11", "license_code": "ABC-123", "app_version": "1.8.0",
    })
    support._set_unread(0)
    yield


def _fake_post(status, body, sink=None):
    def _post(path, payload):
        if sink is not None:
            sink.append((path, payload))
        return status, body
    return _post


def test_submit_thanh_cong_tra_ma_ticket(monkeypatch):
    sink = []
    monkeypatch.setattr(support, "_post", _fake_post(200, {"ok": True, "ticket_code": "HT-000007"}, sink))

    res = support.submit("loi", "Tone sai", "Bài này app dò ra La Thứ nhưng thật ra Đô Trưởng.", "0900")

    assert res["ok"] is True and res["ticket_code"] == "HT-000007"
    path, payload = sink[0]
    assert path == "/api/v1/support/ticket"
    assert payload["device_fingerprint"] == FP
    assert payload["category"] == "loi"
    assert payload["log_excerpt"] == "log giả"


def test_submit_khong_gui_log_khi_khach_tat(monkeypatch):
    sink = []
    monkeypatch.setattr(support, "_post", _fake_post(200, {"ok": True, "ticket_code": "HT-1"}, sink))

    support.submit("khac", "Hỏi", "Nội dung", include_logs=False)

    assert "log_excerpt" not in sink[0][1]


def test_submit_mat_mang_thi_xep_hang_chu_khong_bao_loi(monkeypatch, tmp_path):
    monkeypatch.setattr(support, "_post", _fake_post(0, {}))

    res = support.submit("loi", "Tiêu đề", "Nội dung")

    assert res["ok"] is False and res["queued"] is True
    queued = json.loads((tmp_path / "support_queue.json").read_text(encoding="utf-8"))
    assert len(queued) == 1 and queued[0]["subject"] == "Tiêu đề"


def test_submit_thieu_noi_dung_thi_tu_choi_tai_cho(monkeypatch):
    called = []
    monkeypatch.setattr(support, "_post", _fake_post(200, {"ok": True}, called))

    res = support.submit("loi", "  ", "")

    assert res["ok"] is False and res["queued"] is False
    assert not called, "không được phí một vòng mạng cho form rỗng"


def test_loai_yeu_cau_la_thi_quy_ve_khac(monkeypatch):
    sink = []
    monkeypatch.setattr(support, "_post", _fake_post(200, {"ok": True, "ticket_code": "HT-1"}, sink))

    support.submit("khong-ton-tai", "T", "N")

    assert sink[0][1]["category"] == "khac"


def test_inbox_cap_nhat_bo_dem_chua_doc(monkeypatch):
    monkeypatch.setattr(support, "_post", _fake_post(200, {
        "ok": True, "unread_count": 2,
        "tickets": [{"ticket_code": "HT-1", "subject": "x", "messages": []}],
    }))

    res = support.inbox()

    assert res["ok"] is True and len(res["tickets"]) == 1
    assert support.unread_count() == 2


def test_mat_mang_thi_giu_nguyen_bo_dem_cu(monkeypatch):
    support._set_unread(3)
    monkeypatch.setattr(support, "_post", _fake_post(0, {}))

    res = support.inbox()

    assert res["ok"] is False
    assert support.unread_count() == 3, "mất mạng không có nghĩa là đã đọc hết"


def test_mark_read_giam_bo_dem(monkeypatch):
    support._set_unread(1)
    monkeypatch.setattr(support, "_post", _fake_post(200, {"ok": True}))

    assert support.mark_read("HT-1") is True
    assert support.unread_count() == 0


def test_bo_dem_khong_bao_gio_am(monkeypatch):
    monkeypatch.setattr(support, "_post", _fake_post(200, {"ok": True}))
    support._set_unread(0)

    support.mark_read("HT-1")

    assert support.unread_count() == 0


def test_khong_co_server_thi_khong_kha_dung(monkeypatch):
    monkeypatch.setattr(support, "_server_base", lambda: "")
    assert support.available() is False
    assert support.poll_inbox() == 0


def test_flush_bo_muc_bi_server_tu_choi_han(monkeypatch, tmp_path):
    """Một mục hỏng không được làm kẹt hàng đợi mãi mãi."""
    (tmp_path / "support_queue.json").write_text(
        json.dumps([{"subject": "hong"}, {"subject": "cung hong"}]), encoding="utf-8"
    )
    monkeypatch.setattr(support, "_post", _fake_post(422, {"ok": False, "message": "sai dữ liệu"}))

    thread_target = {}
    monkeypatch.setattr(
        support.threading, "Thread",
        lambda target, daemon=True: type("T", (), {"start": lambda _self: thread_target.setdefault("r", target())})(),
    )
    support.flush_queue()

    assert json.loads((tmp_path / "support_queue.json").read_text(encoding="utf-8")) == []


def test_flush_giu_lai_khi_van_mat_mang(monkeypatch, tmp_path):
    (tmp_path / "support_queue.json").write_text(json.dumps([{"subject": "cho gui"}]), encoding="utf-8")
    monkeypatch.setattr(support, "_post", _fake_post(0, {}))
    monkeypatch.setattr(
        support.threading, "Thread",
        lambda target, daemon=True: type("T", (), {"start": lambda _self: target()})(),
    )

    support.flush_queue()

    kept = json.loads((tmp_path / "support_queue.json").read_text(encoding="utf-8"))
    assert len(kept) == 1, "mất mạng thì phải giữ lại để gửi lần sau"
