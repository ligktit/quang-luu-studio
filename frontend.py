import customtkinter as ctk
import os
import tkinter.filedialog as filedialog
import tkinter as tk
from tkinter import Canvas
import backend

# --- CẤU HÌNH GIAO DIỆN ---
ctk.set_default_color_theme("blue")

ctk.set_appearance_mode("Dark")

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
    
    # Auto-Tune Control (gửi đến Studio One)
    "auto_tune_key": 34,       # Key gốc (0-127) -> Auto-Tune
    "auto_tune_scale": 35,     # Scale type (0=Major, 127=Minor) -> Auto-Tune
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
    def __init__(self, parent, score_result):
        super().__init__(parent)
        
        self.title("🎤 Kết quả chấm điểm")
        self.geometry("500x600")
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
            text_color="#22C55E"
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
            text_color="#94A3B8"
        ).pack()
        
        ctk.CTkLabel(
            score_frame,
            text=f"{total_score:.1f}",
            font=("Inter", 48, "bold"),
            text_color=score_color
        ).pack(pady=5)
        
        # Chi tiết các chỉ số
        details_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        details_frame.pack(fill="both", expand=True, pady=10)
        
        metrics = [
            ("Độ chính xác Pitch", "pitch_accuracy", "#3B82F6"),
            ("Độ ổn định Pitch", "pitch_stability", "#8B5CF6"),
            ("Độ nhất quán Âm lượng", "volume_consistency", "#10B981"),
            ("Độ chính xác Nhịp điệu", "timing_accuracy", "#EAB308")
        ]
        
        for label, key, color in metrics:
            self._create_metric_row(details_frame, label, score_result.get(key, 0), color)
        
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
        
        # Feedback
        feedback_frame = ctk.CTkFrame(main_frame)
        feedback_frame.pack(fill="x", pady=10)
        
        ctk.CTkLabel(
            feedback_frame,
            text=score_result.get("feedback", ""),
            font=("Inter", 14, "bold"),
            text_color="#22C55E",
            wraplength=450
        ).pack(pady=15, padx=15)
        
        # Nút đóng
        ctk.CTkButton(
            main_frame,
            text="Đóng",
            command=self.destroy,
            width=150,
            height=40,
            font=("Inter", 14, "bold")
        ).pack(pady=20)
    
    def _create_metric_row(self, parent, label, value, color):
        """Tạo một dòng hiển thị metric"""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=5)
        
        # Label
        ctk.CTkLabel(
            row,
            text=label,
            font=("Inter", 12),
            width=200,
            anchor="w"
        ).pack(side="left", padx=10)
        
        # Progress bar
        progress = ctk.CTkProgressBar(row, width=200, height=20)
        progress.pack(side="left", padx=10)
        progress.set(value / 100)
        progress.configure(progress_color=color)
        
        # Value
        ctk.CTkLabel(
            row,
            text=f"{value:.1f}",
            font=("Inter", 12, "bold"),
            text_color=color,
            width=60
        ).pack(side="left", padx=5)
    
    def _get_score_color(self, score):
        """Lấy màu dựa trên điểm số"""
        if score >= 90:
            return "#22C55E"  # Green
        elif score >= 80:
            return "#10B981"  # Green
        elif score >= 70:
            return "#EAB308"  # Yellow
        elif score >= 60:
            return "#F59E0B"  # Orange
        else:
            return "#EF4444"  # Red

