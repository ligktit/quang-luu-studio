"""
ui.components.sfx_button_area
==============================
Dynamic, user-managed SFX button area for Quang Lưu Studio.

Features:
  - FlowLayout wrap for SFX buttons + [+] add button
  - Empty state label
  - Right-click context menu: Sửa / Xoá
  - Drag-and-drop reorder via QDrag
  - Add/Edit dialog (emoji, label, file path)
  - Visual indicator (red pulsing border) for missing files
  - Signal: sfx_changed(list) → parent saves to settings
  - Signal: sfx_play(str path) → parent plays audio
"""
import os
import uuid

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QDialog, QLineEdit, QPushButton,
    QFileDialog, QMenu, QScrollArea, QFrame
)
from PySide6.QtCore import (
    Qt, Signal, QTimer, QMimeData, QPoint, QSize, QRectF, QByteArray
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QLinearGradient, QDrag, QFont, QBrush
)

from ui.design_tokens import C, SP, FONT, FONT_MONO
from ui.components.painter_button import PainterButton


# ── Simple Flow Layout ────────────────────────────────────────────────────────
class FlowLayout(QHBoxLayout):
    """
    Minimal flow layout: wraps items across rows.
    Implemented via a custom QWidget with resizeEvent to re-flow children.
    """
    pass


class _HBoxContainer(QWidget):
    """Simple horizontal container for SFX buttons."""

    def __init__(self, spacing=8, padding=4, parent=None):
        super().__init__(parent)
        self._padding = padding
        lay = QHBoxLayout(self)
        lay.setContentsMargins(padding, padding, padding, padding)
        lay.setSpacing(spacing)
        lay.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    @property
    def _layout(self):
        return self.layout()

    def add_widget(self, w: QWidget):
        # Insert before the last item (which is the [+] btn), or append if empty
        count = self._layout.count()
        self._layout.insertWidget(max(0, count), w)

    def insert_widget(self, idx: int, w: QWidget):
        self._layout.insertWidget(idx, w)

    def remove_widget(self, w: QWidget):
        self._layout.removeWidget(w)
        w.hide()
        w.setParent(None)

    def index_of(self, w: QWidget) -> int:
        return self._layout.indexOf(w)

    def count(self) -> int:
        return self._layout.count()

    def widget_at(self, idx: int):
        item = self._layout.itemAt(idx)
        return item.widget() if item else None

    def move_widget(self, from_idx: int, to_idx: int):
        w = self.widget_at(from_idx)
        if w:
            self._layout.removeWidget(w)
            self._layout.insertWidget(to_idx, w)


