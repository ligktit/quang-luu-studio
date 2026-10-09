"""Mô hình chung của Tự sửa âm thanh: trạng thái, kết quả, mục kiểm tra."""
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    OK = "ok"
    LOI = "loi"
    KHONG_RO = "khong_ro"
    BO_QUA = "bo_qua"
    DA_SUA = "da_sua"
    CAN_LAM_TAY = "can_lam_tay"


# Mục phụ thuộc mang một trong các trạng thái này thì mục sau bỏ qua.
# KHONG_RO không chặn: "không biết" không có nghĩa là hỏng.
BLOCKING = frozenset({Status.LOI, Status.CAN_LAM_TAY, Status.BO_QUA})

# Thứ tự sửa: cầu nối → phần mềm thu âm → Windows → trình duyệt.
GROUP_ORDER = ("bridge", "daw", "windows", "browser")
GROUP_TITLES = {
    "bridge": "Cầu nối MIDI",
    "daw": "Phần mềm thu âm",
    "windows": "Windows",
    "browser": "Trình duyệt",
}


@dataclass(frozen=True)
class Finding:
    status: Status
    message: str
    detail: str = ""
    fixable: bool = False
    guide: tuple = field(default_factory=tuple)


def ok(message):
    return Finding(Status.OK, message)


def loi(message, fixable=True, guide=(), detail=""):
    return Finding(Status.LOI, message, detail=detail, fixable=fixable, guide=tuple(guide))


def khong_ro(message, detail=""):
    return Finding(Status.KHONG_RO, message, detail=detail)


def bo_qua(message):
    return Finding(Status.BO_QUA, message)


def da_sua(message):
    return Finding(Status.DA_SUA, message)


def can_lam_tay(message, guide=()):
    return Finding(Status.CAN_LAM_TAY, message, guide=tuple(guide))


class Check:
    """Một mục kiểm tra. Lớp con đặt thuộc tính và viết detect/fix.

    detect() không được thay đổi gì trên máy. fix() chỉ được gọi khi detect()
    ra LOI có fixable=True (hoặc KHONG_RO khi fix_when_unknown=True).
    """
    id = ""
    group = "bridge"
    title = ""
    requires = ()
    timeout_s = 15.0
    fix_timeout_s = 30.0
    fix_when_unknown = False

    def applies(self, ctx) -> bool:
        return True

    def detect(self, ctx) -> Finding:
        raise NotImplementedError

    def fix(self, ctx) -> Finding:
        raise NotImplementedError