class ColorButton(ctk.CTkButton):
    """Button đơn sắc với hiệu ứng hover và press"""
    def __init__(self, master, color=None, **kwargs):
        # Màu mặc định
        if color is None:
            color = "#22C55E"  # Green
        
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
        title_color = "#EF4444" if is_expired else "#22C55E"
        
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
            text_color="#94A3B8",
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
            text_color="#EF4444",
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
                    text_color="#94A3B8"
                ).pack(anchor="w", padx=15, pady=(10, 5))
                
                ctk.CTkLabel(
                    info_frame,
                    text=f"Ngày kích hoạt: {activation.get('activation_date', 'N/A')}",
                    font=("Inter", 11),
                    text_color="#94A3B8"
                ).pack(anchor="w", padx=15, pady=2)
        
        # Nút kích hoạt
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(pady=20)
        
        ColorButton(
            button_frame,
            text="✅ Kích hoạt",
            width=150,
            height=40,
            color="#22C55E",
            font=("Inter", 14, "bold"),
            command=self.activate
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            button_frame,
            text="❌ Thoát",
            width=150,
            height=40,
            font=("Inter", 14, "bold"),
            fg_color="#EF4444",
            hover_color="#DC2626",
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
                text_color="#EF4444"
            )
            return
        
        # Validate và kích hoạt
        success, message = backend.ActivationManager.activate(code)
        
        if success:
            self.message_label.configure(
                text=f"✅ {message}",
                text_color="#22C55E"
            )
            self.activated = True
            
            # Đợi 1.5 giây rồi đóng và gọi callback
            self.after(1500, self.close_and_continue)
        else:
            self.message_label.configure(
                text=f"❌ {message}",
                text_color="#EF4444"
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
            text_color="#22C55E"
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
            color="#6366F1",  # Indigo
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
            color="#6366F1",  # Indigo
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
            color="#22C55E",  # Green
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
                text_color="#EF4444",
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
                text_color="#EF4444",
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
        
        # 1. Cấu hình cửa sổ
        self.title("Quang Lưu Studio")
        self.geometry("1200x420")
        self.attributes("-topmost", True)
        
        # Lưới chính: Header(0) - Menu(1) - Body(2)
        self.grid_rowconfigure(2, weight=1) 
        self.grid_columnconfigure(0, weight=1)

        # --- KHỞI TẠO GIAO DIỆN ---
        self.setup_header() # Row 0
        self.setup_menu()   # Row 1
        self.setup_body()   # Row 2
        
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
                self.status_indicator.configure(text=status_text, text_color="#22C55E")
            else:
                self.status_indicator.configure(text="Chưa kết nối", text_color="#EF4444")

    def update_midi_status(self):
        """Cập nhật trạng thái MIDI hiện tại"""
        if hasattr(self, 'status_indicator'):
            if self.engine.is_midi_connected():
                port_name = self.engine.get_midi_port_name()
                self.status_indicator.configure(
                    text=f"Đã kết nối: {port_name}", 
                    text_color="#22C55E"
                )
            else:
                self.status_indicator.configure(text="Chưa kết nối", text_color="#EF4444")

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
        """Khu vực trên cùng: Tone, Chữ chạy, Điểm số, Trạng thái"""
        self.header_frame = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 10))
        self.header_frame.grid_columnconfigure(1, weight=1)

        # --- 1. KHU VỰC TONE (TRÁI) ---
        self.tone_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.tone_frame.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        ctk.CTkLabel(self.tone_frame, text="Tone Bài Hát:", font=("Inter", 14, "bold")).pack(side="left", padx=(0, 10))
        
        music_keys = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B", 
                     "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]
        self.tone_option = ctk.CTkOptionMenu(
            self.tone_frame, 
            values=music_keys, 
            width=100,
            command=self.on_tone_selected
        )
        self.tone_option.pack(side="left")

        # --- 2. KHU VỰC CHỮ CHẠY (GIỮA) ---
        self.marquee_container = ctk.CTkFrame(self.header_frame, fg_color="#0f172a", corner_radius=0, height=35)
        self.marquee_container.grid(row=0, column=1, padx=20, pady=10, sticky="ew")
        
        self.marquee_text = "✨ Bản quyền thuộc về Quang Lưu - Tuấn Phúc - 0973306273 | 0326405221 🎶🎶 --- Chúc bạn có những bản thu âm tuyệt vời! 🎤"
        self.marquee_label = ctk.CTkLabel(
            self.marquee_container, 
            text=self.marquee_text, 
            text_color="#FACC15", 
            font=("Inter", 16, "bold")
        )
        
        self.marquee_x = 800 
        self.marquee_label.place(x=self.marquee_x, y=5)
        self.animate_marquee()

        # --- 3. KHU VỰC ĐIỂM SỐ (GIỮA-PHẢI) ---
        self.score_frame = ctk.CTkFrame(self.header_frame, fg_color="#1e293b", corner_radius=8)
        self.score_frame.grid(row=0, column=2, padx=10, pady=8, sticky="e")
        
        # Container cho điểm số
        score_container = ctk.CTkFrame(self.score_frame, fg_color="transparent")
        score_container.pack(padx=8, pady=5)
        
        # Label "Điểm số"
        ctk.CTkLabel(
            score_container,
            text="Điểm số:",
            font=("Inter", 10),
            text_color="#94A3B8"
        ).pack()
        
        # Khung hiển thị điểm số lớn
        self.score_display_frame = ctk.CTkFrame(score_container, fg_color="#0f172a", corner_radius=5)
        self.score_display_frame.pack(pady=(3, 0))
        
        self.score_label = ctk.CTkLabel(
            self.score_display_frame,
            text="--",
            font=("Inter", 20, "bold"),
            text_color="#94A3B8",
            width=60
        )
        self.score_label.pack(padx=8, pady=3)

        # --- 4. KHU VỰC TRẠNG THÁI (PHẢI) ---
        self.status_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.status_frame.grid(row=0, column=3, padx=20, pady=10, sticky="e")

        ctk.CTkLabel(self.status_frame, text="Trạng thái:", font=("Inter", 12)).pack(side="left", padx=(0, 5))
        
        self.status_indicator = ctk.CTkLabel(
            self.status_frame, 
            text="Đang kiểm tra...", 
            text_color="#EAB308", 
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
                    text_color="#94A3B8"
                )
    
    def _get_score_color(self, score):
        """Lấy màu dựa trên điểm số"""
        if score >= 90:
            return "#22C55E"  # Green
        elif score >= 85:
            return "#10B981"  # Light Green
        elif score >= 80:
            return "#84CC16"  # Lime
        else:
            return "#EAB308"  # Yellow

    def animate_marquee(self):
        """Logic làm chữ chạy"""
        self.marquee_x -= 1.5
        
        if self.marquee_x < -700: 
            self.marquee_x = self.marquee_container.winfo_width() if self.marquee_container.winfo_width() > 0 else 800
            
        self.marquee_label.place(x=self.marquee_x, y=5)
        self.after(20, self.animate_marquee)
    
    def setup_menu(self):
        """Khu vực Menu Toolbar"""
        self.menu_frame = ctk.CTkFrame(self, height=50, corner_radius=0, fg_color="transparent")
        self.menu_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        
        # Danh sách nút Text với callback và màu sắc riêng
        text_btns = [
            ("Dò Tone", self.on_do_tone, "#3B82F6"),  # Blue
            ("Lấy Tone", self.on_lay_tone, "#8B5CF6"),  # Purple
            ("Tone Auto", self.on_tone_auto, "#10B981"),  # Green
            ("Bè", self.on_be, "#A855F7"),  # Purple - sẽ thay đổi màu khi toggle
            ("Vang", self.on_vang, "#EAB308"),  # Yellow - sẽ thay đổi màu khi toggle
            ("Nhạc", self.on_nhac, "#3B8ED0"),  # Blue
            ("Fix Méo", self.on_fix_meo, "#F59E0B"),  # Orange
            ("Chấm điểm", self.on_score, "#EC4899")  # Pink - Nút chấm điểm mới
        ]
        
        # Tạo nhóm nút Text (Bên trái) với màu sắc
        for btn_text, callback, color in text_btns:
            btn = ColorButton(
                self.menu_frame, 
                text=btn_text,
                width=80, 
                height=32,
                color=color,
                font=("Inter", 13, "bold"),
                command=callback
            )
            btn.pack(side="left", padx=(0, 5))
            
            # Lưu reference cho buttons Bè và Vang để có thể cập nhật màu
            if btn_text == "Bè":
                self.be_button = btn
            elif btn_text == "Vang":
                self.vang_button = btn

        # Danh sách nút Icon với callback và màu sắc riêng
        icon_btns = [
            {"icon": "🔍", "color": "#06B6D4", "callback": None},  # Cyan - Voice search
            {"icon": "💾", "color": "#10B981", "callback": self.on_save},  # Green - Save song
            {"icon": "📋", "color": "#8B5CF6", "callback": self._show_songs_list},  # Purple - Songs list
            {"icon": "📂", "color": "#6366F1", "callback": self.on_open},  # Indigo - Open file
            {"icon": "⏺️", "color": "#EF4444", "callback": self.on_record}  # Red - Record
        ]

        # Tạo nhóm nút Icon (Bên phải) với màu sắc
        for item in reversed(icon_btns):
            btn = ColorButton(
                self.menu_frame,
                text=item["icon"],
                width=40,
                height=32,
                color=item["color"],
                font=("Segoe UI Emoji", 18),
                command=item["callback"]
            )
            btn.pack(side="right", padx=(5, 0))
    
    # --- CALLBACKS CHO MENU BUTTONS ---
    def on_do_tone(self):
        """Dò Tone bài hát đang phát - thu âm trực tiếp từ hệ thống"""
        self._start_tone_detection()
    
    def on_lay_tone(self):
        # Chỉ gửi MIDI CC
        self.engine.send_midi(MIDI_CC["lay_tone"], 127)
    
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
                self.be_button.configure(fg_color="#10B981")  # Green khi ON
            else:
                self.be_button.configure(fg_color="#A855F7")  # Purple khi OFF
    
    def on_vang(self):
        """Toggle button Vang: bật/tắt"""
        self.vang_state = not self.vang_state
        # Gửi MIDI CC: 127 = ON, 0 = OFF
        midi_value = 127 if self.vang_state else 0
        self.engine.send_midi(MIDI_CC["vang"], midi_value)
        # Cập nhật màu button để hiển thị trạng thái
        if hasattr(self, 'vang_button'):
            if self.vang_state:
                self.vang_button.configure(fg_color="#10B981")  # Green khi ON
            else:
                self.vang_button.configure(fg_color="#EAB308")  # Yellow khi OFF
    
    def on_nhac(self):
        # Chỉ gửi MIDI CC
        self.engine.send_midi(MIDI_CC["nhac"], 127)
    
    def on_fix_meo(self):
        # Chỉ gửi MIDI CC
        self.engine.send_midi(MIDI_CC["fix_meo"], 127)
    
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
            text_color="#3B82F6"
        ).pack(pady=(10, 5))
        
        # Status label
        self._tone_status = ctk.CTkLabel(
            main_frame,
            text="🔊 Đang lắng nghe bài hát...",
            font=("Inter", 14),
            text_color="#94A3B8"
        )
        self._tone_status.pack(pady=5)
        
        # Countdown label lớn
        self._tone_countdown = ctk.CTkLabel(
            main_frame,
            text=f"{RECORD_DURATION}",
            font=("Inter", 48, "bold"),
            text_color="#22C55E"
        )
        self._tone_countdown.pack(pady=5)
        
        # Hướng dẫn
        ctk.CTkLabel(
            main_frame,
            text="💡 Hãy đảm bảo bài hát đang phát trên loa/headphone",
            font=("Inter", 11),
            text_color="#64748B",
            wraplength=380
        ).pack(pady=(5, 0))
        
        # Progress bar
        self._tone_progress = ctk.CTkProgressBar(main_frame, width=350, height=8)
        self._tone_progress.pack(pady=10)
        self._tone_progress.set(0)
        self._tone_progress.configure(progress_color="#3B82F6")
        
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
            text_color="#3B82F6"
        ).pack(pady=(10, 15))
        
        # Key display lớn
        key_frame = ctk.CTkFrame(main_frame, fg_color="#1e293b", corner_radius=15)
        key_frame.pack(pady=10, padx=30)
        
        ctk.CTkLabel(
            key_frame,
            text="TONE",
            font=("Inter", 12),
            text_color="#94A3B8"
        ).pack(pady=(15, 0))
        
        key_display = result.get("key_display", "?")
        ctk.CTkLabel(
            key_frame,
            text=key_display,
            font=("Inter", 48, "bold"),
            text_color="#22C55E"
        ).pack(pady=(5, 5))
        
        scale_text = "Trưởng (Major)" if result.get("scale") == "Major" else "Thứ (Minor)"
        ctk.CTkLabel(
            key_frame,
            text=scale_text,
            font=("Inter", 14),
            text_color="#94A3B8"
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
            text_color="#94A3B8"
        ).pack(anchor="w", pady=(0, 5))
        
        conf_bar = ctk.CTkProgressBar(conf_frame, width=350, height=15)
        conf_bar.pack(fill="x")
        conf_bar.set(max(0, min(1, confidence)))
        conf_color = "#22C55E" if confidence >= 0.7 else ("#EAB308" if confidence >= 0.5 else "#EF4444")
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
                text_color="#94A3B8"
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
                        text_color="#22C55E" if prev_key is None else "#EAB308"
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
                text_color="#94A3B8"
            ).pack(anchor="w", pady=(0, 3))
            
            for r in top_results[:3]:
                corr_pct = max(0, min(100, r["correlation"] * 100))
                color = "#22C55E" if r == top_results[0] else "#64748B"
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
            text_color="#10B981"
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
        """Bật/tắt recording"""
        self.is_recording = not self.is_recording
        # Record vẫn dùng hotkey vì chưa có MIDI CC mapping
        # Có thể thêm MIDI CC cho record nếu cần
        self.engine.send_hotkey(["ctrl", "shift", "r"])
    
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
            text_color="#22C55E"
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
            color="#3B82F6",
            font=("Inter", 14, "bold"),
            command=choose_file
        ).pack(side="left", padx=10)
        
        ColorButton(
            button_frame,
            text="▶️ YouTube URL",
            width=180,
            height=50,
            color="#EF4444",
            font=("Inter", 14, "bold"),
            command=choose_youtube
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            source_dialog,
            text="Hủy",
            command=source_dialog.destroy,
            width=100
        ).pack(pady=20)
    
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
            text_color="#EF4444"
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
            color="#EF4444",
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
        """Xử lý chấm điểm từ file hoặc YouTube"""
        # Hiển thị dialog đang xử lý
        processing_dialog = ctk.CTkToplevel(self)
        processing_dialog.title("Đang xử lý...")
        processing_dialog.geometry("350x180")
        processing_dialog.attributes("-topmost", True)
        processing_dialog.transient(self)
        
        status_label = ctk.CTkLabel(
            processing_dialog,
            text="🎤 Đang tải audio..." if is_youtube else "🎤 Đang phân tích audio...",
            font=("Inter", 16, "bold")
        )
        status_label.pack(pady=20)
        
        progress = ctk.CTkProgressBar(processing_dialog, width=300)
        progress.pack(pady=10)
        progress.set(0.1)
        
        # Xử lý trong thread riêng để không block UI
        def process_audio():
            try:
                print("=" * 60)
                print("🎤 [CHẤM ĐIỂM] Bắt đầu chấm điểm thủ công...")
                print(f"📂 Nguồn: {'YouTube URL' if is_youtube else 'File audio'}")
                print(f"🔗 Source: {source}")
                
                scoring_engine = backend.ScoringEngine()
                
                # Tải audio từ YouTube hoặc load từ file
                if is_youtube:
                    try:
                        status_label.configure(text="📥 Đang tải từ YouTube...")
                        progress.set(0.2)
                        
                        audio_path = scoring_engine.download_youtube_audio(source)
                        if not audio_path:
                            print("❌ [CHẤM ĐIỂM] Không thể tải audio từ YouTube")
                            processing_dialog.destroy()
                            self._show_error("Không thể tải audio từ YouTube. Vui lòng kiểm tra URL.")
                            return
                        
                        status_label.configure(text="🎤 Đang phân tích audio...")
                        progress.set(0.5)
                    except ImportError as e:
                        print(f"❌ [CHẤM ĐIỂM] Lỗi import: {e}")
                        processing_dialog.destroy()
                        self._show_error(str(e))
                        return
                    except Exception as e:
                        print(f"❌ [CHẤM ĐIỂM] Lỗi tải YouTube: {e}")
                        processing_dialog.destroy()
                        self._show_error(f"Lỗi tải YouTube: {str(e)}")
                        return
                else:
                    audio_path = source
                    progress.set(0.3)
                    print(f"📂 [CHẤM ĐIỂM] Sử dụng file audio: {audio_path}")
                
                # Load audio
                try:
                    if not scoring_engine.load_audio(audio_path):
                        print("❌ [CHẤM ĐIỂM] Không thể load audio file")
                        processing_dialog.destroy()
                        self._show_error("Không thể load file audio. Vui lòng kiểm tra file.")
                        return
                except ImportError as e:
                    print(f"❌ [CHẤM ĐIỂM] Lỗi import: {e}")
                    processing_dialog.destroy()
                    self._show_error(str(e))
                    return
                
                progress.set(0.7)
                status_label.configure(text="📊 Đang tính điểm...")
                
                # Tính điểm
                print("🧮 [CHẤM ĐIỂM] Đang tính điểm...")
                result = scoring_engine.calculate_score()
                
                # Cleanup temp file nếu là YouTube
                if is_youtube:
                    print("🧹 [CHẤM ĐIỂM] Đang dọn dẹp file tạm...")
                    scoring_engine.cleanup_temp_file()
                
                progress.set(1.0)
                processing_dialog.destroy()
                
                if result:
                    print("=" * 60)
                    print("✅ [CHẤM ĐIỂM] Kết quả chấm điểm:")
                    print(f"   📊 Điểm tổng: {result.get('total_score', 0):.1f}")
                    print(f"   🎵 Pitch accuracy: {result.get('pitch_accuracy', 0):.1f}")
                    print(f"   📈 Pitch stability: {result.get('pitch_stability', 0):.1f}")
                    print(f"   🔊 Volume consistency: {result.get('volume_consistency', 0):.1f}")
                    print(f"   ⏱️  Timing accuracy: {result.get('timing_accuracy', 0):.1f}")
                    print(f"   💬 Feedback: {result.get('feedback', 'N/A')}")
                    print("=" * 60)
                    
                    # Lưu điểm số và cập nhật hiển thị
                    self.current_score = result.get("total_score", 0)
                    self.update_score_display(self.current_score)
                    
                    # Hiển thị kết quả
                    ScoringDialog(self, result)
                else:
                    print("❌ [CHẤM ĐIỂM] Không thể tính điểm")
                    self._show_error("Không thể tính điểm. Vui lòng thử lại.")
            except Exception as e:
                print("=" * 60)
                print(f"❌ [CHẤM ĐIỂM] Lỗi: {e}")
                import traceback
                print(traceback.format_exc())
                print("=" * 60)
                processing_dialog.destroy()
                self._show_error(f"Lỗi: {str(e)}")
        
        import threading
        thread = threading.Thread(target=process_audio, daemon=True)
        thread.start()
    
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
            text_color="#EF4444",
            wraplength=350
        ).pack(pady=30, padx=20)
        
        ctk.CTkButton(
            error_dialog,
            text="Đóng",
            command=error_dialog.destroy,
            width=100
        ).pack(pady=10)
    
    def _show_save_song_dialog(self):
        """Dialog lưu bài hát"""
        save_dialog = ctk.CTkToplevel(self)
        save_dialog.title("💾 Lưu bài hát")
        save_dialog.geometry("500x300")
        save_dialog.attributes("-topmost", True)
        save_dialog.transient(self)
        
        ctk.CTkLabel(
            save_dialog,
            text="💾 Lưu bài hát",
            font=("Inter", 20, "bold"),
            text_color="#10B981"
        ).pack(pady=15)
        
        # Tên bài hát
        title_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        title_frame.pack(fill="x", padx=30, pady=10)
        
        ctk.CTkLabel(title_frame, text="Tên bài hát:", font=("Inter", 14)).pack(anchor="w", pady=(0, 5))
        title_entry = ctk.CTkEntry(title_frame, width=440, placeholder_text="Nhập tên bài hát")
        title_entry.pack(fill="x")
        
        # URL YouTube
        url_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        url_frame.pack(fill="x", padx=30, pady=10)
        
        ctk.CTkLabel(url_frame, text="URL YouTube:", font=("Inter", 14)).pack(anchor="w", pady=(0, 5))
        url_entry = ctk.CTkEntry(url_frame, width=440, placeholder_text="https://www.youtube.com/watch?v=...")
        url_entry.pack(fill="x")
        
        # Tone
        tone_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        tone_frame.pack(fill="x", padx=30, pady=10)
        
        ctk.CTkLabel(tone_frame, text="Tone bài hát:", font=("Inter", 14)).pack(anchor="w", pady=(0, 5))
        music_keys = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B", 
                     "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m", "Am", "Bbm", "Bm"]
        tone_option = ctk.CTkOptionMenu(tone_frame, values=music_keys, width=440)
        tone_option.pack(fill="x")
        # Sử dụng tone hiện tại từ header
        current_tone = getattr(self, 'current_tone', 'C')
        if hasattr(self, 'tone_option'):
            current_tone = self.tone_option.get()
        tone_option.set(current_tone)
        
        def save_song():
            title = title_entry.get().strip()
            url = url_entry.get().strip()
            tone = tone_option.get()
            
            if not title or not url:
                self._show_error("Vui lòng nhập đầy đủ tên bài hát và URL")
                return
            
            if "youtube.com" not in url and "youtu.be" not in url:
                self._show_error("URL không hợp lệ. Vui lòng nhập URL YouTube.")
                return
            
            if backend.SongManager.add_song(title, url, tone):
                save_dialog.destroy()
                # Hiển thị thông báo thành công
                success_label = ctk.CTkLabel(
                    self,
                    text="✅ Đã lưu bài hát!",
                    text_color="#10B981",
                    font=("Inter", 12, "bold")
                )
                success_label.place(relx=0.5, rely=0.1, anchor="center")
                self.after(2000, success_label.destroy)
            else:
                self._show_error("Lỗi khi lưu bài hát")
        
        button_frame = ctk.CTkFrame(save_dialog, fg_color="transparent")
        button_frame.pack(pady=20)
        
        ColorButton(
            button_frame,
            text="💾 Lưu",
            width=120,
            color="#10B981",
            command=save_song
        ).pack(side="left", padx=5)
        
        ctk.CTkButton(
            button_frame,
            text="Hủy",
            width=120,
            command=save_dialog.destroy
        ).pack(side="left", padx=5)
    
    def _show_songs_list(self):
        """Hiển thị danh sách bài hát đã lưu"""
        songs = backend.SongManager.load_songs()
        
        list_dialog = ctk.CTkToplevel(self)
        list_dialog.title("📋 Danh sách bài hát")
        list_dialog.geometry("700x500")
        list_dialog.attributes("-topmost", True)
        list_dialog.transient(self)
        
        # Header
        header_frame = ctk.CTkFrame(list_dialog)
        header_frame.pack(fill="x", padx=20, pady=(20, 10))
        
        ctk.CTkLabel(
            header_frame,
            text="📋 Danh sách bài hát đã lưu",
            font=("Inter", 20, "bold"),
            text_color="#22C55E"
        ).pack(pady=15)
        
        # Scrollable frame cho danh sách
        scroll_frame = ctk.CTkScrollableFrame(list_dialog)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        if not songs:
            ctk.CTkLabel(
                scroll_frame,
                text="Chưa có bài hát nào được lưu",
                font=("Inter", 14),
                text_color="#94A3B8"
            ).pack(pady=50)
        else:
            for song in songs:
                song_frame = ctk.CTkFrame(scroll_frame)
                song_frame.pack(fill="x", pady=5)
                
                # Thông tin bài hát
                info_frame = ctk.CTkFrame(song_frame, fg_color="transparent")
                info_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                
                ctk.CTkLabel(
                    info_frame,
                    text=song.get("title", "Không có tên"),
                    font=("Inter", 14, "bold")
                ).pack(anchor="w")
                
                ctk.CTkLabel(
                    info_frame,
                    text=f"Tone: {song.get('tone', 'N/A')} | {song.get('date_added', '')}",
                    font=("Inter", 11),
                    text_color="#94A3B8"
                ).pack(anchor="w", pady=(2, 0))
                
                # Nút Play và Delete
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
                    color="#22C55E",
                    command=make_play_func(song)
                ).pack(side="left", padx=2)
                
                ColorButton(
                    button_frame,
                    text="🗑️",
                    width=50,
                    height=35,
                    color="#EF4444",
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
        self.body_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        self.body_frame.grid_columnconfigure((0, 1, 2), weight=1)
        self.body_frame.grid_rowconfigure(0, weight=1)

        # === 1. CỘT TRÁI: TONE ===
        self.col_left = ctk.CTkFrame(self.body_frame)
        self.col_left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        ctk.CTkLabel(
            self.col_left, 
            text="ĐIỀU CHỈNH TONE", 
            font=("Inter", 16, "bold"), 
            text_color="#22C55E"
        ).pack(pady=15)

        # Tone Nhạc
        self.tone_music_frame = self.create_tone_control(self.col_left, "Tone Nhạc", "tone_music")
        
        # Tone Giọng
        self.tone_voice_frame = self.create_tone_control(self.col_left, "Tone Giọng", "tone_voice")

        # === 2. CỘT GIỮA: MIXER ===
        self.col_center = ctk.CTkFrame(self.body_frame)
        self.col_center.grid(row=0, column=1, sticky="nsew", padx=10)
        
        ctk.CTkLabel(
            self.col_center, 
            text="MIXER TỔNG", 
            font=("Inter", 16, "bold"), 
            text_color="#22C55E"
        ).pack(pady=(15, 10))

        slider_container = ctk.CTkFrame(self.col_center, fg_color="transparent")
        slider_container.pack(fill="both", expand=True)

        mix_config = [
            {"icon": "🔊", "color": "#3B8ED0", "label": "NHẠC", "cc": "mix_music", "range": (0, 100), "default": 70, "unit": ""},
            {"icon": "🎙️", "color": "#EF4444", "label": "MIC", "cc": "mix_mic", "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "📢", "color": "#EAB308", "label": "VANG", "cc": "mix_reverb", "range": (-10, 10), "default": 0, "unit": " dB"},
            {"icon": "👥", "color": "#A855F7", "label": "BÈ", "cc": "mix_backing", "range": (0, 100), "default": 70, "unit": ""}
        ]
        
        for i in range(4): 
            slider_container.grid_columnconfigure(i, weight=1)

        self.mixer_sliders = {}
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
                    # Chuyển đổi từ slider value (0-100) sang giá trị thực tế
                    if unit == " dB":
                        # Range -10 đến +10 dB
                        # Slider: 0 = -10dB, 50 = 0dB, 100 = +10dB
                        db_value = min_val + ((max_val - min_val) * (value / 100))
                        db_value = round(db_value, 1)
                        # Format hiển thị: +0.0 dB, -5.0 dB, +10.0 dB
                        label_widget.configure(text=f"{db_value:+.1f}{unit}")
                        # Chuyển đổi dB sang MIDI CC: -10dB=0, 0dB=64, +10dB=127
                        # Công thức: midi_value = ((db_value - min_val) / (max_val - min_val)) * 127
                        midi_value = int(((db_value - min_val) / (max_val - min_val)) * 127)
                        midi_value = max(0, min(127, midi_value))
                    else:
                        # Range 0-100 (cho Nhạc và Bè)
                        int_value = int(value)
                        label_widget.configure(text=f"{int_value}{unit}")
                        midi_value = int((value / 100) * 127)
                    
                    # Gửi MIDI CC
                    self.engine.send_midi(MIDI_CC[cc_key], midi_value)
                return update_val

            # Slider với màu sắc
            slider = ctk.CTkSlider(
                slider_container, 
                orientation="vertical", 
                height=120,
                width=20,
                from_=0, to=100,
                progress_color=item["color"],
                button_color=interpolate_color(item["color"], "#FFFFFF", 0.5),
                button_hover_color=interpolate_color(item["color"], "#FFFFFF", 0.7),
                button_length=12,
                command=make_update_func(val_label, item["cc"], min_val, max_val, unit)
            )
            # Set giá trị mặc định: 0 dB = giữa slider (50)
            if unit == " dB":
                slider.set(50)  # Giữa slider = 0 dB
            else:
                slider.set(default_val)
            slider.grid(row=1, column=i, padx=5, pady=5)
            
            self.mixer_sliders[item["cc"]] = slider
            
            # Icon
            ctk.CTkLabel(
                slider_container, 
                text=item["icon"], 
                text_color=item["color"],
                font=("Segoe UI Emoji", 32)
            ).grid(row=2, column=i, pady=(0, 0))

        # === 3. CỘT PHẢI: CHẾ ĐỘ HÁT ===
        self.col_right = ctk.CTkFrame(self.body_frame)
        self.col_right.grid(row=0, column=2, sticky="nsew", padx=(10, 0))
        
        ctk.CTkLabel(
            self.col_right, 
            text="CHẾ ĐỘ HÁT", 
            font=("Inter", 16, "bold"), 
            text_color="#22C55E"
        ).pack(pady=15)
        
        btn_container = ctk.CTkFrame(self.col_right, fg_color="transparent")
        btn_container.pack(fill="both", expand=True, padx=20)
        
        # Mode buttons với màu sắc riêng
        modes_config = [
            ("Đa Thể Loại", "#22C55E"),  # Green
            ("Bolero", "#F59E0B"),  # Orange
            ("Dân Ca", "#EF4444"),  # Red
            ("Lofi", "#8B5CF6"),  # Purple
            ("Remix", "#EC4899"),  # Pink
            ("Pop", "#3B82F6")  # Blue
        ]
        
        btn_container.grid_columnconfigure((0, 1), weight=1)
        
        self.mode_buttons = {}
        for i, (mode, color) in enumerate(modes_config):
            r = i // 2
            c = i % 2
            
            btn = ColorButton(
                btn_container, 
                text=mode, 
                height=45, 
                font=("Inter", 13, "bold"),
                color=color,
                command=lambda m=mode: self.on_mode_selected(m)
            )
            btn.grid(row=r, column=c, padx=5, pady=8, sticky="ew")
            self.mode_buttons[mode] = btn

    def create_tone_control(self, parent, label_text, cc_key):
        """Tạo điều khiển tone với nút +/-"""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(pady=10)
        
        ctk.CTkLabel(frame, text=label_text, font=("Inter", 14)).pack(pady=(0, 5))
        
        ctrl_frame = ctk.CTkFrame(frame, fg_color="transparent")
        ctrl_frame.pack()
        
        value_label = ctk.CTkLabel(
            ctrl_frame, 
            text="0", 
            width=40, 
            font=("Inter", 16, "bold")
        )
        
        def update_display(value):
            value_label.configure(text=f"{value:+d}")
            # Gửi MIDI CC (chuyển -12 to +12 thành 0-127)
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
        
        # Nút - với màu xanh dương
        ColorButton(
            ctrl_frame, 
            text="-", 
            width=40, 
            height=30, 
            color="#3B82F6",  # Blue
            command=decrease
        ).pack(side="left", padx=5)
        
        value_label.pack(side="left", padx=5)
        
        # Nút + với màu xanh lá
        ColorButton(
            ctrl_frame, 
            text="+", 
            width=40, 
            height=30, 
            color="#10B981",  # Green
            command=increase
        ).pack(side="left", padx=5)
        
        return frame

    def on_mode_selected(self, mode):
        """Xử lý khi chọn chế độ hát"""
        # Mode colors mapping
        mode_colors = {
            "Đa Thể Loại": "#22C55E",  # Green
            "Bolero": "#F59E0B",  # Orange
            "Dân Ca": "#EF4444",  # Red
            "Lofi": "#8B5CF6",  # Purple
            "Remix": "#EC4899",  # Pink
            "Pop": "#3B82F6"  # Blue
        }
        
        # Cập nhật màu cho nút - làm sáng nút được chọn
        for m, btn in self.mode_buttons.items():
            base_color = mode_colors.get(m, "#334155")
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
