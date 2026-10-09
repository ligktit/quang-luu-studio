"""Hộp "Quản lý giao diện" của Dev Mode.

Hiện/ẩn, đổi thứ tự (kéo-thả hoặc ↑/↓), sửa, xoá (chỉ widget tự thêm) và
khôi phục mặc định từng panel. Mọi thao tác chạy trên BẢN SAO ui_config —
chỉ ghi ui_config.json khi bấm Lưu; Huỷ/đóng thì bỏ hết. Calibration (Bypass,
mode_config) do Widget Builder trả về được gom vào `calibrations` để
MainDashboard áp sau khi Lưu.
"""
import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QTabWidget, QVBoxLayout,
)

from core import devmode_backup, ui_layout
from core.config import UiConfigManager
from ui import responsive as rp
from ui.design_tokens import C, FONT
from ui.dialogs.widget_builder import WidgetBuilderDialog

ID_ROLE = Qt.UserRole
_PANELS = list(ui_layout.PANEL_TITLES)


class WidgetManagerDialog(QDialog):
    def __init__(self, parent=None, panel_name="mixer", ui_config=None, engine=None, midi_cc=None):
        super().__init__(parent)
        self.setWindowTitle("Quản lý giao diện")
        rp.set_min_width(self, 460)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")

        source = ui_config if ui_config is not None else UiConfigManager.load_ui_config()
        self.working = copy.deepcopy(source)
        self.calibrations = []
        self.restored = False
        self.restored_backups = []
        self._dirty = False
        self._engine = engine
        self._midi_cc = midi_cc
        self._populating = False

        vl = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.lists = {}
        for panel, title in ui_layout.PANEL_TITLES.items():
            lst = QListWidget()
            lst.setDragDropMode(QAbstractItemView.InternalMove)
            lst.setDefaultDropAction(Qt.MoveAction)
            lst.itemChanged.connect(lambda item, p=panel: self._on_item_changed(p, item))
            lst.model().rowsMoved.connect(lambda *_a, p=panel: self._sync_order(p))
            lst.currentRowChanged.connect(lambda _r: self._refresh_buttons())
            lst.itemDoubleClicked.connect(lambda _i: self._edit_selected())
            self.lists[panel] = lst
            self.tabs.addTab(lst, title)
            self._populate(panel)
        vl.addWidget(self.tabs)

        hint = QLabel("Tích để hiện, bỏ tích để ẩn · kéo hoặc ↑/↓ để đổi thứ tự · nhấp đúp để sửa")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px;")
        vl.addWidget(hint)

        row = QHBoxLayout()
        self.up_btn = QPushButton("↑")
        self.down_btn = QPushButton("↓")
        self.edit_btn = QPushButton("Sửa")
        self.delete_btn = QPushButton("Xoá")
        self.add_btn = QPushButton("+ Thêm")
        self.up_btn.clicked.connect(lambda: self._move_selected(-1))
        self.down_btn.clicked.connect(lambda: self._move_selected(1))
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.add_btn.clicked.connect(self._add)
        for b in (self.up_btn, self.down_btn, self.edit_btn, self.delete_btn):
            row.addWidget(b)
        row.addStretch()
        row.addWidget(self.add_btn)
        vl.addLayout(row)

        self.reset_btn = QPushButton("Khôi phục mặc định panel này")
        self.reset_btn.clicked.connect(self._reset_panel)
        vl.addWidget(self.reset_btn)

        self.footer = QHBoxLayout()
        self.export_btn = QPushButton("Xuất file")
        self.export_btn.setToolTip("Lưu giao diện + cân chỉnh MIDI của máy này ra một file .json")
        self.export_btn.clicked.connect(self._export)
        self.import_btn = QPushButton("Nhập file")
        self.import_btn.setToolTip("Nạp giao diện + cân chỉnh MIDI từ file đã xuất")
        self.import_btn.clicked.connect(self._import)
        self.footer.addWidget(self.export_btn)
        self.footer.addWidget(self.import_btn)
        self.footer.addStretch()
        self.save_btn = QPushButton("Lưu")
        self.save_btn.setStyleSheet(f"background-color: {C['green']}; padding: 5px;")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn = QPushButton("Huỷ")
        self.cancel_btn.clicked.connect(self.reject)
        self.footer.addWidget(self.save_btn)
        self.footer.addWidget(self.cancel_btn)
        vl.addLayout(self.footer)

        self.tabs.currentChanged.connect(lambda _i: self._refresh_buttons())
        self.tabs.setCurrentIndex(_PANELS.index(panel_name) if panel_name in _PANELS else 0)
        self._refresh_buttons()

    # ── Truy cập ─────────────────────────────────────────────
    def current_panel(self):
        return _PANELS[self.tabs.currentIndex()]

    def _entries(self, panel):
        entries = self.working.get(panel)
        if not isinstance(entries, list):
            entries = self.working[panel] = []
        return entries

    def _find(self, panel, wid):
        entries = self._entries(panel)
        i = ui_layout.index_of(entries, wid)
        return entries[i] if i >= 0 else None

    def _selected_id(self):
        item = self.lists[self.current_panel()].currentItem()
        return item.data(ID_ROLE) if item else None

    def select(self, panel, wid):
        self.tabs.setCurrentIndex(_PANELS.index(panel))
        lst = self.lists[panel]
        for i in range(lst.count()):
            if lst.item(i).data(ID_ROLE) == wid:
                lst.setCurrentRow(i)
                return

    # ── Vẽ danh sách ─────────────────────────────────────────
    def _row_text(self, panel, entry):
        tag = "" if ui_layout.is_custom(panel, entry) else "có sẵn"
        cc = entry.get("cc")
        if isinstance(cc, int) and not isinstance(cc, bool):
            tag = f"{tag} · CC {cc}" if tag else f"CC {cc}"
        elif not tag:
            tag = "chưa gán CC"
        return f"{entry.get('label') or entry.get('id')}   —   {tag}"

    def _style_item(self, item, hidden):
        item.setForeground(QColor(C["text_muted"] if hidden else C["text"]))

    def _populate(self, panel, select_id=None):
        lst = self.lists[panel]
        self._populating = True
        try:
            lst.clear()
            for e in self._entries(panel):
                if not isinstance(e, dict):
                    continue
                item = QListWidgetItem(self._row_text(panel, e))
                item.setData(ID_ROLE, e.get("id"))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                hidden = bool(e.get("hidden"))
                item.setCheckState(Qt.Unchecked if hidden else Qt.Checked)
                self._style_item(item, hidden)
                lst.addItem(item)
        finally:
            self._populating = False
        if select_id is not None:
            self.select(panel, select_id)

    def _refresh_buttons(self):
        panel = self.current_panel()
        wid = self._selected_id()
        entry = self._find(panel, wid) if wid is not None else None
        for b in (self.up_btn, self.down_btn, self.edit_btn):
            b.setEnabled(entry is not None)
        self.delete_btn.setEnabled(entry is not None and ui_layout.is_custom(panel, entry))

    # ── Thao tác ─────────────────────────────────────────────
    def _on_item_changed(self, panel, item):
        if self._populating:
            return
        wid = item.data(ID_ROLE)
        hidden = item.checkState() != Qt.Checked
        entry = self._find(panel, wid)
        if entry is None or bool(entry.get("hidden")) == hidden:
            return
        ui_layout.set_hidden(self._entries(panel), wid, hidden)
        self._dirty = True
        # Đổi màu chữ cũng phát itemChanged — chặn vòng lặp.
        self._populating = True
        try:
            self._style_item(item, hidden)
        finally:
            self._populating = False

    def _sync_order(self, panel):
        lst = self.lists[panel]
        ids = [lst.item(i).data(ID_ROLE) for i in range(lst.count())]
        self.working[panel] = ui_layout.reorder(self._entries(panel), ids)
        self._dirty = True

    def _move_selected(self, delta):
        panel = self.current_panel()
        wid = self._selected_id()
        if wid is None:
            return
        entries = self._entries(panel)
        idx = ui_layout.index_of(entries, wid)
        if ui_layout.move(entries, idx, delta) != idx:
            self._dirty = True
        self._populate(panel, wid)

    def _builder(self, panel, widget_type, existing=None):
        return WidgetBuilderDialog(self, panel_name=panel, widget_type=widget_type,
                                   existing_data=existing, engine=self._engine,
                                   ui_config=self.working, midi_cc=self._midi_cc)

    def _take_result(self, dlg):
        if dlg.exec() != QDialog.Accepted or not dlg.result_data:
            return None
        if dlg.result_calibration:
            self.calibrations.append(dlg.result_calibration)
        self._dirty = True
        return dlg.result_data

    def _edit_selected(self):
        panel = self.current_panel()
        wid = self._selected_id()
        entry = self._find(panel, wid) if wid is not None else None
        if entry is None:
            return
        data = self._take_result(self._builder(panel, entry.get("type", "button"), entry))
        if data is None:
            return
        entries = self._entries(panel)
        entries[ui_layout.index_of(entries, wid)] = data
        self._populate(panel, wid)

    def _add(self):
        panel = self.current_panel()
        data = self._take_result(self._builder(panel, "slider" if panel == "mixer" else "button"))
        if data is None:
            return
        self._entries(panel).append(data)
        self._populate(panel, data.get("id"))

    def _delete_selected(self):
        panel = self.current_panel()
        wid = self._selected_id()
        entry = self._find(panel, wid) if wid is not None else None
        if entry is None or not ui_layout.is_custom(panel, entry):
            return
        answer = QMessageBox.question(
            self, "Xoá widget",
            f"Xoá “{entry.get('label') or wid}”? Sau khi Lưu sẽ không hoàn tác được.")
        if answer != QMessageBox.Yes:
            return
        ui_layout.delete_custom(panel, self._entries(panel), wid)
        self._dirty = True
        self._populate(panel)
        self._refresh_buttons()

    def _reset_panel(self):
        panel = self.current_panel()
        title = ui_layout.PANEL_TITLES[panel]
        answer = QMessageBox.question(
            self, "Khôi phục mặc định",
            f"Đưa panel {title} về mặc định? Widget tự thêm của panel này sẽ bị xoá.")
        if answer != QMessageBox.Yes:
            return
        ui_layout.reset_panel(self.working, panel)
        self._dirty = True
        self._populate(panel)
        self._refresh_buttons()

    # ── Xuất / Nhập ──────────────────────────────────────────
    def _export(self):
        if self._dirty:
            QMessageBox.information(self, "Xuất file",
                                    "Có thay đổi chưa lưu — bấm Lưu trước rồi mới xuất.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Xuất cấu hình giao diện", devmode_backup.default_filename(),
            "Cấu hình (*.json)")
        if not path:
            return
        try:
            devmode_backup.export_backup(path)
        except Exception as e:
            QMessageBox.warning(self, "Xuất file", f"Không xuất được: {e}")
            return
        QMessageBox.information(self, "Xuất file", f"Đã xuất:\n{path}")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Nhập cấu hình giao diện", "", "Cấu hình (*.json)")
        if not path:
            return
        try:
            backup = devmode_backup.read_backup(path)
        except devmode_backup.BackupError as e:
            QMessageBox.warning(self, "Nhập file", str(e))
            return
        text = (f"{devmode_backup.summarize(backup)}\n\n"
                "Cấu hình hiện tại sẽ được sao lưu tự động trước khi ghi đè.")
        if self._dirty:
            text += "\nCác thay đổi chưa lưu trong hộp này sẽ bị bỏ."
        if QMessageBox.question(self, "Nhập cấu hình", text) != QMessageBox.Yes:
            return
        try:
            self.restored_backups = devmode_backup.restore_backup(backup)
        except devmode_backup.BackupError as e:
            QMessageBox.warning(self, "Nhập file", str(e))
            return
        self.restored = True
        self.accept()

    # ── Lưu / đóng ───────────────────────────────────────────
    def _on_save(self):
        if not UiConfigManager.save_ui_config(self.working):
            QMessageBox.warning(self, "Quản lý giao diện",
                                "Không lưu được ui_config.json — thay đổi vẫn còn trong hộp này.")
            return
        self._dirty = False
        self.accept()

    def reject(self):
        # Nút Huỷ, phím Esc và nút X (QDialog.closeEvent gọi reject() và tự
        # bỏ qua sự kiện đóng nếu hộp vẫn hiện) đều đi qua đây.
        if self._dirty and not self.restored:
            answer = QMessageBox.question(self, "Bỏ thay đổi", "Bỏ các thay đổi chưa lưu?")
            if answer != QMessageBox.Yes:
                return
        super().reject()
