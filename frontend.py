import customtkinter as ctk
import os
import tkinter.filedialog as filedialog
import tkinter as tk
from tkinter import Canvas
import backend

# --- CẤU HÌNH GIAO DIỆN ---
ctk.set_default_color_theme("blue")
ctk.set_appearance_mode("Dark")

# Bảng màu chuẩn — khớp ui.html (Social Star Karaoke Studio)
COLORS = {
    "bg_main": "#1a1f36",       # App background
    "bg_card": "#242b42",       # Card background
    "bg_card_hover": "#353b50", # Card hover/track
    "primary": "#6366F1",       # Indigo 500
    "primary_hover": "#4F46E5", # Indigo 600
    "teal": "#0abde3",          # Teal — Volume, Lấy Tone, Tone Nhạc, Đa Thể Loại
    "orange": "#ff9f43",        # Orange — Dò Tone, Bolero, Mic slider
    "pink": "#ff6b6b",          # Pink — Tone Auto, Remix
    "deep_purple": "#5f27cd",   # Deep Purple — Fix Méo
    "accent": "#ff4b5c",        # Red accent — Tune, Effects, Tone Giọng, Dân Ca
    "light_purple": "#a55eea",  # Light Purple — Chấm điểm, Social Audio, Lofi
    "blue": "#54a0ff",          # Blue — Pop
    "success": "#10B981",       # Emerald 500
    "success_hover": "#059669", # Emerald 600
    "danger": "#EF4444",        # Rose 500
    "danger_hover": "#DC2626",  # Rose 600
    "warning": "#F59E0B",       # Amber 500
    "warning_hover": "#D97706", # Amber 600
    "text_main": "#F8FAFC",     # Slate 50
    "text_muted": "#94A3B8",    # Slate 400
    "border": "#334155"         # Slate 700
}

# --- MIDI CC MAPPING ---
MIDI_CC = {
    # Sliders - Tone
    "tone_music": 10,      # Tone Nhạc
    "tone_voice": 11,      # Tone Giọng
    
    # Sliders - Mixer
    "mix_music": 20,       # Nhạc
    "mix_mic": 21,         # Mic
    "mix_reverb": 22,      # Vang
    "mix_backing": 23,     # Bè
    
    # Buttons - Tone Functions
    "do_tone": 30,         # Dò Tone
    "lay_tone": 31,        # Lấy Tone
    "tone_auto": 32,       # Tone Auto
    
    # Buttons - Mixer Functions
    "be": 40,              # Bè
    "vang": 41,            # Vang
    "nhac": 42,            # Nhạc
    "fix_meo": 43,         # Fix Méo
    
    # Buttons - Mixer Mute (Toggle Mở/Tắt từng kênh)
    "mute_music": 50,      # Mute Nhạc (0=Unmute, 127=Mute)
    "mute_mic": 51,        # Mute Mic
    "mute_reverb": 52,     # Mute Vang
    "mute_backing": 53,    # Mute Bè
    
    # Auto-Tune Control (gửi đến Studio One)
    "auto_tune_key": 34,       # Key gốc (0-127) -> Auto-Tune
    "auto_tune_scale": 35,     # Scale type (0=Major, 127=Minor) -> Auto-Tune
    "tune_on_off": 36,         # Tune On/Off bypass (0=Off, 127=On)
}

# HOTKEY MAPPING đã được thay thế bằng MIDI CC mapping
# Chỉ giữ lại record nếu cần thiết

# --- GRADIENT COLORS ---
def hex_to_rgb(hex_color):
    """Chuyển đổi hex color sang RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def rgb_to_hex(rgb):
    """Chuyển đổi RGB sang hex color"""
    return '#%02x%02x%02x' % rgb

def interpolate_color(color1, color2, factor):
    """Tạo màu trung gian giữa 2 màu"""
    rgb1 = hex_to_rgb(color1)
    rgb2 = hex_to_rgb(color2)
    r = int(rgb1[0] + (rgb2[0] - rgb1[0]) * factor)
    g = int(rgb1[1] + (rgb2[1] - rgb1[1]) * factor)
    b = int(rgb1[2] + (rgb2[2] - rgb1[2]) * factor)
    return rgb_to_hex((r, g, b))

class ScoringDialog(ctk.CTkToplevel):
    """Dialog hiển thị kết quả chấm điểm"""
    def __init__(self, parent, score_result, animated=True):
        super().__init__(parent)
        
        self.title("🎤 Kết quả chấm điểm")
        self.geometry("500x700")
        self.attributes("-topmost", True)
        self.transient(parent)
        
        # Container chính
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Tiêu đề
        ctk.CTkLabel(
            main_frame,
            text="🎤 KẾT QUẢ CHẤM ĐIỂM",
            font=("Inter", 24, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=(10, 20))
        
        # Điểm tổng
        score_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        score_frame.pack(pady=10)
        
        total_score = score_result.get("total_score", 0)
        score_color = self._get_score_color(total_score)
        
        ctk.CTkLabel(
            score_frame,
            text="ĐIỂM TỔNG",
            font=("Inter", 14),
            text_color=COLORS["text_muted"]
        ).pack()
        
        self.score_label = ctk.CTkLabel(
            score_frame,
            text="0.0" if animated else f"{total_score:.1f}",
            font=("Inter", 48, "bold"),
            text_color=score_color
        )
        self.score_label.pack(pady=5)
        
        # Chi tiết các chỉ số
        details_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        details_frame.pack(fill="both", expand=True, pady=10)
        
        metrics = [
            ("Độ chính xác Pitch", "pitch_accuracy", COLORS["primary"]),
            ("Độ ổn định Pitch", "pitch_stability", COLORS["primary_hover"]),
            ("Độ nhất quán Âm lượng", "volume_consistency", COLORS["success"]),
            ("Độ chính xác Nhịp điệu", "timing_accuracy", COLORS["warning"])
        ]
        
        self.metric_bars = []
        for label, key, color in metrics:
            bar = self._create_metric_row(details_frame, label, score_result.get(key, 0), color, animated=animated)
            if bar:
                self.metric_bars.append((bar, score_result.get(key, 0)))
        
        # Thông tin bổ sung
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(fill="x", pady=10)
        
        info_text = f"""
Pitch trung bình: {score_result.get('pitch_mean', 0):.2f} Hz
Độ lệch chuẩn: {score_result.get('pitch_std', 0):.2f} Hz
Thời lượng: {score_result.get('duration', 0):.2f} giây
        """
        
        ctk.CTkLabel(
            info_frame,
            text=info_text.strip(),
            font=("Inter", 11),
            justify="left"
        ).pack(pady=10, padx=10)
        
        # Feedback + Gợi ý cải thiện
        feedback_frame = ctk.CTkFrame(main_frame)
        feedback_frame.pack(fill="x", pady=10)
        
        # Parse feedback (có thể là dict hoặc string)
        feedback_data = score_result.get("feedback", "")
        if isinstance(feedback_data, dict):
            main_feedback = feedback_data.get("main", "")
            tips = feedback_data.get("tips", [])
        else:
            main_feedback = str(feedback_data)
            tips = []
        
        # Main feedback
        ctk.CTkLabel(
            feedback_frame,
            text=main_feedback,
            font=("Inter", 15, "bold"),
            text_color=score_color,
            wraplength=450
        ).pack(pady=(15, 5), padx=15)
        
        # Tips - gợi ý cải thiện
        if tips:
            ctk.CTkLabel(
                feedback_frame,
                text="💡 Gợi ý cải thiện:",
                font=("Inter", 12, "bold"),
                text_color=COLORS["text_muted"],
                anchor="w"
            ).pack(anchor="w", padx=15, pady=(8, 2))
            
            for tip in tips:
                ctk.CTkLabel(
                    feedback_frame,
                    text=tip,
                    font=("Inter", 11),
                    text_color=COLORS["text_main"],
                    wraplength=430,
                    anchor="w",
                    justify="left"
                ).pack(anchor="w", padx=20, pady=2)
        
        # Padding bottom
        ctk.CTkFrame(feedback_frame, fg_color="transparent", height=10).pack()
        
        # Nút đóng
        ctk.CTkButton(
            main_frame,
            text="Đóng",
            command=self.destroy,
            width=150,
            height=40,
            font=("Inter", 14, "bold")
        ).pack(pady=20)
        
        # Bắt đầu animation count-up
        if animated:
            self._animate_score(total_score, score_color)
    
    def _animate_score(self, target_score, color, step=0):
        """Animation đếm điểm từ 0 đến target"""
        total_steps = 30  # 30 frames ~ 1.5s
        if step <= total_steps:
            t = step / total_steps
            eased = 1 - (1 - t) ** 3  # ease-out cubic
            current = eased * target_score
            self.score_label.configure(text=f"{current:.1f}")
            
            for bar, val in self.metric_bars:
                bar.set(eased * val / 100)
            
            self.after(50, lambda: self._animate_score(target_score, color, step + 1))
        else:
            self.score_label.configure(text=f"{target_score:.1f}")
            for bar, val in self.metric_bars:
                bar.set(val / 100)
    
    def _create_metric_row(self, parent, label, value, color, animated=False):
        """Tạo hàng hiển thị metric với thanh progress"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        
        label_frame = ctk.CTkFrame(row, fg_color="transparent")
        label_frame.pack(fill="x")
        
        ctk.CTkLabel(
            label_frame,
            text=label,
            font=("Inter", 12),
            anchor="w"
        ).pack(side="left")
        
        ctk.CTkLabel(
            label_frame,
            text=f"{value:.1f}%",
            font=("Inter", 12, "bold"),
            text_color=color,
            anchor="e"
        ).pack(side="right")
        
        bar = ctk.CTkProgressBar(row, progress_color=color, height=8)
        bar.pack(fill="x", pady=(2, 0))
        bar.set(0 if animated else value / 100)
        
        return bar
    
    def _get_score_color(self, score):
        """Lấy màu dựa trên điểm số"""
        if score >= 90:
            return COLORS["success"]
        elif score >= 80:
            return COLORS["success_hover"]
        elif score >= 70:
            return COLORS["warning"]
        elif score >= 60:
            return COLORS["warning_hover"]
        else:
            return COLORS["danger"]

