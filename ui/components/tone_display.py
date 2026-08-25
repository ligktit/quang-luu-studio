"""Ô tone + nút Major/Minor + ô "kế tiếp" cho thanh header.

Bám đúng ngôn ngữ thiết kế sẵn có của app, KHÔNG dựng widget vẽ tay kiểu mới:

* `ToneDisplay` vẫn là QComboBox tạo dáng bằng QSS y như mọi combobox khác —
  chỉ khác cỡ chữ (18px thay vì 13px) để nhìn được từ xa. Không tự vẽ.
* `ScaleToggle` kế thừa `PainterButton`, tức là dùng chung đúng cái nút mà cả
  app đang dùng (gradient, hover, glow, lấp lánh Premium). Trạng thái đổi bằng
  chữ + màu, y hệt nút Major/Minor đã có ở `_sync_scale_button`.
* `NextTonePill` cao 28px, bo 6px, màu lấy từ design tokens — cùng khuôn với
  các nút trên header.

Cả ba giữ API của QComboBox (`currentText`/`setCurrentText`/`currentTextChanged`/
`QSignalBlocker`) vì hơn 40 chỗ trong app và tests đã gọi tới `tone_combo` /
`scale_combo`. Đổi hình thức mà không phải sửa chỗ gọi nào.

Ba widget chỉ HIỂN THỊ, không gửi MIDI — MIDI vẫn do engine và các handler
`_on_tone_selected` / `_on_scale_selected` lo, tránh hai nguồn bắn trùng.
"""
from PySide6.QtWidgets import QComboBox, QWidget, QSizePolicy
from PySide6.QtCore import Qt, QRectF, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QFont, QPen

from ui.design_tokens import C, FONT
from ui.components.painter_button import PainterButton

# Tên Việt của 12 nốt — dùng cho tooltip (không hiện thành dòng thứ hai để ô
# tone giữ đúng chiều cao 30px như các điều khiển khác trên header).
NOTE_VI = {
    "C": "Đô", "C#": "Đô thăng", "D": "Rê", "D#": "Rê thăng", "E": "Mi", "F": "Fa",
    "F#": "Fa thăng", "G": "Sol", "G#": "Sol thăng", "A": "La", "A#": "La thăng", "B": "Si",
}


