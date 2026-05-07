import re
import codecs

file_path = r"d:\Projects\LiveStudio\quang-luu-studio\ui\dialogs\settings_dialog.py"

with codecs.open(file_path, "r", "utf-8") as f:
    content = f.read()

# 1. Thêm SVG_EYE_OPEN
content = re.sub(r'SVG_WRENCH,(\r?\n\))', r'SVG_WRENCH,\n    SVG_EYE_OPEN,\1', content)

# 2. Thêm tab trợ năng
tabs_replace = '''        # Tab 3: Tools
        self._tabs.addTab(
            self._build_tools_tab(),
            self._svg_icon(SVG_WRENCH, "white", 16),
            "Công cụ",
        )

        # Tab 4: Accessibility
        self._tabs.addTab(
            self._build_accessibility_tab(settings),
            self._svg_icon(SVG_EYE_OPEN, "white", 16),
            "Trợ năng",
        )

        outer.addWidget(self._tabs, 1)'''
content = re.sub(r'        # Tab 3: Tools.*?outer\.addWidget\(self\._tabs, 1\)', tabs_replace, content, flags=re.DOTALL)

# 3. Hàm _build_accessibility_tab
acc_tab = '''        lay.addStretch()
        return tab

    def _build_accessibility_tab(self, settings):
        tab = QWidget()
        tab.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(12)

        lay.addWidget(self._section_header(SVG_EYE_OPEN, "Hỗ trợ người khiếm thị"))
        lay.addWidget(self._section_card(self._build_accessibility_options))

        lay.addStretch()
        return tab

    def _build_paths(self, vl):'''
content = content.replace('        lay.addStretch()\r\n        return tab\r\n\r\n    def _build_paths(self, vl):', acc_tab.replace('\n', '\r\n'))
content = content.replace('        lay.addStretch()\n        return tab\n\n    def _build_paths(self, vl):', acc_tab)

# 4. Hàm _build_accessibility_options
acc_options = '''        vl.addWidget(self._cb_close_br)

    def _build_accessibility_options(self, vl):
        acc = backend.AppConfig.get("accessibility") or {}
        vl.setSpacing(8)
        
        self._cb_tts = QCheckBox("Bật giọng nói thông báo (TTS)")
        self._cb_tts.setStyleSheet(self._checkbox_qss)
        self._cb_tts.setChecked(acc.get("tts_enabled", False))
        self._cb_tts.setAccessibleName("Bật thông báo giọng nói TTS")
        vl.addWidget(self._cb_tts)

        self._cb_announce_focus = QCheckBox("Đọc tên nút/thanh trượt khi chọn (Announce Focus)")
        self._cb_announce_focus.setStyleSheet(self._checkbox_qss)
        self._cb_announce_focus.setChecked(acc.get("announce_focus", True))
        self._cb_announce_focus.setAccessibleName("Đọc tên điều khiển khi được chọn")
        vl.addWidget(self._cb_announce_focus)

        self._cb_announce_state = QCheckBox("Đọc trạng thái khi thay đổi (Tone, Điểm, etc.)")
        self._cb_announce_state.setStyleSheet(self._checkbox_qss)
        self._cb_announce_state.setChecked(acc.get("announce_state", True))
        self._cb_announce_state.setAccessibleName("Đọc thay đổi trạng thái")
        vl.addWidget(self._cb_announce_state)

        self._cb_voice_cmd = QCheckBox("Bật điều khiển bằng giọng nói (Giữ Ctrl+Space)")
        self._cb_voice_cmd.setStyleSheet(self._checkbox_qss)
        self._cb_voice_cmd.setChecked(acc.get("voice_command_enabled", False))
        self._cb_voice_cmd.setAccessibleName("Điều khiển bằng giọng nói")
        vl.addWidget(self._cb_voice_cmd)

        self._cb_high_contrast = QCheckBox("Chế độ tương phản cao (Nền đen, chữ vàng)")
        self._cb_high_contrast.setStyleSheet(self._checkbox_qss)
        self._cb_high_contrast.setChecked(acc.get("high_contrast", False))
        self._cb_high_contrast.setAccessibleName("Bật chế độ tương phản cao")
        vl.addWidget(self._cb_high_contrast)

        self._cb_focus_ring = QCheckBox("Viền chỉ thị nổi bật (Focus Ring Dày)")
        self._cb_focus_ring.setStyleSheet(self._checkbox_qss)
        self._cb_focus_ring.setChecked(acc.get("focus_ring_thick", False))
        self._cb_focus_ring.setAccessibleName("Bật viền nổi bật")
        vl.addWidget(self._cb_focus_ring)

    def _create_audio_combos(self, settings):'''
content = content.replace('        vl.addWidget(self._cb_close_br)\r\n\r\n    def _create_audio_combos(self, settings):', acc_options.replace('\n', '\r\n'))
content = content.replace('        vl.addWidget(self._cb_close_br)\n\n    def _create_audio_combos(self, settings):', acc_options)

# 5. Lưu settings
save_replace = '''        s["record_loopback_device"] = self._combo_lb.currentData()
        s["record_mic_device"]      = self._combo_mic.currentData()

        acc = backend.AppConfig.get("accessibility") or {}
        if hasattr(self, "_cb_tts"):
            acc["tts_enabled"] = self._cb_tts.isChecked()
            acc["announce_focus"] = self._cb_announce_focus.isChecked()
            acc["announce_state"] = self._cb_announce_state.isChecked()
            acc["voice_command_enabled"] = self._cb_voice_cmd.isChecked()
            acc["high_contrast"] = self._cb_high_contrast.isChecked()
            acc["focus_ring_thick"] = self._cb_focus_ring.isChecked()
            backend.AppConfig.update("accessibility", acc)

        backend.ConfigManager.save_settings(s)'''
content = content.replace('        s["record_loopback_device"] = self._combo_lb.currentData()\r\n        s["record_mic_device"]      = self._combo_mic.currentData()\r\n        backend.ConfigManager.save_settings(s)', save_replace.replace('\n', '\r\n'))
content = content.replace('        s["record_loopback_device"] = self._combo_lb.currentData()\n        s["record_mic_device"]      = self._combo_mic.currentData()\n        backend.ConfigManager.save_settings(s)', save_replace)

with codecs.open(file_path, "w", "utf-8") as f:
    f.write(content)
print("Updated settings_dialog.py")