class ManualToneDialog(ctk.CTkToplevel):
    """Dialog nhập timeline tone thủ công cho bài hát YouTube"""
    def __init__(self, parent, engine, on_tone_detected_callback=None, edit_url=None):
        super().__init__(parent)
        self.parent_app = parent
        self.engine = engine
        self.on_tone_detected_callback = on_tone_detected_callback
        self.entry_rows = []  # List of (time_entry, tone_option, row_frame)
        
        self.title("🎵 Dò Tone Thủ Công")
        self.geometry("700x650")
        self.attributes("-topmost", True)
        self.transient(parent)
        
        # Container chính
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Tiêu đề
        ctk.CTkLabel(
            main_frame,
            text="🎵 Dò Tone Thủ Công",
            font=("Inter", 22, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(5, 10))
        
        ctk.CTkLabel(
            main_frame,
            text="Nhập thời gian và tone tương ứng. Khi video YouTube phát đến thời điểm đó,\nchương trình sẽ tự động gửi tone cho Auto-Tune.",
            font=("Inter", 12),
            text_color=COLORS["text_muted"],
            justify="center"
        ).pack(pady=(0, 10))
        
        # --- URL + Tên bài ---
        info_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        info_frame.pack(fill="x", pady=5)
        
        # URL
        url_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        url_row.pack(fill="x", pady=3)
        ctk.CTkLabel(url_row, text="YouTube URL:", font=("Inter", 13, "bold"), width=110, anchor="w").pack(side="left")
        self.url_entry = ctk.CTkEntry(url_row, placeholder_text="https://www.youtube.com/watch?v=...")
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # Tên bài hát
        title_row = ctk.CTkFrame(info_frame, fg_color="transparent")
        title_row.pack(fill="x", pady=3)
        ctk.CTkLabel(title_row, text="Tên bài hát:", font=("Inter", 13, "bold"), width=110, anchor="w").pack(side="left")
        self.title_entry = ctk.CTkEntry(title_row, placeholder_text="Nhập tên bài hát")
        self.title_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # --- Header bảng timeline ---
        table_header = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_card"], corner_radius=8)
        table_header.pack(fill="x", pady=(10, 0))
        ctk.CTkLabel(table_header, text="Thời gian (MM:SS)", font=("Inter", 12, "bold"), width=160, anchor="w").pack(side="left", padx=15, pady=8)
        ctk.CTkLabel(table_header, text="Tone", font=("Inter", 12, "bold"), width=140, anchor="w").pack(side="left", padx=10)
        ctk.CTkLabel(table_header, text="", width=50).pack(side="left")
        
        # --- Scrollable frame cho danh sách entries ---
        self.entries_frame = ctk.CTkScrollableFrame(main_frame, height=250)
        self.entries_frame.pack(fill="both", expand=True, pady=(0, 5))
        
        # Nút thêm dòng
        add_btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        add_btn_frame.pack(fill="x", pady=5)
        
        ctk.CTkButton(
            add_btn_frame,
            text="➕ Thêm dòng",
            width=120,
            height=30,
            font=("Inter", 13),
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            command=self._add_entry_row
        ).pack(side="left")
        
        # --- Nút hành động ---
        action_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_frame.pack(fill="x", pady=(10, 5))
        
        ctk.CTkButton(
            action_frame,
            text="💾 Lưu Timeline",
            width=130,
            height=36,
            font=("Inter", 13, "bold"),
            fg_color=COLORS["success"],
            hover_color=COLORS["success_hover"],
            command=self._save_timeline
        ).pack(side="left", padx=3)
        
        ctk.CTkButton(
            action_frame,
            text="▶️ Phát & Gửi Tone",
            width=150,
            height=36,
            font=("Inter", 13, "bold"),
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            command=self._play_and_send
        ).pack(side="left", padx=3)
        
        ctk.CTkButton(
            action_frame,
            text="📋 Danh sách đã lưu",
            width=150,
            height=36,
            font=("Inter", 13, "bold"),
            fg_color=COLORS["bg_card_hover"],
            hover_color=COLORS["border"],
            command=self._show_saved_list
        ).pack(side="left", padx=3)
        
        ctk.CTkButton(
            action_frame,
            text="Đóng",
            width=80,
            height=36,
            font=("Inter", 13),
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self.destroy
        ).pack(side="right", padx=3)
        
        # Label thông báo
        self.message_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=("Inter", 12),
            text_color=COLORS["success"]
        )
        self.message_label.pack(pady=3)
        
        # Thêm 3 dòng mặc định
        for _ in range(3):
            self._add_entry_row()
        
        # Load timeline nếu edit_url được truyền vào
        if edit_url:
            self._load_existing_timeline(edit_url)
    
    def _add_entry_row(self, time_str="", key_display="C"):
        """Thêm 1 dòng nhập time-tone"""
        row_frame = ctk.CTkFrame(self.entries_frame, fg_color="transparent")
        row_frame.pack(fill="x", pady=2)
        
        # Time entry
        time_entry = ctk.CTkEntry(
            row_frame,
            placeholder_text="0:00",
            width=160,
            height=32,
            font=("Inter", 13)
        )
        time_entry.pack(side="left", padx=(15, 10))
        if time_str:
            time_entry.insert(0, time_str)
        
        # Tone dropdown
        music_keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B",
                     "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm"]
        tone_option = ctk.CTkOptionMenu(
            row_frame,
            values=music_keys,
            width=140,
            height=32,
            font=("Inter", 13)
        )
        tone_option.pack(side="left", padx=10)
        tone_option.set(key_display)
        
        # Nút xóa
        def remove_row():
            row_frame.destroy()
            self.entry_rows = [(t, k, f) for t, k, f in self.entry_rows if f != row_frame]
        
        ctk.CTkButton(
            row_frame,
            text="❌",
            width=40,
            height=32,
            font=("Segoe UI Emoji", 14),
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=remove_row
        ).pack(side="left", padx=5)
        
        self.entry_rows.append((time_entry, tone_option, row_frame))
    
    def _get_entries(self):
        """Thu thập tất cả entries hợp lệ"""
        entries = []
        for time_entry, tone_option, row_frame in self.entry_rows:
            if not row_frame.winfo_exists():
                continue
            time_str = time_entry.get().strip()
            if not time_str:
                continue
            time_seconds = backend.ManualToneTimeline.parse_time_str(time_str)
            if time_seconds is None:
                continue
            entries.append({
                "time": time_seconds,
                "key_display": tone_option.get()
            })
        return entries
    
    def _show_message(self, text, color="#22C55E"):
        """Hiện thông báo"""
        self.message_label.configure(text=text, text_color=color)
        self.after(4000, lambda: self.message_label.configure(text=""))
    
    def _save_timeline(self):
        """Lưu timeline"""
        url = self.url_entry.get().strip()
        title = self.title_entry.get().strip()
        
        if not url:
            self._show_message("⚠️ Vui lòng nhập YouTube URL!", "#EF4444")
            return
        if "youtube.com" not in url and "youtu.be" not in url:
            self._show_message("⚠️ URL không hợp lệ. Vui lòng nhập URL YouTube.", "#EF4444")
            return
        if not title:
            self._show_message("⚠️ Vui lòng nhập tên bài hát!", "#EF4444")
            return
        
        entries = self._get_entries()
        if not entries:
            self._show_message("⚠️ Vui lòng nhập ít nhất 1 cặp thời gian-tone hợp lệ!", "#EF4444")
            return
        
        success = backend.ManualToneTimeline.save_timeline(url, title, entries)
        if success:
            self._show_message(f"✅ Đã lưu timeline: {title} ({len(entries)} entries)")
        else:
            self._show_message("❌ Lỗi khi lưu timeline!", "#EF4444")
    
    def _play_and_send(self):
        """Mở YouTube + bắt đầu replay manual timeline"""
        url = self.url_entry.get().strip()
        if not url:
            self._show_message("⚠️ Vui lòng nhập YouTube URL!", "#EF4444")
            return
        
        entries = self._get_entries()
        if not entries:
            self._show_message("⚠️ Vui lòng nhập ít nhất 1 cặp thời gian-tone!", "#EF4444")
            return
        
        # Parse entries thành format đầy đủ cho engine
        parsed = []
        for entry in entries:
            key_info = backend.ManualToneTimeline.parse_key_display(entry["key_display"])
            if key_info:
                parsed.append({
                    "time": entry["time"],
                    "key_display": key_info["key_display"],
                    "key_index": key_info["key_index"],
                    "scale": key_info["scale"]
                })
        parsed.sort(key=lambda x: x["time"])
        
        if not parsed:
            self._show_message("⚠️ Không có entry hợp lệ!", "#EF4444")
            return
        
        # Callback cập nhật UI tone selector
        def on_tone_detected(result):
            if result and hasattr(self.parent_app, 'tone_option'):
                try:
                    key_display = result.get('key_display', 'C')
                    self.parent_app.after(0, lambda: [
                        self.parent_app.tone_option.set(key_display),
                        setattr(self.parent_app, 'current_tone', key_display),
                        self.parent_app.on_tone_selected(key_display)
                    ])
                except:
                    pass
        
        def on_video_end(score_result):
            if score_result:
                self.parent_app.current_score = score_result.get("total_score", 0)
                self.parent_app.update_score_display(self.parent_app.current_score)
                ScoringDialog(self.parent_app, score_result)
        
        # Mở YouTube + replay manual timeline
        self.engine.open_youtube_url(
            url,
            on_video_end_callback=on_video_end,
            on_tone_detected=on_tone_detected,
            manual_timeline=parsed
        )
        
        self._show_message(f"▶️ Đang phát... ({len(parsed)} tone changes)")
    
    def _load_existing_timeline(self, url):
        """Load timeline đã lưu vào form"""
        self.url_entry.delete(0, "end")
        self.url_entry.insert(0, url)
        
        timeline_data = backend.ManualToneTimeline.load_timeline(url)
        if timeline_data:
            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, timeline_data.get("title", ""))
            
            # Xóa entries cũ
            for _, _, row_frame in self.entry_rows:
                if row_frame.winfo_exists():
                    row_frame.destroy()
            self.entry_rows.clear()
            
            # Thêm entries từ timeline
            for entry in timeline_data.get("timeline", []):
                time_str = backend.ManualToneTimeline.seconds_to_time_str(entry["time"])
                self._add_entry_row(time_str=time_str, key_display=entry.get("key_display", "C"))
    
    def _show_saved_list(self):
        """Hiển thị danh sách timeline đã lưu"""
        all_timelines = backend.ManualToneTimeline.load_all()
        
        list_dialog = ctk.CTkToplevel(self)
        list_dialog.title("📋 Danh sách Timeline đã lưu")
        list_dialog.geometry("650x450")
        list_dialog.attributes("-topmost", True)
        list_dialog.transient(self)
        
        ctk.CTkLabel(
            list_dialog,
            text="📋 Timeline đã lưu",
            font=("Inter", 20, "bold"),
            text_color="#6366F1"
        ).pack(pady=15)
        
        scroll_frame = ctk.CTkScrollableFrame(list_dialog)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=5)
        
        if not all_timelines:
            ctk.CTkLabel(
                scroll_frame,
                text="Chưa có timeline nào được lưu",
                font=("Inter", 14),
                text_color="#94A3B8"
            ).pack(pady=50)
        else:
            for video_id, data in all_timelines.items():
                self._create_timeline_row(scroll_frame, data, list_dialog)
        
        ctk.CTkButton(
            list_dialog,
            text="Đóng",
            width=100,
            command=list_dialog.destroy
        ).pack(pady=10)
    
    def _create_timeline_row(self, parent, data, list_dialog):
        """Tạo 1 hàng trong danh sách timeline"""
        row = ctk.CTkFrame(parent)
        row.pack(fill="x", pady=4)
        
        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        
        # Tên bài
        ctk.CTkLabel(
            info,
            text=data.get("title", "Không tên"),
            font=("Inter", 14, "bold")
        ).pack(anchor="w")
        
        # Chi tiết timeline
        timeline = data.get("timeline", [])
        tones_preview = " → ".join(
            f"{backend.ManualToneTimeline.seconds_to_time_str(e['time'])}:{e['key_display']}"
            for e in timeline[:5]
        )
        if len(timeline) > 5:
            tones_preview += f" ... (+{len(timeline)-5})"
        
        ctk.CTkLabel(
            info,
            text=f"{len(timeline)} entries | {tones_preview}",
            font=("Inter", 11),
            text_color="#94A3B8",
            wraplength=400
        ).pack(anchor="w", pady=(2, 0))
        
        # Buttons
        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="right", padx=10, pady=8)
        
        url = data.get("url", "")
        
        # Nút chỉnh sửa
        def edit_tl():
            list_dialog.destroy()
            self._load_existing_timeline(url)
        
        ctk.CTkButton(
            btn_frame, text="✏️", width=40, height=32,
            font=("Segoe UI Emoji", 14),
            fg_color="#3B82F6", hover_color="#2563EB",
            command=edit_tl
        ).pack(side="left", padx=2)
        
        # Nút phát
        def play_tl():
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, url)
            self.title_entry.delete(0, "end")
            self.title_entry.insert(0, data.get("title", ""))
            
            # Xóa + load entries
            for _, _, rf in self.entry_rows:
                if rf.winfo_exists():
                    rf.destroy()
            self.entry_rows.clear()
            for entry in timeline:
                time_str = backend.ManualToneTimeline.seconds_to_time_str(entry["time"])
                self._add_entry_row(time_str=time_str, key_display=entry.get("key_display", "C"))
            
            list_dialog.destroy()
            self._play_and_send()
        
        ctk.CTkButton(
            btn_frame, text="▶️", width=40, height=32,
            font=("Segoe UI Emoji", 14),
            fg_color="#22C55E", hover_color="#16A34A",
            command=play_tl
        ).pack(side="left", padx=2)
        
        # Nút xóa
        def delete_tl():
            backend.ManualToneTimeline.delete_timeline(url)
            list_dialog.destroy()
            self._show_saved_list()
        
        ctk.CTkButton(
            btn_frame, text="🗑️", width=40, height=32,
            font=("Segoe UI Emoji", 14),
            fg_color="#EF4444", hover_color="#DC2626",
            command=delete_tl
        ).pack(side="left", padx=2)


class ColorButton(ctk.CTkButton):
    """Button đơn sắc với hiệu ứng hover và press"""
    def __init__(self, master, color=None, **kwargs):
        # Màu mặc định
        if color is None:
            color = COLORS["success"]  # Green
        
        self.base_color = color
        
        # Tạo màu hover (sáng hơn 20%)
        self.hover_color = interpolate_color(color, "#FFFFFF", 0.2)
        # Tạo màu press (tối hơn 20%)
        self.press_color = interpolate_color(color, "#000000", 0.2)
        
        # Lấy fg_color từ kwargs hoặc dùng màu base
        if "fg_color" not in kwargs:
            kwargs["fg_color"] = color
        if "hover_color" not in kwargs:
            kwargs["hover_color"] = self.hover_color
        
        super().__init__(master, **kwargs)
        
        # Bind events để tạo hiệu ứng
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.bind("<Button-1>", self.on_press)
        self.bind("<ButtonRelease-1>", self.on_release)
    
    def on_enter(self, event):
        """Hiệu ứng khi hover - sáng hơn"""
        self.configure(fg_color=self.hover_color)
    
    def on_leave(self, event):
        """Hiệu ứng khi rời chuột"""
        self.configure(fg_color=self.base_color)
    
    def on_press(self, event):
        """Hiệu ứng khi nhấn - tối hơn"""
        self.configure(fg_color=self.press_color)
    
    def on_release(self, event):
        """Hiệu ứng khi thả"""
        self.configure(fg_color=self.hover_color)