class ToneDisplay(QComboBox):
    """Combobox chọn tone, cỡ chữ lớn hơn để đọc được từ xa.

    Vẫn là combobox thường: bấm ra danh sách 12 nốt, tạo dáng bằng QSS như mọi
    combobox khác trong app. Chỉ thêm 2 việc: đổi màu theo độ tin cậy
    (`set_accent`) và nháy viền một lần khi tone vừa đổi (`flash`).
    """

    # Tự tạo dáng bằng QSS riêng — _handle_tone_result bỏ qua, không áp QSS 13px cũ đè lên.
    SELF_STYLED = True

    BOX_H = 30
    FLASH_MS = 600

    def __init__(self, parent=None):
        super().__init__(parent)
        self._accent = C["text"]
        self._flashing = False
        self._flash_enabled = True
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._end_flash)
        self.setFixedHeight(self.BOX_H)
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_qss()

    # ── Tạo dáng (cùng khuôn QSS với các combobox khác) ──────────────────────
    def _apply_qss(self):
        accent = self._accent
        border = accent if self._flashing else "rgba(255, 255, 255, 0.85)"
        width = 3 if self._flashing else 2
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: transparent;
                color: {accent};
                border: {width}px solid {border};
                border-radius: 8px;
                padding: 1px 8px;
                font-size: 18px;
                font-weight: 800;
                font-family: {FONT};
            }}
            QComboBox::drop-down {{ border: none; width: 10px; }}
            QComboBox QAbstractItemView {{
                background-color: {C['card']};
                color: {C['text']};
                selection-background-color: {accent};
                border: 1px solid rgba(255, 255, 255, 0.5);
                font-size: 13px;
                font-family: {FONT};
            }}
        """)

    # ── API cho dashboard ────────────────────────────────────────────────────
    def set_accent(self, color: str):
        """Màu theo độ tin cậy: xanh = chắc, cam = chưa chắc."""
        self._accent = color
        self._apply_qss()

    def set_scale_text(self, scale: str):
        """Thể hiện tại — chỉ vào tooltip; ô này luôn hiện nốt gốc như trước,
        còn Major/Minor đã có nút bên cạnh nói rõ."""
        key = self.currentText() or "C"
        vi = NOTE_VI.get(key, key)
        label = "Minor" if scale == "Minor" else "Major"
        self.setToolTip(f"Tone hiện tại: {key} {label} ({vi})")

    def set_flash_enabled(self, on: bool):
        """Kiosk hoặc người dùng tắt hiệu ứng → chỉ đổi chữ, không nháy."""
        self._flash_enabled = bool(on)
        if not on and self._flashing:
            self._end_flash()

    def flash(self):
        """Nháy viền ĐÚNG MỘT LẦN khi tone vừa đổi (không nhấp nháy liên tục)."""
        if not self._flash_enabled:
            return
        self._flashing = True
        self._apply_qss()
        self._flash_timer.start(self.FLASH_MS)

    def _end_flash(self):
        self._flashing = False
        self._apply_qss()


class ScaleToggle(PainterButton):
    """Nút Major/Minor — một chạm là đổi, không phải xổ danh sách.

    Dùng chung `PainterButton` với các nút khác trên header nên trông y hệt
    chúng. Màu và chữ theo đúng quy ước đã có ở `_sync_scale_button`:
    Major = xanh lá, Minor = cam.

    Bên ngoài vẫn đọc/ghi bằng "Major"/"Minor" như combobox cũ.
    """

    # PainterButton tự vẽ, không dùng QSS — xem SELF_STYLED ở ToneDisplay.
    SELF_STYLED = True

    currentTextChanged = Signal(str)

    # Nhãn hiện trên nút — dùng thẳng Major/Minor như tên tiếng Anh trong nhạc lý,
    # cũng là bộ giá trị hợp lệ mà setCurrentText() kiểm tra.
    LABELS = {"Major": "Major", "Minor": "Minor"}
    COLORS = {"Major": C["green"], "Minor": C["orange"]}

    def __init__(self, parent=None):
        super().__init__("Major", color=C["green"], height=28, radius=6,
                         font_size=11, fixed_width=62, parent=parent)
        self._value = "Major"
        self.clicked.connect(self._toggle)
        self.setFocusPolicy(Qt.StrongFocus)
        self._refresh()

    # ── API tương thích QComboBox ────────────────────────────────────────────
    def currentText(self) -> str:
        return self._value

    def setCurrentText(self, text: str):
        if text not in self.LABELS or text == self._value:
            return
        self._value = text
        self._refresh()
        self.currentTextChanged.emit(self._value)

    def currentIndex(self) -> int:
        return 0 if self._value == "Major" else 1

    def setCurrentIndex(self, index: int):
        self.setCurrentText("Major" if index == 0 else "Minor")

    def count(self) -> int:
        return 2

    def itemText(self, index: int) -> str:
        return "Major" if index == 0 else "Minor"

    def findText(self, text: str) -> int:
        return {"Major": 0, "Minor": 1}.get(text, -1)

    def addItems(self, _items):
        """Nuốt lặng — hai giá trị là cố định. Có mặt để chỗ gọi cũ không vỡ."""

    # ── Hành vi ──────────────────────────────────────────────────────────────
    def _toggle(self):
        self.setCurrentText("Minor" if self._value == "Major" else "Major")

    def _refresh(self):
        self.setText(self.LABELS[self._value])
        self._color = QColor(self.COLORS[self._value])
        other = "Minor" if self._value == "Major" else "Major"
        self.setToolTip(f"Đang ở thể {self.LABELS[self._value]}. Bấm để đổi sang {other}.")
        self.update()

    def keyPressEvent(self, event):
        # Bàn phím / trình đọc màn hình: Space hoặc Enter cũng đổi được.
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._toggle()
            event.accept()
            return
        super().keyPressEvent(event)


class NextTonePill(QWidget):
    """Ô "kế tiếp": tone sắp đổi + đếm ngược số giây + thanh vơi dần.

    Cùng chiều cao (28px) và độ bo (6px) với các nút trên header. Hai cách đọc
    dùng CHUNG một con số (thời gian còn lại của đoạn hiện tại): chữ cho người
    cần chính xác, thanh cho người chỉ liếc qua.
    """

    PILL_H = 28
    PILL_W = 104
    RADIUS = 6
    URGENT_SEC = 5.0    # dưới ngưỡng này → chuyển cam, báo sắp đổi

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._key = ""
        self._seconds = None
        self._fraction = None    # phần còn lại của đoạn: 1.0 → 0.0
        self._message = ""
        self.setFixedSize(self.PILL_W, self.PILL_H)
        self.setToolTip("Tone kế tiếp và thời gian còn lại")
        self.setAccessibleName("Tone kế tiếp")

    # ── API ──────────────────────────────────────────────────────────────────
    def set_next(self, key_display: str, seconds_left: float, fraction_left: float):
        self._key = key_display or ""
        self._seconds = max(0.0, float(seconds_left))
        self._fraction = None if fraction_left is None else max(0.0, min(1.0, float(fraction_left)))
        self._message = ""
        self.update()

    def set_message(self, text: str):
        """Không có mốc kế tiếp (cuối bài / user chỉnh tay / chưa có timeline)."""
        self._key = ""
        self._seconds = None
        self._fraction = None
        self._message = text or ""
        self.update()

    def _is_urgent(self) -> bool:
        return self._seconds is not None and self._seconds <= self.URGENT_SEC

    def _font(self, px, bold=False):
        f = QFont()
        f.setFamilies(["Be Vietnam Pro", "Segoe UI"])
        f.setPixelSize(px)
        if bold:
            f.setWeight(QFont.Bold)
        return f

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        accent = QColor(C["orange"] if self._is_urgent() else C["text_muted"])

        # Nền + viền mảnh, cùng khuôn với nút trên header
        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        _bg = QColor(C["bg"]); _bg.setAlpha(200)
        p.setPen(Qt.NoPen)
        p.setBrush(_bg)
        p.drawRoundedRect(rect, self.RADIUS, self.RADIUS)
        _bd = QColor(C["border"]); _bd.setAlpha(170)
        p.setPen(QPen(_bd, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(rect, self.RADIUS, self.RADIUS)

        if self._message:
            p.setFont(self._font(10))
            p.setPen(QColor(C["text_muted"]))
            p.drawText(rect, Qt.AlignCenter, self._message)
            return

        # ▸ kế G                    0:12
        p.setFont(self._font(11, True))
        p.setPen(accent)
        p.drawText(QRectF(7, 1, w - 14, 17), Qt.AlignLeft | Qt.AlignVCenter,
                   f"▸ {self._key}")
        if self._seconds is not None:
            mm = int(self._seconds) // 60
            ss = int(self._seconds) % 60
            p.setPen(accent if self._is_urgent() else QColor(C["text"]))
            p.drawText(QRectF(7, 1, w - 14, 17), Qt.AlignRight | Qt.AlignVCenter,
                       f"{mm}:{ss:02d}")

        # Thanh vơi dần — cùng tỉ lệ với số giây ở trên
        bar_y = h - 8.0
        bar_w = w - 14.0
        _track = QColor(C["border"]); _track.setAlpha(140)
        p.setPen(Qt.NoPen)
        p.setBrush(_track)
        p.drawRoundedRect(QRectF(7, bar_y, bar_w, 3), 1.5, 1.5)
        if self._fraction is not None and self._fraction > 0:
            p.setBrush(QColor(C["orange"] if self._is_urgent() else C["primary"]))
            p.drawRoundedRect(QRectF(7, bar_y, bar_w * self._fraction, 3), 1.5, 1.5)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
