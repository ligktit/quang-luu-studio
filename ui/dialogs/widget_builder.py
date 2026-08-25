import uuid
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QComboBox, QPushButton, QSpinBox, QCheckBox, QColorDialog
)
from PySide6.QtCore import Qt
from ui.design_tokens import C, FONT
from ui import responsive as rp

class WidgetBuilderDialog(QDialog):
    def __init__(self, parent=None, panel_name="mixer", widget_type="slider", existing_data=None):
        super().__init__(parent)
        self.panel_name = panel_name
        self.widget_type = widget_type
        self.existing_data = existing_data
        self.result_data = None
        
        title = "Sửa Widget" if existing_data else "Thêm Widget Mới"
        self.setWindowTitle(f"{title} - {panel_name.capitalize()}")
        rp.set_min_width(self, 350)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")
        
        self.vl = QVBoxLayout(self)
        self.vl.setSpacing(10)
        
        self._build_fields()
        self._build_buttons()
        
        if self.existing_data:
            self._load_data()
            
    def _add_row(self, label_text, widget):
        hl = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(100)
        hl.addWidget(lbl)
        hl.addWidget(widget)
        self.vl.addLayout(hl)
        return widget
        
    def _build_fields(self):
        # Type
        self.type_combo = QComboBox()
        self.type_combo.addItems(["slider", "button"])
        self.type_combo.setCurrentText(self.widget_type)
        self.type_combo.currentTextChanged.connect(self._on_type_changed)
        self._add_row("Loại Widget:", self.type_combo)
        
        # Label
        self.label_input = QLineEdit()
        self._add_row("Tên (Label):", self.label_input)
        
        # Color
        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("#HexColor")
        self.color_btn = QPushButton("Chọn màu")
        self.color_btn.clicked.connect(self._pick_color)
        
        chl = QHBoxLayout()
        lbl = QLabel("Màu sắc:")
        lbl.setFixedWidth(100)
        chl.addWidget(lbl)
        chl.addWidget(self.color_input)
        chl.addWidget(self.color_btn)
        self.vl.addLayout(chl)
        
        # CC — giá trị -1 = "không gán" (special value), phân biệt với CC 0 hợp lệ.
        # Nhờ vậy nút built-in chỉ bị override khi kỹ thuật viên chủ động chọn một CC.
        self.cc_input = QSpinBox()
        self.cc_input.setRange(-1, 127)
        self.cc_input.setSpecialValueText("— (không gán)")
        self.cc_input.setValue(-1)
        self._add_row("MIDI CC:", self.cc_input)
        
        # --- Slider Specific ---
        self.slider_widget = QVBoxLayout()
        self.slider_widget.setContentsMargins(0, 0, 0, 0)
        
        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("♪, ☉, ≡")
        self.min_val = QSpinBox()
        self.min_val.setRange(-127, 127)
        self.max_val = QSpinBox()
        self.max_val.setRange(-127, 127)
        self.max_val.setValue(100)
        
        hl1 = QHBoxLayout()
        hl1.addWidget(QLabel("Icon:"))
        hl1.addWidget(self.icon_input)
        self.slider_widget.addLayout(hl1)
        
        hl2 = QHBoxLayout()
        hl2.addWidget(QLabel("Min:"))
        hl2.addWidget(self.min_val)
        hl2.addWidget(QLabel("Max:"))
        hl2.addWidget(self.max_val)
        self.slider_widget.addLayout(hl2)
        
        self.has_mute_cb = QCheckBox("Có nút Mute")
        self.slider_widget.addWidget(self.has_mute_cb)
        
        self.vl.addLayout(self.slider_widget)
        
        # --- Button Specific ---
        self.button_widget = QVBoxLayout()
        self.button_widget.setContentsMargins(0, 0, 0, 0)
        
        self.on_val = QSpinBox()
        self.on_val.setRange(0, 127)
        self.on_val.setValue(127)
        self.off_val = QSpinBox()
        self.off_val.setRange(0, 127)
        
        hl3 = QHBoxLayout()
        hl3.addWidget(QLabel("On Value:"))
        hl3.addWidget(self.on_val)
        hl3.addWidget(QLabel("Off Value:"))
        hl3.addWidget(self.off_val)
        self.button_widget.addLayout(hl3)
        
        self.is_toggle_cb = QCheckBox("Là nút Toggle (Bật/Tắt)")
        self.is_toggle_cb.setChecked(True)
        self.button_widget.addWidget(self.is_toggle_cb)
        
        self.vl.addLayout(self.button_widget)
        
        self._on_type_changed(self.widget_type)
        
    def _build_buttons(self):
        hl = QHBoxLayout()
        self.save_btn = QPushButton("Lưu")
        self.save_btn.setStyleSheet(f"background-color: {C['green']}; padding: 5px;")
        self.save_btn.clicked.connect(self._on_save)
        
        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.clicked.connect(self.reject)
        
        hl.addWidget(self.save_btn)
        hl.addWidget(self.cancel_btn)
        self.vl.addLayout(hl)
        
    def _pick_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.color_input.setText(color.name())
            
    def _on_type_changed(self, text):
        if text == "slider":
            self._set_layout_visible(self.slider_widget, True)
            self._set_layout_visible(self.button_widget, False)
        else:
            self._set_layout_visible(self.slider_widget, False)
            self._set_layout_visible(self.button_widget, True)
            
    def _set_layout_visible(self, layout, visible):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget():
                item.widget().setVisible(visible)
            elif item.layout():
                self._set_layout_visible(item.layout(), visible)
                
    def _load_data(self):
        d = self.existing_data
        self.type_combo.setCurrentText(d.get("type", "slider"))
        self.label_input.setText(d.get("label", ""))
        self.color_input.setText(d.get("color", ""))
        
        # CC: số (custom hoặc override) → hiển thị; tên chuỗi (built-in slider) → khoá;
        # không có cc → để ở "— (không gán)" (-1), không override action gốc.
        cc = d.get("cc")
        if isinstance(cc, int):
            self.cc_input.setValue(cc)
        elif isinstance(cc, str):
            # CC dạng tên (built-in, tra trong app_config.json -> midi_cc):
            # khoá spinbox để khi Lưu không ghi đè tên bằng số
            self.cc_input.setEnabled(False)
            self.cc_input.setToolTip(f'CC built-in: "{cc}" — giữ nguyên khi lưu')
        # cc is None → giữ nguyên -1 (không gán)
            
        if d.get("type") == "slider":
            self.icon_input.setText(d.get("icon", ""))
            r = d.get("range", [0, 100])
            self.min_val.setValue(r[0])
            self.max_val.setValue(r[1])
            self.has_mute_cb.setChecked(d.get("has_mute", False))
        else:
            self.on_val.setValue(d.get("on_value", 127))
            self.off_val.setValue(d.get("off_value", 0))
            self.is_toggle_cb.setChecked(d.get("is_toggle", True))
            
    def _on_save(self):
        t = self.type_combo.currentText()
        # Khi sửa widget có sẵn: xuất phát từ bản copy của entry gốc để giữ nguyên
        # các field dialog không quản lý (action, desc, unit, has_inf_bottom, ...).
        base = dict(self.existing_data) if self.existing_data else {"hidden": False}
        wid = base.get("id") or f"custom_{uuid.uuid4().hex[:8]}"

        base.update({
            "id": wid,
            "type": t,
            "label": self.label_input.text(),
            "color": self.color_input.text() or "#ffffff",
        })
        # CC dạng tên (built-in) bị khoá trong _load_data — giữ nguyên.
        # Sửa được: >=0 ghi đè CC số (override action gốc); -1 = không gán → bỏ key cc.
        if self.cc_input.isEnabled():
            v = self.cc_input.value()
            if v >= 0:
                base["cc"] = v
            else:
                base.pop("cc", None)

        if t == "slider":
            base.update({
                "icon": self.icon_input.text(),
                "range": [self.min_val.value(), self.max_val.value()],
                "has_mute": self.has_mute_cb.isChecked(),
            })
            base.setdefault("default", 0)
        else:
            base.update({
                "on_value": self.on_val.value(),
                "off_value": self.off_val.value(),
                "is_toggle": self.is_toggle_cb.isChecked()
            })

        self.result_data = base
        self.accept()