class ActivationDialog(ctk.CTk):
    """Dialog nhập activation code"""
    def __init__(self, callback=None, is_expired=False):
        super().__init__()
        self.callback = callback
        self.is_expired = is_expired
        self.activated = False
        
        self.title("🔐 Kích hoạt ứng dụng")
        self.geometry("500x400")
        self.attributes("-topmost", True)
        self.resizable(False, False)
        
        # Container chính
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Tiêu đề
        title_text = "⏰ License đã hết hạn" if is_expired else "🔐 Kích hoạt ứng dụng"
        title_color = COLORS["danger"] if is_expired else COLORS["success"]
        
        ctk.CTkLabel(
            main_frame,
            text=title_text,
            font=("Inter", 24, "bold"),
            text_color=title_color
        ).pack(pady=(0, 10))
        
        # Thông báo
        if is_expired:
            days_remaining = backend.ActivationManager.get_days_remaining()
            info_text = (
                "License của bạn đã hết hạn.\n"
                "Vui lòng nhập mã kích hoạt mới để tiếp tục sử dụng.\n"
                "💡 Lưu ý: Cấu hình và dữ liệu của bạn sẽ được giữ nguyên."
            )
        else:
            info_text = "Chào mừng đến với Quang Lưu Studio!\nVui lòng nhập mã kích hoạt để sử dụng ứng dụng."
        
        ctk.CTkLabel(
            main_frame,
            text=info_text,
            font=("Inter", 13),
            text_color=COLORS["text_muted"],
            justify="center",
            wraplength=400
        ).pack(pady=(0, 20))
        
        # Frame nhập code
        code_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        code_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            code_frame,
            text="Mã kích hoạt:",
            font=("Inter", 14, "bold")
        ).pack(anchor="w", pady=(0, 5))
        
        self.code_entry = ctk.CTkEntry(
            code_frame,
            placeholder_text="Nhập mã kích hoạt (ví dụ: AB12-CD34-EF56-GH78-IJ90)",
            width=440,
            height=40,
            font=("Inter", 14)
        )
        self.code_entry.pack(fill="x", pady=(0, 10))
        self.code_entry.focus()
        
        # Label thông báo lỗi/thành công
        self.message_label = ctk.CTkLabel(
            code_frame,
            text="",
            font=("Inter", 12),
            text_color=COLORS["danger"],
            wraplength=400
        )
        self.message_label.pack(pady=(0, 10))
        
        # Thông tin license (nếu đã kích hoạt trước đó)
        if is_expired:
            activation = backend.ActivationManager.load_activation()
            if activation:
                info_frame = ctk.CTkFrame(main_frame)
                info_frame.pack(fill="x", pady=10)
                
                ctk.CTkLabel(
                    info_frame,
                    text="📋 Thông tin license cũ:",
                    font=("Inter", 12, "bold"),
                    text_color=COLORS["text_muted"]
                ).pack(anchor="w", padx=15, pady=(10, 5))
                
                ctk.CTkLabel(
                    info_frame,
                    text=f"Ngày kích hoạt: {activation.get('activation_date', 'N/A')}",
                    font=("Inter", 11),
                    text_color=COLORS["text_muted"]
                ).pack(anchor="w", padx=15, pady=2)
        
        # Nút kích hoạt
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=20)
        
        ColorButton(
            button_frame,
            text="✅ Kích hoạt",
            width=150,
            height=40,
            color=COLORS["success"],
            font=("Inter", 14, "bold"),
            command=self.activate
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            button_frame,
            text="❌ Thoát",
            width=150,
            height=40,
            font=("Inter", 14, "bold"),
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self.quit_app
        ).pack(side="left", padx=5)
        
        # Bind Enter key
        self.code_entry.bind("<Return>", lambda e: self.activate())
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
    
    def activate(self):
        """Xử lý kích hoạt"""
        code = self.code_entry.get().strip()
        
        if not code:
            self.message_label.configure(
                text="⚠️ Vui lòng nhập mã kích hoạt!",
                text_color=COLORS["danger"]
            )
            return
        
        # Validate và kích hoạt
        success, message = backend.ActivationManager.activate(code)
        
        if success:
            self.message_label.configure(
                text=f"✅ {message}",
                text_color=COLORS["success"]
            )
            self.activated = True
            
            # Đợi 1.5 giây rồi đóng và gọi callback
            self.after(1500, self.close_and_continue)
        else:
            self.message_label.configure(
                text=f"❌ {message}",
                text_color=COLORS["danger"]
            )
            # Xóa code entry để nhập lại
            self.code_entry.delete(0, "end")
            self.code_entry.focus()
    
    def close_and_continue(self):
        """Đóng dialog và tiếp tục"""
        self.destroy()
        if self.callback:
            self.callback()
    
    def quit_app(self):
        """Thoát ứng dụng"""
        self.destroy()
        import sys
        sys.exit(0)


