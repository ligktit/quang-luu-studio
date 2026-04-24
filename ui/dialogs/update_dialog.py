"""Update available dialog."""
import threading

from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextBrowser, QProgressBar,
)

from core.version import __version__


class _UpdateSignals(QObject):
    progress = Signal(int, int)   # downloaded, total
    error    = Signal(str)
    done     = Signal()


class UpdateDialog(QDialog):
    """
    Shows information about a new release and lets the user choose
    to install, defer, or skip the version.
    """

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self._release = release
        self._signals = _UpdateSignals()
        self._signals.progress.connect(self._on_progress)
        self._signals.error.connect(self._on_error)
        self._signals.done.connect(self._on_done)

        self.setWindowTitle(f"Có phiên bản mới: v{release.version}")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        size_mb = self._release.size_bytes / 1_000_000
        header  = QLabel(
            f"<h2 style='margin:0'>🎉 Phiên bản {self._release.version} đã sẵn sàng</h2>"
            f"<p style='color:gray;margin-top:4px'>"
            f"Phiên bản hiện tại: <b>v{__version__}</b> &nbsp;→&nbsp; "
            f"Mới: <b>v{self._release.version}</b>"
            f"&nbsp;&nbsp;|&nbsp;&nbsp;Dung lượng: {size_mb:.1f} MB</p>"
        )
        header.setTextFormat(Qt.RichText)
        layout.addWidget(header)

        # Release notes
        notes_label = QLabel("<b>Nội dung cập nhật:</b>")
        layout.addWidget(notes_label)

        notes = QTextBrowser()
        notes.setMarkdown(self._release.body or "_Không có ghi chú phát hành._")
        notes.setMaximumHeight(280)
        notes.setReadOnly(True)
        layout.addWidget(notes)

        # Progress bar (hidden initially)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 100)
        layout.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setVisible(False)
        layout.addWidget(self._status_label)

        # Buttons
        hb = QHBoxLayout()
        hb.setSpacing(8)

        self._btn_install = QPushButton("⬇️  Tải & Cài đặt ngay")
        self._btn_install.setDefault(True)
        self._btn_install.clicked.connect(self._on_install)

        btn_later = QPushButton("🕐 Để sau")
        btn_later.clicked.connect(self.reject)

        btn_skip = QPushButton("🚫 Bỏ qua phiên bản này")
        btn_skip.clicked.connect(self._on_skip)

        hb.addWidget(self._btn_install)
        hb.addWidget(btn_later)
        hb.addWidget(btn_skip)
        layout.addLayout(hb)

    # ── Button handlers ─────────────────────────────────────────────────────────

    def _on_install(self):
        self._btn_install.setEnabled(False)
        self._btn_install.setText("Đang tải xuống...")
        self._progress.setVisible(True)
        self._status_label.setVisible(True)
        self._status_label.setText("Đang kết nối...")

        def do_download():
            from core.updater import download_and_install
            download_and_install(
                self._release,
                on_progress=lambda d, t: self._signals.progress.emit(d, t),
                on_error=lambda msg: self._signals.error.emit(msg),
                silent=False,
            )

        threading.Thread(target=do_download, daemon=True).start()

    def _on_skip(self):
        self._save_skipped_version(self._release.version)
        self.reject()

    # ── Progress / error callbacks (main thread via signal) ─────────────────────

    def _on_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int(downloaded * 100 / total)
            self._progress.setValue(pct)
            size_mb = downloaded / 1_000_000
            self._status_label.setText(f"Đang tải: {size_mb:.1f} MB / {total / 1_000_000:.1f} MB")
        else:
            self._status_label.setText(f"Đang tải: {downloaded / 1_000_000:.1f} MB...")

    def _on_error(self, msg: str):
        self._btn_install.setEnabled(True)
        self._btn_install.setText("⬇️  Tải & Cài đặt ngay")
        self._progress.setVisible(False)
        self._status_label.setText(f"❌ {msg}")

    def _on_done(self):
        # Normally run_installer exits the app — this is a fallback
        self.accept()

    # ── Persist skip preference ──────────────────────────────────────────────────

    @staticmethod
    def _save_skipped_version(version: str):
        try:
            from core.config import ConfigManager
            settings = ConfigManager.load_settings() or {}
            update_cfg = settings.get("update", {})
            update_cfg["skipped_version"] = version
            settings["update"] = update_cfg
            ConfigManager.save_settings(settings)
        except Exception:
            pass

    @staticmethod
    def should_skip(version: str) -> bool:
        try:
            from core.config import ConfigManager
            settings   = ConfigManager.load_settings() or {}
            update_cfg = settings.get("update", {})
            return update_cfg.get("skipped_version") == version
        except Exception:
            return False
