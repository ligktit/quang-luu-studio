import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QWidget, QLineEdit, QComboBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer

from ui.design_tokens import C, FONT, card_qss, scrollarea_qss, combo_qss, header_card_qss, footer_card_qss, input_field_qss
from ui.components.painter_button import PainterButton
from ui.components.svg_icons import SVG_CLOSE
from frontend_qt import add_shadow

_ALL_KEYS = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
    "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm",
]
_CHROMATIC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


class EditSongDialog(QDialog):
    """Dialog chỉnh sửa chuỗi tone/timeline cho một bài hát."""

    def __init__(self, parent, song: dict):
        super().__init__(parent)
        self._dashboard = parent
        self._song = song
        self._song_url   = song.get("url", "")
        self._song_title = song.get("title", "Không có tên")
        self._song_id    = song.get("id")

        tl_data = backend.ManualToneTimeline.load_timeline(self._song_url) if self._song_url else None
        existing = tl_data["timeline"] if (tl_data and tl_data.get("timeline")) else []
        if not existing:
            existing = [{"time": 0.0, "key_display": song.get("tone", "C"), "key_index": 0, "scale": "Major"}]
        self._initial_entries = existing

        self.setWindowTitle(f"Chỉnh sửa: {self._song_title[:40]}")
        self.setMinimumSize(640, 580)
        self.resize(660, 680)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._entry_widgets = []   # list of (time_input, key_combo, row_frame)
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._build_header())
        body_widget, self._scroll, self._entries_layout = self._build_body()
        outer.addWidget(body_widget, 1)
        outer.addWidget(self._build_footer())

        for entry in self._initial_entries:
            self._add_entry_row(entry.get("time", 0.0), entry.get("key_display", "C"))

    def _build_header(self):
        hdr = QFrame()
        hdr.setStyleSheet(header_card_qss())
        lay = QVBoxLayout(hdr)
        lay.setContentsMargins(20, 14, 20, 12)
        lay.setSpacing(4)

        title = QLabel("Chỉnh sửa chuỗi tone")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {C['primary']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)

        sub = QLabel(f"♫  {self._song_title[:55]}")
        sub.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)
        return hdr

    def _build_body(self):
        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 10)
        body.setSpacing(8)
        body.addWidget(self._build_preview())
        body.addWidget(self._build_col_headers())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollarea_qss(width=5))
        entries_container = QWidget()
        entries_container.setStyleSheet(f"background-color: {C['bg']};")
        entries_layout = QVBoxLayout(entries_container)
        entries_layout.setSpacing(6)
        entries_layout.setContentsMargins(0, 4, 0, 4)
        entries_layout.addStretch()
        scroll.setWidget(entries_container)
        body.addWidget(scroll, 1)

        add_btn = PainterButton("+ Thêm mốc", color=C["teal"], height=34, radius=14, font_size=12)
        add_btn.clicked.connect(self._on_add_entry)
        body.addWidget(add_btn)

        wrapper = QWidget()
        wrapper.setStyleSheet(f"background: {C['bg']}; border: none;")
        wrapper.setLayout(body)
        return wrapper, scroll, entries_layout

    def _build_preview(self):
        """Khung xem trước chuỗi chuyển tone, cập nhật trực tiếp khi sửa."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(34,197,94,0.08);
                border-radius: 8px; border: 1px solid {C['border']};
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(8)

        tag = QLabel("Xem trước")
        tag.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {C['green']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        lay.addWidget(tag)

        self._preview_label = QLabel("")
        self._preview_label.setWordWrap(True)
        self._preview_label.setStyleSheet(
            f"font-size: 13px; color: {C['text']}; font-family: {FONT};"
            f" background: transparent; border: none;"
        )
        lay.addWidget(self._preview_label, 1)
        return frame

    def _update_preview(self):
        """Dựng lại chuỗi tone từ trạng thái các dòng hiện tại (đã sort theo thời gian)."""
        if not hasattr(self, "_preview_label"):
            return
        items = []
        for time_input, key_combo, _ in self._entry_widgets:
            secs = backend.ManualToneTimeline.parse_time_str(time_input.text().strip())
            label = backend.ManualToneTimeline.seconds_to_time_str(secs) if secs is not None else "??:??"
            items.append((secs if secs is not None else float("inf"), label, key_combo.currentText()))
        items.sort(key=lambda x: x[0])
        chain = "  →  ".join(f"{lbl} {key}" for _, lbl, key in items)
        self._preview_label.setText(chain or "—")

    def _build_col_headers(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(56,189,248,12), stop:1 rgba(56,189,248,0));
                border-radius: 6px; border: none;
            }}
        """)
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(14, 6, 10, 6)

        for text, width, color in [
            ("#",  28, C["text_muted"]),
            ("Thời gian (MM:SS)", 110, C["teal"]),
            ("Key / Scale", 0, C["teal"]),
            ("Xóa", 40, C["text_muted"]),
        ]:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size: 11px; font-weight: bold; color: {color};"
                f" font-family: {FONT}; background: transparent; border: none;"
            )
            if text == "Key / Scale":
                lay.addWidget(lbl, 1)
            else:
                if width:
                    lbl.setFixedWidth(width)
                if text == "Xóa":
                    lbl.setAlignment(Qt.AlignCenter)
                lay.addWidget(lbl)
        return frame

    def _build_footer(self):
        footer = QFrame()
        footer.setStyleSheet(footer_card_qss())
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        save_btn = PainterButton("Lưu thay đổi", color=C["green"],      height=40, radius=18, font_size=14)
        cancel_btn = PainterButton("Hủy",         color=C["card_hover"], height=40, radius=18, font_size=14)
        save_btn.clicked.connect(self._on_save)
        cancel_btn.clicked.connect(self.close)

        lay.addWidget(save_btn, 1)
        lay.addWidget(cancel_btn)
        return footer

    # ── Entry rows ────────────────────────────────────────────

    _time_input_qss = input_field_qss()
    _time_error_qss = f"""
        QLineEdit {{
            background-color: {C['bg']}; color: {C['accent']};
            border: 2px solid {C['accent']}; border-radius: 6px;
            padding: 6px 8px; font-size: 14px; font-weight: bold; font-family: {FONT};
        }}
    """
    _key_combo_qss = combo_qss(color=C["green"], font_size=14)

    def _add_entry_row(self, time_val=0.0, key_display="C"):
        # Insert before the trailing stretch
        stretch_idx = self._entries_layout.count() - 1

        row = QFrame()
        row.setStyleSheet(f"""
            QFrame {{
                background-color: {C['card']};
                border-radius: 8px;
                border: 1px solid {C['border']};
            }}
        """)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(8)

        num_badge = QLabel(f"{len(self._entry_widgets) + 1}")
        num_badge.setObjectName("num_badge")
        num_badge.setFixedSize(24, 24)
        num_badge.setAlignment(Qt.AlignCenter)
        num_badge.setStyleSheet(f"""
            background-color: rgba(56,189,248,0.15); border-radius: 12px;
            color: {C['teal']}; font-size: 11px; font-weight: 700;
            font-family: {FONT}; border: none;
        """)
        lay.addWidget(num_badge)

        time_input = QLineEdit(backend.ManualToneTimeline.seconds_to_time_str(time_val))
        time_input.setFixedWidth(90)
        time_input.setPlaceholderText("MM:SS")
        time_input.setStyleSheet(self._time_input_qss)
        time_input.textChanged.connect(self._update_preview)
        lay.addWidget(time_input)

        key_combo = QComboBox()
        key_combo.addItems(_ALL_KEYS)
        if key_display in _ALL_KEYS:
            key_combo.setCurrentText(key_display)
        key_combo.setStyleSheet(self._key_combo_qss)
        key_combo.currentTextChanged.connect(self._update_preview)
        lay.addWidget(key_combo, 1)

        rm_btn = PainterButton("", color=C["accent"], height=32, radius=6,
                                svg_content=SVG_CLOSE, svg_size=14, fixed_width=32)
        rm_btn.setToolTip("Xóa mốc này")
        rm_btn.clicked.connect(lambda: self._remove_row(row))
        lay.addWidget(rm_btn)

        self._entries_layout.insertWidget(stretch_idx, row)
        self._entry_widgets.append((time_input, key_combo, row))
        self._update_preview()

    def _remove_row(self, row):
        if len(self._entry_widgets) <= 1:
            QMessageBox.warning(self, "Cảnh báo", "Phải có ít nhất 1 entry!")
            return
        for i, (_, _, rf) in enumerate(self._entry_widgets):
            if rf is row:
                self._entry_widgets.pop(i)
                break
        row.setParent(None)
        row.deleteLater()
        self._refresh_numbering()
        self._update_preview()

    def _refresh_numbering(self):
        for i, (_, _, rf) in enumerate(self._entry_widgets):
            badge = rf.findChild(QLabel, "num_badge")
            if badge:
                badge.setText(str(i + 1))

    def _on_add_entry(self):
        last_time = 0
        last_key  = "C"
        if self._entry_widgets:
            last_input, last_kc, _ = self._entry_widgets[-1]
            parsed = backend.ManualToneTimeline.parse_time_str(last_input.text())
            if parsed is not None:
                last_time = parsed
            last_key = last_kc.currentText()
        self._add_entry_row(last_time + 30, last_key)
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    # ── Save ──────────────────────────────────────────────────

    def _on_save(self):
        entries = []
        has_error = False
        seen_times = {}          # time_seconds → time_input đầu tiên dùng mốc đó
        dup_inputs = []          # các ô có thời gian trùng

        for time_input, key_combo, _ in self._entry_widgets:
            time_seconds = backend.ManualToneTimeline.parse_time_str(time_input.text().strip())
            if time_seconds is None:
                time_input.setStyleSheet(self._time_error_qss)
                has_error = True
                continue

            # Phát hiện mốc thời gian trùng nhau
            if time_seconds in seen_times:
                dup_inputs.append(time_input)
                if seen_times[time_seconds] is not None:
                    dup_inputs.append(seen_times[time_seconds])
                    seen_times[time_seconds] = None  # đã đánh dấu, tránh thêm lần 2
            else:
                seen_times[time_seconds] = time_input
                time_input.setStyleSheet(self._time_input_qss)

            key_display = key_combo.currentText()
            is_minor    = key_display.endswith("m")
            key_root    = key_display[:-1] if is_minor else key_display
            try:
                key_index = _CHROMATIC.index(key_root)
            except ValueError:
                key_index = 0

            entries.append({
                "time":        float(time_seconds),
                "key_display": key_display,
                "key_index":   key_index,
                "scale":       "Minor" if is_minor else "Major",
            })

        if has_error:
            self._dashboard._show_message("⚠️ Vui lòng sửa thời gian không hợp lệ (MM:SS)", is_error=True)
            return
        if dup_inputs:
            for inp in dup_inputs:
                inp.setStyleSheet(self._time_error_qss)
            self._dashboard._show_message("⚠️ Có 2 mốc trùng thời gian — mỗi mốc cần thời gian khác nhau", is_error=True)
            return
        if not entries:
            self._dashboard._show_message("⚠️ Cần ít nhất 1 entry!", is_error=True)
            return

        entries.sort(key=lambda x: x["time"])

        # Cảnh báo nếu chuỗi tone không bắt đầu từ 0:00 (cho phép tiếp tục)
        if entries[0]["time"] != 0:
            reply = QMessageBox.question(
                self, "Mốc đầu khác 0:00",
                "Mốc tone đầu tiên không bắt đầu từ 0:00.\n"
                "Đoạn đầu bài hát sẽ không có tone nào áp dụng.\n\nVẫn tiếp tục lưu?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        if not self._song_url:
            self._dashboard._show_message("⚠️ Bài hát không có URL!", is_error=True)
            return

        if backend.ManualToneTimeline.save_timeline(self._song_url, self._song_title, entries):
            first_key = entries[0]["key_display"]
            if self._song_id:
                backend.SongManager.update_song(self._song_id, tone=first_key)
            self._dashboard._show_message(f"✅ Đã lưu {len(entries)} mốc thời gian!")
            self.close()
            from ui.dialogs.songs_list import SongsListDialog
            SongsListDialog(self._dashboard).exec()
        else:
            self._dashboard._show_message("❌ Lỗi khi lưu timeline!", is_error=True)
