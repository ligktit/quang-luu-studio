"""
ui.dialogs.setlist_dialog — Live Setlist / Auto-Pilot (Phase 5, Premium)

Dialog chọn 1 playlist làm "setlist" cho buổi live:
  * Combo chọn playlist (lấy từ PlaylistManager.load_playlists()).
  * Bảng hàng đợi: bài hiện tại (highlight) + các bài kế tiếp; hiện tone đã
    prefetch nếu có trong cache.
  * "Bắt đầu Auto-Pilot": phát bài đầu, tự prefetch tone bài kế trong nền.
  * "Bài kế": chuyển sang bài kế (áp preset + mở URL do integrator xử lý).

TÁCH RỜI frontend: dialog KHÔNG gọi trực tiếp frontend. Mọi hành động "phát bài"
đi qua callback ``on_play(song_dict)`` truyền vào constructor; integrator nối
callback này vào luồng mở URL + áp preset (xem docs/integration/phase5_setlist.md).

Việc tạo SetlistController + prefetch được integrator cấp qua ``make_controller``
(thường = engine.make_setlist). Nếu không cấp, dialog vẫn chạy ở chế độ thuần UI
(không prefetch) — fail-soft.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QWidget, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from ui.design_tokens import (
    C, FONT, card_qss, scrollarea_qss, header_card_qss, footer_card_qss, combo_qss,
)
from ui.components.painter_button import PainterButton

from core.songs import PlaylistManager, SongManager
from core.engine._setlist import tone_already_cached, _song_url


class SetlistDialog(QDialog):
    """Hàng đợi bài cho buổi live + Auto-Pilot.

    parent: dashboard/frontend (chỉ dùng làm parent Qt).
    on_play: callable(song_dict) — integrator nối vào mở URL + áp preset.
    make_controller: callable(songs)->SetlistController (vd engine.make_setlist).
                     None → chế độ UI thuần (không prefetch).
    """

    # Phát kèm cho integrator nếu muốn lắng nghe thay vì on_play.
    play_requested = Signal(dict)

    def __init__(self, parent, on_play=None, make_controller=None):
        super().__init__(parent)
        self._on_play = on_play
        self._make_controller = make_controller
        self._controller = None

        self.setWindowTitle("Live Setlist / Auto-Pilot")
        self.setMinimumHeight(560)
        self.setMinimumWidth(720)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        self._playlists = PlaylistManager.load_playlists()
        self._songs_by_id = {s.get("id"): s for s in SongManager.load_songs()}
        self._queue = []          # list[dict] bài trong playlist đang chọn
        self._build_ui()
        self._reload_queue()

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._build_header())
        outer.addWidget(self._build_selector_bar())
        outer.addWidget(self._build_scroll(), 1)
        outer.addWidget(self._build_footer())

    def _build_header(self):
        hdr = QFrame()
        hdr.setStyleSheet(header_card_qss())
        lay = QHBoxLayout(hdr)
        lay.setContentsMargins(20, 14, 20, 12)
        title = QLabel("🎬  Live Setlist / Auto-Pilot")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {C['primary']};"
            f" font-family: {FONT}; background: transparent; border: none;"
        )
        lay.addWidget(title)
        lay.addStretch()
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT};"
            f" background: transparent; border: none;"
        )
        lay.addWidget(self._status_lbl)
        return hdr

    def _build_selector_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background-color: {C['bg']}; border-bottom: 1px solid {C['border']};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        lbl = QLabel("Playlist:")
        lbl.setStyleSheet(f"color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        lay.addWidget(lbl)

        self._playlist_combo = QComboBox()
        self._playlist_combo.setMinimumWidth(260)
        self._playlist_combo.setStyleSheet(combo_qss(color=C["primary"], font_size=12))
        if not self._playlists:
            self._playlist_combo.addItem("(Chưa có playlist nào)", None)
        else:
            for p in self._playlists:
                n = len(p.get("song_ids", []))
                self._playlist_combo.addItem(f"📂  {p.get('name', '')}  ({n} bài)", p.get("id"))
        self._playlist_combo.currentIndexChanged.connect(lambda _i: self._reload_queue())
        lay.addWidget(self._playlist_combo)
        lay.addStretch()
        return bar

    def _build_scroll(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollarea_qss(width=6))
        content = QWidget()
        content.setStyleSheet(f"background-color: {C['bg']};")
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setSpacing(8)
        self._list_layout.setContentsMargins(16, 14, 16, 14)
        scroll.setWidget(content)
        return scroll

    def _build_footer(self):
        footer = QFrame()
        footer.setStyleSheet(footer_card_qss())
        lay = QHBoxLayout(footer)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        self._start_btn = PainterButton("▶  Bắt đầu Auto-Pilot", color=C["green"], height=40, radius=14, font_size=13)
        self._start_btn.clicked.connect(self._on_start)
        lay.addWidget(self._start_btn)

        self._next_btn = PainterButton("⏭  Bài kế", color=C["primary"], height=40, radius=14, font_size=13)
        self._next_btn.setToolTip("Chuyển sang bài kế tiếp")
        self._next_btn.clicked.connect(self._on_next)
        self._next_btn.setEnabled(False)
        lay.addWidget(self._next_btn)

        lay.addStretch()
        close_btn = PainterButton("×  Đóng", color=C["card_hover"], height=40, radius=14, font_size=13)
        close_btn.clicked.connect(self.close)
        lay.addWidget(close_btn)
        return footer

    # ── Queue / list ─────────────────────────────────────────────────────────

    def _selected_playlist(self):
        pid = self._playlist_combo.currentData()
        return next((p for p in self._playlists if p.get("id") == pid), None)

    def _reload_queue(self):
        pl = self._selected_playlist()
        ids = pl.get("song_ids", []) if pl else []
        self._queue = [self._songs_by_id[i] for i in ids if i in self._songs_by_id]
        self._controller = None
        self._next_btn.setEnabled(False)
        self._start_btn.setEnabled(bool(self._queue))
        self._status_lbl.setText(f"{len(self._queue)} bài" if self._queue else "Hàng đợi trống")
        self._rebuild_list(current_index=-1)

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _rebuild_list(self, current_index=-1):
        self._clear_list()
        if not self._queue:
            self._list_layout.addWidget(self._build_empty_state())
            self._list_layout.addStretch()
            return
        for idx, song in enumerate(self._queue):
            self._list_layout.addWidget(
                self._build_song_card(idx, song, is_current=(idx == current_index))
            )
        self._list_layout.addStretch()

    def _build_empty_state(self):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background-color: rgba(30,41,59,120); border-radius: 14px;"
            f" border: 1px dashed {C['border']}; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(30, 30, 30, 30)
        msg = QLabel("Playlist trống — thêm bài vào playlist ở 'Danh sách bài hát'")
        msg.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 14px; font-family: {FONT};"
            f" background: transparent; border: none;"
        )
        msg.setAlignment(Qt.AlignCenter)
        msg.setWordWrap(True)
        lay.addWidget(msg)
        return frame

    def _build_song_card(self, idx, song, is_current=False):
        border = C["green"] if is_current else C["border"]
        card = QFrame()
        card.setStyleSheet(card_qss(radius=10, border_left=border))
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(8)

        num = QLabel("▶" if is_current else f"{idx + 1}")
        num.setFixedSize(24, 24)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet(
            f"color: {C['green'] if is_current else '#64748b'}; font-size: 12px;"
            f" font-weight: 700; background: transparent; border: none;"
        )
        lay.addWidget(num)

        info = QVBoxLayout()
        info.setSpacing(3)
        title = song.get("title", "Không có tên")
        if is_current:
            title = f"{title}   ◀ ĐANG PHÁT"
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(
            f"font-size: 14px; font-weight: bold; font-family: {FONT}; border: none;"
            f" background: transparent; color: {C['green'] if is_current else C['text']};"
        )
        info.addWidget(t_lbl)

        # Hiện tone đã lưu của bài + cờ "đã prefetch" nếu cache có sẵn.
        tone_text = f"Tone: {song.get('tone', 'N/A')}"
        url = _song_url(song)
        if url and tone_already_cached(url):
            tone_text += "   •  ✓ tone đã sẵn"
        d_lbl = QLabel(tone_text)
        d_lbl.setStyleSheet(
            f"color: {C['text_muted']}; font-size: 12px; font-family: {FONT};"
            f" border: none; background: transparent;"
        )
        info.addWidget(d_lbl)
        lay.addLayout(info, 1)
        return card

    # ── Auto-Pilot actions ───────────────────────────────────────────────────

    def _ensure_controller(self):
        if self._controller is not None:
            return self._controller
        if self._make_controller is not None:
            try:
                self._controller = self._make_controller(self._queue)
            except Exception:
                self._controller = None
        return self._controller

    def _on_start(self):
        if not self._queue:
            return
        ctrl = self._ensure_controller()
        if ctrl is not None:
            song = ctrl.advance()
        else:
            # Chế độ UI thuần: phát bài đầu, theo dõi index nội bộ.
            self._plain_index = 0
            song = self._queue[0]
        if not song:
            return
        self._play(song)
        self._after_advance(song)

    def _on_next(self):
        ctrl = self._controller
        if ctrl is not None:
            song = ctrl.advance()
        else:
            nxt = getattr(self, "_plain_index", -1) + 1
            song = self._queue[nxt] if 0 <= nxt < len(self._queue) else None
            self._plain_index = nxt
        if not song:
            self._status_lbl.setText("✓ Đã hết setlist")
            self._next_btn.setEnabled(False)
            return
        self._play(song)
        self._after_advance(song)

    def _current_index(self):
        if self._controller is not None:
            return self._controller.index
        return getattr(self, "_plain_index", -1)

    def _after_advance(self, song):
        cur = self._current_index()
        self._rebuild_list(current_index=cur)
        has_next = cur + 1 < len(self._queue)
        self._next_btn.setEnabled(has_next)
        self._status_lbl.setText(f"Bài {cur + 1}/{len(self._queue)}")
        # Prefetch tone bài kế trong nền.
        ctrl = self._controller
        if ctrl is not None:
            detect_fn = getattr(ctrl, "_engine_detect_fn", None)
            if detect_fn is not None:
                try:
                    ctrl.prefetch_next(detect_fn, on_done=self._on_prefetch_done)
                except Exception:
                    pass

    def _on_prefetch_done(self, url, was_cached):
        # Refresh list để hiện cờ "✓ tone đã sẵn" (Qt: chỉ chạm UI nếu cùng thread;
        # an toàn nhất là không động UI ở đây — cờ sẽ hiện ở lần rebuild kế).
        pass

    def _play(self, song):
        self.play_requested.emit(song)
        if self._on_play is not None:
            try:
                self._on_play(song)
            except Exception:
                pass
