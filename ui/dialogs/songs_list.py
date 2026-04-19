import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QWidget, QMessageBox,
)
from PySide6.QtCore import Qt

from ui.design_tokens import C, FONT, card_qss, scrollarea_qss, header_card_qss, footer_card_qss
from ui.components.painter_button import PainterButton
from ui.components.svg_icons import SVG_PLAY, SVG_EDIT, SVG_TRASH
from frontend_qt import add_shadow


class SongsListDialog(QDialog):
    """Dialog danh sách bài hát đã lưu."""

    def __init__(self, parent):
        super().__init__(parent)
        self._dashboard = parent
        self.setWindowTitle("Danh sách bài hát")
        self.setMinimumHeight(520)
        self.setMinimumWidth(780)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._build_ui()
        self.adjustSize()

    def _build_ui(self):
        songs = backend.SongManager.load_songs()
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._build_header(len(songs)))
        outer.addWidget(self._build_scroll(songs), 1)
        outer.addWidget(self._build_footer())

    def _build_header(self, count):
        hdr = QFrame()
        hdr.setStyleSheet(header_card_qss())
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(20, 14, 20, 12)

        title = QLabel("🎵  Danh sách bài hát")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {C['green']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        lay.addWidget(title)
        lay.addStretch()

        count_lbl = QLabel(f"{count} bài")
        count_lbl.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        lay.addWidget(count_lbl)
        return hdr

    def _build_scroll(self, songs):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollarea_qss(width=6))
        content = QWidget()
        content.setMinimumWidth(740)
        content.setStyleSheet(f"background-color: {C['bg']};")
        lay = QVBoxLayout(content)
        lay.setSpacing(8)
        lay.setContentsMargins(16, 14, 16, 14)

        if not songs:
            lay.addWidget(self._build_empty_state())
        else:
            for idx, song in enumerate(songs):
                lay.addWidget(self._build_song_card(idx, song))

        lay.addStretch()
        scroll.setWidget(content)
        return scroll

    def _build_empty_state(self):
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(30,41,59,120);
                border-radius: 14px;
                border: 1px dashed {C['border']};
            }}
        """)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(30, 30, 30, 30)

        icon = QLabel("🎵")
        icon.setStyleSheet("font-size: 36px; background: transparent; border: none;")
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        lbl = QLabel("Chưa có bài hát nào được lưu")
        lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 15px; font-family: {FONT}; background: transparent; border: none;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        hint = QLabel("Nhấn nút 💾 để lưu bài hát từ YouTube")
        hint.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; font-style: italic; font-family: {FONT}; background: transparent; border: none;")
        hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(hint)
        return frame

    def _build_song_card(self, idx, song):
        card = QFrame()
        card.setStyleSheet(card_qss(radius=10, border_left=C["green"]))
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 10, 10)
        lay.setSpacing(10)

        num = QLabel(f"{idx + 1}")
        num.setFixedSize(24, 24)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; background: transparent; border: none;")
        lay.addWidget(num)

        info = QVBoxLayout()
        info.setSpacing(3)

        song_url = song.get("url", "")
        has_timeline = False
        if song_url:
            tl_data = backend.ManualToneTimeline.load_timeline(song_url)
            has_timeline = tl_data is not None and bool(tl_data.get("timeline"))

        s_title = song.get("title", "Không có tên")
        if has_timeline:
            s_title += "  ♫"

        t_lbl = QLabel(s_title)
        t_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; font-family: {FONT}; border: none; background: transparent; color: {C['text']};")
        info.addWidget(t_lbl)

        tone_text = f"Tone: {song.get('tone', 'N/A')}"
        if has_timeline:
            tl_entries = tl_data.get("timeline", [])
            tone_text += f"  |  {len(tl_entries)} đoạn tone"
        date_str = song.get("date_added", "")
        if date_str:
            tone_text += f"  |  {date_str}"
        d_lbl = QLabel(tone_text)
        d_lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT}; border: none; background: transparent;")
        info.addWidget(d_lbl)
        lay.addLayout(info, 1)

        play_btn = PainterButton("", color=C["green"], height=36, radius=8,
                                  svg_content=SVG_PLAY, svg_size=16, fixed_width=40)
        play_btn.setToolTip("Phát")
        play_btn.clicked.connect(self._make_play(song))

        edit_btn = PainterButton("", color=C["primary"], height=36, radius=8,
                                  svg_content=SVG_EDIT, svg_size=16, fixed_width=40)
        edit_btn.setToolTip("Chỉnh sửa chuỗi tone")
        edit_btn.clicked.connect(self._make_edit(song))

        del_btn = PainterButton("", color=C["accent"], height=36, radius=8,
                                 svg_content=SVG_TRASH, svg_size=16, fixed_width=40)
        del_btn.setToolTip("Xóa")
        del_btn.clicked.connect(self._make_del(song.get("id")))

        lay.addWidget(play_btn)
        lay.addWidget(edit_btn)
        lay.addWidget(del_btn)
        return card

    def _build_footer(self):
        footer = QFrame()
        footer.setStyleSheet(footer_card_qss())
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(16, 10, 16, 10)
        close_btn = PainterButton("×  Đóng", color=C["card_hover"], height=38, radius=14, font_size=13)
        close_btn.clicked.connect(self.close)
        lay.addStretch()
        lay.addWidget(close_btn)
        return footer

    # ── Callbacks ─────────────────────────────────────────────

    def _make_play(self, song):
        def _play():
            url   = song.get("url")
            tone  = song.get("tone", "C")
            title = song.get("title", "")
            if not url:
                return
            tl_data   = backend.ManualToneTimeline.load_timeline(url)
            manual_tl = tl_data["timeline"] if tl_data and tl_data.get("timeline") else None
            self._dashboard.engine.open_youtube_url(
                url,
                on_video_end_callback=lambda res: None,
                on_tone_detected=lambda result: self._dashboard._tone_result_signal.emit(result),
                manual_timeline=manual_tl,
            )
            from PySide6.QtCore import QSignalBlocker
            with QSignalBlocker(self._dashboard.tone_combo):
                self._dashboard.tone_combo.setCurrentText(tone)
            if self._dashboard._waveform is not None and title:
                self._dashboard._waveform.set_song_info(title, tone, "Major", 0)
            if title:
                self._dashboard._marquee_text = f"🎵 {title}   ★   {tone}"
            self.close()
        return _play

    def _make_del(self, song_id):
        def _del():
            reply = QMessageBox.question(
                self, "Xác nhận", "Bạn có chắc chắn muốn xóa bài hát này?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                backend.SongManager.delete_song(song_id)
                self.close()
                SongsListDialog(self._dashboard).exec()
        return _del

    def _make_edit(self, song):
        def _edit():
            from ui.dialogs.edit_song import EditSongDialog
            self.close()
            EditSongDialog(self._dashboard, song).exec()
        return _edit
