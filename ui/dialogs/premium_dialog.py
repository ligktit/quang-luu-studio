"""
Dialog mời nâng cấp Premium (upsell).

Hiển thị khi người dùng Standard/trial chạm vào một tính năng Premium.
exec() trả QDialog.Accepted nếu người dùng muốn nhập mã / nâng cấp — caller
(frontend) sẽ mở ActivationDialog. Trả Rejected nếu họ đóng/bỏ qua.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

from ui.design_tokens import C, FONT, lighten
from ui import responsive as rp

# Mô tả ngắn gọn từng tính năng Premium (hiển thị trong dialog).
_FEATURE_BLURB = {
    "scoring":      "Chấm điểm giọng hát chi tiết: cao độ, nhịp, độ ổn định + gợi ý luyện tập.",
    "smart_recall": "Tự khôi phục tone, scale, mức mixer và mode đã chỉnh cho từng bài.",
    "cloud_sync":   "Đồng bộ thư viện bài, timeline và lịch sử điểm qua nhiều thiết bị.",
    "progress":     "Theo dõi tiến bộ luyện hát qua biểu đồ điểm số theo thời gian.",
    "setlist":      "Hàng đợi bài cho buổi live: tự dò tone trước và chuyển bài mượt mà.",
    "auto_echo":    "Tự mở Vang khi nhạc chạy và tắt Vang khi hết nhạc — nói chuyện giữa bài không bị vọng.",
}


class PremiumUpsellDialog(QDialog):
    def __init__(self, feature: str, label: str, parent=None):
        super().__init__(parent)
        self._feature = feature
        self.setWindowTitle("Tính năng Premium")
        self.setWindowIcon(QIcon("app_icon.ico"))
        rp.set_fixed_width(self, 460)
        self.setModal(True)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._build_ui(label)

    def _build_ui(self, label: str):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header gradient ──
        header = QFrame()
        header.setFixedHeight(96)
        header.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {C['card']}, stop:0.5 rgba(168,85,247,30), stop:1 {C['card']});
                border-bottom: 1px solid rgba(168,85,247,0.35);
            }}
        """)
        hl = QVBoxLayout(header)
        hl.setContentsMargins(24, 18, 24, 14)
        hl.setSpacing(4)
        crown = QLabel("👑 PREMIUM")
        crown.setStyleSheet(
            f"font-size: 13px; font-weight: 900; letter-spacing: 2px;"
            f" color: {C['light_purple']}; font-family: {FONT}; background: transparent; border: none;"
        )
        crown.setAlignment(Qt.AlignCenter)
        hl.addWidget(crown)
        title = QLabel(f"“{label}” là tính năng Premium")
        title.setStyleSheet(
            f"font-size: 17px; font-weight: 800; color: {C['text']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        hl.addWidget(title)
        outer.addWidget(header)

        # ── Body ──
        body = QVBoxLayout()
        body.setContentsMargins(28, 20, 28, 22)
        body.setSpacing(16)

        blurb = QLabel(_FEATURE_BLURB.get(self._feature, "Tính năng này chỉ có ở gói Premium."))
        blurb.setWordWrap(True)
        blurb.setStyleSheet(
            f"font-size: 14px; color: {C['text_muted']}; font-family: {FONT};"
            f" background: transparent; border: none;"
        )
        body.addWidget(blurb)

        hint = QLabel("Nâng cấp lên Premium để mở khóa, hoặc nhập mã kích hoạt Premium bạn đã có.")
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT};"
            f" background: transparent; border: none;"
        )
        body.addWidget(hint)

        # ── Buttons ──
        row = QHBoxLayout()
        row.setSpacing(10)
        later = QPushButton("Để sau")
        later.setCursor(Qt.PointingHandCursor)
        later.setFixedHeight(40)
        later.setStyleSheet(
            f"QPushButton {{ background-color: {C['card']}; color: {C['text_muted']};"
            f" border: 1px solid {C['border']}; border-radius: 8px; font-size: 13px;"
            f" font-weight: 600; font-family: {FONT}; padding: 0 18px; }}"
            f" QPushButton:hover {{ background-color: {C['card_hover']}; }}"
        )
        later.clicked.connect(self.reject)
        row.addWidget(later)

        upgrade = QPushButton("Nhập mã / Nâng cấp")
        upgrade.setCursor(Qt.PointingHandCursor)
        upgrade.setFixedHeight(40)
        upgrade.setStyleSheet(
            f"QPushButton {{ background-color: {C['light_purple']}; color: white;"
            f" border: none; border-radius: 8px; font-size: 13px; font-weight: 800;"
            f" font-family: {FONT}; padding: 0 18px; }}"
            f" QPushButton:hover {{ background-color: {lighten(C['light_purple'], 0.12)}; }}"
        )
        upgrade.clicked.connect(self.accept)
        row.addWidget(upgrade, 1)
        body.addLayout(row)

        outer.addLayout(body)
