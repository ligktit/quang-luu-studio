# ui/dialogs/first_run_dialog.py
"""Quang Lưu Studio — Hộp thoại lần chạy đầu sau khi cài.

Thay cho [Code] của bộ cài Inno: tạo file mặc định, chạy setup_all.bat /auto
(cổng MIDI, Surface Studio One, script Cubase), hỏi cài loopMIDI nếu thiếu,
hỏi dọn bản cũ trong Program Files. Việc nặng chạy trong QThread để cửa sổ
không đơ. Cờ first_run_done CHỈ được ghi khi đi hết luồng — đóng ngang thì
lần mở sau chạy lại.
"""
import logging
import os
import sys

from PySide6.QtCore import QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)

from core import first_run
from core.config import APP_DIR, DATA_DIR, ConfigManager
from ui.design_tokens import C, FONT

log = logging.getLogger(__name__)


class _Job(QThread):
    done = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # không để luồng chết im lặng
            self.done.emit(e)


class FirstRunDialog(QDialog):
    def __init__(self, app_dir, data_dir, legacy_dir=None, run_setup=True, parent=None):
        super().__init__(parent)
        self._app_dir = app_dir
        self._data_dir = data_dir
        self._legacy_dir = legacy_dir
        self._run_setup = run_setup
        self._code = None
        self._tried_loopmidi = False
        self._notes = []
        self._job = None
        self._started = False
        self._sau_de_sau = self._ket_thuc

        self.setWindowTitle("Quang Lưu Studio")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")
        vl = QVBoxLayout(self)
        self._lbl_title = QLabel("Đang chuẩn bị Quang Lưu Studio")
        self._lbl_title.setStyleSheet("font-size:16px; font-weight:600;")
        self._lbl_status = QLabel("")
        self._lbl_status.setWordWrap(True)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)   # chạy vô hạn — không đo được % của setup_all
        self._progress.setTextVisible(False)
        self._lbl_notes = QLabel("")
        self._lbl_notes.setWordWrap(True)
        for w in (self._lbl_title, self._lbl_status, self._progress, self._lbl_notes):
            vl.addWidget(w)

        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_loopmidi = QPushButton("Cài loopMIDI")
        self._btn_legacy = QPushButton("Dọn bản cũ")
        self._btn_later = QPushButton("Để sau")
        self._btn_continue = QPushButton("Tiếp tục")
        for b in (self._btn_loopmidi, self._btn_legacy, self._btn_later, self._btn_continue):
            b.hide()
            row.addWidget(b)
        vl.addLayout(row)

        self._btn_loopmidi.clicked.connect(self._cai_loopmidi)
        self._btn_legacy.clicked.connect(self._don_ban_cu)
        self._btn_later.clicked.connect(self._de_sau)
        self._btn_continue.clicked.connect(self._xong)

    # ── tiện ích ──
    def showEvent(self, event):
        super().showEvent(event)
        if not self._started:
            self._started = True
            QTimer.singleShot(0, self._bat_dau)

    def _buttons(self, *visible):
        for b in (self._btn_loopmidi, self._btn_legacy, self._btn_later, self._btn_continue):
            b.setVisible(b in visible)
        self._progress.setVisible(not visible)

    def _chay(self, status, fn, then):
        self._lbl_status.setText(status)
        self._buttons()
        self._job = _Job(fn, self)
        self._job.done.connect(lambda result, job=self._job: self._job_xong(job, result, then))
        self._job.start()

    def _job_xong(self, job, result, then):
        job.wait()   # luồng vừa phát tín hiệu cuối run() → chờ nó thoát hẳn trước khi đi tiếp
        then(result)

    def reject(self):
        # Đang chạy việc nền (setup_all, cài loopMIDI, dọn bản cũ): không đóng ngang,
        # nếu không QThread bị huỷ khi còn chạy.
        if self._job is not None and self._job.isRunning():
            return
        super().reject()

    def _chay_setup_all(self):
        self._chay("Đang tạo cổng MIDI và kết nối với DAW…",
                   lambda: first_run.run_setup_all(self._app_dir), self._sau_setup_all)

    # ── luồng ──
    def _bat_dau(self):
        if not self._run_setup:
            self._buoc_ban_cu()
            return
        pf = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles", "")
        daw_kind = first_run.default_daw(pf, os.environ.get("APPDATA", ""))
        try:
            first_run.ensure_default_data_files(self._data_dir, daw_kind)
        except Exception:
            log.exception("Không tạo được file dữ liệu mặc định")
        self._chay_setup_all()

    def _sau_setup_all(self, code):
        self._code = code if isinstance(code, int) else first_run.SETUP_ALL_FAILED
        if (self._code > 0 and self._code & 1 and not self._tried_loopmidi
                and first_run.find_loopmidi() is None):
            self._lbl_status.setText(
                "Máy chưa có loopMIDI — phần mềm tạo cổng MIDI ảo để app điều khiển DAW. "
                "Cần cài một lần; Windows sẽ hỏi quyền.")
            self._buttons(self._btn_loopmidi, self._btn_later)
            self._sau_de_sau = self._buoc_ban_cu
            return
        self._buoc_ban_cu()

    def _cai_loopmidi(self):
        self._tried_loopmidi = True
        self._chay("Đang cài loopMIDI…", first_run.install_loopmidi_elevated, self._sau_cai_loopmidi)

    def _sau_cai_loopmidi(self, ok):
        if ok is True:
            self._chay_setup_all()
        else:
            self._notes.append("Chưa cài được loopMIDI. Tải tại https://www.tobias-erichsen.de/software/loopmidi.html "
                               "rồi chạy setup_all.bat trong thư mục cài đặt.")
            self._buoc_ban_cu()

    def _buoc_ban_cu(self):
        if self._legacy_dir is None:
            self._ket_thuc()
            return
        self._lbl_status.setText(
            "Máy còn bản Quang Lưu Studio cũ trong Program Files. Dọn đi để khỏi nhầm biểu tượng? "
            "Windows sẽ hỏi quyền. Dữ liệu bài hát và cài đặt không bị đụng.")
        self._buttons(self._btn_legacy, self._btn_later)
        self._sau_de_sau = self._ket_thuc

    def _don_ban_cu(self):
        legacy = self._legacy_dir

        def work():
            first_run.migrate_legacy_app_config(legacy)
            return first_run.cleanup_legacy_elevated(legacy)
        self._chay("Đang dọn bản cũ…", work, self._sau_don_ban_cu)

    def _sau_don_ban_cu(self, ok):
        if ok is not True:
            self._notes.append(
                "Chưa dọn được bản cũ (có thể đã bấm Không ở hộp hỏi quyền, hoặc thư mục cài cũ cần gỡ tay "
                "trong Cài đặt → Ứng dụng). App sẽ hỏi lại lần mở sau.")
        self._ket_thuc()

    def _de_sau(self):
        self._sau_de_sau()

    def _ket_thuc(self):
        if self._run_setup:
            settings = ConfigManager.load_settings()
            ConfigManager.save_settings(first_run.mark_done(settings))
        notes = first_run.describe_setup_all_code(self._code) + self._notes
        if not notes:
            self.accept()
            return
        self._lbl_status.setText("Đã xong. Còn vài việc cần làm:")
        self._lbl_notes.setText("\n".join("• " + n for n in notes))
        self._buttons(self._btn_continue)

    def _xong(self):
        self.accept()


def run_first_run_if_needed():
    """Gọi từ main.py trước cổng kích hoạt. Chỉ chạy ở bản cài Velopack."""
    if not first_run.is_velopack_install(APP_DIR):
        return
    settings = ConfigManager.load_settings()
    legacy = first_run.find_legacy_install() or None   # "" = khoá cũ không có đường dẫn → không có gì để dọn
    need_setup = not first_run.is_done(settings)
    if not need_setup and legacy is None:
        return
    if QApplication.instance() is None:
        QApplication(sys.argv)
    FirstRunDialog(APP_DIR, DATA_DIR, legacy_dir=legacy, run_setup=need_setup).exec()
