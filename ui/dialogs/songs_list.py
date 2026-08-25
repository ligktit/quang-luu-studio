import backend
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QWidget, QMessageBox, QLineEdit, QComboBox,
    QMenu, QInputDialog,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from ui.design_tokens import C, FONT, card_qss, scrollarea_qss, header_card_qss, footer_card_qss, combo_qss, input_field_qss
from ui.components.painter_button import PainterButton
from ui import responsive as rp
from ui.components.svg_icons import SVG_PLAY, SVG_EDIT, SVG_TRASH

_SAVE_KEYS = [
    "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
    "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm",
]


class SongsListDialog(QDialog):
    """Dialog danh sách bài hát đã lưu — tìm kiếm, yêu thích, playlist."""

    def __init__(self, parent):
        super().__init__(parent)
        self._dashboard = parent
        self._search_text = ""
        self._filter = ("all", None)   # ("all"|"fav"|"playlist", playlist_id)
        self.setWindowTitle("Danh sách bài hát")
        rp.apply_dialog_size(self, 880, 640, min_w=820, min_h=560)
        self.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")
        self._refresh_data()
        self._build_ui()
        self.adjustSize()

    # ── Data ──────────────────────────────────────────────────

    def _refresh_data(self):
        self._songs = backend.SongManager.load_songs()
        self._playlists = backend.PlaylistManager.load_playlists()

    # ── Build UI ──────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._build_header())
        outer.addWidget(self._build_filter_bar())
        outer.addWidget(self._build_scroll(), 1)
        outer.addWidget(self._build_footer())
        self._rebuild_list()

    def _build_header(self):
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

        # Premium entry points (gate ở dashboard; badge tooltip cho biết Premium).
        try:
            from core import entitlements
            _is_prem = entitlements.is_premium()
        except Exception:
            _is_prem = True
        prog_btn = PainterButton("📈 Tiến bộ", color=C["creative"], height=34, radius=12, font_size=12, fixed_width=104)
        prog_btn.setToolTip("Bảng tiến bộ luyện hát" + ("" if _is_prem else " — Premium"))
        prog_btn.clicked.connect(self._dashboard._show_progress_dialog)
        lay.addWidget(prog_btn)

        setlist_btn = PainterButton("🎤 Setlist", color=C["pink"], height=34, radius=12, font_size=12, fixed_width=100)
        setlist_btn.setToolTip("Live Setlist / Auto-Pilot" + ("" if _is_prem else " — Premium"))
        setlist_btn.clicked.connect(self._dashboard._show_setlist)
        lay.addWidget(setlist_btn)

        # Lấy tone của cả danh sách từ thư viện cộng đồng trong MỘT vòng mạng,
        # thay vì ngồi dò lại từng bài mất hàng chục giây mỗi bài.
        self._sync_btn = PainterButton(
            "☁ Đồng bộ tone", color=C["blue"], height=34, radius=12, font_size=12, fixed_width=126
        )
        self._sync_btn.setToolTip(
            "Lấy tone bài chưa có từ thư viện chung"
        )
        self._sync_btn.setAccessibleName("Đồng bộ tone từ cộng đồng")
        self._sync_btn.clicked.connect(self._on_sync_tones)
        lay.addWidget(self._sync_btn)

        self._count_lbl = QLabel("")
        self._count_lbl.setStyleSheet(f"font-size: 13px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
        lay.addWidget(self._count_lbl)
        return hdr

    def _on_sync_tones(self):
        """Tra thư viện cộng đồng cho các bài CHƯA có tone trong máy.

        Bài đã có tone (dò rồi hoặc sửa tay) thì không đụng tới: dữ liệu của
        chính khách luôn thắng dữ liệu của người lạ.
        """
        from core import tone_share
        from core.tone_cache import ManualToneTimeline, ToneCacheManager

        if not tone_share.enabled():
            self._dashboard._show_message(
                "Đồng bộ tone cộng đồng đang tắt. Bật lại trong Thiết lập › Công cụ.",
                is_error=True,
            )
            return

        pending = []
        for song in self._songs:
            url = song.get("url", "")
            if not url or not tone_share.song_key(url):
                continue  # bài local: không có mã video để đối chiếu
            if ManualToneTimeline.load_timeline(url):
                continue
            cached = ToneCacheManager.get_cached_tone(url)
            if cached and cached.get("key_timeline"):
                continue
            pending.append(song)

        if not pending:
            self._dashboard._show_message("Mọi bài trong danh sách đều đã có tone.")
            return

        self._sync_btn.setEnabled(False)
        self._sync_btn.setText("Đang lấy…")
        self._start_sync_worker(pending)

    def _start_sync_worker(self, pending):
        """Chạy tra cứu ở luồng nền — mất mạng thì timeout 10s, không treo UI."""
        from PySide6.QtCore import QThread, Signal

        urls = [song.get("url", "") for song in pending]

        class _SyncWorker(QThread):
            done = Signal(object)

            def run(self):
                try:
                    from core import tone_share
                    self.done.emit(tone_share.lookup_many(urls))
                except Exception as e:
                    print(f"[SYNC-TONE] lỗi: {e}")
                    self.done.emit({})

        worker = _SyncWorker(self)
        self._sync_worker = worker  # giữ tham chiếu: QThread bị GC giữa chừng là crash
        worker.done.connect(lambda found: self._on_sync_done(found, pending))
        worker.start()

    def _on_sync_done(self, found, pending):
        import backend

        self._sync_btn.setEnabled(True)
        self._sync_btn.setText("☁ Đồng bộ tone")

        applied = 0
        for song in pending:
            entry = found.get(song.get("url", ""))
            if not entry or not entry.get("key_timeline"):
                continue
            # tone_share đã ghi vào tone_cache; ở đây chỉ cập nhật cột tone hiển
            # thị trong danh sách bài hát.
            primary = entry.get("primary_key") or entry["key_timeline"][0].get("key_display", "")
            if song.get("id") and primary:
                backend.SongManager.update_song(song["id"], tone=primary)
                applied += 1

        if applied:
            self._refresh_data()
            self._rebuild_list()
            self._dashboard._show_message(
                f"Đã lấy tone cho {applied}/{len(pending)} bài"
            )
        else:
            self._dashboard._show_message(
                f"Chưa ai trong mạng lưới dò {len(pending)} bài này"
            )

    def _build_filter_bar(self):
        bar = QFrame()
        bar.setStyleSheet(f"background-color: {C['bg']}; border-bottom: 1px solid {C['border']};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Tìm theo tên bài hát...")
        self._search_input.setStyleSheet(input_field_qss())
        self._search_input.textChanged.connect(self._on_search)
        lay.addWidget(self._search_input, 1)

        self._playlist_combo = QComboBox()
        self._playlist_combo.setMinimumWidth(180)
        self._playlist_combo.setStyleSheet(combo_qss(color=C["primary"], font_size=12))
        self._populate_playlist_combo()
        self._playlist_combo.currentIndexChanged.connect(self._on_playlist_filter)
        lay.addWidget(self._playlist_combo)

        new_pl_btn = PainterButton("+ Playlist", color=C["teal"], height=34, radius=12, font_size=12, fixed_width=96)
        new_pl_btn.setToolTip("Tạo playlist mới")
        new_pl_btn.clicked.connect(self._create_playlist)
        lay.addWidget(new_pl_btn)

        self._rename_pl_btn = PainterButton("✎", color=C["card_hover"], height=34, radius=8, font_size=14, fixed_width=38)
        self._rename_pl_btn.setToolTip("Đổi tên playlist đang chọn")
        self._rename_pl_btn.clicked.connect(self._rename_playlist)
        lay.addWidget(self._rename_pl_btn)

        self._del_pl_btn = PainterButton("🗑", color=C["card_hover"], height=34, radius=8, font_size=13, fixed_width=38)
        self._del_pl_btn.setToolTip("Xóa playlist đang chọn")
        self._del_pl_btn.clicked.connect(self._delete_playlist)
        lay.addWidget(self._del_pl_btn)

        self._update_playlist_btns()
        return bar

    def _populate_playlist_combo(self, select=None):
        """Dựng lại combo playlist. select = ('all'|'fav'|'playlist', id) để chọn lại."""
        combo = self._playlist_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("🎵  Tất cả bài hát", ("all", None))
        combo.addItem("⭐  Yêu thích", ("fav", None))
        for p in self._playlists:
            combo.addItem(f"📂  {p.get('name', '')}", ("playlist", p.get("id")))
        # Chọn lại
        target = select or self._filter
        idx = 0
        for i in range(combo.count()):
            if combo.itemData(i) == target:
                idx = i
                break
        combo.setCurrentIndex(idx)
        self._filter = combo.itemData(idx)
        combo.blockSignals(False)

    def _update_playlist_btns(self):
        is_pl = self._filter[0] == "playlist"
        self._rename_pl_btn.setEnabled(is_pl)
        self._del_pl_btn.setEnabled(is_pl)

    def _build_scroll(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(scrollarea_qss(width=6))
        content = QWidget()
        content.setMinimumWidth(780)
        content.setStyleSheet(f"background-color: {C['bg']};")
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setSpacing(8)
        self._list_layout.setContentsMargins(16, 14, 16, 14)
        scroll.setWidget(content)
        return scroll

    # ── List rebuild ──────────────────────────────────────────

    def _filtered_songs(self):
        mode, pid = self._filter
        if mode == "playlist":
            pl = next((p for p in self._playlists if p.get("id") == pid), None)
            ids = pl.get("song_ids", []) if pl else []
            by_id = {s.get("id"): s for s in self._songs}
            songs = [by_id[i] for i in ids if i in by_id]   # giữ thứ tự playlist
        else:
            songs = backend.SongManager.sort_for_display(self._songs)
            if mode == "fav":
                songs = [s for s in songs if s.get("favorite")]
        if self._search_text:
            q = self._search_text.lower()
            songs = [s for s in songs if q in s.get("title", "").lower()]
        return songs

    def _clear_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _rebuild_list(self):
        self._clear_list()
        songs = self._filtered_songs()
        self._count_lbl.setText(f"{len(songs)} / {len(self._songs)} bài")
        if not songs:
            self._list_layout.addWidget(self._build_empty_state())
        else:
            for idx, song in enumerate(songs):
                self._list_layout.addWidget(self._build_song_card(idx, song))
        self._list_layout.addStretch()

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

        if self._search_text or self._filter[0] != "all":
            msg = "Không có bài hát phù hợp bộ lọc"
            hint = "Thử xóa tìm kiếm hoặc chọn 'Tất cả bài hát'"
        else:
            msg = "Chưa có bài hát nào được lưu"
            hint = "Nhấn nút 💾 để lưu bài hát từ YouTube"

        lbl = QLabel(msg)
        lbl.setStyleSheet(f"color: {C['text_muted']}; font-size: 15px; font-family: {FONT}; background: transparent; border: none;")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl)

        h = QLabel(hint)
        h.setStyleSheet(f"color: {C['text_muted']}; font-size: 12px; font-style: italic; font-family: {FONT}; background: transparent; border: none;")
        h.setAlignment(Qt.AlignCenter)
        lay.addWidget(h)
        return frame

    def _build_song_card(self, idx, song):
        card = QFrame()
        card.setStyleSheet(card_qss(radius=10, border_left=C["green"]))
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 10, 10)
        lay.setSpacing(8)

        num = QLabel(f"{idx + 1}")
        num.setFixedSize(22, 22)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 700; background: transparent; border: none;")
        lay.addWidget(num)

        is_fav = bool(song.get("favorite"))
        fav_btn = PainterButton("★" if is_fav else "☆",
                                color=C["orange"] if is_fav else C["card_hover"],
                                height=32, radius=8, font_size=15, fixed_width=34)
        fav_btn.setToolTip("Bỏ yêu thích" if is_fav else "Đánh dấu yêu thích")
        fav_btn.clicked.connect(self._make_toggle_fav(song.get("id")))
        lay.addWidget(fav_btn)

        info = QVBoxLayout()
        info.setSpacing(3)

        song_url = song.get("url", "")
        has_timeline = False
        tl_data = None
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
            tone_text += f"  |  {len(tl_data.get('timeline', []))} đoạn tone"
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

        more_btn = PainterButton("⋯", color=C["card_hover"], height=36, radius=8, font_size=18, fixed_width=40)
        more_btn.setToolTip("Tùy chọn")
        more_btn.clicked.connect(self._make_menu(song, more_btn))

        lay.addWidget(play_btn)
        lay.addWidget(more_btn)
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

    # ── Filter callbacks ──────────────────────────────────────

    def _on_search(self, text):
        self._search_text = text.strip()
        self._rebuild_list()

    def _on_playlist_filter(self, _idx):
        data = self._playlist_combo.currentData()
        if data:
            self._filter = data
        self._update_playlist_btns()
        self._rebuild_list()

    # ── Playlist management ───────────────────────────────────

    def _create_playlist(self):
        name, ok = QInputDialog.getText(self, "Tạo playlist", "Tên playlist:")
        if not ok:
            return
        pl = backend.PlaylistManager.create_playlist(name)
        if pl is None:
            self._dashboard._show_message("Tên playlist rỗng hoặc đã tồn tại", is_error=True)
            return
        self._refresh_data()
        self._populate_playlist_combo(select=("playlist", pl["id"]))
        self._filter = ("playlist", pl["id"])
        self._update_playlist_btns()
        self._rebuild_list()

    def _rename_playlist(self):
        if self._filter[0] != "playlist":
            return
        pid = self._filter[1]
        pl = next((p for p in self._playlists if p.get("id") == pid), None)
        if not pl:
            return
        name, ok = QInputDialog.getText(self, "Đổi tên playlist", "Tên mới:", text=pl.get("name", ""))
        if not ok:
            return
        if not backend.PlaylistManager.rename_playlist(pid, name):
            self._dashboard._show_message("Tên rỗng hoặc trùng playlist khác", is_error=True)
            return
        self._refresh_data()
        self._populate_playlist_combo(select=("playlist", pid))
        self._rebuild_list()

    def _delete_playlist(self):
        if self._filter[0] != "playlist":
            return
        pid = self._filter[1]
        pl = next((p for p in self._playlists if p.get("id") == pid), None)
        if not pl:
            return
        reply = QMessageBox.question(
            self, "Xác nhận",
            f"Xóa playlist '{pl.get('name', '')}'?\n(Các bài hát KHÔNG bị xóa.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        backend.PlaylistManager.delete_playlist(pid)
        self._refresh_data()
        self._filter = ("all", None)
        self._populate_playlist_combo(select=("all", None))
        self._update_playlist_btns()
        self._rebuild_list()

    # ── Song callbacks ────────────────────────────────────────

    def _make_toggle_fav(self, song_id):
        def _toggle():
            backend.SongManager.toggle_favorite(song_id)
            self._refresh_data()
            self._rebuild_list()
        return _toggle

    def _make_play(self, song):
        def _play():
            url   = song.get("url")
            tone  = song.get("tone", "C")
            title = song.get("title", "")
            if not url:
                return
            tl_data   = backend.ManualToneTimeline.load_timeline(url)
            manual_tl = tl_data["timeline"] if tl_data and tl_data.get("timeline") else None
            dash = self._dashboard
            # Nạp timeline cho phần hiển thị (ô "kế tiếp" + đếm ngược ở header).
            dash._set_tone_timeline(manual_tl or [], song.get("duration", 0) or 0)
            play_cb = dash._load_embedded_video if dash._embedded_player_active() else None
            if play_cb is not None:
                dash._embedded_current_url = url
            dash.engine.open_youtube_url(
                url,
                on_video_end_callback=lambda res: None,
                on_tone_detected=lambda result: dash._tone_result_signal.emit(result),
                manual_timeline=manual_tl,
                play_callback=play_cb,
            )
            from PySide6.QtCore import QSignalBlocker
            with QSignalBlocker(self._dashboard.tone_combo):
                self._dashboard.tone_combo.setCurrentText(tone)
            # Smart Recall (Premium): khôi phục preset đã lưu (tự gate, im lặng nếu Standard).
            if hasattr(self._dashboard, "_apply_song_preset"):
                self._dashboard._apply_song_preset(song)
            if self._dashboard._waveform is not None and title:
                self._dashboard._waveform.set_song_info(title, tone, "Major", 0)
            if title:
                self._dashboard._marquee_text = f"🎵 {title}   ★   {tone}"
            self.close()
        return _play

    def _make_menu(self, song, anchor_btn):
        def _open_menu():
            menu = QMenu(self)
            menu.setStyleSheet(f"""
                QMenu {{ background-color: {C['card']}; color: {C['text']};
                         border: 1px solid {C['border']}; font-family: {FONT}; font-size: 13px; }}
                QMenu::item {{ padding: 7px 22px; }}
                QMenu::item:selected {{ background-color: {C['primary']}; color: #ffffff; }}
                QMenu::separator {{ height: 1px; background: {C['border']}; margin: 4px 8px; }}
            """)

            act_info = QAction("✏️  Sửa thông tin", menu)
            act_info.triggered.connect(lambda: self._edit_info(song))
            menu.addAction(act_info)

            act_tone = QAction("🎚️  Sửa chuỗi tone", menu)
            act_tone.triggered.connect(lambda: self._edit_tone(song))
            menu.addAction(act_tone)

            act_preset = QAction("🎚️  Lưu preset hiện tại vào bài", menu)
            act_preset.triggered.connect(lambda: self._save_preset_for(song))
            menu.addAction(act_preset)

            # Submenu playlist
            pl_menu = menu.addMenu("📂  Playlist")
            containing = backend.PlaylistManager.playlists_containing(song.get("id"))
            if self._playlists:
                for p in self._playlists:
                    a = QAction(p.get("name", ""), pl_menu)
                    a.setCheckable(True)
                    a.setChecked(p.get("id") in containing)
                    a.triggered.connect(self._make_toggle_playlist(p.get("id"), song.get("id")))
                    pl_menu.addAction(a)
                pl_menu.addSeparator()
            new_a = QAction("➕  Playlist mới…", pl_menu)
            new_a.triggered.connect(lambda: self._add_to_new_playlist(song.get("id")))
            pl_menu.addAction(new_a)

            menu.addSeparator()
            act_del = QAction("🗑️  Xóa bài hát", menu)
            act_del.triggered.connect(lambda: self._delete_song(song.get("id")))
            menu.addAction(act_del)

            menu.exec(anchor_btn.mapToGlobal(anchor_btn.rect().bottomLeft()))
        return _open_menu

    def _save_preset_for(self, song):
        """Smart Recall (Premium): lưu trạng thái UI hiện tại làm preset của bài."""
        dash = self._dashboard
        if not dash._require_premium("smart_recall", "Smart Recall"):
            return
        preset = dash._capture_current_preset()
        if backend.SongManager.save_preset(song.get("id"), preset):
            dash._show_message("Đã lưu thiết lập cho bài hát")
            self._refresh_data()
            self._rebuild_list()
        else:
            dash._show_message("Không lưu được thiết lập", is_error=True)

    def _make_toggle_playlist(self, playlist_id, song_id):
        def _toggle(checked=False):
            containing = backend.PlaylistManager.playlists_containing(song_id)
            if playlist_id in containing:
                backend.PlaylistManager.remove_song_from_playlist(playlist_id, song_id)
            else:
                backend.PlaylistManager.add_song_to_playlist(playlist_id, song_id)
            self._refresh_data()
            self._rebuild_list()
        return _toggle

    def _add_to_new_playlist(self, song_id):
        name, ok = QInputDialog.getText(self, "Tạo playlist", "Tên playlist:")
        if not ok:
            return
        pl = backend.PlaylistManager.create_playlist(name)
        if pl is None:
            self._dashboard._show_message("Tên playlist rỗng hoặc đã tồn tại", is_error=True)
            return
        backend.PlaylistManager.add_song_to_playlist(pl["id"], song_id)
        self._refresh_data()
        self._populate_playlist_combo(select=self._filter)
        self._rebuild_list()

    def _delete_song(self, song_id):
        reply = QMessageBox.question(
            self, "Xác nhận", "Bạn có chắc chắn muốn xóa bài hát này?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            backend.SongManager.delete_song(song_id)
            self._refresh_data()
            self._rebuild_list()

    def _edit_tone(self, song):
        from ui.dialogs.edit_song import EditSongDialog
        self.close()
        EditSongDialog(self._dashboard, song).exec()

    # ── Edit basic info ───────────────────────────────────────

    def _edit_info(self, song):
        dlg = QDialog(self)
        dlg.setWindowTitle("✏️ Sửa thông tin bài hát")
        rp.apply_dialog_size(dlg, 520, 320, fixed=True, max_scale=1.25)
        dlg.setStyleSheet(f"background-color: {C['bg']}; color: {C['text']};")

        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(8)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet(f"font-size: 12px; color: {C['text_muted']}; font-family: {FONT}; background: transparent; border: none;")
            return l

        outer.addWidget(_lbl("Tên bài hát"))
        title_input = QLineEdit(song.get("title", ""))
        title_input.setStyleSheet(input_field_qss())
        outer.addWidget(title_input)

        outer.addWidget(_lbl("Tone"))
        tone_combo = QComboBox()
        tone_combo.addItems(_SAVE_KEYS)
        cur_tone = song.get("tone", "C")
        if cur_tone in _SAVE_KEYS:
            tone_combo.setCurrentText(cur_tone)
        tone_combo.setStyleSheet(combo_qss(color=C["green"], font_size=13))
        outer.addWidget(tone_combo)

        outer.addWidget(_lbl("URL YouTube"))
        url_input = QLineEdit(song.get("url", ""))
        url_input.setStyleSheet(input_field_qss())
        outer.addWidget(url_input)

        outer.addStretch()

        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)
        save_btn = PainterButton("Lưu thay đổi", color=C["green"], height=40, radius=16, font_size=14)
        cancel_btn = PainterButton("Hủy", color=C["card_hover"], height=40, radius=16, font_size=14, fixed_width=90)

        def _do_save():
            new_title = title_input.text().strip()
            new_url = url_input.text().strip()
            if not new_title:
                self._dashboard._show_message("Tên bài hát không được để trống", is_error=True)
                return
            backend.SongManager.update_song(
                song.get("id"),
                title=new_title,
                url=new_url,
                tone=tone_combo.currentText(),
            )
            dlg.accept()
            self._dashboard._show_message("Đã cập nhật thông tin bài hát")
            self._refresh_data()
            self._rebuild_list()

        save_btn.clicked.connect(_do_save)
        cancel_btn.clicked.connect(dlg.reject)
        btn_box.addWidget(save_btn, 1)
        btn_box.addWidget(cancel_btn)
        outer.addLayout(btn_box)

        dlg.exec()
