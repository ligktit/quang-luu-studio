"""Client-facing: kích hoạt & xác thực license."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.schemas import (
    ActivateRequest,
    LicenseResponse,
    TrialRequest,
    TrialResponse,
    VerifyRequest,
)
from app.security import decode_license_token, limiter
from app.services import licensing
from app.services.licensing import LicenseError

router = APIRouter(prefix="/api/v1", tags=["activation"])


def _error(e: LicenseError) -> JSONResponse:
    body = LicenseResponse(valid=False, status=e.status, message=e.message).model_dump(mode="json")
    return JSONResponse(status_code=e.http_status, content=body)


def _legacy_identities(decoded: dict | None, payload: VerifyRequest) -> set[str]:
    """
    Các fingerprint CŨ mà máy này chứng minh được là của mình.

    Có hai nguồn, và chúng KHÔNG mạnh ngang nhau:

    1. `legacy_fingerprint` do client gửi kèm — client **tính lại tại chỗ từ phần
       cứng máy** (MachineGuid + MAC + tên máy + CPU). Chép file activation.json
       sang máy khác không giả được giá trị này. Đây là đường chuẩn.

    2. Claim `fp` trong token — chữ ký của chính server, xác nhận máy này từng
       được cấp phép dưới danh tính đó. Yếu hơn: nó nằm trong file, nên ai chép
       được file thì "chứng minh" được. Bù lại, đây là thứ DUY NHẤT client ≤1.6.2
       gửi lên, nên nó cứu được đội hình đang chạy ngoài thị trường ngay hôm nay,
       không phải chờ bản cập nhật.

    Vì vậy nguồn 2 CHỈ dùng khi request không có nguồn 1 — tức là client cũ. Máy
    nào đã lên 1.6.3 là tự động quay về quy tắc chặt, không cần đụng lại server.
    Khi toàn đội hình đã cập nhật (xem /admin/devices), xoá hẳn nhánh này.

    Token không có claim `fp` không bao giờ được tính (đã chặn ở caller).
    """
    if payload.legacy_fingerprint:
        return {payload.legacy_fingerprint} - {payload.device_fingerprint}
    if decoded and decoded.get("fp"):
        return {decoded["fp"]} - {payload.device_fingerprint}
    return set()


@router.post("/activate", response_model=LicenseResponse)
@limiter.limit(settings.rate_limit_activate)
def activate(request: Request, payload: ActivateRequest, db: Session = Depends(get_db)):
    try:
        result = licensing.activate(
            db,
            code=payload.code,
            fingerprint=payload.device_fingerprint,
            hostname=payload.hostname,
            os=payload.os,
            app_version=payload.app_version,
            legacy_fingerprint=payload.legacy_fingerprint,
        )
        return LicenseResponse(**result)
    except LicenseError as e:
        return _error(e)


@router.post("/trial/start", response_model=TrialResponse)
@limiter.limit(settings.rate_limit_activate)
def trial_start(request: Request, payload: TrialRequest, db: Session = Depends(get_db)):
    """Xin dùng thử cho một máy. Máy đã dùng rồi sẽ nhận lại đúng mốc bắt đầu cũ."""
    result = licensing.start_trial(
        db,
        fingerprint=payload.device_fingerprint,
        hostname=payload.hostname,
        os=payload.os,
        app_version=payload.app_version,
        legacy_fingerprint=payload.legacy_fingerprint,
    )
    return TrialResponse(**result)


@router.post("/license/verify", response_model=LicenseResponse)
@limiter.limit(settings.rate_limit_verify)
def verify(request: Request, payload: VerifyRequest, db: Session = Depends(get_db)):
    # Lấy code: ưu tiên token (đã ký) → fallback code thô.
    #
    # Token QUÁ HẠN vẫn được chấp nhận ở đây (verify_exp=False): đó chính là lúc
    # client cần token mới. Hiệu lực thật do DB quyết ngay bên dưới, và claim
    # `fp` vẫn phải khớp máy gửi lên nên token nhặt được của máy khác vô dụng.
    code = payload.code
    decoded = None
    if payload.token:
        decoded = decode_license_token(payload.token, verify_exp=False)
        if decoded is None:
            # Token rác/ký bằng khoá lạ. Còn mã thô thì vẫn cho check-in bằng mã
            # (device phải có sẵn trong DB), không thì mới từ chối.
            if not payload.code:
                return _error(LicenseError("Token không hợp lệ.", status="invalid", http_status=401))
        elif not decoded.get("fp"):
            # Token không ràng máy — ai nhặt được cũng dùng lại được.
            return _error(LicenseError("Token không khớp thiết bị.", status="invalid", http_status=403))
        elif payload.legacy_fingerprint and decoded["fp"] not in (
            payload.device_fingerprint, payload.legacy_fingerprint
        ):
            # Client mới (có gửi legacy_fingerprint) chịu quy tắc CHẶT: token phải
            # thuộc đúng máy này, hoặc đúng danh tính cũ mà máy tự tính lại được.
            return _error(LicenseError("Token không khớp thiết bị.", status="invalid", http_status=403))
        else:
            code = decoded.get("code")

    if not code:
        return _error(LicenseError("Thiếu mã hoặc token.", status="invalid", http_status=400))

    # `fp` trong token khác fingerprint gửi lên KHÔNG còn bị từ chối thẳng: đó
    # chính là dấu hiệu máy vừa đổi fingerprint. Token là chữ ký của server nên
    # nó là bằng chứng hợp lệ về danh tính cũ — find_device() sẽ chỉ nối lại khi
    # danh tính đó thật sự thuộc ĐÚNG mã license này và bản ghi chưa bị chặn.
    try:
        result = licensing.verify(
            db, code=code, fingerprint=payload.device_fingerprint,
            app_version=payload.app_version,
            legacy_fingerprint=_legacy_identities(decoded, payload),
        )
        return LicenseResponse(**result)
    except LicenseError as e:
        return _error(e)
