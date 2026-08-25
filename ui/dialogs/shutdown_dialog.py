"""
Quang Lưu Studio — Hộp thoại "đang đóng Studio One an toàn".

Đóng sạch Studio One cần lưu bài, chờ nó ghi xong rồi chờ process thoát hẳn —
tổng cộng có thể vài chục giây. Trước đây việc này chạy nền trong thread daemon
rồi bị os._exit(0) cắt ngang sau 4 giây, nên gần như luôn rơi vào tắt cứng.

Giờ chạy trước mặt người dùng: có dòng trạng thái, có nút bỏ qua, và app chỉ
thoát khi Studio One đã thật sự đóng (hoặc kỹ thuật viên bấm bỏ qua).
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)
from PySide6.QtCore import Qt, QThread, Signal

from ui.design_tokens import C, FONT, lighten


class _CloseWorker(QThread):
    progress = Signal(str)
    finished_result = Signal(dict)

    def __init__(self, engine, timeout_sec, force_kill, should_abort, parent=None):
        super().__init__(parent)
        self._engine = engine
        self._timeout = timeout_sec
        self._force_kill = force_kill
        self._should_abort = should_abort

    def run(self):
        try:
            result = self._engine.close_studio_one_safely(
                timeout_sec=self._timeout,
                save=True,
                force_kill=self._force_kill,
                on_progress=self.progress.emit,
                should_abort=self._should_abort,
            )
        except Exception as e:
            result = {"status": "error", "saved": False, "error": str(e)}
        self.finished_result.emit(result)


class StudioOneShutdownDialog(QDialog):
    """Chờ Studio One lưu bài và thoát. exec() trả về khi xong hoặc bị bỏ qua."""

    def __init__(self, engine, timeout_sec=45.0, force_kill=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Đang đóng Studio One")
        self.setModal(True)
        self.setFixedWidth(430)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        self.result_data = {"status": "aborted", "saved": False}
        self._aborted = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 18)
        lay.setSpacing(12)

        title = QLabel("Đang đóng Studio One an toàn")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 900; color: {C['text']};"
            f" font-family: {FONT}; background: transparent;"
        )
        lay.addWidget(title)

        hint = QLabel(
            "Đang lưu bài và chờ Studio One tự thoát. Đừng tắt máy lúc này — "
            "tắt ngang sẽ khiến lần mở sau Studio One đòi phục hồi phiên."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text_muted']};"
            f" font-family: {FONT}; background: transparent;"
        )
        lay.addWidget(hint)

        bar = QProgressBar()
        bar.setRange(0, 0)          # chạy vô định — không đoán được còn bao lâu
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(f"""
            QProgressBar {{ background-color: {C['card']}; border: none; border-radius: 4px; }}
            QProgressBar::chunk {{ background-color: {C['teal']}; border-radius: 4px; }}
        """)
        lay.addWidget(bar)

        self._status = QLabel("Đang chuẩn bị...")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {C['teal']};"
            f" font-family: {FONT}; background: transparent;"
        )
        lay.addWidget(self._status)

        row = QHBoxLayout()
        row.addStretch()
        skip = QPushButton("Bỏ qua, thoát ngay")
        skip.setCursor(Qt.PointingHandCursor)
        skip.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['card_hover']}; color: {C['text']};
                border: none; border-radius: 12px; padding: 9px 16px;
                font-size: 12px; font-weight: 700; font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: {lighten(C['card_hover'], 0.12)}; }}
        """)
        skip.setToolTip("Để Studio One chạy tiếp và thoát app ngay")
        skip.clicked.connect(self._on_skip)
        row.addWidget(skip)
        lay.addLayout(row)

        self._worker = _CloseWorker(engine, timeout_sec, force_kill,
                                    lambda: self._aborted, self)
        self._worker.progress.connect(self._status.setText)
        self._worker.finished_result.connect(self._on_done)
        self._worker.start()

    def _on_skip(self):
        self._aborted = True
        self._status.setText("Đang dừng...")

    def _on_done(self, result):
        self.result_data = result
        self.accept()

    def closeEvent(self, event):
        # Không cho tắt hộp thoại giữa chừng bằng Esc/Alt+F4 — worker vẫn đang
        # thao tác cửa sổ Studio One, biến mất giữa chừng là hỏng việc.
        if self._worker.isRunning():
            self._aborted = True
            self._worker.wait(3000)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._on_skip()
            return
        super().keyPressEvent(event)
