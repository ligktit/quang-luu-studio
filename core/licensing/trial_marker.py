"""
Mốc bắt đầu dùng thử lưu song song trong registry Windows.

Vì sao cần: activation.json nằm trong %APPDATA% và người dùng xoá được. Registry
là bản sao thứ hai — muốn reset dùng thử phải xoá cả hai chỗ, mà kể cả xoá hết
thì lần xin dùng thử tiếp theo server vẫn trả về mốc cũ theo fingerprint máy
(xem core/licensing/client.start_trial_online).

HKCU chứ không phải HKLM: ghi HKLM cần quyền admin, mà app chạy quyền thường.
"""
import logging

log = logging.getLogger(__name__)

_KEY_PATH = r"Software\QuangLuuStudio"
_VALUE_NAME = "TrialStart"


def read() -> float:
    """Mốc bắt đầu dùng thử (epoch giây). 0.0 nếu chưa có / không đọc được."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return float(value)
    except Exception as e:  # chưa có key, không phải Windows, giá trị hỏng
        log.debug("Không đọc được mốc dùng thử trong registry: %s", e)
        return 0.0


def write(started_at: float) -> None:
    """Ghi mốc bắt đầu. Chỉ ghi nếu chưa có hoặc mốc mới SỚM HƠN mốc đang lưu."""
    try:
        import winreg
        existing = read()
        if existing and existing <= started_at:
            return  # đã có mốc sớm hơn — giữ nguyên, không cho đẩy hạn về sau
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _KEY_PATH, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, repr(float(started_at)))
    except Exception as e:
        log.debug("Không ghi được mốc dùng thử vào registry: %s", e)
