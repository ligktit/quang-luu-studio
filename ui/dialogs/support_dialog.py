"""
Quang Lưu Studio — Hộp thoại Hỗ trợ (kênh hai chiều khách ↔ dev).

Tab "Gửi yêu cầu": khách mô tả vấn đề, kèm nhật ký lỗi nếu muốn.
Tab "Hộp thư"    : xem lại các yêu cầu đã gửi + trả lời của dev, nói tiếp được.

Mọi lời gọi mạng đều chạy trong QThread riêng — dialog KHÔNG bao giờ đứng hình
khi quán mất mạng (urllib timeout 10s là quá đủ để người dùng tưởng app treo).

Tự chứa về style (chỉ dùng design_tokens) như tech_unlock.py, để mở được từ cả
header lẫn nơi khác mà không kéo theo frontend_qt.
"""
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import support
from ui.design_tokens import C, FONT, SP, lighten
from ui import responsive as rp


def _btn_qss(color: str, radius: int = 12, size: int = 13) -> str:
    return f"""
        QPushButton {{
            background-color: {color}; color: #0F172A;
            border: none; border-radius: {radius}px;
            padding: 9px 16px; font-size: {size}px; font-weight: 700;
            font-family: {FONT};
        }}
        QPushButton:hover {{ background-color: {lighten(color, 0.12)}; }}
        QPushButton:disabled {{ background-color: {C['card_hover']}; color: {C['text_muted']}; }}
    """.strip()


_INPUT_QSS = f"""
    QLineEdit, QTextEdit, QComboBox {{
        background-color: rgba(15, 23, 42, 225);
        color: {C['text']};
        border: 1px solid rgba(148, 163, 184, 55);
        border-radius: 10px;
        padding: 8px 12px;
        font-size: 13px;
        font-family: {FONT};
    }}
    QLineEdit:focus, QTextEdit:focus {{ border-color: {C['teal']}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background-color: {C['card']}; color: {C['text']};
        selection-background-color: {C['card_hover']};
    }}
"""

# Tab dạng viên thuốc — chép cùng khuôn với SettingsDialog. Không có khối này
# thì Qt vẽ tab mặc định màu xám hệ thống, trông như dialog của phần mềm khác.
_DIALOG_QSS = f"""
    QDialog {{ background-color: {C['bg']}; color: {C['text']}; }}
    QTabWidget::pane {{ border: none; background: transparent; top: -1px; }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background-color: rgba(30, 41, 59, 165);
        color: {C['text_muted']};
        padding: 7px 18px;
        margin: 6px 4px 4px 0;
        border: 1px solid rgba(51, 65, 85, 150);
        border-radius: 12px;
        font-size: 13px;
        font-weight: 700;
        font-family: {FONT};
        min-height: 24px;
    }}
    QTabBar::tab:selected {{
        color: {C['text']};
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 rgba(56, 189, 248, 210),
            stop:1 rgba(59, 130, 246, 188));
        border: 1px solid rgba(125, 211, 252, 170);
    }}
    QTabBar::tab:hover:!selected {{
        color: {C['text']};
        background-color: rgba(51, 65, 85, 210);
        border-color: rgba(148, 163, 184, 80);
    }}
"""

_STATUS_LABELS = {
    "new": "Đã gửi",
    "open": "Đang xử lý",
    "answered": "Dev đã trả lời",
    "closed": "Đã đóng",
}

_STATUS_COLORS = {
    "new": C["text_muted"],
    "open": C["orange"],
    "answered": C["green"],
    "closed": C["text_muted"],
}


class _Worker(QThread):
    """Chạy một hàm mạng ở luồng nền, trả kết quả về main thread qua signal."""

    done = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as e:  # mạng/urllib có thể ném đủ kiểu — không được sập UI
            self.done.emit({"ok": False, "message": f"Lỗi không mong đợi: {e}"})


