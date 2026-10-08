import uuid
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QWidget, QFrame,
    QComboBox, QPushButton, QSpinBox, QDoubleSpinBox, QCheckBox, QColorDialog
)
from PySide6.QtCore import Qt
from core import so_values
from ui.design_tokens import C, FONT
from ui import responsive as rp


def _config():
    """AppConfig + mặc định — import muộn để dialog dựng được cả khi test."""
    from core.config import AppConfig, DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT
    return AppConfig, DEFAULT_MODE_CONFIG, DEFAULT_TOGGLE_INVERT


class WidgetBuilderDialog(QDialog):
    """Thêm/sửa widget ở Dev Mode.

    Giá trị bật/tắt của nút nhập theo đơn vị STUDIO ONE (On/Off, %, dải số,
    mục trong danh sách) — app tự quy đổi ra MIDI qua core.so_values.

    Nút gửi MIDI theo một trong ba "đích" (xem _value_target):
      • "custom"        — nút có CC số: on_value/off_value nằm ngay trong entry.
      • "mode_config"   — nút MODE có sẵn: giá trị thật nằm ở mode_config[nhãn].
      • "toggle_invert" — Auto-Tune/Fix Méo/Bè/Tắt Ồn: chỉ có cờ Bypass.
    Hai đích sau được trả qua `result_calibration` để MainDashboard ghi vào
    calibration_overrides.json (DATA_DIR, không cần quyền admin).
    """

    def __init__(self, parent=None, panel_name="mixer", widget_type="slider", existing_data=None):
        super().__init__(parent)
        self.panel_name = panel_name
        self.widget_type = widget_type
        self.existing_data = existing_data
        self.result_data = None
        self.result_calibration = None
        self._loading = False

        title = "Sửa Widget" if existing_data else "Thêm Widget Mới"
        self.setWindowTitle(f"{title} - {panel_name.capitalize()}")
        rp.set_min_width(self, 420)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']}; font-family: {FONT};")

        self.vl = QVBoxLayout(self)
        self.vl.setSpacing(10)

        self._build_fields()
        self._build_buttons()

        self._load_data()
        self._on_type_changed(self.type_combo.currentText())

    def _add_row(self, label_text, widget, layout=None):
        hl = QHBoxLayout()
        lbl = QLabel(label_text)
        lbl.setFixedWidth(100)
        hl.addWidget(lbl)
        hl.addWidget(widget)
        (layout or self.vl).addLayout(hl)
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
        self.cc_input.valueChanged.connect(lambda _v: self._refresh_value_section())
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
        self.button_box = QWidget()
        self._build_button_section(self.button_box)
        self.vl.addWidget(self.button_box)

    def _build_button_section(self, box):
        vl = QVBoxLayout(box)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(8)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color: {C['border']};")
        vl.addWidget(sep)

        head = QLabel("Giá trị trong Studio One")
        head.setStyleSheet("font-weight: 700;")
        vl.addWidget(head)

        self.so_type_combo = QComboBox()
        for key in so_values.TYPES:
            self.so_type_combo.addItem(so_values.TYPE_LABELS[key], key)
        self.so_type_combo.currentIndexChanged.connect(lambda _i: self._refresh_value_section())
        self._add_row("Kiểu tham số:", self.so_type_combo, vl)

        # Công tắc: chỉ cần biết có phải Bypass hay không.
        self.bypass_cb = QCheckBox("Gán vào Bypass của plugin (đảo chiều)")
        self.bypass_cb.setToolTip(
            "Bật khi control trong Studio One là nút Bypass: Bypass On = plugin TẮT.\n"
            "App sẽ gửi Bypass Off khi nút BẬT và đọc phản hồi theo đúng chiều đó,\n"
            "để đèn nút không bị ngược với Studio One.")
        self.bypass_cb.toggled.connect(lambda _c: self._refresh_preview())
        vl.addWidget(self.bypass_cb)

        # Khoảng số: dải của tham số đúng như Studio One hiển thị.
        self.range_box = QWidget()
        rl = QHBoxLayout(self.range_box)
        rl.setContentsMargins(0, 0, 0, 0)
        self.range_min = self._make_double(-100000, 100000, -12)
        self.range_max = self._make_double(-100000, 100000, 12)
        self.range_unit = QLineEdit()
        self.range_unit.setPlaceholderText("st, dB, ms…")
        self.range_unit.setMaximumWidth(80)
        for w in (self.range_min, self.range_max):
            w.valueChanged.connect(lambda _v: self._refresh_value_section())
        self.range_unit.textChanged.connect(lambda _t: self._refresh_value_section())
        rl.addWidget(QLabel("Từ:"))
        rl.addWidget(self.range_min)
        rl.addWidget(QLabel("đến:"))
        rl.addWidget(self.range_max)
        rl.addWidget(QLabel("Đơn vị:"))
        rl.addWidget(self.range_unit)
        vl.addWidget(self.range_box)

        # Danh sách lựa chọn: gõ đúng tên các mục theo thứ tự trong Studio One.
        self.options_input = QLineEdit()
        self.options_input.setPlaceholderText("Các mục theo thứ tự, cách nhau bởi dấu phẩy — vd: Tắt, Nhẹ, Mạnh")
        self.options_input.textChanged.connect(lambda _t: self._rebuild_option_combos())
        self.options_row = QWidget()
        orl = QHBoxLayout(self.options_row)
        orl.setContentsMargins(0, 0, 0, 0)
        olbl = QLabel("Các lựa chọn:")
        olbl.setFixedWidth(100)
        orl.addWidget(olbl)
        orl.addWidget(self.options_input)
        vl.addWidget(self.options_row)

        # Hai dòng giá trị: khi nút BẬT / khi nút TẮT.
        self.on_row, self.on_num, self.on_combo, self.on_preview = self._make_value_row("Khi nút BẬT:")
        self.off_row, self.off_num, self.off_combo, self.off_preview = self._make_value_row("Khi nút TẮT:")
        vl.addWidget(self.on_row)
        vl.addWidget(self.off_row)

        # Công tắc không có dòng nhập — tóm tắt quy đổi hiện ở đây.
        self.switch_preview = QLabel()
        self.switch_preview.setStyleSheet(f"color: {C['text_muted']};")
        vl.addWidget(self.switch_preview)

        self.value_note = QLabel()
        self.value_note.setWordWrap(True)
        self.value_note.setStyleSheet(f"color: {C['text_muted']}; font-size: 11px;")
        # Dành sẵn 3 dòng: nhãn xuống dòng có chiều cao phụ thuộc chiều rộng
        # (heightForWidth). Nếu để nó quyết định cỡ tối thiểu của dialog mỗi lần
        # đổi ghi chú, Qt ép cỡ cửa sổ hai bước lệch nhau một dòng và in
        # "QWindowsWindow::setGeometry: Unable to set geometry" mỗi lần đổi
        # CC / Kiểu tham số. Ghi chú dài nhất ~2,7 dòng ở bề rộng tối thiểu.
        self.value_note.ensurePolished()
        self.value_note.setMinimumHeight(self.value_note.fontMetrics().lineSpacing() * 3 + 4)
        vl.addWidget(self.value_note)

        self.is_toggle_cb = QCheckBox("Là nút Toggle (Bật/Tắt)")
        self.is_toggle_cb.setChecked(True)
        self.is_toggle_cb.toggled.connect(lambda _c: self._refresh_value_section())
        vl.addWidget(self.is_toggle_cb)

    @staticmethod
    def _make_double(lo, hi, value):
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(2)
        sb.setValue(value)
        return sb

    def _make_value_row(self, label_text):
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(100)
        num = self._make_double(0, 100, 0)
        num.valueChanged.connect(lambda _v: self._refresh_preview())
        combo = QComboBox()
        combo.currentIndexChanged.connect(lambda _i: self._refresh_preview())
        preview = QLabel()
        preview.setStyleSheet(f"color: {C['text_muted']};")
        hl.addWidget(lbl)
        hl.addWidget(num)
        hl.addWidget(combo)
        hl.addWidget(preview, 1)
        return row, num, combo, preview

    def _build_buttons(self):
        self.error_label = QLabel()
        self.error_label.setStyleSheet(f"color: {C['accent']};")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        self.vl.addWidget(self.error_label)

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
        # Có parent: cửa sổ chính đang ghim trên cùng thì hộp chọn màu không
        # bị nó che mất.
        color = QColorDialog.getColor(parent=self)
        if color.isValid():
            self.color_input.setText(color.name())

    def _on_type_changed(self, text):
        self._set_layout_visible(self.slider_widget, text == "slider")
        self.button_box.setVisible(text != "slider")
        if text != "slider":
            self._refresh_value_section()
        self.adjustSize()

    def _set_layout_visible(self, layout, visible):
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget():
                item.widget().setVisible(visible)
            elif item.layout():
                self._set_layout_visible(item.layout(), visible)

    # ── Đích lưu giá trị bật/tắt ─────────────────────────────
    def _action(self):
        return (self.existing_data or {}).get("action", "") or ""

    def _cc_override(self):
        return self.cc_input.isEnabled() and self.cc_input.value() >= 0

    def _value_target(self):
        """Giá trị bật/tắt của nút này nằm ở đâu (None = nút không gửi MIDI)."""
        if self._cc_override():
            return "custom"
        action = self._action()
        _, _, default_invert = _config()
        if action in default_invert:
            return "toggle_invert"
        if self.panel_name == "mode" and action.startswith("set_mode"):
            return "mode_config"
        return None

    def _mode_cfg(self, label):
        app_config, default_modes, _ = _config()
        try:
            modes = app_config.get_mode_config() or {}
        except Exception:
            modes = {}
        return modes.get(label) or default_modes.get(label)

    def _stored_spec(self):
        """Mô tả so_value của đích hiện tại, khớp với MIDI app đang thật sự gửi."""
        d = self.existing_data or {}
        target = self._value_target()
        if target == "toggle_invert":
            app_config, _, _ = _config()
            try:
                invert = bool(app_config.get_toggle_invert().get(self._action(), False))
            except Exception:
                invert = False
            return {"type": "switch", "bypass": invert}
        if target == "mode_config":
            cfg = self._mode_cfg(d.get("label", "")) or {}
            return so_values.resolve_spec(
                d.get("so_value"), cfg.get("on_value", 127), cfg.get("off_value", 0))
        if not d:
            return {"type": "switch", "bypass": False}
        return so_values.resolve_spec(
            d.get("so_value"), d.get("on_value", 127), d.get("off_value", 0))

    # ── Nạp / đọc mô tả so_value từ các ô nhập ───────────────
    def _apply_spec(self, spec):
        self._loading = True
        try:
            t = spec.get("type", "switch")
            self.so_type_combo.setCurrentIndex(max(0, self.so_type_combo.findData(t)))
            self.bypass_cb.setChecked(bool(spec.get("bypass", False)))
            if t == "range":
                self.range_min.setValue(float(spec.get("min", 0)))
                self.range_max.setValue(float(spec.get("max", 100)))
                self.range_unit.setText(spec.get("unit", ""))
            if t == "list":
                self.options_input.setText(", ".join(spec.get("options") or []))
            self._refresh_value_section()
            if t in ("percent", "range", "midi"):
                self.on_num.setValue(float(spec.get("on", 0)))
                self.off_num.setValue(float(spec.get("off", 0)))
            elif t == "list":
                self.on_combo.setCurrentIndex(int(spec.get("on", 0)))
                self.off_combo.setCurrentIndex(int(spec.get("off", 0)))
        finally:
            self._loading = False
        self._refresh_preview()

    def _options(self):
        return [o.strip() for o in self.options_input.text().split(",") if o.strip()]

    def _current_spec(self):
        t = self.so_type_combo.currentData()
        if t == "switch":
            return {"type": "switch", "bypass": self.bypass_cb.isChecked()}
        if t == "list":
            return {"type": "list", "options": self._options(),
                    "on": max(0, self.on_combo.currentIndex()),
                    "off": max(0, self.off_combo.currentIndex())}
        spec = {"type": t, "on": self.on_num.value(), "off": self.off_num.value()}
        if t == "range":
            spec.update(min=self.range_min.value(), max=self.range_max.value(),
                        unit=self.range_unit.text().strip())
        if t == "midi":
            spec["on"], spec["off"] = int(spec["on"]), int(spec["off"])
        return spec

    def _validation_error(self, spec):
        t = spec.get("type")
        if t == "range" and spec["min"] == spec["max"]:
            return "Khoảng số: giá trị 'Từ' và 'đến' phải khác nhau."
        if t == "list" and len(spec["options"]) < 2:
            return "Danh sách lựa chọn cần ít nhất 2 mục (cách nhau bởi dấu phẩy)."
        return None

    def _rebuild_option_combos(self):
        options = self._options()
        for combo in (self.on_combo, self.off_combo):
            keep = combo.currentIndex()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(options)
            combo.setCurrentIndex(min(max(keep, 0), len(options) - 1) if options else -1)
            combo.blockSignals(False)
        self._refresh_preview()

    def _refresh_value_section(self):
        """Hiện đúng ô nhập theo đích + kiểu tham số đang chọn."""
        target = self._value_target()
        has_values = target is not None

        # Auto-Tune/Fix Méo/Bè/Tắt Ồn chỉ có cờ đảo chiều → khoá ở Công tắc.
        if target == "toggle_invert":
            self.so_type_combo.setCurrentIndex(self.so_type_combo.findData("switch"))
        self.so_type_combo.setEnabled(has_values and target != "toggle_invert")
        t = self.so_type_combo.currentData()

        self.bypass_cb.setVisible(has_values and t == "switch")
        self.range_box.setVisible(has_values and t == "range")
        self.options_row.setVisible(has_values and t == "list")
        numeric = t in ("percent", "range", "midi")
        for row, num, combo in ((self.on_row, self.on_num, self.on_combo),
                                (self.off_row, self.off_num, self.off_combo)):
            row.setVisible(has_values and t != "switch")
            num.setVisible(numeric)
            combo.setVisible(t == "list")

        if t == "percent":
            lo, hi, dec, suffix = 0, 100, 1, " %"
        elif t == "range":
            lo = min(self.range_min.value(), self.range_max.value())
            hi = max(self.range_min.value(), self.range_max.value())
            unit = self.range_unit.text().strip()
            dec, suffix = 2, (f" {unit}" if unit else "")
        else:
            lo, hi, dec, suffix = 0, 127, 0, ""
        for num in (self.on_num, self.off_num):
            num.blockSignals(True)
            num.setDecimals(dec)
            num.setRange(lo, hi)
            num.setSuffix(suffix)
            num.blockSignals(False)
        if t == "list" and self.on_combo.count() != len(self._options()):
            self._rebuild_option_combos()

        # Nút MODE luôn là bật/tắt; nút có sẵn thì không có lựa chọn này.
        show_toggle = self.panel_name == "tools" and target == "custom"
        self.is_toggle_cb.setVisible(show_toggle)
        self.off_row.setEnabled(not show_toggle or self.is_toggle_cb.isChecked())

        notes = {
            None: "Nút này không gửi MIDI. Gán MIDI CC ở trên nếu muốn nó điều khiển Studio One.",
            "toggle_invert": "Nút có sẵn: chỉ chọn được chiều. Bật ô Bypass nếu control trong "
                             "Studio One là nút Bypass của plugin.",
        }
        type_notes = {
            "percent": "Nhập đúng số % Studio One hiển thị trên núm (Mix, Dry/Wet, Send…).",
            "range": "Nhập dải của núm đúng như Studio One hiển thị, rồi giá trị muốn đặt. "
                     "Chỉ chính xác với núm chia đều — núm kiểu tần số/thời gian (log) "
                     "hãy dùng MIDI thô.",
            "list": "Gõ tên các mục của menu/nút chọn trong plugin theo đúng thứ tự từ trên "
                    "xuống, rồi chọn mục ứng với BẬT/TẮT.",
            "midi": "Nhập thẳng giá trị MIDI 0–127 — chỉ dùng khi các kiểu trên không phù hợp.",
            "switch": "Tích Bypass nếu control trong Studio One là nút Bypass của plugin "
                      "(Bypass On = plugin tắt) — đèn nút trên app sẽ không bị ngược.",
        }
        self.value_note.setText(notes.get(target) if target in notes else type_notes.get(t, ""))

        if not self._loading:
            self._refresh_preview()

    def _refresh_preview(self):
        if self._loading:
            return
        spec = self._current_spec()
        has_values = self._value_target() is not None
        err = self._validation_error(spec) if has_values else None
        self.error_label.setText(err or "")
        self.error_label.setVisible(bool(err))

        if not has_values or err:
            for lbl in (self.on_preview, self.off_preview):
                lbl.setText("")
            self.switch_preview.setVisible(False)
            return

        on_midi, off_midi = so_values.midi_pair(spec)
        if spec["type"] == "switch":
            self.switch_preview.setText(
                f"BẬT → {so_values.describe(spec, 'on')} (MIDI {on_midi})    "
                f"TẮT → {so_values.describe(spec, 'off')} (MIDI {off_midi})")
            self.switch_preview.setVisible(True)
            return
        self.switch_preview.setVisible(False)
        for lbl, key, midi in ((self.on_preview, "on", on_midi), (self.off_preview, "off", off_midi)):
            text = f"→ MIDI {midi}"
            if spec["type"] in ("percent", "range"):
                # Làm tròn sang 128 nấc MIDI — cho thấy Studio One thật sự nhận gì.
                text += f"  (Studio One {so_values.describe(spec, key)})"
            lbl.setText(text)

    # ── Nạp / lưu ────────────────────────────────────────────
    def _load_data(self):
        d = self.existing_data
        if not d:
            self._apply_spec(self._stored_spec())
            return
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
            self.is_toggle_cb.setChecked(d.get("is_toggle", True))
        self._apply_spec(self._stored_spec())

    def _on_save(self):
        t = self.type_combo.currentText()
        # Khi sửa widget có sẵn: xuất phát từ bản copy của entry gốc để giữ nguyên
        # các field dialog không quản lý (action, desc, unit, has_inf_bottom, ...).
        base = dict(self.existing_data) if self.existing_data else {"hidden": False}
        wid = base.get("id") or f"custom_{uuid.uuid4().hex[:8]}"
        label = self.label_input.text()

        base.update({
            "id": wid,
            "type": t,
            "label": label,
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

        calibration = None
        if t == "slider":
            base.update({
                "icon": self.icon_input.text(),
                "range": [self.min_val.value(), self.max_val.value()],
                "has_mute": self.has_mute_cb.isChecked(),
            })
            base.setdefault("default", 0)
        else:
            target = self._value_target()
            spec = self._current_spec()
            if target is not None:
                err = self._validation_error(spec)
                if err:
                    self.error_label.setText(err)
                    self.error_label.setVisible(True)
                    return
            on_midi, off_midi = so_values.midi_pair(spec)

            if target == "custom":
                base.update({
                    "on_value": on_midi,
                    "off_value": off_midi,
                    "so_value": spec,
                    "is_toggle": self.is_toggle_cb.isChecked(),
                })
            elif target == "mode_config":
                # MODE có sẵn gửi theo mode_config[nhãn] — ghi giá trị vào đó,
                # giữ nguyên CC. Đổi nhãn thì mang CC của nhãn cũ sang.
                old_label = (self.existing_data or {}).get("label", "")
                cfg = dict(self._mode_cfg(label) or self._mode_cfg(old_label) or {})
                if "cc" in cfg:
                    cfg.update(on_value=on_midi, off_value=off_midi)
                    calibration = {"mode_config": {label: cfg}}
                base["so_value"] = spec
            elif target == "toggle_invert":
                calibration = {"toggle_invert": {self._action(): bool(spec.get("bypass"))}}
            # target None: nút không gửi MIDI → không có giá trị nào để ghi.

        self.result_data = base
        self.result_calibration = calibration
        self.accept()
