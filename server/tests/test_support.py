"""Kênh hỗ trợ hai chiều: gửi ticket → dev trả lời → khách đọc."""
FP = "device-fingerprint-support-001"
FP2 = "device-fingerprint-support-002"


def _create(client, fp=FP, subject="Không dò được tone", **kw):
    payload = {
        "device_fingerprint": fp,
        "subject": subject,
        "body": "Mở bài lên thì app báo lỗi tải YouTube.",
        "category": "loi",
        "contact": "0900000000",
        "app_version": "1.8.0",
    }
    payload.update(kw)
    return client.post("/api/v1/support/ticket", json=payload)


def test_tao_ticket_khong_can_license(client):
    """Máy CHƯA kích hoạt vẫn phải gửi được hỗ trợ — đó là người cần nhất."""
    r = _create(client)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ticket_code"].startswith("HT-")


def test_inbox_chi_tra_ticket_cua_may_minh(client):
    _create(client, fp=FP)
    _create(client, fp=FP2, subject="Câu hỏi khác")

    r = client.post("/api/v1/support/inbox", json={"device_fingerprint": FP})
    assert r.status_code == 200
    tickets = r.json()["tickets"]
    assert len(tickets) == 1
    assert tickets[0]["subject"] == "Không dò được tone"
    assert len(tickets[0]["messages"]) == 1


def test_dev_tra_loi_thi_khach_thay_chua_doc(admin_client):
    code = _create(admin_client).json()["ticket_code"]
    tid = int(code.split("-")[1])

    admin_client.post(f"/admin/support/{tid}/reply", data={"body": "Anh cập nhật lên 1.8.0 giúp em."})

    r = admin_client.post("/api/v1/support/inbox", json={"device_fingerprint": FP})
    body = r.json()
    assert body["unread_count"] == 1
    ticket = body["tickets"][0]
    assert ticket["status"] == "answered"
    assert [m["sender"] for m in ticket["messages"]] == ["customer", "dev"]

    admin_client.post("/api/v1/support/ticket/read", json={"device_fingerprint": FP, "ticket_code": code})
    assert admin_client.post("/api/v1/support/inbox", json={"device_fingerprint": FP}).json()["unread_count"] == 0


def test_may_khac_khong_dung_duoc_ma_ticket(client):
    """Biết mã HT-xxxx thôi không đủ — ticket chứa số điện thoại của khách."""
    code = _create(client, fp=FP).json()["ticket_code"]

    r = client.post(
        "/api/v1/support/ticket/reply",
        json={"device_fingerprint": FP2, "ticket_code": code, "body": "chen ngang"},
    )
    assert r.status_code == 404

    r = client.post(
        "/api/v1/support/ticket/read",
        json={"device_fingerprint": FP2, "ticket_code": code},
    )
    assert r.status_code == 404


def test_khach_tra_loi_tiep_thi_ticket_mo_lai(admin_client):
    code = _create(admin_client).json()["ticket_code"]
    tid = int(code.split("-")[1])
    admin_client.post(f"/admin/support/{tid}/reply", data={"body": "Anh thử lại giúp em."})

    r = admin_client.post(
        "/api/v1/support/ticket/reply",
        json={"device_fingerprint": FP, "ticket_code": code, "body": "Vẫn lỗi anh ơi."},
    )
    assert r.status_code == 200

    ticket = admin_client.post("/api/v1/support/inbox", json={"device_fingerprint": FP}).json()["tickets"][0]
    assert ticket["status"] == "open"
    assert len(ticket["messages"]) == 3


def test_ticket_da_dong_thi_khong_tra_loi_duoc(admin_client):
    code = _create(admin_client).json()["ticket_code"]
    tid = int(code.split("-")[1])
    admin_client.post(f"/admin/support/{tid}/status", data={"status": "closed"})

    r = admin_client.post(
        "/api/v1/support/ticket/reply",
        json={"device_fingerprint": FP, "ticket_code": code, "body": "còn nữa"},
    )
    assert r.status_code == 409


def test_loai_yeu_cau_la_thi_quy_ve_khac(client):
    code = _create(client, category="hackerman").json()["ticket_code"]
    ticket = client.post("/api/v1/support/inbox", json={"device_fingerprint": FP}).json()["tickets"][0]
    assert ticket["ticket_code"] == code
    assert ticket["category"] == "khac"


def test_admin_xem_danh_sach_va_chi_tiet(admin_client):
    code = _create(admin_client).json()["ticket_code"]
    tid = int(code.split("-")[1])

    r = admin_client.get("/admin/support")
    assert r.status_code == 200 and code in r.text

    r = admin_client.get(f"/admin/support/{tid}")
    assert r.status_code == 200 and "Không dò được tone" in r.text

    # Mở ra rồi thì không còn là "new" — bảng tổng quan phải đếm đúng việc chưa ngó.
    ticket = admin_client.post("/api/v1/support/inbox", json={"device_fingerprint": FP}).json()["tickets"][0]
    assert ticket["status"] == "open"
