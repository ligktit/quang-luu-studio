import sys
import logging
import logging.handlers
from pathlib import Path


class _StreamToLogger:
    """
    Chuyển hướng sys.stdout / sys.stderr → logging.
    Dùng để bắt toàn bộ print() và traceback khi chạy frozen (PyInstaller).
    """
    def __init__(self, logger: logging.Logger, level: int = logging.INFO):
        self._logger = logger
        self._level  = level
        self._buf    = ""

    def write(self, msg: str):
        if not msg:
            return
        self._buf += msg
        # Flush mỗi khi gặp newline
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if line:
                self._logger.log(self._level, line)

    def flush(self):
        if self._buf.strip():
            self._logger.log(self._level, self._buf.rstrip())
            self._buf = ""

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("StreamToLogger has no real file descriptor")


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    """
    Khởi tạo hệ thống logging:
    - app.log   : tất cả bản ghi INFO+ (rotating, 5 MB x 3 bản)
    - errors.log: chỉ ERROR+ (rotating, 2 MB x 5 bản)
    - console   : chỉ in khi KHÔNG frozen (dev mode)
    - stdout/stderr bị redirect vào log khi frozen (PyInstaller)
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:
        return  # Đã được cấu hình (tránh gọi 2 lần)

    root.setLevel(logging.DEBUG)  # Root nhận tất cả; handler tự lọc

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler 1: app.log — INFO+
    fh = logging.handlers.RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8",
        delay=False,
    )
    fh.setLevel(level)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Handler 2: errors.log — ERROR+ only
    eh = logging.handlers.RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
        delay=False,
    )
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    root.addHandler(eh)

    # Handler 3: console — chỉ khi dev mode (không frozen)
    if not getattr(sys, "frozen", False):
        ch = logging.StreamHandler()
        ch.setLevel(level)
        ch.setFormatter(fmt)
        root.addHandler(ch)

    # Redirect stdout/stderr → log CHỈ khi frozen (PyInstaller, console=False)
    # Dev mode giữ nguyên console thật để debug dễ hơn
    if getattr(sys, "frozen", False):
        _stdout_log = logging.getLogger("stdout")
        _stderr_log = logging.getLogger("stderr")
        sys.stdout = _StreamToLogger(_stdout_log, logging.INFO)
        sys.stderr = _StreamToLogger(_stderr_log, logging.ERROR)

    # Tắt hoàn toàn noise từ thư viện bên thứ ba (chỉ hiện ERROR)
    for _noisy in ("librosa", "yt_dlp", "numba", "audioread", "urllib3", "PIL", "matplotlib", "joblib", "comtypes"):
        logging.getLogger(_noisy).setLevel(logging.ERROR)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def flush_logs() -> None:
    """Flush tất cả log handlers — gọi trước khi app thoát."""
    for handler in logging.getLogger().handlers:
        try:
            handler.flush()
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
