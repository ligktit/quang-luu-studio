"""
ui.components.active_modes_bar
==============================
Dải **ĐANG BẬT** — điểm danh mọi chế độ và nút chức năng đang bật, gom vào một
hàng ngay dưới dải visualizer.

Vì sao cần: đèn báo nằm trên chính từng nút, nằm rải ở hai panel (MODE và Công
cụ). Đang hát mà muốn biết máy đang chạy những gì thì phải quét mắt khắp màn
hình. Dải này trả lời câu đó trong một cái liếc.

**Tự ẩn khi không có gì bật** — `set_items([])` là dải biến mất hẳn khỏi bố cục
(không phải để trống), nhường chỗ cho các panel bên dưới. Dải chỉ xuất hiện khi
thật sự có thứ để báo.

Không phụ thuộc gói Premium: dải visualizer là của Premium và tắt được trong
Thiết lập, còn dải trạng thái thì bản nào cũng phải thấy.

Self-contained: KHÔNG import frontend_qt (tránh vòng import). Dữ liệu vào qua
`set_items([(nhãn, màu)])`.
"""
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from ui.design_tokens import C, FONT

_TITLE = "ĐANG BẬT"

_PAD_X = 10          # lề trái/phải trong dải
_GAP_TITLE = 10      # khoảng cách sau chữ "ĐANG BẬT"
_GAP_CHIP = 14       # khoảng cách giữa các mục
_DOT_R = 3.5         # bán kính chấm màu


class ActiveModesBar(QWidget):
    """Một hàng chấm màu + tên của những thứ đang bật. Trống thì tự ẩn."""

    def __init__(self, parent=None, height: int = 30):
        super().__init__(parent)
        self._items = []
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Dải chế độ đang bật")
        self._apply_accessible_text()
        # Ẩn từ đầu: chưa có dữ liệu thì chưa có gì để báo. Ẩn TRƯỚC khi vào
        # layout nên không có cú nhấp nháy lúc dựng cửa sổ.
        self.setVisible(False)

    # ── dữ liệu ─────────────────────────────────────────────────────────────
    def items(self):
        """Bản sao danh sách đang hiện (dùng cho test và phần đọc màn hình)."""
        return list(self._items)

    def set_items(self, items):
        """Đặt lại danh sách [(nhãn, màu)]; danh sách rỗng thì ẩn cả dải.

        Hàm này bị gọi mỗi lần bấm bất kỳ nút nào, nên phải rẻ: giống hệt lần
        trước thì không vẽ lại.
        """
        new = [(str(label), str(color)) for label, color in (items or [])]
        changed = new != self._items
        self._items = new
        self.setVisible(bool(new))   # Qt tự bỏ qua nếu trạng thái không đổi
        if not changed:
            return
        self._apply_accessible_text()
        self.update()

    def _apply_accessible_text(self):
        if self._items:
            text = "Đang bật: " + ", ".join(label for label, _ in self._items)
        else:
            text = "Chưa bật chế độ nào"
        self.setAccessibleDescription(text)
        self.setToolTip(text)

    # ── vẽ ──────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        if not self._items:
            return   # trống thì dải đã bị ẩn; có lọt tới đây cũng không vẽ gì

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(QPen(QColor(C["border"]), 1))
        p.setBrush(QColor(C["card"]))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)

        p.setFont(QFont(FONT, 8, QFont.Bold))
        p.setPen(QColor(C["text_muted"]))
        title_w = p.fontMetrics().horizontalAdvance(_TITLE)
        p.drawText(QRectF(_PAD_X, 0, title_w, h), Qt.AlignVCenter | Qt.AlignLeft, _TITLE)

        x = _PAD_X + title_w + _GAP_TITLE
        limit = w - _PAD_X

        p.setFont(QFont(FONT, 9, QFont.Bold))
        fm = p.fontMetrics()
        for i, (label, color) in enumerate(self._items):
            text_w = fm.horizontalAdvance(label)
            need = _DOT_R * 2 + 5 + text_w
            # Hết chỗ: bỏ dở giữa chừng thì người dùng tưởng chỉ có bấy nhiêu
            # đang bật — phải nói rõ còn mấy cái nữa.
            if x + need > limit and i > 0:
                rest = "+%d" % (len(self._items) - i)
                rest_w = fm.horizontalAdvance(rest)
                p.setPen(QColor(C["text_muted"]))
                p.drawText(QRectF(max(x, limit - rest_w), 0, rest_w, h),
                           Qt.AlignVCenter | Qt.AlignLeft, rest)
                return

            col = QColor(color)
            if not col.isValid():
                col = QColor(C["primary"])
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QRectF(x, h / 2 - _DOT_R, _DOT_R * 2, _DOT_R * 2))

            p.setPen(col.lighter(125))
            p.drawText(QRectF(x + _DOT_R * 2 + 5, 0, text_w, h),
                       Qt.AlignVCenter | Qt.AlignLeft, label)
            x += need + _GAP_CHIP
