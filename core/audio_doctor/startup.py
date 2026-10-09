"""Quyết định lúc nào chạy lượt kiểm tra khởi động — logic thuần, đồng hồ do ngoài đưa vào."""


class StartupGate:
    """
    - "run": cửa sổ chính DAW đã đứng yên `settle_s` giây, hoặc đã chờ đủ `wait_s`.
    - "rerun": lần "run" xảy ra do hết giờ chờ, sau đó DAW mới sẵn sàng → chạy lại
      MỘT lần để gỡ cảnh báo "chưa mở xong" nếu mọi thứ đã ổn.
    """

    def __init__(self, wait_s=180.0, settle_s=10.0, start=0.0):
        self.wait_s = float(wait_s)
        self.settle_s = float(settle_s)
        self.start = float(start)
        self._ready_since = None
        self._ran = False
        self._ran_ready = False

    @property
    def done(self) -> bool:
        return self._ran and self._ran_ready

    def update(self, now, daw_ready):
        if daw_ready:
            if self._ready_since is None:
                self._ready_since = now
        else:
            self._ready_since = None
        settled = self._ready_since is not None and now - self._ready_since >= self.settle_s
        if not self._ran:
            if settled:
                self._ran = self._ran_ready = True
                return "run"
            if now - self.start >= self.wait_s:
                self._ran = True
                return "run"
            return None
        if not self._ran_ready and settled:
            self._ran_ready = True
            return "rerun"
        return None
