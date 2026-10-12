"""Hộp thoại Tự sửa âm thanh: danh sách mục theo nhóm, trạng thái từng mục, hướng dẫn làm tay."""
import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QScrollArea, QToolButton,
    QVBoxLayout, QWidget,
)

from core.audio_doctor.model import GROUP_ORDER, GROUP_TITLES, Status
from ui import responsive as rp
from ui.design_tokens import C, FONT, scrollarea_qss
from ui.ui_invoker import UiInvoker

_ICON = {
    None: ("…", C["text_muted"]),
    Status.OK: ("✓", C["green"]),
    Status.DA_SUA: ("✓", C["green"]),
    Status.LOI: ("✗", C["accent"]),
    Status.CAN_LAM_TAY: ("!", C["orange"]),
    Status.KHONG_RO: ("?", C["text_muted"]),
    Status.BO_QUA: ("–", C["text_muted"]),
}


class _Row(QWidget):
    def __init__(self, check, parent=None):
        super().__init__(parent)
        self.check = check
        self.status = None
        self.finding = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        top = QHBoxLayout()
        self.icon = QLabel("·")
        self.icon.setFixedWidth(18)
        title = QLabel(f"<b>{check.title}</b>")
        self.msg_label = QLabel("")
        self.msg_label.setWordWrap(True)
        self.guide_btn = QToolButton()
        self.guide_btn.setText("Hướng dẫn")
        self.guide_btn.setCheckable(True)
        self.guide_btn.hide()
        top.addWidget(self.icon)
        top.addWidget(title)
        top.addStretch()
        top.addWidget(self.guide_btn)
        lay.addLayout(top)
        lay.addWidget(self.msg_label)
        self.guide_label = QLabel("")
        self.guide_label.setWordWrap(True)
        self.guide_label.hide()
        lay.addWidget(self.guide_label)
        self.guide_btn.toggled.connect(self.guide_label.setVisible)

    def set_finding(self, finding):
        self.finding = finding
        self.status = None if finding is None else finding.status
        glyph, color = _ICON[self.status]
        self.icon.setText(glyph)
        self.icon.setStyleSheet(f"color: {color}; font-weight: bold;")
        self.msg_label.setText("Đang kiểm tra…" if finding is None else finding.message)
        self.setAccessibleName(f"{self.check.title}: {self.msg_label.text()}")
        guide = () if finding is None else finding.guide
        self.guide_label.setText("\n".join(f"{i}. {s}" for i, s in enumerate(guide, 1)))
        self.guide_btn.setVisible(bool(guide) and self.status is Status.CAN_LAM_TAY)


class AudioDoctorDialog(QDialog):
    _progress = Signal(object, object)
    _finished = Signal(object)

    def __init__(self, dashboard, service, auto_fix=True):
        super().__init__(dashboard)
        self._dashboard = dashboard
        self._service = service
        self._invoker = UiInvoker(self)
        self._running = False
        self.report = None
        self.setWindowTitle("Tự sửa âm thanh")
        # Nền tối tường minh: thiếu nó thì chữ sáng của theme rơi lên nền sáng
        # mặc định của Windows, gần như không đọc được.
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")
        rp.set_min_width(self, 520)
        self.setMinimumHeight(rp.px(420, self))
        root = QVBoxLayout(self)
        self.summary_label = QLabel("Đang kiểm tra…")
        self.summary_label.setWordWrap(True)
        root.addWidget(self.summary_label)

        body = QWidget()
        bl = QVBoxLayout(body)
        self.rows = {}
        checks = service.runner.checks
        for group in GROUP_ORDER:
            members = [c for c in checks if c.group == group]
            if not members:
                continue
            head = QLabel(GROUP_TITLES[group])
            head.setStyleSheet("font-weight: bold; margin-top: 6px;")
            bl.addWidget(head)
            for c in members:
                row = _Row(c)
                row.hide()                   # chỉ hiện mục áp dụng cho máy này
                self.rows[c.id] = row
                bl.addWidget(row)
        bl.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollarea_qss())
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        btns = QHBoxLayout()
        self.fix_btn = QPushButton("Tự sửa lại")
        self.check_btn = QPushButton("Kiểm tra lại")
        self.send_btn = QPushButton("Gửi cho kỹ thuật")
        close_btn = QPushButton("Đóng")
        for b in (self.fix_btn, self.check_btn, self.send_btn):
            btns.addWidget(b)
        btns.addStretch()
        btns.addWidget(close_btn)
        root.addLayout(btns)
        self.fix_btn.clicked.connect(lambda: self.start("fix"))
        self.check_btn.clicked.connect(lambda: self.start("check"))
        self.send_btn.clicked.connect(self._send_to_support)
        close_btn.clicked.connect(self.close)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        if auto_fix:
            self.start("fix")

    # ── chạy ────────────────────────────────────────────────────────────────
    def start(self, mode):
        if self._running:
            return
        self._running = True
        for b in (self.fix_btn, self.check_btn, self.send_btn):
            b.setEnabled(False)
        self.summary_label.setText("Đang sửa…" if mode == "fix" else "Đang kiểm tra…")

        def work():
            rep = self._service.run(mode, "button", ask=self._ask,
                                    on_progress=lambda c, f: self._progress.emit(c, f))
            self._finished.emit(rep)

        threading.Thread(target=work, daemon=True, name="audio-doctor-run").start()

    def _ask(self, question):
        return self._invoker.call(
            lambda: QMessageBox.question(self, "Tự sửa âm thanh", question)
            == QMessageBox.StandardButton.Yes)

    def _on_progress(self, check, finding):
        row = self.rows.get(check.id)
        if row is None:
            return
        row.show()
        row.set_finding(finding)
        if finding is not None and finding.status in (Status.DA_SUA, Status.CAN_LAM_TAY):
            self._speak(f"{check.title}: {finding.message}")

    def _on_finished(self, report):
        self._running = False
        self.report = report
        for b in (self.fix_btn, self.check_btn, self.send_btn):
            b.setEnabled(True)
        res = report.results.values()
        fixed = sum(1 for f in res if f.status is Status.DA_SUA)
        manual = [f for f in res if f.status in (Status.CAN_LAM_TAY, Status.LOI)]
        if not manual:
            text = f"Đã sửa {fixed} mục. Âm thanh đã sẵn sàng." if fixed else "Mọi thứ đều ổn."
        else:
            text = (f"Đã sửa {fixed} mục. Còn {len(manual)} mục cần làm tay — "
                    "bấm «Hướng dẫn» ở từng mục, hoặc «Gửi cho kỹ thuật».")
        self.summary_label.setText(text)
        # DAW mở xong giữa chừng thường chiếm tiền cảnh, che mất hộp thoại.
        self.raise_()
        self.activateWindow()
        self._speak(text)
        cb = getattr(self._dashboard, "_on_audio_doctor_report", None)
        if cb:
            cb(report, "button")

    def _speak(self, text):
        speak = getattr(self._dashboard, "_a11y_speak", None)
        if speak:
            try:
                speak(text)
            except Exception:
                pass

    def _send_to_support(self):
        if self.report is None:
            return
        rep = self.report
        n = len(rep.problems())

        def work():
            from core import support
            res = support.submit("loi", f"Tự sửa âm thanh: còn {n} mục cần làm tay",
                                 rep.summary(), include_logs=True)
            self._dashboard._message_signal.emit(res.get("message") or "Đã gửi cho kỹ thuật",
                                                 not res.get("ok") and not res.get("queued"))

        threading.Thread(target=work, daemon=True).start()