class SetupView(ctk.CTk):
    """Màn hình cấu hình ban đầu"""
    def __init__(self, callback=None):
        super().__init__()
        self.callback = callback
        
        # Load settings hiện có nếu có
        existing_settings = backend.ConfigManager.load()
        
        self.title("Quang Lưu Studio - Cấu hình")
        self.geometry("600x400")
        self.attributes("-topmost", True)
        
        # Container chính
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(fill="both", expand=True, padx=30, pady=30)
        
        # Tiêu đề
        ctk.CTkLabel(
            main_frame, 
            text="⚙️ Cấu hình ban đầu", 
            font=("Inter", 24, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=(0, 30))
        
        # Đường dẫn Studio One
        s1_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        s1_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(s1_frame, text="Đường dẫn Studio One (.exe hoặc .song):", font=("Inter", 14)).pack(anchor="w", pady=(0, 5))
        s1_path_frame = ctk.CTkFrame(s1_frame, fg_color="transparent")
        s1_path_frame.pack(fill="x")
        
        self.s1_entry = ctk.CTkEntry(s1_path_frame, placeholder_text="Chọn file .exe hoặc .song")
        self.s1_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # Load giá trị hiện có nếu có
        if existing_settings and existing_settings.get("studio_one_path"):
            self.s1_entry.insert(0, existing_settings["studio_one_path"])
        
        ColorButton(
            s1_path_frame, 
            text="📂", 
            width=50,
            color=COLORS["primary"],  # Indigo
            command=self.browse_studio_one
        ).pack(side="right")
        
        # Đường dẫn Browser
        web_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        web_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(web_frame, text="Đường dẫn Browser:", font=("Inter", 14)).pack(anchor="w", pady=(0, 5))
        web_path_frame = ctk.CTkFrame(web_frame, fg_color="transparent")
        web_path_frame.pack(fill="x")
        
        self.web_entry = ctk.CTkEntry(web_path_frame, placeholder_text="Chọn file .exe của browser")
        self.web_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        # Load giá trị hiện có nếu có
        if existing_settings and existing_settings.get("browser_path"):
            self.web_entry.insert(0, existing_settings["browser_path"])
        
        ColorButton(
            web_path_frame, 
            text="📂", 
            width=50,
            color=COLORS["primary"],  # Indigo
            command=self.browse_browser
        ).pack(side="right")
        
        # Checkbox tự động mở Studio One
        auto_launch_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        auto_launch_frame.pack(fill="x", pady=10)
        
        # Load giá trị auto_launch hiện có
        auto_launch_value = False
        if existing_settings and "auto_launch_studio_one" in existing_settings:
            auto_launch_value = existing_settings["auto_launch_studio_one"]
        
        self.auto_launch_var = ctk.BooleanVar(value=auto_launch_value)
        auto_launch_checkbox = ctk.CTkCheckBox(
            auto_launch_frame,
            text="🚀 Tự động mở Studio One khi khởi động ứng dụng",
            variable=self.auto_launch_var,
            font=("Inter", 13)
        )
        auto_launch_checkbox.pack(anchor="w")
        
        # Nút lưu
        ColorButton(
            main_frame,
            text="💾 Lưu và tiếp tục",
            font=("Inter", 16, "bold"),
            height=40,
            color=COLORS["success"],  # Green
            command=self.save_and_continue
        ).pack(pady=20)
    
    def browse_studio_one(self):
        file = filedialog.askopenfilename(
            title="Chọn Studio One (.exe hoặc .song)",
            filetypes=[
                ("Studio One Files", "*.exe *.song"),
                ("Executable", "*.exe"),
                ("Song file", "*.song"),
                ("All files", "*.*")
            ]
        )
        if file:
            self.s1_entry.delete(0, "end")
            self.s1_entry.insert(0, file)
    
    def browse_browser(self):
        file = filedialog.askopenfilename(
            title="Chọn Browser",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")]
        )
        if file:
            self.web_entry.delete(0, "end")
            self.web_entry.insert(0, file)
    
    def save_and_continue(self):
        s1_path = self.s1_entry.get().strip()
        web_path = self.web_entry.get().strip()
        auto_launch = self.auto_launch_var.get()
        
        if not s1_path or not web_path:
            # Hiển thị thông báo lỗi
            error_label = ctk.CTkLabel(
                self, 
                text="⚠️ Vui lòng nhập đầy đủ đường dẫn!", 
                text_color=COLORS["danger"],
                font=("Inter", 12)
            )
            error_label.place(relx=0.5, rely=0.9, anchor="center")
            self.after(3000, error_label.destroy)
            return
        
        # Kiểm tra file Studio One có tồn tại không
        if s1_path and not os.path.exists(s1_path):
            error_label = ctk.CTkLabel(
                self, 
                text="⚠️ Đường dẫn Studio One không tồn tại!", 
                text_color=COLORS["danger"],
                font=("Inter", 12)
            )
            error_label.place(relx=0.5, rely=0.9, anchor="center")
            self.after(3000, error_label.destroy)
            return
        
        backend.ConfigManager.save(s1_path, web_path, auto_launch)
        self.destroy()
        if self.callback:
            self.callback()

class MainDashboard(ctk.CTk):
    def __init__(self, settings=None):
        super().__init__()
        
        # Khởi tạo backend engine
        self.engine = backend.SystemEngine(settings)
        self.settings = settings or {}
        
        # Trạng thái
        self.tone_music_value = 0  # -12 to +12
        self.tone_voice_value = 0  # -12 to +12
        self.current_mode = "Đa Thể Loại"
        self.is_recording = False
        self.current_tone = "C"  # Tone mặc định
        self.current_score = None  # Điểm số hiện tại
        
        # Trạng thái toggle cho buttons
        self.be_state = False  # Bè button state
        self.vang_state = False  # Vang button state
        
        # Trạng thái Mute cho mixer channels (icon toggle buttons)
        self.mute_states = {
            "mix_music": False,   # NHẠC: False = đang bật (unmuted)
            "mix_mic": False,     # MIC
            "mix_reverb": False,  # VANG
            "mix_backing": False  # BÈ
        }
        
        # Trạng thái AutoKey
        self.autokey_active = False
        
        # Trạng thái Tune On/Off
        self.tune_state = True  # Tune mặc định là BẬT
        
        # Trạng thái Scale (Major/Minor)
        self.current_scale = "Major"  # Mặc định Major
        
        # 1. Cấu hình cửa sổ
        self.title("Quang Lưu Studio")
        self.geometry("1050x520")
        self.attributes("-topmost", True)
        
        # Lưới chính: Header(0) - Body(1) - BottomBar(2)
        self.grid_rowconfigure(1, weight=1) 
        self.grid_columnconfigure(0, weight=1)

        # --- KHỞI TẠO GIAO DIỆN ---
        self.setup_header()      # Row 0
        self.setup_body()        # Row 1
        self.setup_bottom_bar()  # Row 2
        
        # Đăng ký callback MIDI để tự động cập nhật status indicator
        self.engine.register_midi_callback(self.on_midi_status_changed)
        
        # Cập nhật trạng thái ban đầu
        self.update_midi_status()
        
        # Kiểm tra kết nối MIDI định kỳ (backup, ít thường xuyên hơn)
        self.check_midi_connection()
        
        # Tự động mở Studio One nếu được cấu hình
        self.auto_launch_studio_one()

    def on_midi_status_changed(self, connected, port_name=None):
        """Callback được gọi khi trạng thái MIDI thay đổi"""
        if hasattr(self, 'status_indicator'):
            if connected:
                status_text = f"Đã kết nối" + (f": {port_name}" if port_name else "")
                self.status_indicator.configure(text=status_text, text_color=COLORS["success"])
            else:
                self.status_indicator.configure(text="Chưa kết nối", text_color=COLORS["danger"])

    def update_midi_status(self):
        """Cập nhật trạng thái MIDI hiện tại"""
        if hasattr(self, 'status_indicator'):
            if self.engine.is_midi_connected():
                port_name = self.engine.get_midi_port_name()
                self.status_indicator.configure(
                    text=f"Đã kết nối: {port_name}", 
                    text_color=COLORS["success"]
                )
            else:
                self.status_indicator.configure(text="Chưa kết nối", text_color=COLORS["danger"])

    def check_midi_connection(self):
        """Kiểm tra và cập nhật trạng thái MIDI (backup check)"""
        # Chỉ thử reconnect nếu chưa kết nối
        if not self.engine.is_midi_connected():
            # Thử kết nối lại (chỉ 1 lần thử để không spam)
            self.engine.connect_midi(retry_count=1, delay=0.5)
        
        # Kiểm tra lại sau 5 giây (ít thường xuyên hơn vì đã có callback)
        self.after(5000, self.check_midi_connection)
    
    def auto_launch_studio_one(self):
        """Tự động mở Studio One nếu được cấu hình"""
        if self.settings.get("auto_launch_studio_one") and self.settings.get("studio_one_path"):
            studio_one_path = self.settings["studio_one_path"]
            if os.path.exists(studio_one_path):
                # Đợi một chút để app khởi động xong rồi mới mở Studio One
                self.after(1000, lambda: self.engine.launch_app(studio_one_path))
                print("✅ Tự động mở Studio One...")

    def setup_header(self):
        # Khu vực trên cùng: Tone, Chữ chạy, Điểm số, Trạng thái
        self.header_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 5))
        self.header_frame.grid_columnconfigure(1, weight=1)

        # --- 1. KHU VỰC TONE (TRÁI) ---
        self.tone_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.tone_frame.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        ctk.CTkLabel(self.tone_frame, text="Tone Bài Hát:", font=("Inter", 14, "bold")).pack(side="left", padx=(0, 5))
        
        music_keys = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B", 
                     "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "A#m", "Bm"]
        self.tone_option = ctk.CTkOptionMenu(
            self.tone_frame, 
            values=music_keys, 
            width=100,
            command=self.on_tone_selected
        )
        self.tone_option.pack(side="left")
        
        # --- 1b. AUTOKEY LIVE INDICATOR (bên phải tone selector) ---
        self.autokey_indicator_frame = ctk.CTkFrame(self.tone_frame, fg_color=COLORS["bg_card"], corner_radius=8)
        # Ẩn khi chưa bật AutoKey
        
        # Đèn nhấp nháy (bật/tắt xanh lá)
        self.autokey_dot = ctk.CTkLabel(
            self.autokey_indicator_frame,
            text="●",
            font=("Inter", 14),
            text_color=COLORS["success"],
            width=16
        )
        self.autokey_dot.pack(side="left", padx=(8, 2))
        
        # Label "Key:"
        ctk.CTkLabel(
            self.autokey_indicator_frame,
            text="Key:",
            font=("Inter", 11),
            text_color=COLORS["text_muted"]
        ).pack(side="left", padx=(2, 2))
        
        # Key hiện tại (lớn, nổi bật)
        self.autokey_key_label = ctk.CTkLabel(
            self.autokey_indicator_frame,
            text="...",
            font=("Inter", 18, "bold"),
            text_color=COLORS["text_main"]
        )
        self.autokey_key_label.pack(side="left", padx=2)
        
        # Scale (Trưởng/Thứ)
        self.autokey_scale_label = ctk.CTkLabel(
            self.autokey_indicator_frame,
            text="",
            font=("Inter", 11),
            text_color=COLORS["warning"]
        )
        self.autokey_scale_label.pack(side="left", padx=(0, 4))
        
        # Confidence nhỏ
        self.autokey_conf_label = ctk.CTkLabel(
            self.autokey_indicator_frame,
            text="",
            font=("Inter", 10),
            text_color=COLORS["text_muted"]
        )
        self.autokey_conf_label.pack(side="left", padx=(0, 8))
        
        self._autokey_dot_visible = True  # Trạng thái nhấp nháy

        # --- 2. KHU VỰC CHỮ CHẠY (GIỮA) ---
        self.marquee_container = ctk.CTkFrame(self.header_frame, fg_color=COLORS["bg_main"], corner_radius=0, height=30)
        self.marquee_container.grid(row=0, column=1, padx=10, pady=5, sticky="ew")
        
        self.marquee_text = "✨ Bản quyền thuộc về Quang Lưu - Tuấn Phúc - 0973306273 | 0326405221 🎶🎶 --- Chúc bạn có những bản thu âm tuyệt vời! 🎤"
        self.marquee_label = ctk.CTkLabel(
            self.marquee_container, 
            text=self.marquee_text, 
            text_color=COLORS["warning"], 
            font=("Inter", 16, "bold")
        )
        
        self.marquee_x = 800 
        self.marquee_label.place(x=self.marquee_x, y=5)
        self.animate_marquee()

        # --- 3. KHU VỰC ĐIỂM SỐ (GIỮA-PHẢI) ---
        self.score_frame = ctk.CTkFrame(self.header_frame, fg_color=COLORS["bg_card"], corner_radius=8)
        self.score_frame.grid(row=0, column=2, padx=5, pady=4, sticky="e")
        
        # Container cho điểm số
        score_container = ctk.CTkFrame(self.score_frame, fg_color="transparent")
        score_container.pack(padx=8, pady=5)
        
        # Label "Điểm số"
        ctk.CTkLabel(
            score_container,
            text="Điểm số:",
            font=("Inter", 10),
            text_color=COLORS["text_muted"]
        ).pack()
        
        # Khung hiển thị điểm số lớn
        self.score_display_frame = ctk.CTkFrame(score_container, fg_color=COLORS["bg_main"], corner_radius=5)
        self.score_display_frame.pack(pady=(3, 0))
        
        self.score_label = ctk.CTkLabel(
            self.score_display_frame,
            text="--",
            font=("Inter", 20, "bold"),
            text_color=COLORS["text_muted"],
            width=60
        )
        self.score_label.pack(padx=8, pady=3)

        # --- 4. KHU VỰC TRẠNG THÁI (PHẢI) ---
        self.status_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.status_frame.grid(row=0, column=3, padx=10, pady=5, sticky="e")

        # Nút Learn MIDI (mới thêm)
        ColorButton(
            self.status_frame,
            text="🎹 Learn MIDI",
            width=100,
            height=28,
            color=COLORS["deep_purple"],
            font=("Inter", 11, "bold"),
            command=self.engine.trigger_midi_learn
        ).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(self.status_frame, text="Trạng thái:", font=("Inter", 12)).pack(side="left", padx=(0, 5))
        
        self.status_indicator = ctk.CTkLabel(
            self.status_frame, 
            text="Đang kiểm tra...", 
            text_color=COLORS["warning"], 
            font=("Inter", 14, "bold")
        )
        self.status_indicator.pack(side="left")

    def on_tone_selected(self, value):
        """Xử lý khi chọn tone bài hát"""
        # Có thể gửi MIDI hoặc cập nhật trạng thái
        # Lưu tone hiện tại để sử dụng khi lưu bài hát
        self.current_tone = value
    
    def update_score_display(self, score):
        """Cập nhật hiển thị điểm số trong header"""
        if hasattr(self, 'score_label'):
            if score is not None:
                self.score_label.configure(
                    text=f"{score:.1f}",
                    text_color=self._get_score_color(score)
                )
            else:
                self.score_label.configure(
                    text="--",
                    text_color=COLORS["text_muted"]
                )
    
    def _get_score_color(self, score):
        """Lấy màu dựa trên điểm số"""
        if score >= 90:
            return COLORS["success"]  # Green
        elif score >= 85:
            return COLORS["success_hover"]  # Light Green
        elif score >= 80:
            return COLORS["warning"]  # Lime
        else:
            return COLORS["warning_hover"]  # Yellow

    def animate_marquee(self):
        """Logic làm chữ chạy"""
        self.marquee_x -= 1.5
        
        if self.marquee_x < -700: 
            self.marquee_x = self.marquee_container.winfo_width() if self.marquee_container.winfo_width() > 0 else 800
            
        self.marquee_label.place(x=self.marquee_x, y=5)
        self.after(20, self.animate_marquee)
    
    def setup_menu(self):
        """Legacy — buttons đã chuyển vào body và bottom bar"""
        pass
    
    # --- CALLBACKS CHO MENU BUTTONS ---
    def on_do_tone(self):
        """Toggle AutoKey: dò tone liên tục toàn bài hát"""
        if self.autokey_active:
            # Đang chạy → dừng
            self.autokey_active = False
            self.engine.stop_autokey()
            
            # Đổi nút về trạng thái ban đầu
            if hasattr(self, 'do_tone_button'):
                self.do_tone_button.configure(fg_color=COLORS["primary"])  # Blue
                self.do_tone_button.configure(text="Dò Tone")
            
            # Ẩn indicator
            self.autokey_indicator_frame.pack_forget()
        else:
            # Chưa chạy → bật
            self.autokey_active = True
            
            # Đổi nút thành trạng thái đang chạy
            if hasattr(self, 'do_tone_button'):
                self.do_tone_button.configure(fg_color=COLORS["danger"])  # Red
                self.do_tone_button.configure(text="⏹ Dừng")
            
            # Hiện indicator live
            self.autokey_indicator_frame.pack(side="left", padx=(10, 0))
            self.autokey_key_label.configure(text="...")
            self.autokey_scale_label.configure(text="")
            self.autokey_conf_label.configure(text="")
            self._animate_autokey_dot()
            
            # Bắt đầu AutoKey
            self.engine.start_autokey(on_key_update=self._on_autokey_update)
    
    def _animate_autokey_dot(self):
        """Nhấp nháy đèn xanh khi AutoKey đang chạy"""
        if not self.autokey_active:
            return
        self._autokey_dot_visible = not self._autokey_dot_visible
        color = COLORS["success"] if self._autokey_dot_visible else COLORS["bg_main"]
        try:
            self.autokey_dot.configure(text_color=color)
        except:
            return
        self.after(500, self._animate_autokey_dot)
    
    def _on_autokey_update(self, result):
        """Callback từ AutoKey thread → cập nhật UI qua after()"""
        # Thread-safe: dùng after() để cập nhật trên main thread
        try:
            self.after(0, lambda r=result: self._update_autokey_ui(r))
        except:
            pass
    
    def _update_autokey_ui(self, result):
        """Cập nhật UI từ kết quả AutoKey (chạy trên main thread)"""
        status = result.get('status', '')
        
        if status == 'stopped':
            # AutoKey đã dừng từ backend
            self.autokey_active = False
            if hasattr(self, 'do_tone_button'):
                self.do_tone_button.configure(fg_color=COLORS["primary"], text="Dò Tone")
            try:
                self.autokey_indicator_frame.pack_forget()
            except:
                pass
            return
        
        if status == 'listening':
            # Im lặng, đang lắng nghe
            self.autokey_key_label.configure(
                text=result.get('key_display', '...'),
                text_color=COLORS["text_muted"]
            )
            self.autokey_scale_label.configure(text="")
            self.autokey_conf_label.configure(text="🎙️")
            return
        
        if status == 'detected':
            key_display = result.get('key_display', '?')
            scale = result.get('scale', '')
            confidence = result.get('confidence', 0)
            conf_pct = max(0, min(100, confidence * 100))
            key_changed = result.get('key_changed', False)
            
            # Cập nhật indicator
            text_color = COLORS["success"] if key_changed else COLORS["text_main"]
            self.autokey_key_label.configure(text=key_display, text_color=text_color)
            
            # Scale (Trưởng/Thứ)
            scale_text = "Trưởng" if scale == "Major" else "Thứ" if scale == "Minor" else ""
            self.autokey_scale_label.configure(text=scale_text)
            
            self.autokey_conf_label.configure(text=f"{conf_pct:.0f}%")
            
            # Cập nhật tone selector
            if hasattr(self, 'tone_option'):
                try:
                    self.tone_option.set(key_display)
                    self.current_tone = key_display
                except:
                    pass
    
    def on_lay_tone(self):
        """Mở dialog Dò Tone Thủ Công"""
        # Callback cập nhật UI khi tone thay đổi
        def on_tone_detected(result):
            if result:
                key_display = result.get('key_display', 'C')
                try:
                    if hasattr(self, 'tone_option'):
                        self.after(0, lambda: [
                            self.tone_option.set(key_display),
                            setattr(self, 'current_tone', key_display),
                            self.on_tone_selected(key_display)
                        ])
                except:
                    pass
        
        ManualToneDialog(
            self,
            engine=self.engine,
            on_tone_detected_callback=on_tone_detected
        )
    
    def on_tone_auto(self):
        # Chỉ gửi MIDI CC
        self.engine.send_midi(MIDI_CC["tone_auto"], 127)
    
    def on_be(self):
        """Toggle button Bè: bật/tắt"""
        self.be_state = not self.be_state
        # Gửi MIDI CC: 127 = ON, 0 = OFF
        midi_value = 127 if self.be_state else 0
        self.engine.send_midi(MIDI_CC["be"], midi_value)
        # Cập nhật màu button để hiển thị trạng thái
        if hasattr(self, 'be_button'):
            if self.be_state:
                self.be_button.configure(fg_color=COLORS["success"])  # Green khi ON
            else:
                self.be_button.configure(fg_color=COLORS["primary_hover"])  # Purple khi OFF
    
    def on_vang(self):
        """Toggle button Vang: bật/tắt"""
        self.vang_state = not self.vang_state
        # Gửi MIDI CC: 127 = ON, 0 = OFF
        midi_value = 127 if self.vang_state else 0
        self.engine.send_midi(MIDI_CC["vang"], midi_value)
        # Cập nhật màu button để hiển thị trạng thái
        if hasattr(self, 'vang_button'):
            if self.vang_state:
                self.vang_button.configure(fg_color=COLORS["success"])  # Green khi ON
            else:
                self.vang_button.configure(fg_color=COLORS["warning"])  # Yellow khi OFF
    
    def on_nhac(self):
        # Chỉ gửi MIDI CC
        self.engine.send_midi(MIDI_CC["nhac"], 127)
    
    def on_fix_meo(self):
        # Chỉ gửi MIDI CC
        self.engine.send_midi(MIDI_CC["fix_meo"], 127)
    
    def on_tune_toggle(self):
        """Toggle Tune On/Off - Bật/tắt Auto-Tune trong Studio One"""
        self.tune_state = not self.tune_state
        midi_value = 127 if self.tune_state else 0
        self.engine.send_midi(MIDI_CC["tune_on_off"], midi_value)
        
        # Cập nhật màu button
        if hasattr(self, 'tune_button'):
            if self.tune_state:
                self.tune_button.base_color = COLORS["success"]
                self.tune_button.hover_color = interpolate_color(COLORS["success"], "#FFFFFF", 0.2)
                self.tune_button.configure(fg_color=COLORS["success"], text="Tune ✓")
            else:
                self.tune_button.base_color = COLORS["danger"]
                self.tune_button.hover_color = interpolate_color(COLORS["danger"], "#FFFFFF", 0.2)
                self.tune_button.configure(fg_color=COLORS["danger"], text="Tune ✗")
    
    def on_scale_toggle(self):
        """Toggle Scale Major ↔ Minor → gửi MIDI CC đến Auto-Tune"""
        if self.current_scale == "Major":
            self.current_scale = "Minor"
            self.engine.send_midi(MIDI_CC["auto_tune_scale"], 127)
            if hasattr(self, 'scale_button'):
                self.scale_button.base_color = COLORS["primary"]
                self.scale_button.hover_color = interpolate_color(COLORS["primary"], "#FFFFFF", 0.2)
                self.scale_button.configure(fg_color=COLORS["primary"], text="Minor")
        else:
            self.current_scale = "Major"
            self.engine.send_midi(MIDI_CC["auto_tune_scale"], 0)
            if hasattr(self, 'scale_button'):
                self.scale_button.base_color = COLORS["success"]
                self.scale_button.hover_color = interpolate_color(COLORS["success"], "#FFFFFF", 0.2)
                self.scale_button.configure(fg_color=COLORS["success"], text="Major")

    # --- DÒ TONE - THU ÂM TRỰC TIẾP TỪ HỆ THỐNG ---
    def _start_tone_detection(self):
        """Bắt đầu dò tone bằng cách thu âm loopback từ hệ thống"""
        RECORD_DURATION = 5  # Thu âm 5 giây (HPSS + energy-weighted → đủ chính xác)
        
        # Dialog hiển thị countdown
        self._tone_dialog = ctk.CTkToplevel(self)
        self._tone_dialog.title("🎵 Dò Tone")
        self._tone_dialog.geometry("420x250")
        self._tone_dialog.attributes("-topmost", True)
        self._tone_dialog.transient(self)
        self._tone_dialog.resizable(False, False)
        
        # Container
        main_frame = ctk.CTkFrame(self._tone_dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Icon + title
        ctk.CTkLabel(
            main_frame,
            text="🎵 ĐANG DÒ TONE",
            font=("Inter", 20, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(10, 5))
        
        # Status label
        self._tone_status = ctk.CTkLabel(
            main_frame,
            text="🔊 Đang lắng nghe bài hát...",
            font=("Inter", 14),
            text_color=COLORS["text_muted"]
        )
        self._tone_status.pack(pady=5)
        
        # Countdown label lớn
        self._tone_countdown = ctk.CTkLabel(
            main_frame,
            text=f"{RECORD_DURATION}",
            font=("Inter", 48, "bold"),
            text_color=COLORS["success"]
        )
        self._tone_countdown.pack(pady=5)
        
        # Hướng dẫn
        ctk.CTkLabel(
            main_frame,
            text="💡 Hãy đảm bảo bài hát đang phát trên loa/headphone",
            font=("Inter", 11),
            text_color=COLORS["text_muted"],
            wraplength=380
        ).pack(pady=(5, 0))
        
        # Progress bar
        self._tone_progress = ctk.CTkProgressBar(main_frame, width=350, height=8)
        self._tone_progress.pack(pady=10)
        self._tone_progress.set(0)
        self._tone_progress.configure(progress_color=COLORS["primary"])
        
        # Callback cập nhật countdown trên UI (gọi từ background thread)
        def on_progress(seconds_remaining):
            try:
                self._tone_countdown.configure(text=f"{seconds_remaining}")
                progress_val = 1.0 - (seconds_remaining / RECORD_DURATION)
                self._tone_progress.set(progress_val)
            except:
                pass
        
        # Callback khi hoàn thành
        def on_complete(result):
            try:
                self._tone_dialog.destroy()
            except:
                pass
            
            if result:
                # Cập nhật tone selector trong header
                key_display = result.get("key_display", "C")
                if hasattr(self, 'tone_option'):
                    try:
                        self.tone_option.set(key_display)
                        self.current_tone = key_display
                    except:
                        pass
                
                # Hiển thị dialog kết quả
                self._show_tone_result(result)
        
        # Callback khi lỗi
        def on_error(error_msg):
            try:
                self._tone_dialog.destroy()
            except:
                pass
            self._show_error(f"Lỗi dò tone: {error_msg}")
        
        # Bắt đầu thu âm + phân tích trong background
        self.engine.detect_tone(
            duration=RECORD_DURATION,
            on_complete=on_complete,
            on_error=on_error,
            on_progress=on_progress
        )
    
    def _show_tone_result(self, result):
        """Hiển thị kết quả dò tone"""
        has_timeline = bool(result.get("key_timeline"))
        dialog_height = 520 if has_timeline else 420
        
        result_dialog = ctk.CTkToplevel(self)
        result_dialog.title("🎵 Kết quả Dò Tone")
        result_dialog.geometry(f"450x{dialog_height}")
        result_dialog.attributes("-topmost", True)
        result_dialog.transient(self)
        
        main_frame = ctk.CTkFrame(result_dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Header
        header_text = "🎵 KẾT QUẢ DÒ TONE"
        if result.get("from_cache"):
            header_text += " (Cache)"
        ctk.CTkLabel(
            main_frame,
            text=header_text,
            font=("Inter", 22, "bold"),
            text_color=COLORS["primary"]
        ).pack(pady=(10, 15))
        
        # Key display lớn
        key_frame = ctk.CTkFrame(main_frame, fg_color=COLORS["bg_card"], corner_radius=15)
        key_frame.pack(pady=10, padx=30)
        
        ctk.CTkLabel(
            key_frame,
            text="TONE",
            font=("Inter", 12),
            text_color=COLORS["text_muted"]
        ).pack(pady=(15, 0))
        
        key_display = result.get("key_display", "?")
        ctk.CTkLabel(
            key_frame,
            text=key_display,
            font=("Inter", 48, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=(5, 5))
        
        scale_text = "Trưởng (Major)" if result.get("scale") == "Major" else "Thứ (Minor)"
        ctk.CTkLabel(
            key_frame,
            text=scale_text,
            font=("Inter", 14),
            text_color=COLORS["text_muted"]
        ).pack(pady=(0, 15))
        
        # Confidence bar
        confidence = result.get("confidence", 0)
        confidence_pct = max(0, min(100, confidence * 100))
        
        conf_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        conf_frame.pack(fill="x", pady=10, padx=30)
        
        ctk.CTkLabel(
            conf_frame,
            text=f"Độ chính xác: {confidence_pct:.1f}%",
            font=("Inter", 13),
            text_color=COLORS["text_muted"]
        ).pack(anchor="w", pady=(0, 5))
        
        conf_bar = ctk.CTkProgressBar(conf_frame, width=350, height=15)
        conf_bar.pack(fill="x")
        conf_bar.set(max(0, min(1, confidence)))
        conf_color = COLORS["success"] if confidence >= 0.7 else (COLORS["warning"] if confidence >= 0.5 else COLORS["danger"])
        conf_bar.configure(progress_color=conf_color)
        
        # Timeline chuyển tone (nếu có)
        timeline = result.get("key_timeline", [])
        if len(timeline) > 1:
            tl_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            tl_frame.pack(fill="x", pady=5, padx=30)
            
            ctk.CTkLabel(
                tl_frame,
                text="⏱️ Chuyển tone:",
                font=("Inter", 12, "bold"),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", pady=(0, 3))
            
            prev_key = None
            for entry in timeline:
                if entry['key_display'] != prev_key:
                    t = entry.get('time', 0)
                    mins = t // 60
                    secs = t % 60
                    time_str = f"{mins}:{secs:02d}" if mins > 0 else f"{secs}s" 
                    marker = "🟢" if prev_key is None else "🔄"
                    ctk.CTkLabel(
                        tl_frame,
                        text=f"  {marker} {time_str}: {entry['key_display']}",
                        font=("Inter", 11),
                        text_color=COLORS["success"] if prev_key is None else COLORS["warning"]
                    ).pack(anchor="w", pady=1)
                    prev_key = entry['key_display']
        
        # Top alternatives
        top_results = result.get("top_results", [])
        if len(top_results) > 1:
            alt_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
            alt_frame.pack(fill="x", pady=5, padx=30)
            
            ctk.CTkLabel(
                alt_frame,
                text="Các tone có thể:",
                font=("Inter", 12, "bold"),
                text_color=COLORS["text_muted"]
            ).pack(anchor="w", pady=(0, 3))
            
            for r in top_results[:3]:
                corr_pct = max(0, min(100, r["correlation"] * 100))
                color = COLORS["success"] if r == top_results[0] else COLORS["text_muted"]
                ctk.CTkLabel(
                    alt_frame,
                    text=f"  {r['key']}: {corr_pct:.1f}%",
                    font=("Inter", 11),
                    text_color=color
                ).pack(anchor="w", pady=1)
        
        # MIDI info
        ctk.CTkLabel(
            main_frame,
            text="📤 Đã gửi MIDI đến Auto-Tune trên Studio One",
            font=("Inter", 11),
            text_color=COLORS["success"]
        ).pack(pady=8)
        
        ctk.CTkButton(
            main_frame,
            text="Đóng",
            command=result_dialog.destroy,
            width=150,
            height=40,
            font=("Inter", 14, "bold")
        ).pack(pady=10)
    
    def on_save(self):
        """Lưu bài hát đang phát trên YouTube"""
        self._show_save_song_dialog()
    
    def on_open(self):
        """Mở file Studio One"""
        if self.settings.get("studio_one_path"):
            self.engine.launch_app(self.settings["studio_one_path"])
    
    def on_record(self):
        """Bật/tắt recording + capture loopback audio"""
        self.is_recording = not self.is_recording
        self.engine.send_hotkey(["ctrl", "shift", "r"])
        
        if self.is_recording:
            # Bắt đầu báo hiệu thu âm + capture audio
            self._start_record_animation()
            if hasattr(self, 'status_indicator'):
                self.status_indicator.configure(text="Đang thu âm...", text_color=COLORS["danger"])
            self._start_audio_capture()
        else:
            # Dừng capture + báo hiệu
            self._stop_audio_capture()
            self._stop_record_animation()
            self.update_midi_status()
            # Hỏi chấm điểm
            self.after(500, self._ask_scoring_after_record)
    
    def _start_audio_capture(self):
        """Bắt đầu capture audio loopback khi recording"""
        self._recorded_audio = None
        self._capture_active = True
        
        import threading
        def capture_loop():
            try:
                import soundcard as sc
                import numpy as np
                
                default_speaker = sc.default_speaker()
                loopback_mic = None
                
                all_mics = sc.all_microphones(include_loopback=True)
                speaker_name = default_speaker.name if default_speaker else ""
                for mic in all_mics:
                    if hasattr(mic, 'isloopback') and mic.isloopback:
                        if speaker_name and speaker_name.lower() in mic.name.lower():
                            loopback_mic = mic
                
                if not loopback_mic:
                    try:
                        loopback_mic = sc.get_microphone(id=str(default_speaker.name), include_loopback=True)
                    except:
                        pass
                
                if not loopback_mic:
                    print("⚠️ [CAPTURE] Không tìm thấy loopback, bỏ qua capture")
                    return
                
                print(f"🎤 [CAPTURE] Bắt đầu capture: {loopback_mic.name}")
                sample_rate = 44100
                chunks = []
                
                with loopback_mic.recorder(samplerate=sample_rate, channels=1) as recorder:
                    while self._capture_active:
                        chunk = recorder.record(numframes=sample_rate)  # 1 second chunks
                        chunks.append(chunk)
                
                if chunks:
                    audio = np.concatenate(chunks, axis=0)
                    if audio.ndim > 1:
                        audio = audio[:, 0]
                    self._recorded_audio = audio.astype(np.float32)
                    self._recorded_sample_rate = sample_rate
                    duration = len(self._recorded_audio) / sample_rate
                    print(f"✅ [CAPTURE] Thu được {duration:.1f}s audio")
            except Exception as e:
                print(f"⚠️ [CAPTURE] Lỗi capture: {e}")
        
        threading.Thread(target=capture_loop, daemon=True).start()
    
    def _stop_audio_capture(self):
        """Dừng capture audio"""
        self._capture_active = False
            
    def _start_record_animation(self):
        self._record_blink_state = True
        self._animate_record_button()
        
    def _animate_record_button(self):
        if not getattr(self, "is_recording", False):
            return
            
        if hasattr(self, "record_button"):
            color = COLORS["danger"] if self._record_blink_state else COLORS["bg_main"]
            text_icon = "⏸️" if self._record_blink_state else "⏺️"
            self.record_button.base_color = color
            self.record_button.configure(fg_color=color, text=text_icon)
            self._record_blink_state = not self._record_blink_state
            
        self.after(600, self._animate_record_button)
        
    def _stop_record_animation(self):
        if hasattr(self, "record_button"):
            color = COLORS["danger"]
            self.record_button.base_color = color
            self.record_button.configure(fg_color=color, text="⏺️")
    
    def on_score(self):
        """Chấm điểm sau khi hát - Hiển thị dialog chọn nguồn"""
        # Dialog chọn nguồn
        source_dialog = ctk.CTkToplevel(self)
        source_dialog.title("Chọn nguồn audio")
        source_dialog.geometry("400x200")
        source_dialog.attributes("-topmost", True)
        source_dialog.transient(self)
        
        ctk.CTkLabel(
            source_dialog,
            text="🎤 Chọn nguồn audio để chấm điểm",
            font=("Inter", 18, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=20)
        
        button_frame = ctk.CTkFrame(source_dialog, fg_color="transparent")
        button_frame.pack(pady=10)
        
        def choose_file():
            source_dialog.destroy()
            self._score_from_file()
        
        def choose_youtube():
            source_dialog.destroy()
            self._score_from_youtube()
        
        ColorButton(
            button_frame,
            text="📁 Chọn file audio",
            width=180,
            height=50,
            color=COLORS["primary"],
            font=("Inter", 14, "bold"),
            command=choose_file
        ).pack(side="left", padx=10)
        
        ColorButton(
            button_frame,
            text="▶️ YouTube URL",
            width=180,
            height=50,
            color=COLORS["danger"],
            font=("Inter", 14, "bold"),
            command=choose_youtube
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            source_dialog,
            text="Hủy",
            command=source_dialog.destroy,
            width=100
        ).pack(pady=20)
    
    def _ask_scoring_after_record(self):
        """Hỏi người dùng có muốn chấm điểm sau thu âm không"""
        ask_dialog = ctk.CTkToplevel(self)
        ask_dialog.title("🎤 Chấm điểm")
        ask_dialog.geometry("420x200")
        ask_dialog.attributes("-topmost", True)
        ask_dialog.transient(self)
        
        ctk.CTkLabel(
            ask_dialog,
            text="✅ Đã hoàn thành thu âm!",
            font=("Inter", 18, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=(25, 5))
        
        ctk.CTkLabel(
            ask_dialog,
            text="Bạn có muốn chấm điểm không?",
            font=("Inter", 14),
            text_color=COLORS["text_muted"]
        ).pack(pady=5)
        
        btn_frame = ctk.CTkFrame(ask_dialog, fg_color="transparent")
        btn_frame.pack(pady=20)
        
        def do_score():
            ask_dialog.destroy()
            self._score_recorded_audio()
        
        ColorButton(
            btn_frame,
            text="🎤 Chấm điểm",
            width=150,
            height=45,
            color=COLORS["success"],
            font=("Inter", 14, "bold"),
            command=do_score
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            btn_frame,
            text="Bỏ qua",
            width=100,
            height=45,
            font=("Inter", 14),
            command=ask_dialog.destroy
        ).pack(side="left", padx=10)
    
    def _score_recorded_audio(self):
        """Chấm điểm trực tiếp audio vừa thu âm (loopback capture)"""
        recorded = getattr(self, '_recorded_audio', None)
        
        if recorded is None or len(recorded) == 0:
            self._show_error("Không capture được audio. Vui lòng chọn file thủ công.")
            self._score_from_file()
            return
        
        # Animated loading dialog
        processing_dialog = ctk.CTkToplevel(self)
        processing_dialog.title("")
        processing_dialog.geometry("380x250")
        processing_dialog.attributes("-topmost", True)
        processing_dialog.transient(self)
        processing_dialog.overrideredirect(True)
        
        processing_dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - 380) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 250) // 2
        processing_dialog.geometry(f"380x250+{x}+{y}")
        
        main_frame = ctk.CTkFrame(processing_dialog, corner_radius=15)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        self._spinner_idx = 0
        spinner_label = ctk.CTkLabel(main_frame, text="🎵", font=("Segoe UI Emoji", 40))
        spinner_label.pack(pady=(25, 10))
        
        status_label = ctk.CTkLabel(
            main_frame, text="Đang chấm điểm...",
            font=("Inter", 16, "bold"), text_color=COLORS["primary"]
        )
        status_label.pack(pady=5)
        
        progress = ctk.CTkProgressBar(main_frame, width=280, mode="indeterminate")
        progress.pack(pady=10)
        progress.start()
        
        ctk.CTkLabel(
            main_frame, text="Phân tích bản thu âm vừa ghi",
            font=("Inter", 11), text_color=COLORS["text_muted"]
        ).pack(pady=5)
        
        def animate_spinner():
            if not processing_dialog.winfo_exists():
                return
            notes = ["🎵", "🎶", "🎤", "🎧", "🎵"]
            self._spinner_idx = (self._spinner_idx + 1) % len(notes)
            spinner_label.configure(text=notes[self._spinner_idx])
            processing_dialog.after(400, animate_spinner)
        
        processing_dialog.after(400, animate_spinner)
        
        import threading
        def score_thread():
            try:
                scoring_engine = backend.ScoringEngine()
                scoring_engine.load_audio_data(recorded, getattr(self, '_recorded_sample_rate', 44100))
                
                result = scoring_engine.calculate_score(quick=True)
                
                self.after(0, processing_dialog.destroy)
                
                if result:
                    print(f"✅ [CHẤM ĐIỂM] Điểm: {result.get('total_score', 0):.1f}")
                    self.current_score = result.get("total_score", 0)
                    self.after(0, lambda: self.update_score_display(self.current_score))
                    self.after(300, lambda: ScoringDialog(self, result, animated=True))
                else:
                    self.after(100, lambda: self._show_error("Không thể tính điểm."))
            except Exception as e:
                print(f"❌ [CHẤM ĐIỂM] Lỗi: {e}")
                self.after(0, processing_dialog.destroy)
                self.after(100, lambda: self._show_error(f"Lỗi: {str(e)}"))
        
        threading.Thread(target=score_thread, daemon=True).start()
    
    def _score_from_file(self):
        """Chấm điểm từ file audio"""
        # Mở dialog chọn file audio
        file_path = filedialog.askopenfilename(
            title="Chọn file audio để chấm điểm",
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.flac *.m4a *.ogg"),
                ("WAV files", "*.wav"),
                ("MP3 files", "*.mp3"),
                ("All files", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        self._process_scoring(file_path, is_youtube=False)
    
    def _score_from_youtube(self):
        """Chấm điểm từ YouTube URL"""
        # Dialog nhập YouTube URL
        url_dialog = ctk.CTkToplevel(self)
        url_dialog.title("Nhập YouTube URL")
        url_dialog.geometry("500x180")
        url_dialog.attributes("-topmost", True)
        url_dialog.transient(self)
        
        ctk.CTkLabel(
            url_dialog,
            text="📺 Nhập URL video YouTube",
            font=("Inter", 16, "bold"),
            text_color=COLORS["danger"]
        ).pack(pady=15)
        
        url_entry = ctk.CTkEntry(
            url_dialog,
            width=450,
            placeholder_text="https://www.youtube.com/watch?v=...",
            font=("Inter", 12)
        )
        url_entry.pack(pady=10)
        url_entry.focus()
        
        def process_url():
            youtube_url = url_entry.get().strip()
            if not youtube_url:
                self._show_error("Vui lòng nhập URL YouTube")
                return
            
            if "youtube.com" not in youtube_url and "youtu.be" not in youtube_url:
                self._show_error("URL không hợp lệ. Vui lòng nhập URL YouTube.")
                return
            
            url_dialog.destroy()
            self._process_scoring(youtube_url, is_youtube=True)
        
        button_frame = ctk.CTkFrame(url_dialog, fg_color="transparent")
        button_frame.pack(pady=10)
        
        ColorButton(
            button_frame,
            text="Xác nhận",
            width=120,
            color=COLORS["danger"],
            command=process_url
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            button_frame,
            text="Hủy",
            width=120,
            command=url_dialog.destroy
        ).pack(side="left", padx=5)
        
        # Enter để xác nhận
        url_entry.bind("<Return>", lambda e: process_url())
    
    def _process_scoring(self, source, is_youtube=False):
        """Xử lý chấm điểm với animation loading"""
        # Hiển thị dialog đang xử lý với animation
        processing_dialog = ctk.CTkToplevel(self)
        processing_dialog.title("")
        processing_dialog.geometry("380x250")
        processing_dialog.attributes("-topmost", True)
        processing_dialog.transient(self)
        processing_dialog.overrideredirect(True)  # Bỏ title bar
        
        # Center dialog
        processing_dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - 380) // 2
        y = self.winfo_rooty() + (self.winfo_height() - 250) // 2
        processing_dialog.geometry(f"380x250+{x}+{y}")
        
        main_frame = ctk.CTkFrame(processing_dialog, corner_radius=15)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Spinner animation text
        spinner_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█", "▇", "▆", "▅", "▄", "▃", "▂"]
        self._spinner_idx = 0
        
        spinner_label = ctk.CTkLabel(
            main_frame,
            text="🎵",
            font=("Segoe UI Emoji", 40)
        )
        spinner_label.pack(pady=(25, 10))
        
        status_label = ctk.CTkLabel(
            main_frame,
            text="Đang chuẩn bị..." if is_youtube else "Đang phân tích...",
            font=("Inter", 16, "bold"),
            text_color=COLORS["primary"]
        )
        status_label.pack(pady=5)
        
        progress = ctk.CTkProgressBar(main_frame, width=280, mode="indeterminate")
        progress.pack(pady=10)
        progress.start()
        
        detail_label = ctk.CTkLabel(
            main_frame,
            text="Vui lòng chờ...",
            font=("Inter", 11),
            text_color=COLORS["text_muted"]
        )
        detail_label.pack(pady=5)
        
        # Spinner animation
        def animate_spinner():
            if not processing_dialog.winfo_exists():
                return
            notes = ["🎵", "🎶", "🎤", "🎧", "🎵"]
            self._spinner_idx = (self._spinner_idx + 1) % len(notes)
            spinner_label.configure(text=notes[self._spinner_idx])
            processing_dialog.after(400, animate_spinner)
        
        processing_dialog.after(400, animate_spinner)
        
        # Xử lý trong thread riêng
        def process_audio():
            try:
                print("=" * 60)
                print("🎤 [CHẤM ĐIỂM] Bắt đầu chấm điểm...")
                
                scoring_engine = backend.ScoringEngine()
                
                if is_youtube:
                    try:
                        self.after(0, lambda: status_label.configure(text="Đang tải từ YouTube..."))
                        self.after(0, lambda: detail_label.configure(text="Tải audio từ video"))
                        
                        audio_path = scoring_engine.download_youtube_audio(source)
                        if not audio_path:
                            self.after(0, processing_dialog.destroy)
                            self.after(100, lambda: self._show_error("Không thể tải audio từ YouTube."))
                            return
                        
                        self.after(0, lambda: status_label.configure(text="Đang phân tích..."))
                        self.after(0, lambda: detail_label.configure(text="Phân tích chất lượng âm thanh"))
                    except Exception as e:
                        self.after(0, processing_dialog.destroy)
                        self.after(100, lambda: self._show_error(f"Lỗi tải YouTube: {str(e)}"))
                        return
                else:
                    audio_path = source
                
                # Load audio
                try:
                    self.after(0, lambda: detail_label.configure(text="Đọc dữ liệu âm thanh..."))
                    if not scoring_engine.load_audio(audio_path):
                        self.after(0, processing_dialog.destroy)
                        self.after(100, lambda: self._show_error("Không thể load file audio."))
                        return
                except ImportError as e:
                    self.after(0, processing_dialog.destroy)
                    self.after(100, lambda: self._show_error(str(e)))
                    return
                
                self.after(0, lambda: status_label.configure(text="Đang tính điểm..."))
                self.after(0, lambda: detail_label.configure(text="Đánh giá độ chính xác và ổn định"))
                
                # Tính điểm (quick mode - nhẹ tay và nhanh)
                result = scoring_engine.calculate_score(quick=True)
                
                if is_youtube:
                    scoring_engine.cleanup_temp_file()
                
                # Đóng processing dialog
                self.after(0, processing_dialog.destroy)
                
                if result:
                    print(f"✅ [CHẤM ĐIỂM] Điểm tổng: {result.get('total_score', 0):.1f}")
                    
                    self.current_score = result.get("total_score", 0)
                    self.after(0, lambda: self.update_score_display(self.current_score))
                    
                    # Hiển kết quả với animation
                    self.after(300, lambda: ScoringDialog(self, result, animated=True))
                else:
                    self.after(100, lambda: self._show_error("Không thể tính điểm."))
            except Exception as e:
                print(f"❌ [CHẤM ĐIỂM] Lỗi: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, processing_dialog.destroy)
                self.after(100, lambda: self._show_error(f"Lỗi: {str(e)}"))
        
        import threading
        threading.Thread(target=process_audio, daemon=True).start()
    
    def _show_error(self, message):
        """Hiển thị thông báo lỗi"""
        error_dialog = ctk.CTkToplevel(self)
        error_dialog.title("Lỗi")
        error_dialog.geometry("400x150")
        error_dialog.attributes("-topmost", True)
        error_dialog.transient(self)
        
        ctk.CTkLabel(
            error_dialog,
            text=message,
            font=("Inter", 14),
            text_color=COLORS["danger"],
            wraplength=350
        ).pack(pady=30, padx=20)
        
        ctk.CTkButton(
            error_dialog,
            text="Đóng",
            command=error_dialog.destroy,
            width=100
        ).pack(pady=10)
    
    def _show_save_song_dialog(self):
        """Lưu bài hát nhanh - tự động lấy URL, title, tone"""
        auto_url = getattr(self.engine, 'current_youtube_url', '') or ''
        auto_tone = getattr(self, 'current_tone', 'C')
        if hasattr(self, 'tone_option'):
            auto_tone = self.tone_option.get()
        
        # Nếu có URL đang phát → lưu thẳng
        if auto_url:
            auto_title = ''
            # Thử lấy title từ manual timeline
            timeline_data = backend.ManualToneTimeline.load_timeline(auto_url)
            if timeline_data:
                auto_title = timeline_data.get('title', '')
                tl = timeline_data.get('timeline', [])
                if tl:
                    auto_tone = tl[0].get('key_display', auto_tone)
            
            # Nếu chưa có title, lấy từ YouTube
            if not auto_title:
                try:
                    import yt_dlp
                    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(auto_url, download=False)
                        auto_title = info.get('title', 'Bài hát không tên')
                except:
                    auto_title = 'Bài hát không tên'
            
            if backend.SongManager.add_song(auto_title, auto_url, auto_tone):
                success_label = ctk.CTkLabel(
                    self,
                    text=f"✅ Đã lưu: {auto_title[:40]}",
                    text_color=COLORS["success"],
                    font=("Inter", 12, "bold")
                )
                success_label.place(relx=0.5, rely=0.1, anchor="center")
                self.after(2500, success_label.destroy)
            else:
                self._show_error("Lỗi khi lưu bài hát")
            return
        
        # Không có URL đang phát → dialog nhập URL
        save_dialog = ctk.CTkToplevel(self)
        save_dialog.title("💾 Lưu bài hát")
        save_dialog.geometry("500x200")
        save_dialog.attributes("-topmost", True)
        save_dialog.transient(self)
        
        ctk.CTkLabel(
            save_dialog,
            text="💾 Nhập URL bài hát cần lưu",
            font=("Inter", 18, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=15)
        
        url_entry = ctk.CTkEntry(
            save_dialog, width=440,
            placeholder_text="https://www.youtube.com/watch?v=...",
            font=("Inter", 12)
        )
        url_entry.pack(padx=30, pady=10)
        url_entry.focus()
        
        def save_from_url():
            url = url_entry.get().strip()
            if not url or ("youtube.com" not in url and "youtu.be" not in url):
                self._show_error("Vui lòng nhập URL YouTube hợp lệ")
                return
            
            save_dialog.destroy()
            
            # Lấy title + tone tự động
            title = 'Bài hát không tên'
            tone = auto_tone
            
            timeline_data = backend.ManualToneTimeline.load_timeline(url)
            if timeline_data:
                title = timeline_data.get('title', title)
                tl = timeline_data.get('timeline', [])
                if tl:
                    tone = tl[0].get('key_display', tone)
            else:
                try:
                    import yt_dlp
                    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                        title = info.get('title', title)
                except:
                    pass
            
            if backend.SongManager.add_song(title, url, tone):
                success_label = ctk.CTkLabel(
                    self,
                    text=f"✅ Đã lưu: {title[:40]}",
                    text_color=COLORS["success"],
                    font=("Inter", 12, "bold")
                )
                success_label.place(relx=0.5, rely=0.1, anchor="center")
                self.after(2500, success_label.destroy)
            else:
                self._show_error("Lỗi khi lưu bài hát")
        
        btn_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        ColorButton(
            btn_frame, text="💾 Lưu", width=120,
            color=COLORS["success"], command=save_from_url
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            btn_frame, text="Hủy", width=120,
            command=save_dialog.destroy
        ).pack(side="left", padx=5)
        
        url_entry.bind("<Return>", lambda e: save_from_url())
    
    def _show_songs_list(self):
        """Hiển thị danh sách bài hát đã lưu"""
        songs = backend.SongManager.load_songs()
        
        list_dialog = ctk.CTkToplevel(self)
        list_dialog.title("📋 Danh sách bài hát")
        list_dialog.geometry("750x500")
        list_dialog.attributes("-topmost", True)
        list_dialog.transient(self)
        
        # Header
        header_frame = ctk.CTkFrame(list_dialog)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(
            header_frame,
            text="📋 Danh sách bài hát đã lưu",
            font=("Inter", 20, "bold"),
            text_color=COLORS["success"]
        ).pack(pady=15)
        
        # Scrollable frame cho danh sách
        scroll_frame = ctk.CTkScrollableFrame(list_dialog)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        if not songs:
            ctk.CTkLabel(
                scroll_frame,
                text="Chưa có bài hát nào được lưu",
                font=("Inter", 14),
                text_color=COLORS["text_muted"]
            ).pack(pady=50)
        else:
            for song in songs:
                song_frame = ctk.CTkFrame(scroll_frame)
                song_frame.pack(fill="x", pady=5)
                
                # Thông tin bài hát
                info_frame = ctk.CTkFrame(song_frame, fg_color="transparent")
                info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                
                # Kiểm tra manual timeline
                song_url = song.get("url", "")
                has_timeline = False
                if song_url:
                    tl_data = backend.ManualToneTimeline.load_timeline(song_url)
                    has_timeline = tl_data is not None and bool(tl_data.get('timeline'))
                
                # Title + badge timeline
                title_line = ctk.CTkFrame(info_frame, fg_color="transparent")
                title_line.pack(anchor="w")
                
                ctk.CTkLabel(
                    title_line,
                    text=song.get("title", "Không có tên"),
                    font=("Inter", 14, "bold")
                ).pack(side="left")
                
                if has_timeline:
                    ctk.CTkLabel(
                        title_line,
                        text="  🎵",
                        font=("Segoe UI Emoji", 12),
                        text_color=COLORS["primary_hover"]
                    ).pack(side="left")
                
                # Info line
                tone_text = f"Tone: {song.get('tone', 'N/A')}"
                if has_timeline:
                    tl_entries = tl_data.get('timeline', [])
                    tone_text += f" | 🎵 {len(tl_entries)} tone changes"
                tone_text += f" | {song.get('date_added', '')}"
                
                ctk.CTkLabel(
                    info_frame,
                    text=tone_text,
                    font=("Inter", 11),
                    text_color=COLORS["text_muted"]
                ).pack(anchor="w", pady=(2, 0))
                
                # Nút Play, Dò Tone và Delete
                button_frame = ctk.CTkFrame(song_frame, fg_color="transparent")
                button_frame.pack(side="right", padx=10, pady=10)
                
                def make_play_func(song_data):
                    def play_song():
                        url = song_data.get("url")
                        tone = song_data.get("tone", "C")
                        
                        if url:
                            def on_video_end(score_result):
                                if score_result:
                                    self.current_score = score_result.get("total_score", 0)
                                    self.update_score_display(self.current_score)
                                    ScoringDialog(self, score_result)
                            
                            def on_tone_detected(result):
                                """Callback khi phát hiện tone/chuyển tone tự động"""
                                if result:
                                    key_display = result.get('key_display', 'C')
                                    try:
                                        if hasattr(self, 'tone_option'):
                                            self.tone_option.set(key_display)
                                            self.current_tone = key_display
                                            self.on_tone_selected(key_display)
                                    except:
                                        pass
                            
                            self.engine.open_youtube_url(
                                url,
                                on_video_end_callback=on_video_end,
                                on_tone_detected=on_tone_detected
                            )
                            
                            # Thiết lập tone
                            if hasattr(self, 'tone_option'):
                                self.tone_option.set(tone)
                                self.on_tone_selected(tone)
                            
                            list_dialog.destroy()
                    return play_song
                
                def make_edit_tone_func(song_data):
                    def edit_tone():
                        url = song_data.get("url", "")
                        list_dialog.destroy()
                        ManualToneDialog(self, engine=self.engine, edit_url=url)
                    return edit_tone
                
                def make_delete_func(song_id):
                    def delete_song():
                        if backend.SongManager.delete_song(song_id):
                            list_dialog.destroy()
                            self._show_songs_list()  # Refresh list
                    return delete_song
                
                ColorButton(
                    button_frame,
                    text="▶️",
                    width=50,
                    height=35,
                    color=COLORS["success"],
                    command=make_play_func(song)
                ).pack(side="left", padx=2)
                
                ColorButton(
                    button_frame,
                    text="✏️",
                    width=50,
                    height=35,
                    color=COLORS["primary_hover"],
                    command=make_edit_tone_func(song)
                ).pack(side="left", padx=2)
                
                ColorButton(
                    button_frame,
                    text="🗑️",
                    width=50,
                    height=35,
                    color=COLORS["danger"],
                    command=make_delete_func(song.get("id"))
                ).pack(side="left", padx=2)
        
        # Nút đóng
        ctk.CTkButton(
            list_dialog,
            text="Đóng",
            command=list_dialog.destroy,
            width=150,
            height=40
        ).pack(pady=15)
    
    def setup_body(self):
        self.body_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.body_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 5))
        
        self.body_frame.grid_columnconfigure(0, weight=2)  # Cột trái
        self.body_frame.grid_columnconfigure(1, weight=3)  # Cột giữa (rộng nhất)
        self.body_frame.grid_columnconfigure(2, weight=2)  # Cột phải
        self.body_frame.grid_rowconfigure(0, weight=1)

        # ╔══════════════════════════════════════╗
        # ║  1. CỘT TRÁI: TONE & AUTO           ║
        # ╚══════════════════════════════════════╝
        self.col_left = ctk.CTkFrame(self.body_frame)
        self.col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        # --- Section 1: Tone & Auto Buttons (grid 2×4) ---
        ctk.CTkLabel(
            self.col_left, 
            text="Tone & Auto", 
            font=("Inter", 14, "bold"), 
            text_color=COLORS["success"]
        ).pack(pady=(10, 8))
        
        btn_grid = ctk.CTkFrame(self.col_left, fg_color=COLORS["bg_card"], corner_radius=10)
        btn_grid.pack(padx=10, fill="x", pady=(0, 5))
        btn_grid.grid_columnconfigure((0, 1), weight=1)
        
        # Danh sách buttons cho grid — màu khớp ui.html
        func_btns = [
            ("Dò Tone", self.on_do_tone, COLORS["orange"]),
            ("Lấy Tone", self.on_lay_tone, COLORS["teal"]),
            ("Tone Auto", self.on_tone_auto, COLORS["pink"]),
            ("Fix Méo", self.on_fix_meo, COLORS["deep_purple"]),
            ("Tune", self.on_tune_toggle, COLORS["accent"]),
            ("Chấm điểm", self.on_score, COLORS["light_purple"]),
        ]
        
        for i, (text, callback, color) in enumerate(func_btns):
            r = i // 2
            c = i % 2
            btn = ColorButton(
                btn_grid,
                text=text,
                height=35,
                font=("Inter", 12, "bold"),
                color=color,
                command=callback
            )
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
            
            # Lưu reference cho buttons cần cập nhật state
            if text == "Dò Tone":
                self.do_tone_button = btn
            elif text == "Tune":
                self.tune_button = btn
        
        # --- Section 2: Điều Chỉnh Tone ---
        ctk.CTkLabel(
            self.col_left, 
            text="Điều Chỉnh Tone", 
            font=("Inter", 14, "bold"), 
            text_color=COLORS["success"]
        ).pack(pady=(8, 2))

        # Tone Nhạc (teal)
        self.tone_music_frame = self.create_tone_control(self.col_left, "Tone Nhạc", "tone_music", COLORS["teal"])
        
        # Tone Giọng (red accent)
        self.tone_voice_frame = self.create_tone_control(self.col_left, "Tone Giọng", "tone_voice", COLORS["accent"])

        # ╔══════════════════════════════════════╗
        # ║  2. CỘT GIỮA: MIXER TỔNG            ║
        # ╚══════════════════════════════════════╝
        self.col_center = ctk.CTkFrame(self.body_frame)
        self.col_center.grid(row=0, column=1, sticky="nsew", padx=5)
        
        ctk.CTkLabel(
            self.col_center, 
            text="Mixer Tổng", 
            font=("Inter", 14, "bold"), 
            text_color=COLORS["success"]
        ).pack(pady=(10, 5))

        slider_container = ctk.CTkFrame(self.col_center, fg_color="transparent")
        slider_container.pack(fill="both", expand=True, padx=10)

        # CC keys cho mute toggle tương ứng từng kênh mixer
        mute_cc_map = {
            "mix_music": "mute_music",
            "mix_mic": "mute_mic",
            "mix_reverb": "mute_reverb",
            "mix_backing": "mute_backing"
        }
        
        mix_config = [
            {"icon": "🔊", "icon_muted": "🔇", "color": COLORS["teal"], "label": "Volume", "cc": "mix_music", "range": (0, 100), "default": 70, "unit": ""},
            {"icon": "🎙️", "icon_muted": "🚫", "color": COLORS["orange"], "label": "Mic", "cc": "mix_mic", "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "📢", "icon_muted": "🔇", "color": COLORS["accent"], "label": "Effects", "cc": "mix_reverb", "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "👥", "icon_muted": "🚫", "color": COLORS["light_purple"], "label": "Social Audio", "cc": "mix_backing", "range": (0, 100), "default": 70, "unit": ""}
        ]
        
        for i in range(4): 
            slider_container.grid_columnconfigure(i, weight=1)

        self.mixer_sliders = {}
        self.mute_icon_buttons = {}  # Lưu reference đến icon buttons
        
        for i, item in enumerate(mix_config):
            # Xác định giá trị mặc định và format hiển thị
            default_val = item["default"]
            min_val, max_val = item["range"]
            unit = item["unit"]
            
            # Label giá trị với format dB cho Mic và Vang
            val_label = ctk.CTkLabel(
                slider_container, 
                text=f"{default_val:+d}{unit}" if unit == " dB" else f"{default_val}{unit}", 
                font=("Inter", 14, "bold"), 
                text_color=item["color"]
            )
            val_label.grid(row=0, column=i, pady=(0, 5))

            def make_update_func(label_widget, cc_key, min_val, max_val, unit):
                def update_val(value):
                    if unit == " dB":
                        db_value = min_val + ((max_val - min_val) * (value / 100))
                        db_value = round(db_value, 1)
                        label_widget.configure(text=f"{db_value:+.1f}{unit}")
                        midi_value = int(((db_value - min_val) / (max_val - min_val)) * 127)
                        midi_value = max(0, min(127, midi_value))
                    else:
                        int_value = int(value)
                        label_widget.configure(text=f"{int_value}{unit}")
                        midi_value = int((value / 100) * 127)
                    self.engine.send_midi(MIDI_CC[cc_key], midi_value)
                return update_val

            # Slider dọc — cao hơn để giống hình mẫu
            slider = ctk.CTkSlider(
                slider_container, 
                orientation="vertical", 
                height=150,
                width=22,
                from_=0, to=100,
                progress_color=item["color"],
                button_color=interpolate_color(item["color"], "#FFFFFF", 0.5),
                button_hover_color=interpolate_color(item["color"], "#FFFFFF", 0.7),
                button_length=14,
                command=make_update_func(val_label, item["cc"], min_val, max_val, unit)
            )
            if unit == " dB":
                slider.set(50)
            else:
                slider.set(default_val)
            slider.grid(row=1, column=i, padx=8, pady=5)
            
            self.mixer_sliders[item["cc"]] = slider
            
            # Icon button (Mở/Tắt toggle)
            def make_mute_toggle(cc_key, icon_on, icon_off, color):
                def toggle_mute():
                    self.mute_states[cc_key] = not self.mute_states[cc_key]
                    is_muted = self.mute_states[cc_key]
                    mute_cc = mute_cc_map[cc_key]
                    midi_value = 127 if is_muted else 0
                    self.engine.send_midi(MIDI_CC[mute_cc], midi_value)
                    btn = self.mute_icon_buttons[cc_key]
                    if is_muted:
                        btn.configure(text=icon_off, fg_color=COLORS["bg_card_hover"], text_color=COLORS["text_muted"])
                    else:
                        btn.configure(text=icon_on, fg_color="transparent", text_color=color)
                return toggle_mute
            
            icon_btn = ctk.CTkButton(
                slider_container,
                text=item["icon"],
                text_color=item["color"],
                font=("Segoe UI Emoji", 24),
                fg_color="transparent",
                hover_color=COLORS["bg_card_hover"],
                width=45,
                height=36,
                corner_radius=8,
                command=make_mute_toggle(item["cc"], item["icon"], item["icon_muted"], item["color"])
            )
            icon_btn.grid(row=2, column=i, pady=(0, 2))
            self.mute_icon_buttons[item["cc"]] = icon_btn
            
            # Text label dưới icon (Volume, Mic, Effects, Social Audio)
            ctk.CTkLabel(
                slider_container,
                text=item["label"],
                font=("Inter", 10),
                text_color=COLORS["text_muted"]
            ).grid(row=3, column=i, pady=(0, 8))

        # ╔══════════════════════════════════════╗
        # ║  3. CỘT PHẢI: CHẾ ĐỘ HÁT           ║
        # ╚══════════════════════════════════════╝
        self.col_right = ctk.CTkFrame(self.body_frame)
        self.col_right.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        
        ctk.CTkLabel(
            self.col_right, 
            text="Chế Độ Hát", 
            font=("Inter", 14, "bold"), 
            text_color=COLORS["success"]
        ).pack(pady=(10, 8))
        
        btn_container = ctk.CTkFrame(self.col_right, fg_color="transparent")
        btn_container.pack(fill="both", expand=True, padx=15)
        
        # Mode buttons với màu sắc khớp ui.html
        modes_config = [
            ("Đa Thể Loại", COLORS["teal"]),
            ("Bolero", COLORS["orange"]),
            ("Dân Ca", COLORS["accent"]),
            ("Lofi", COLORS["light_purple"]),
            ("Remix", COLORS["pink"]),
            ("Pop", COLORS["blue"])
        ]
        
        btn_container.grid_columnconfigure((0, 1), weight=1)
        btn_container.grid_rowconfigure((0, 1, 2), weight=1)
        
        self.mode_buttons = {}
        for i, (mode, color) in enumerate(modes_config):
            r = i // 2
            c = i % 2
            
            btn = ColorButton(
                btn_container, 
                text=mode, 
                height=55, 
                font=("Inter", 14, "bold"),
                color=color,
                command=lambda m=mode: self.on_mode_selected(m)
            )
            btn.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
            self.mode_buttons[mode] = btn

    def setup_bottom_bar(self):
        """Thanh điều khiển phía dưới — Record nổi bật ở giữa"""
        self.bottom_bar = ctk.CTkFrame(self, height=55, corner_radius=0, fg_color=COLORS["bg_card"])
        self.bottom_bar.grid(row=2, column=0, sticky="ew", padx=0, pady=0)
        self.bottom_bar.grid_columnconfigure(1, weight=1)  # Giữa stretch
        
        # --- Bên trái: Save + List ---
        left_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        left_frame.grid(row=0, column=0, padx=15, pady=8, sticky="w")
        
        ColorButton(
            left_frame,
            text="💾 Save",
            width=85,
            height=36,
            font=("Inter", 13, "bold"),
            color=COLORS["teal"],
            command=self.on_save
        ).pack(side="left", padx=(0, 8))
        
        ColorButton(
            left_frame,
            text="📋 List",
            width=85,
            height=36,
            font=("Inter", 13, "bold"),
            color=COLORS["orange"],
            command=self._show_songs_list
        ).pack(side="left")
        
        # --- Giữa: RECORD (nổi bật) ---
        center_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        center_frame.grid(row=0, column=1, pady=8)
        
        self.record_button = ctk.CTkButton(
            center_frame,
            text="🎙️  RECORD",
            width=180,
            height=40,
            font=("Inter", 16, "bold"),
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            corner_radius=20,
            command=self.on_record
        )
        self.record_button.pack()
        
        # --- Bên phải: Open + Folder ---
        right_frame = ctk.CTkFrame(self.bottom_bar, fg_color="transparent")
        right_frame.grid(row=0, column=2, padx=15, pady=8, sticky="e")
        
        ColorButton(
            right_frame,
            text="📂 Open",
            width=85,
            height=36,
            font=("Inter", 13, "bold"),
            color=COLORS["pink"],
            command=self.on_open
        ).pack(side="left", padx=(0, 8))
        
        ColorButton(
            right_frame,
            text="📁 Folder",
            width=85,
            height=36,
            font=("Inter", 13, "bold"),
            color=COLORS["light_purple"],
            command=None
        ).pack(side="left")

    def create_tone_control(self, parent, label_text, cc_key, btn_color=None):
        """Điều khiển tone với nút +/- tròn lớn (giống ui.html)"""
        if btn_color is None:
            btn_color = COLORS["teal"]
        frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"], corner_radius=10)
        frame.pack(pady=5, padx=15, fill="x")
        
        inner = ctk.CTkFrame(frame, fg_color="transparent")
        inner.pack(pady=8, padx=10)
        
        ctk.CTkLabel(inner, text=label_text, font=("Inter", 13), text_color=COLORS["text_muted"]).pack(pady=(0, 5))
        
        ctrl_frame = ctk.CTkFrame(inner, fg_color="transparent")
        ctrl_frame.pack()
        
        value_label = ctk.CTkLabel(
            ctrl_frame, 
            text="+0", 
            width=55, 
            font=("Inter", 28, "bold"),
            text_color=btn_color
        )
        
        def update_display(value):
            value_label.configure(text=f"{value:+d}")
            midi_value = int(((value + 12) / 24) * 127)
            self.engine.send_midi(MIDI_CC[cc_key], midi_value)
        
        def decrease():
            if cc_key == "tone_music":
                self.tone_music_value = max(-12, self.tone_music_value - 1)
                update_display(self.tone_music_value)
            else:
                self.tone_voice_value = max(-12, self.tone_voice_value - 1)
                update_display(self.tone_voice_value)
        
        def increase():
            if cc_key == "tone_music":
                self.tone_music_value = min(12, self.tone_music_value + 1)
                update_display(self.tone_music_value)
            else:
                self.tone_voice_value = min(12, self.tone_voice_value + 1)
                update_display(self.tone_voice_value)
        
        # Nút - tròn lớn (màu theo tham số)
        ctk.CTkButton(
            ctrl_frame, 
            text="−", 
            width=48, 
            height=48, 
            corner_radius=24,
            font=("Inter", 22, "bold"),
            fg_color=btn_color,
            hover_color=interpolate_color(btn_color, "#FFFFFF", 0.2),
            command=decrease
        ).pack(side="left", padx=5)
        
        value_label.pack(side="left", padx=8)
        
        # Nút + tròn lớn (màu theo tham số)
        ctk.CTkButton(
            ctrl_frame, 
            text="+", 
            width=48, 
            height=48, 
            corner_radius=24,
            font=("Inter", 22, "bold"),
            fg_color=btn_color,
            hover_color=interpolate_color(btn_color, "#FFFFFF", 0.2),
            command=increase
        ).pack(side="left", padx=5)
        
        return frame

    def on_mode_selected(self, mode):
        """Xử lý khi chọn chế độ hát"""
        # Mode colors mapping
        mode_colors = {
            "Đa Thể Loại": COLORS["success"],  # Green
            "Bolero": COLORS["warning"],  # Orange
            "Dân Ca": COLORS["danger"],  # Red
            "Lofi": COLORS["primary_hover"],  # Purple
            "Remix": COLORS["danger_hover"],  # Pink
            "Pop": COLORS["primary"]  # Blue
        }
        
        # Cập nhật màu cho nút - làm sáng nút được chọn
        for m, btn in self.mode_buttons.items():
            base_color = mode_colors.get(m, COLORS["bg_card_hover"])
            if m == mode:
                # Làm sáng màu cho mode được chọn
                btn.base_color = interpolate_color(base_color, "#FFFFFF", 0.2)
                btn.hover_color = interpolate_color(base_color, "#FFFFFF", 0.3)
                btn.press_color = interpolate_color(base_color, "#000000", 0.1)
                btn.configure(fg_color=btn.base_color)
            else:
                # Tối hơn một chút cho mode không được chọn
                btn.base_color = interpolate_color(base_color, "#000000", 0.2)
                btn.hover_color = interpolate_color(base_color, "#FFFFFF", 0.1)
                btn.press_color = interpolate_color(base_color, "#000000", 0.3)
                btn.configure(fg_color=btn.base_color)
        
        self.current_mode = mode
        # Có thể gửi MIDI hoặc thực hiện hành động khác
        # Ví dụ: gửi Program Change message
        # self.engine.send_midi_program(mode_index)

# --- DEBUG ---
if __name__ == "__main__":
    app = MainDashboard()
    app.mainloop()
