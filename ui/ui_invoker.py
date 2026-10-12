"""Gọi một hàm trên thread của QObject (thường là main thread) và chờ kết quả."""
from PySide6.QtCore import QObject, QThread, Qt, Signal


class UiInvoker(QObject):
    _job = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job.connect(self._run, Qt.BlockingQueuedConnection)

    @staticmethod
    def _run(job):
        job()

    def call(self, fn, *args):
        # Đang ở đúng thread thì gọi thẳng — BlockingQueued trên cùng thread là treo.
        if QThread.currentThread() == self.thread():
            return fn(*args)
        box = {}

        def job():
            try:
                box["v"] = fn(*args)
            except BaseException as e:  # noqa: BLE001
                box["e"] = e

        self._job.emit(job)
        if "e" in box:
            raise box["e"]
        return box.get("v")