class SupportDialog(QDialog):
    """Hộp thoại hỗ trợ. Gọi: SupportDialog(parent).exec()."""

    # Phát khi số thư chưa đọc đổi → header cập nhật chấm đỏ.
    unread_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Hỗ trợ")
        self.setModal(True)
        rp.apply_dialog_size(self, 700, 620, min_w=640, min_h=560)
        self.setStyleSheet(_DIALOG_QSS)

        # Giữ tham chiếu tới worker đang chạy: QThread bị GC giữa chừng là crash.
        self._workers = []
        self._tickets = []
        self._current = None

        self._build_ui()
        self._reload_inbox()

    # ── Dựng giao diện ──
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(SP.MD)

        title = QLabel("Hỗ trợ kỹ thuật")
        title.setStyleSheet(
            f"font-size: 19px; font-weight: 900; color: {C['text']};"
            f" font-family: {FONT}; background: transparent;"
        )
        outer.addWidget(title)

        sub = QLabel(
            "Gửi yêu cầu cho đội kỹ thuật Quang Lưu Studio. Trả lời sẽ hiện ngay "
            "trong tab Hộp thư của app, không cần chờ điện thoại."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {C['text_muted']};"
            f" font-family: {FONT}; background: transparent;"
        )
        outer.addWidget(sub)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_send_tab(), "Gửi yêu cầu")
        self._tabs.addTab(self._build_inbox_tab(), "Hộp thư")
        outer.addWidget(self._tabs, 1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setVisible(False)
        outer.addWidget(self._status)

        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("Đóng")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(_btn_qss(C["card_hover"]))
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        outer.addLayout(row)

    def _build_send_tab(self) -> QWidget:
        tab = QWidget()
        vl = QVBoxLayout(tab)
        vl.setContentsMargins(4, 14, 4, 4)
        vl.setSpacing(SP.SM)
        tab.setStyleSheet(_INPUT_QSS)

        vl.addWidget(self._label("Loại yêu cầu"))
        self._category = QComboBox()
        for key, text in support.CATEGORIES:
            self._category.addItem(text, key)
        vl.addWidget(self._category)

        vl.addWidget(self._label("Tiêu đề"))
        self._subject = QLineEdit()
        self._subject.setPlaceholderText("Ví dụ: Không tải được bài trên YouTube")
        self._subject.setMaxLength(200)
        vl.addWidget(self._subject)

        vl.addWidget(self._label("Mô tả chi tiết"))
        self._body = QTextEdit()
        self._body.setPlaceholderText(
            "Mô tả càng cụ thể càng nhanh được xử lý: bạn đang làm gì, app báo gì, "
            "xảy ra từ khi nào."
        )
        self._body.setMinimumHeight(150)
        vl.addWidget(self._body, 1)

        vl.addWidget(self._label("Số điện thoại / Zalo (không bắt buộc)"))
        self._contact = QLineEdit()
        self._contact.setPlaceholderText("Để đội kỹ thuật gọi lại khi cần")
        self._contact.setMaxLength(120)
        vl.addWidget(self._contact)

        self._include_logs = QCheckBox("Gửi kèm nhật ký lỗi (giúp xử lý nhanh hơn nhiều)")
        self._include_logs.setChecked(True)
        self._include_logs.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT};"
        )
        vl.addWidget(self._include_logs)

        row = QHBoxLayout()
        row.addStretch()
        self._send_btn = QPushButton("Gửi yêu cầu")
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.setStyleSheet(_btn_qss(C["primary"]))
        self._send_btn.clicked.connect(self._on_send)
        row.addWidget(self._send_btn)
        vl.addLayout(row)
        return tab

    def _build_inbox_tab(self) -> QWidget:
        tab = QWidget()
        tab.setStyleSheet(_INPUT_QSS)
        vl = QVBoxLayout(tab)
        vl.setContentsMargins(4, 14, 4, 4)
        vl.setSpacing(SP.SM)

        head = QHBoxLayout()
        self._inbox_hint = QLabel("Đang tải hộp thư…")
        self._inbox_hint.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT}; background: transparent;"
        )
        head.addWidget(self._inbox_hint)
        head.addStretch()
        refresh = QPushButton("Tải lại")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setStyleSheet(_btn_qss(C["card_hover"], size=12))
        refresh.clicked.connect(self._reload_inbox)
        head.addWidget(refresh)
        vl.addLayout(head)

        self._ticket_list = QListWidget()
        self._ticket_list.setMaximumHeight(150)
        self._ticket_list.setStyleSheet(
            f"QListWidget {{ background-color: {C['card']}; border: 1px solid {C['border']};"
            f" border-radius: 10px; font-family: {FONT}; font-size: 12px; color: {C['text']}; }}"
            f"QListWidget::item {{ padding: 7px 10px; }}"
            f"QListWidget::item:selected {{ background-color: {C['card_hover']}; }}"
        )
        self._ticket_list.currentRowChanged.connect(self._on_pick_ticket)
        vl.addWidget(self._ticket_list)

        self._thread_area = QScrollArea()
        self._thread_area.setWidgetResizable(True)
        self._thread_area.setFrameShape(QFrame.NoFrame)
        # QScrollArea không kế thừa nền của dialog: bỏ ba dòng dưới là giữa app
        # nền tối mọc ra một mảng TRẮNG TOÁT to bằng nửa hộp thoại.
        self._thread_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._thread_area.viewport().setStyleSheet("background: transparent;")
        self._thread_host = QWidget()
        self._thread_host.setStyleSheet("background: transparent;")
        self._thread_layout = QVBoxLayout(self._thread_host)
        self._thread_layout.setContentsMargins(0, 0, 0, 0)
        self._thread_layout.setSpacing(SP.SM)
        self._thread_layout.addStretch()
        self._thread_area.setWidget(self._thread_host)
        vl.addWidget(self._thread_area, 1)

        self._reply_box = QTextEdit()
        self._reply_box.setPlaceholderText("Nhắn tiếp cho đội kỹ thuật…")
        self._reply_box.setMaximumHeight(80)
        vl.addWidget(self._reply_box)

        row = QHBoxLayout()
        row.addStretch()
        self._reply_btn = QPushButton("Gửi trả lời")
        self._reply_btn.setCursor(Qt.PointingHandCursor)
        self._reply_btn.setStyleSheet(_btn_qss(C["green"]))
        self._reply_btn.setEnabled(False)
        self._reply_btn.clicked.connect(self._on_reply)
        row.addWidget(self._reply_btn)
        vl.addLayout(row)
        return tab

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent;"
        )
        return lbl

    # ── Tiện ích ──
    def _show_status(self, text, color=None):
        self._status.setText(text)
        self._status.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {color or C['orange']};"
            f" font-family: {FONT}; background: transparent;"
        )
        self._status.setVisible(bool(text))

    def _run_async(self, fn, on_done):
        """Chạy fn ở luồng nền; on_done nhận kết quả trên main thread."""
        worker = _Worker(fn, self)
        self._workers.append(worker)

        def _finish(result):
            try:
                on_done(result)
            finally:
                if worker in self._workers:
                    self._workers.remove(worker)

        worker.done.connect(_finish)
        worker.start()

    # ── Gửi yêu cầu ──
    def _on_send(self):
        category = self._category.currentData()
        subject = self._subject.text()
        body = self._body.toPlainText()
        contact = self._contact.text()
        include_logs = self._include_logs.isChecked()

        if not subject.strip() or not body.strip():
            self._show_status("Vui lòng nhập tiêu đề và mô tả chi tiết.")
            return

        self._send_btn.setEnabled(False)
        self._show_status("Đang gửi…", C["text_muted"])
        self._run_async(
            lambda: support.submit(category, subject, body, contact, include_logs),
            self._on_sent,
        )

    def _on_sent(self, result):
        self._send_btn.setEnabled(True)
        if result.get("ok"):
            self._show_status(
                f"Đã gửi. Mã yêu cầu của bạn là {result.get('ticket_code')}. "
                "Trả lời của đội kỹ thuật sẽ hiện ở tab Hộp thư.",
                C["green"],
            )
            self._subject.clear()
            self._body.clear()
            self._reload_inbox()
        elif result.get("queued"):
            self._show_status(result.get("message", ""), C["orange"])
            self._subject.clear()
            self._body.clear()
        else:
            self._show_status(result.get("message") or "Không gửi được yêu cầu.", C["accent"])

    # ── Hộp thư ──
    def _reload_inbox(self):
        self._inbox_hint.setText("Đang tải hộp thư…")
        self._run_async(support.inbox, self._on_inbox)

    def _on_inbox(self, result):
        if not result.get("ok"):
            self._inbox_hint.setText(result.get("message") or "Không tải được hộp thư.")
            return

        self._tickets = result.get("tickets") or []
        self._ticket_list.clear()
        for ticket in self._tickets:
            status = ticket.get("status", "")
            mark = " ●" if ticket.get("unread_client") else ""
            item = QListWidgetItem(
                f"{ticket.get('ticket_code', '')} · {ticket.get('subject', '')} "
                f"— {_STATUS_LABELS.get(status, status)}{mark}"
            )
            self._ticket_list.addItem(item)

        if not self._tickets:
            self._inbox_hint.setText("Bạn chưa gửi yêu cầu hỗ trợ nào.")
        else:
            unread = result.get("unread_count") or 0
            self._inbox_hint.setText(
                f"{len(self._tickets)} yêu cầu · {unread} trả lời chưa đọc" if unread
                else f"{len(self._tickets)} yêu cầu"
            )
            self._ticket_list.setCurrentRow(0)

        self.unread_changed.emit(support.unread_count())

    def _on_pick_ticket(self, row):
        if row < 0 or row >= len(self._tickets):
            self._current = None
            self._reply_btn.setEnabled(False)
            return

        ticket = self._tickets[row]
        self._current = ticket
        self._reply_btn.setEnabled(ticket.get("status") != "closed")
        self._render_thread(ticket)

        # Mở ra là coi như đã đọc — tắt chấm đỏ (nền, không chặn UI).
        if ticket.get("unread_client"):
            ticket["unread_client"] = False
            code = ticket.get("ticket_code", "")
            self._run_async(
                lambda: support.mark_read(code),
                lambda _res: self.unread_changed.emit(support.unread_count()),
            )

    def _render_thread(self, ticket):
        while self._thread_layout.count():
            item = self._thread_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        status = ticket.get("status", "")
        head = QLabel(
            f"{ticket.get('subject', '')} — {_STATUS_LABELS.get(status, status)}"
        )
        head.setWordWrap(True)
        head.setStyleSheet(
            f"font-size: 13px; font-weight: 800; color: {_STATUS_COLORS.get(status, C['text'])};"
            f" font-family: {FONT}; background: transparent;"
        )
        self._thread_layout.addWidget(head)

        for msg in ticket.get("messages") or []:
            self._thread_layout.addWidget(self._message_card(msg))
        self._thread_layout.addStretch()

    def _message_card(self, msg) -> QWidget:
        is_dev = msg.get("sender") == "dev"
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background-color: {C['card']};"
            f" border-left: 3px solid {C['green'] if is_dev else C['border']};"
            f" border-radius: 8px; }}"
        )
        vl = QVBoxLayout(card)
        vl.setContentsMargins(12, 9, 12, 10)
        vl.setSpacing(3)

        who = QLabel("Đội kỹ thuật" if is_dev else "Bạn")
        who.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 11px; font-weight: 700;"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        vl.addWidget(who)

        body = QLabel(msg.get("body", ""))
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setStyleSheet(
            f"color: {C['text']}; font-size: 12.5px; font-family: {FONT};"
            f" background: transparent; border: none;"
        )
        vl.addWidget(body)
        return card

    def _on_reply(self):
        if not self._current:
            return
        text = self._reply_box.toPlainText()
        if not text.strip():
            return

        code = self._current.get("ticket_code", "")
        self._reply_btn.setEnabled(False)
        self._show_status("Đang gửi…", C["text_muted"])
        self._run_async(lambda: support.reply(code, text), self._on_replied)

    def _on_replied(self, result):
        self._reply_btn.setEnabled(True)
        if result.get("ok"):
            self._reply_box.clear()
            self._show_status("Đã gửi trả lời.", C["green"])
            self._reload_inbox()
        else:
            self._show_status(result.get("message") or "Không gửi được trả lời.", C["accent"])

    def closeEvent(self, event):
        # Chờ các worker mạng kết thúc để QThread không bị huỷ khi đang chạy.
        for worker in list(self._workers):
            worker.wait(2000)
        super().closeEvent(event)