# ── SFX Item Button ───────────────────────────────────────────────────────────
class SfxItemButton(QWidget):
    """
    Individual SFX button: painted gradient, context menu, drag source.
    """
    clicked = Signal()
    request_edit = Signal(object)   # emits self
    request_delete = Signal(object) # emits self

    def __init__(self, sfx_data: dict, parent=None):
        super().__init__(parent)
        self._data = dict(sfx_data)   # {id, label, name, file_path, color}
        self._hover = False
        self._pressed = False
        self._drag_start_pos = None
        self._missing = False          # file not found
        self._pulse_alpha = 0
        self._pulse_dir = 1

        self.setFixedHeight(28)
        self.setMinimumWidth(52)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self._check_file()

        # Missing-file pulse timer
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick_pulse)
        if self._missing:
            self._pulse_timer.start(40)

    # ── Public API ────────────────────────────────────────────────
    @property
    def data(self) -> dict:
        return dict(self._data)

    def update_data(self, sfx_data: dict):
        self._data = dict(sfx_data)
        self._check_file()
        if self._missing and not self._pulse_timer.isActive():
            self._pulse_timer.start(40)
        elif not self._missing and self._pulse_timer.isActive():
            self._pulse_timer.stop()
            self._pulse_alpha = 0
        self.setToolTip(self._build_tooltip())
        self.update()

    # ── Helpers ───────────────────────────────────────────────────
    def _check_file(self):
        fp = self._data.get("file_path", "")
        self._missing = bool(fp) and not os.path.exists(fp)
        tip = self._build_tooltip()
        self.setToolTip(tip)

    def _build_tooltip(self) -> str:
        fp = self._data.get("file_path", "")
        name = self._data.get("name", "")
        if not fp:
            return f"{name}\n(Chưa gán file)"
        if self._missing:
            return f"{name}\n⚠️ File không tồn tại:\n{fp}"
        return f"{name}\n{fp}"

    def _base_color(self) -> QColor:
        return QColor(self._data.get("color", C["teal"]))

    def _tick_pulse(self):
        self._pulse_alpha += 8 * self._pulse_dir
        if self._pulse_alpha >= 200:
            self._pulse_dir = -1
        elif self._pulse_alpha <= 0:
            self._pulse_dir = 1
        self.update()

    # ── Paint ─────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        r = 8
        rect = QRectF(1, 1, w - 2, h - 2)

        base = self._base_color()

        # Glow on hover
        if self._hover:
            glow = QColor(base)
            glow.setAlpha(40)
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            p.drawRoundedRect(QRectF(0, 0, w, h), r + 2, r + 2)

        # Body gradient
        grad = QLinearGradient(0, 0, 0, h)
        if self._pressed:
            light = self._darken(base, 0.15)
            grad.setColorAt(0.0, light)
            grad.setColorAt(1.0, base)
        elif self._hover:
            grad.setColorAt(0.0, self._lighten(base, 0.20))
            grad.setColorAt(1.0, base)
        else:
            grad.setColorAt(0.0, self._lighten(base, 0.12))
            grad.setColorAt(0.5, base)
            grad.setColorAt(1.0, self._darken(base, 0.12))

        # Border: red pulse if missing, normal otherwise
        if self._missing:
            bc = QColor("#EF4444")
            bc.setAlpha(max(80, self._pulse_alpha))
            p.setPen(QPen(bc, 2))
        elif self._hover:
            bc = self._lighten(base, 0.35)
            bc.setAlpha(200)
            p.setPen(QPen(bc, 1))
        else:
            bc = QColor(base)
            bc.setAlpha(50)
            p.setPen(QPen(bc, 1))

        p.setBrush(grad)
        p.drawRoundedRect(rect, r, r)

        # Top highlight
        if not self._pressed:
            hi = QLinearGradient(0, 1, 0, h * 0.4)
            hi.setColorAt(0, QColor(255, 255, 255, 35))
            hi.setColorAt(1, QColor(255, 255, 255, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(hi)
            p.drawRoundedRect(QRectF(2, 1, w - 4, h * 0.4), r - 1, r - 1)

        # Text: emoji only (name shown in tooltip)
        label = self._data.get("label", "")
        display = label
        font = QFont("Segoe UI")
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, display)
        p.end()

    # ── Mouse ─────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pressed = True
            self._drag_start_pos = e.position().toPoint()
            self.update()
        elif e.button() == Qt.RightButton:
            self._show_context_menu(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._drag_start_pos is None:
            return
        if (e.position().toPoint() - self._drag_start_pos).manhattanLength() < 10:
            return
        # Start drag
        self._pressed = False
        self.update()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self._data.get("id", ""))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, e):
        if self._pressed and e.button() == Qt.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                if self._missing:
                    pass  # could show tooltip, but we keep it subtle
                self.clicked.emit()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self._pressed = False
        self.update()

    def contextMenuEvent(self, e):
        self._show_context_menu(e.globalPos())

    def _show_context_menu(self, global_pos):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 6px;
                padding: 4px;
                font-size: 12px;
                font-family: {FONT};
            }}
            QMenu::item {{
                padding: 6px 16px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {C['card_hover']};
            }}
        """)
        edit_action = menu.addAction("✏️  Sửa")
        del_action  = menu.addAction("🗑️  Xoá")
        chosen = menu.exec(global_pos)
        if chosen == edit_action:
            self.request_edit.emit(self)
        elif chosen == del_action:
            self.request_delete.emit(self)

    # ── Drag-and-drop target ──────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        # Find parent SfxButtonArea and reorder
        area = self._find_area()
        if area:
            src_id = e.mimeData().text()
            area.reorder_by_id(src_id, self._data.get("id", ""))
        e.acceptProposedAction()

    def _find_area(self):
        w = self.parent()
        while w is not None:
            if isinstance(w, SfxButtonArea):
                return w
            w = w.parent()
        return None

    # ── Color helpers ─────────────────────────────────────────────
    @staticmethod
    def _lighten(color: QColor, f=0.2) -> QColor:
        r = min(255, int(color.red()   + (255 - color.red())   * f))
        g = min(255, int(color.green() + (255 - color.green()) * f))
        b = min(255, int(color.blue()  + (255 - color.blue())  * f))
        return QColor(r, g, b, color.alpha())

    @staticmethod
    def _darken(color: QColor, f=0.2) -> QColor:
        r = max(0, int(color.red()   * (1 - f)))
        g = max(0, int(color.green() * (1 - f)))
        b = max(0, int(color.blue()  * (1 - f)))
        return QColor(r, g, b, color.alpha())

    def sizeHint(self):
        # Compact square-ish for emoji
        return QSize(36, 28)


# ── Add / Edit Dialog ────────────────────────────────────────────────────────
class SfxEditDialog(QDialog):
    """Dialog to add or edit an SFX button."""

    _PRESET_COLORS = [
        C["teal"], C["orange"], C["pink"], C["deep_purple"],
        C["blue"], C["green"], C["light_purple"], C["accent"],
    ]

    def __init__(self, sfx_data: dict | None = None, parent=None):
        super().__init__(parent)
        is_edit = sfx_data is not None
        self.setWindowTitle("✏️ Sửa SFX" if is_edit else "➕ Thêm SFX")
        self.setFixedSize(420, 320)
        self.setStyleSheet(f"""
            QDialog {{ background-color: {C['bg']}; color: {C['text']}; }}
            QLabel  {{ color: {C['text_muted']}; font-size: 12px; font-family: {FONT}; background: transparent; }}
            QLineEdit {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
                font-family: {FONT};
            }}
            QLineEdit:focus {{ border-color: {C['teal']}; }}
        """)
        self._result = None
        self._color = (sfx_data or {}).get("color", C["teal"])

        vl = QVBoxLayout(self)
        vl.setSpacing(10)
        vl.setContentsMargins(20, 18, 20, 16)

        # Title
        title = QLabel("✏️ Sửa nút SFX" if is_edit else "➕ Thêm nút SFX mới")
        title.setStyleSheet(f"font-size: 15px; font-weight: 700; color: {C['teal']}; font-family: {FONT}; background:transparent;")
        vl.addWidget(title)

        # Emoji / Label row
        row_emoji = QHBoxLayout()
        row_emoji.addWidget(QLabel("Emoji:"))
        self.inp_emoji = QLineEdit((sfx_data or {}).get("label", "🎵"))
        self.inp_emoji.setFixedWidth(60)
        row_emoji.addWidget(self.inp_emoji)
        row_emoji.addSpacing(12)
        row_emoji.addWidget(QLabel("Tên nút:"))
        self.inp_name = QLineEdit((sfx_data or {}).get("name", ""))
        self.inp_name.setPlaceholderText("VD: Cười, Vỗ tay...")
        row_emoji.addWidget(self.inp_name, 1)
        vl.addLayout(row_emoji)

        # File path row
        row_file = QHBoxLayout()
        row_file.addWidget(QLabel("File:"))
        self.inp_file = QLineEdit((sfx_data or {}).get("file_path", ""))
        self.inp_file.setPlaceholderText("Chọn file .wav hoặc .mp3...")
        row_file.addWidget(self.inp_file, 1)
        btn_browse = QPushButton("📂")
        btn_browse.setFixedSize(36, 32)
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['card']};
                color: {C['text']};
                border: 1px solid {C['border']};
                border-radius: 6px;
                font-size: 14px;
            }}
            QPushButton:hover {{ background-color: {C['card_hover']}; }}
        """)
        btn_browse.clicked.connect(self._browse_file)
        row_file.addWidget(btn_browse)
        vl.addLayout(row_file)

        # Color picker row
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Màu:"))
        self._color_btns = []
        for col in self._PRESET_COLORS:
            cb = QPushButton()
            cb.setFixedSize(22, 22)
            cb.setCursor(Qt.PointingHandCursor)
            is_selected = (col == self._color)
            border = f"2px solid #fff" if is_selected else f"1px solid {C['border']}"
            cb.setStyleSheet(f"background-color: {col}; border-radius: 11px; border: {border};")
            cb.clicked.connect(lambda _, c=col: self._select_color(c))
            color_row.addWidget(cb)
            self._color_btns.append((col, cb))
        color_row.addStretch()
        vl.addLayout(color_row)

        vl.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_cancel = QPushButton("Huỷ")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['card']};
                color: {C['text_muted']};
                border: 1px solid {C['border']};
                border-radius: 8px;
                font-size: 13px;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: {C['card_hover']}; color: {C['text']}; }}
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("✅ Lưu")
        btn_ok.setFixedHeight(34)
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {C['teal']};
                color: #fff;
                border: none;
                border-radius: 8px;
                font-size: 13px;
                font-weight: 700;
                font-family: {FONT};
            }}
            QPushButton:hover {{ background-color: #5acfff; }}
        """)
        btn_ok.clicked.connect(self._accept)
        btn_row.addWidget(btn_cancel, 1)
        btn_row.addWidget(btn_ok, 1)
        vl.addLayout(btn_row)

    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file âm thanh", "",
            "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*.*)"
        )
        if path:
            self.inp_file.setText(path)

    def _select_color(self, color: str):
        self._color = color
        for col, btn in self._color_btns:
            border = f"2px solid #fff" if col == color else f"1px solid {C['border']}"
            btn.setStyleSheet(f"background-color: {col}; border-radius: 11px; border: {border};")

    def _accept(self):
        self._result = {
            "label": self.inp_emoji.text().strip() or "🎵",
            "name":  self.inp_name.text().strip(),
            "file_path": self.inp_file.text().strip(),
            "color": self._color,
        }
        self.accept()

    def get_result(self) -> dict | None:
        return self._result


# ── SFX Button Area (main widget) ────────────────────────────────────────────
class SfxButtonArea(QWidget):
    """
    Dynamic SFX area — scrollable, flow-layout buttons + [+] add button.

    Signals:
        sfx_changed(list)  — emitted whenever the list changes; parent saves to settings
        sfx_play(str)      — emitted when a button is clicked with file_path
    """
    sfx_changed = Signal(list)
    sfx_play    = Signal(str)

    _DEFAULT_SFX = [
        {"id": "sfx_001", "label": "😂", "name": "Cười",    "file_path": "", "color": C["orange"]},
        {"id": "sfx_002", "label": "👏", "name": "Vỗ tay",  "file_path": "", "color": C["teal"]},
        {"id": "sfx_003", "label": "🎉", "name": "Cheer",   "file_path": "", "color": C["pink"]},
    ]

    def __init__(self, sfx_list: list | None = None, app_dir: str = "", parent=None):
        super().__init__(parent)
        self._app_dir = app_dir
        self._btn_widgets: list[SfxItemButton] = []
        self.setAcceptDrops(True)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(4)

        # Scroll area — horizontal scroll for overflow
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setFixedHeight(44)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:horizontal {{
                background: {C['card']};
                height: 4px;
                border-radius: 2px;
            }}
            QScrollBar::handle:horizontal {{
                background: {C['border']};
                border-radius: 2px;
                min-width: 20px;
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0; height: 0;
            }}
        """)

        # Horizontal container inside scroll
        self._flow = _HBoxContainer(spacing=8, padding=4)
        self._flow.setStyleSheet("background: transparent;")
        self._scroll.setWidget(self._flow)
        self._root.addWidget(self._scroll)

        # Empty state label (shown when no buttons)
        self._empty_lbl = QLabel("Chưa có SFX. Nhấn + để thêm.")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet(f"""
            color: {C['text_muted']};
            font-size: 11px;
            font-family: {FONT};
            font-style: italic;
            background: transparent;
            padding: 8px 0;
        """)
        self._root.addWidget(self._empty_lbl)

        # [+] add button — always last in the row
        self._add_btn = PainterButton("＋", color=C["card_hover"], height=28, radius=8, font_size=13)
        self._add_btn.setFixedWidth(36)
        self._add_btn.setToolTip("Thêm nút SFX mới")
        self._add_btn.clicked.connect(self._on_add)
        # Add [+] to flow upfront — buttons will be inserted BEFORE it
        self._flow._layout.addWidget(self._add_btn)
        self._add_btn.show()

        # Load initial data
        initial = sfx_list if sfx_list is not None else []
        if not initial:
            initial = self._inject_default_paths(list(self._DEFAULT_SFX))
        for item in initial:
            self._append_button(item, emit=False)

        self._sync_empty_state()

    # ── Public API ────────────────────────────────────────────────
    def get_sfx_list(self) -> list:
        return [b.data for b in self._btn_widgets]

    def reorder_by_id(self, src_id: str, target_id: str):
        ids = [b.data["id"] for b in self._btn_widgets]
        if src_id not in ids or target_id not in ids:
            return
        si = ids.index(src_id)
        ti = ids.index(target_id)
        if si == ti:
            return
        btn = self._btn_widgets.pop(si)
        self._btn_widgets.insert(ti, btn)
        self._flow.move_widget(si, ti)
        self.sfx_changed.emit(self.get_sfx_list())

    # ── Internal helpers ──────────────────────────────────────────
    def _inject_default_paths(self, items: list) -> list:
        """Fill empty file_paths in default list with bundled sfx/ files."""
        name_map = {"sfx_001": "sfx_laugh.wav", "sfx_002": "sfx_applause.wav", "sfx_003": "sfx_cheer.wav"}
        for item in items:
            if not item.get("file_path") and item.get("id") in name_map:
                candidate = os.path.join(self._app_dir, "sfx", name_map[item["id"]])
                if os.path.exists(candidate):
                    item["file_path"] = candidate
        return items

    def _append_button(self, sfx_data: dict, emit=True):
        """Create a button widget and insert it before the [+] button."""
        data = dict(sfx_data)
        if not data.get("id"):
            data["id"] = f"sfx_{uuid.uuid4().hex[:8]}"

        btn = SfxItemButton(data)
        btn.clicked.connect(lambda b=btn: self._on_sfx_clicked(b))
        btn.request_edit.connect(self._on_edit)
        btn.request_delete.connect(self._on_delete)
        self._btn_widgets.append(btn)

        # Insert before the [+] button
        idx = self._flow.index_of(self._add_btn)
        if idx >= 0:
            self._flow.insert_widget(idx, btn)
        else:
            self._flow.add_widget(btn)
        btn.show()

        self._sync_empty_state()
        if emit:
            self.sfx_changed.emit(self.get_sfx_list())

    def _sync_empty_state(self):
        has_btns = len(self._btn_widgets) > 0
        self._empty_lbl.setVisible(not has_btns)
        # Always show scroll (even if 1 btn), but hide if zero buttons
        self._scroll.setVisible(True)

    # ── Slots ─────────────────────────────────────────────────────
    def _on_add(self):
        dlg = SfxEditDialog(parent=self)
        if dlg.exec() == QDialog.Accepted:
            result = dlg.get_result()
            if result:
                new_id = f"sfx_{uuid.uuid4().hex[:8]}"
                result["id"] = new_id
                self._append_button(result, emit=True)

    def _on_edit(self, btn_widget: SfxItemButton):
        dlg = SfxEditDialog(sfx_data=btn_widget.data, parent=self)
        if dlg.exec() == QDialog.Accepted:
            result = dlg.get_result()
            if result:
                new_data = {**btn_widget.data, **result}
                btn_widget.update_data(new_data)
                self.sfx_changed.emit(self.get_sfx_list())

    def _on_delete(self, btn_widget: SfxItemButton):
        if btn_widget in self._btn_widgets:
            self._btn_widgets.remove(btn_widget)
            self._flow.remove_widget(btn_widget)
            btn_widget.deleteLater()
            self._sync_empty_state()
            self.sfx_changed.emit(self.get_sfx_list())

    def _on_sfx_clicked(self, btn_widget: SfxItemButton):
        fp = btn_widget.data.get("file_path", "")
        if fp:
            self.sfx_play.emit(fp)

    # ── Drag-and-drop (area level) ────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        # If dropped outside any specific button → move to end
        src_id = e.mimeData().text()
        ids = [b.data["id"] for b in self._btn_widgets]
        if src_id in ids:
            si = ids.index(src_id)
            ti = len(self._btn_widgets) - 1
            if si != ti:
                btn = self._btn_widgets.pop(si)
                self._btn_widgets.insert(ti, btn)
                self._flow.move_widget(si, ti)
                self.sfx_changed.emit(self.get_sfx_list())
        e.acceptProposedAction()
