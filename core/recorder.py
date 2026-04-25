"""
Quang Lưu Studio — Audio Recorder
Class: AudioRecorder
"""
import os
import sys
import subprocess
import threading
import tempfile

from core.config import RECORDINGS_DIR


class AudioRecorder:
    """
    Thu âm MIX: loopback (nhạc phát ra loa) + microphone (giọng hát).
    Chạy recorder_worker.py trong process riêng biệt để tránh xung đột COM.
    """
    def __init__(self):
        self.recording = False
        self.output_path = None
        self._process = None
        self._stop_flag_path = None
        self._worker_thread = None
        self.last_error = None
        self._loopback_idx = -1
        self._mic_idx = -1
        # Event để thread báo hiệu "đã khởi động xong" hoặc "lỗi"
        self._started_event = threading.Event()
        self._worker_error = None  # Lỗi từ thread worker
    
    def start_recording(self, output_dir=None,
                         loopback_device_index: int = -1,
                         mic_device_index: int = -1):
        """Bắt đầu thu âm"""
        if self.recording:
            return False
        
        if output_dir is None:
            output_dir = RECORDINGS_DIR
        os.makedirs(output_dir, exist_ok=True)
        
        # Tạo file output
        self.output_path = os.path.join(
            output_dir, 
            f"recording_{int(__import__('time').time())}.wav"
        )
        
        # Tạo file flag (worker chạy khi file tồn tại, dừng khi bị xóa)
        self._stop_flag_path = os.path.join(output_dir, ".recording_flag")
        with open(self._stop_flag_path, "w") as f:
            f.write("recording")
        
        self.recording = True
        
        self.last_error = None
        
        # Lưu device indexes để _run_worker_inline truy cập được
        self._loopback_idx = loopback_device_index
        self._mic_idx = mic_device_index

        # Chạy worker (frozen và dev mode khác nhau)
        if getattr(sys, 'frozen', False):
            # Frozen mode: tìm recorder_worker.py đã bundle
            exe_dir = os.path.dirname(sys.executable)
            meipass = getattr(sys, '_MEIPASS', '')

            worker_path = None
            for candidate in [
                os.path.join(meipass, "recorder_worker.py"),         # _MEIPASS (one-file)
                os.path.join(exe_dir, "recorder_worker.py"),         # Bên cạnh exe
            ]:
                if candidate and os.path.exists(candidate):
                    worker_path = candidate
                    break

            if not worker_path:
                self.last_error = (
                    "Không tìm thấy recorder_worker.py. "
                    "Đảm bảo file này nằm cùng thư mục với QuangLuuStudio.exe"
                )
                print(f"[RECORDER] {self.last_error}")
                self.recording = False
                try:
                    os.remove(self._stop_flag_path)
                except Exception:
                    pass
                return False

            # Reset event trước khi start thread
            self._started_event.clear()
            self._worker_error = None

            self._worker_thread = threading.Thread(
                target=self._run_worker_from_file,
                args=(worker_path,),
                daemon=True
            )
            self._worker_thread.start()

            # Chờ event "STARTED" tối đa 8s
            import time
            started = self._started_event.wait(timeout=8.0)

            if not self._worker_thread.is_alive():
                # Thread đã thoát trước khi set event
                err = self._worker_error or "Worker thoát ngay khi khởi động"
                self.last_error = (
                    f"{err}. "
                    f"Vào ⚙️ Cài đặt → Nguồn thu nhạc để chọn đúng thiết bị."
                )
                print(f"[RECORDER] {self.last_error}")
                self.recording = False
                try:
                    os.remove(self._stop_flag_path)
                except Exception:
                    pass
                return False

            if not started:
                # Timeout nhưng thread vẫn alive → có thể đang init chậm, tiếp tục
                print("[RECORDER] Timeout chờ STARTED, nhưng thread vẫn chạy → tiếp tục")

            print("[RECORDER] Worker đã khởi động (frozen mode)")
            return True

        else:
            # Dev mode: chạy subprocess
            worker_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "recorder_worker.py"
            )
            try:
                self._process = subprocess.Popen(
                    [
                        sys.executable, worker_path,
                        self.output_path,
                        self._stop_flag_path,
                        str(loopback_device_index),
                        str(mic_device_index),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
                print(f"[RECORDER] Đã khởi động tiến trình ghi âm (PID={self._process.pid})")
            except Exception as e:
                self.last_error = f"Không thể khởi tạo subprocess: {e}"
                print(f"[RECORDER] {self.last_error}")
                self.recording = False
                return False
            
            # ── Health-check: chờ worker gửi "STARTED" hoặc "ERROR" trong 5s ──
            started_ok = False
            error_msg = None
            import time, select
            deadline = time.time() + 5.0
            while time.time() < deadline:
                # Kiểm tra process còn sống không
                ret = self._process.poll()
                if ret is not None:
                    # Process đã thoát sớm → thất bại
                    stderr_out = ""
                    try:
                        stderr_out = self._process.stderr.read()
                    except Exception:
                        pass
                    error_msg = f"Worker thoát với exit code {ret}. {stderr_out.strip()[:200]}"
                    if ret == 3:
                        error_msg += "\n💡 Gợi ý: Thiết bị ghi âm có thể đang bị ứng dụng khác (như Studio One) chiếm quyền sử dụng (Exclusive Mode). Hãy chọn thiết bị khác hoặc dùng ASIOVADPRO."
                    break
                
                # Thử đọc 1 dòng stdout (non-blocking)
                try:
                    line = self._process.stdout.readline()
                    if line:
                        line = line.strip()
                        print(f"[RECORDER] Worker: {line}")
                        if line == "STARTED":
                            started_ok = True
                            break
                        elif line.startswith("ERROR"):
                            error_msg = line
                            break
                except Exception:
                    pass
                
                time.sleep(0.1)
            
            if not started_ok:
                if error_msg is None:
                    error_msg = "Timeout: worker không phản hồi trong 5 giây"
                self.last_error = error_msg
                print(f"[RECORDER] {self.last_error}")
                # Dừng process
                try:
                    self._process.kill()
                except Exception:
                    pass
                self._process = None
                # Dọn flag file
                try:
                    os.remove(self._stop_flag_path)
                except Exception:
                    pass
                self.recording = False
                return False
            
            # Drain stdout trong background để không block pipe
            def _drain_stdout():
                try:
                    for line in self._process.stdout:
                        line = line.strip()
                        if line:
                            print(f"[RECORDER] Worker: {line}")
                except Exception:
                    pass
            threading.Thread(target=_drain_stdout, daemon=True).start()
        
        return True
    
    def stop_recording(self, save_path=None):
        """Dừng thu âm.

        Args:
            save_path: Nếu được cung cấp, file ghi âm sẽ được di chuyển tới đường dẫn này.
                       Trả về True nếu thành công, False nếu thất bại.
                       Nếu None, trả về đường dẫn file tạm (None nếu chưa có gì).
        """
        if not self.recording:
            return None
        
        self.recording = False
        
        # Xóa flag file để worker dừng
        if self._stop_flag_path and os.path.exists(self._stop_flag_path):
            try:
                os.remove(self._stop_flag_path)
            except Exception:
                pass
        
        # Đợi process/thread kết thúc
        if self._process:
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
            self._worker_thread = None
        
        if save_path:
            # Di chuyển file tạm → đường dẫn người dùng chọn
            if self.output_path and os.path.exists(self.output_path):
                # Kiểm tra file có dữ liệu thực (WAV header = 44 bytes, cần lớn hơn)
                file_size = os.path.getsize(self.output_path)
                if file_size <= 44:
                    self.last_error = "File ghi âm rỗng — không bắt được âm thanh từ WASAPI Loopback"
                    print(f"[RECORDER] {self.last_error}")
                    try:
                        os.remove(self.output_path)
                    except Exception:
                        pass
                    return False
                try:
                    import shutil
                    shutil.move(self.output_path, save_path)
                    self.output_path = save_path
                    return True
                except Exception as e:
                    self.last_error = f"Lỗi di chuyển file: {e}"
                    print(f"[RECORDER] {self.last_error}")
                    return False
            self.last_error = "Không tìm thấy file ghi âm tạm"
            print(f"[RECORDER] {self.last_error}")
            return False
        
        return self.output_path
    
    def _run_worker_from_file(self, worker_path):
        """
        Frozen mode: exec recorder_worker.py trong thread.
        Set _started_event khi worker print "STARTED".
        """
        import sys as _sys
        import builtins
        import threading as _threading

        old_argv = _sys.argv[:]
        _sys.argv = [
            'recorder_worker.py',
            self.output_path,
            self._stop_flag_path,
            str(self._loopback_idx),
            str(self._mic_idx),
        ]

        # FIX: Monkey-patch print để bắt "STARTED" / "ERROR".
        # Dùng lock để tránh race condition khi nhiều thread in cùng lúc.
        # QUAN TRỌNG: phải restore _orig_print trong finally — bản cũ bị quên.
        _orig_print = builtins.print
        _patch_lock = _threading.Lock()

        def _patched_print(*args, **kwargs):
            _orig_print(*args, **kwargs)
            msg = ' '.join(str(a) for a in args)
            clean = msg.strip()
            with _patch_lock:
                if clean == 'STARTED':
                    self._started_event.set()
                elif clean.startswith('ERROR:') and not self._worker_error:
                    self._worker_error = clean

        builtins.print = _patched_print

        try:
            _orig_print(f"[RECORDER] Exec worker: {worker_path}", flush=True)
            with open(worker_path, 'r', encoding='utf-8') as f:
                code = f.read()

            ns = {
                '__name__': '__main__',
                '__file__': worker_path,
                '__spec__': None,
            }
            exec(compile(code, worker_path, 'exec'), ns)

        except Exception as e:
            _orig_print(f"[RECORDER] Inline worker error: {e}", flush=True)
            import traceback
            traceback.print_exc()
        finally:
            # FIX: Restore builtins.print — nếu bỏ qua, mọi print sau này
            # trong app vẫn dùng patched version → side-effect ngầm.
            builtins.print = _orig_print
            _sys.argv = old_argv

    
    def cleanup(self):
        """Xóa file recording tạm"""
        if self.output_path and os.path.exists(self.output_path):
            try:
                os.remove(self.output_path)
            except Exception:
                pass
