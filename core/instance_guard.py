"""Chặn Velopack tắt ngang app đang chạy.

Update.exe tắt MỌI tiến trình chạy từ thư mục cài khi áp dụng bản đã tải. Vì vậy chỉ
được áp dụng khi tiến trình này là bản duy nhất, và không bao giờ áp dụng trong các
lệnh công cụ (--tu-kiem-tra, --thu-tai, --chuyen-cau-hinh-cu) mà người hát chạy khi
app chính đang mở.

Module này được nạp ở ĐẦU main.py, trước Qt/numba: chỉ stdlib + psutil (nạp trễ).
Mọi lỗi nghiêng về phía an toàn — không chắc thì coi như còn bản khác đang chạy.
"""
import logging
import os
import time

log = logging.getLogger(__name__)

TOOL_FLAGS = ("--tu-kiem-tra", "--thu-tai", "--chuyen-cau-hinh-cu")


def _norm(path):
    return os.path.normcase(os.path.realpath(path))


def _processes(process_iter):
    """Các (pid, đường dẫn exe đã chuẩn hoá) đọc được; tiến trình bị từ chối truy cập bị bỏ qua."""
    if process_iter is None:
        import psutil
        process_iter = psutil.process_iter
    for proc in process_iter(["pid", "exe"]):
        info = proc.info
        exe = info.get("exe")
        if exe:
            yield info.get("pid"), _norm(exe)


def other_instances_running(exe_path=None, own_pid=None, process_iter=None):
    """True nếu còn tiến trình khác (pid khác) chạy cùng file exe này. Lỗi → True."""
    try:
        import sys
        mine = _norm(exe_path or sys.executable)
        own = os.getpid() if own_pid is None else own_pid
        return any(pid != own and exe == mine for pid, exe in _processes(process_iter))
    except Exception as e:
        log.warning("Không liệt kê được tiến trình (coi như còn bản khác đang chạy): %s", e)
        return True


def auto_apply_on_startup_allowed(argv, others_running):
    """Velopack chỉ được tự áp dụng bản chờ khi mở app bình thường và là bản duy nhất."""
    return not (others_running or any(flag in argv for flag in TOOL_FLAGS))


def wait_for_update_exe(app_dir, timeout=300, poll=1.0, process_iter=None,
                        sleep=time.sleep, clock=time.monotonic):
    """Đóng app rồi mở lại ngay: Update.exe (ở thư mục cha của app_dir) đang áp dụng gói
    ~550 MB. Chờ nó xong (tối đa timeout giây) kẻo bản cũ bị tắt ngang giữa chừng.
    True nếu đã gặp Update.exe đang chạy. Lỗi liệt kê → False (không treo app)."""
    try:
        target = _norm(os.path.join(os.path.dirname(os.path.abspath(app_dir)), "Update.exe"))
        start, waited = clock(), False
        while any(exe == target for _, exe in _processes(process_iter)):
            if not waited:
                log.info("Update.exe đang áp dụng bản cập nhật — chờ tối đa %ss", timeout)
            waited = True
            if clock() - start >= timeout:
                log.warning("Chờ Update.exe quá %ss — mở app luôn", timeout)
                break
            sleep(poll)
        return waited
    except Exception as e:
        log.warning("Không kiểm được Update.exe: %s", e)
        return False
