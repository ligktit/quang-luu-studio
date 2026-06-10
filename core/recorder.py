"""
Quang Lưu Studio — Audio Recorder
Class: AudioRecorder
"""
import os
import sys
import queue
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
            
            # ── Reader threads: đọc stdout/stderr NGAY để pipe không bị đầy ──
            # FIX: readline() trên Windows pipe là blocking (select không hoạt
            # động với pipe) → có thể treo GUI thread vĩnh viễn. Thay bằng
            # thread đọc stdout đẩy vào queue; health-check chỉ poll queue.
            proc = self._process
            stdout_queue = queue.Queue()

            def _stdout_reader():
                # Thread này đọc stdout cho tới EOF — vừa phục vụ health-check
                # (qua queue) vừa là drain thường trực để worker không bị block.
                try:
                    for raw_line in proc.stdout:
                        s = raw_line.strip()
                        if s:
                            print(f"[RECORDER] Worker: {s}")
                        stdout_queue.put(raw_line)
                except Exception:
                    pass

            stderr_lines = []

            def _stderr_drain():
                # FIX: stderr=PIPE không được đọc → buffer đầy → worker block
                # giữa chừng. Drain liên tục + giữ lại vài dòng cuối cho error_msg.
                try:
                    for raw_line in proc.stderr:
                        s = raw_line.strip()
                        if s:
                            stderr_lines.append(s)
                            print(f"[RECORDER] Worker stderr: {s}")
                except Exception:
                    pass

            threading.Thread(target=_stdout_reader, daemon=True).start()
            threading.Thread(target=_stderr_drain, daemon=True).start()

            # ── Health-check: chờ worker gửi "STARTED" hoặc "ERROR" trong 5s ──
            started_ok = False
            error_msg = None
            import time
            deadline = time.time() + 5.0
            while time.time() < deadline:
                # Thử lấy 1 dòng stdout từ queue (non-blocking với timeout ngắn)
                try:
                    line = stdout_queue.get(timeout=0.1).strip()
                except queue.Empty:
                    line = None

                if line:
                    if line == "STARTED":
                        started_ok = True
                        break
                    elif line.startswith("ERROR"):
                        error_msg = line
                        break
                    continue  # Còn dòng khác có thể đang chờ

                # Kiểm tra process còn sống không (sau khi queue đã cạn)
                ret = self._process.poll()
                if ret is not None:
                    # Process đã thoát sớm → thất bại. Chờ chút cho stderr drain.
                    time.sleep(0.2)
                    stderr_out = " | ".join(stderr_lines[-3:])
                    error_msg = f"Worker thoát với exit code {ret}. {stderr_out[:200]}"
                    if ret == 3:
                        error_msg += "\n💡 Gợi ý: Thiết bị ghi âm có thể đang bị ứng dụng khác (như Studio One) chiếm quyền sử dụng (Exclusive Mode). Hãy chọn thiết bị khác hoặc dùng ASIOVADPRO."
                    break

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

            # _stdout_reader thread vẫn chạy tới EOF → đóng vai trò drain
            # thường trực, không cần thread drain riêng nữa.

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
            # FIX: patch là process-wide — nếu logic bắt message lỗi thì
            # mọi print trong app chết theo. Bọc try/except, fallback về
            # print gốc khi có sự cố.
            try:
                _orig_print(*args, **kwargs)
                msg = ' '.join(str(a) for a in args)
                clean = msg.strip()
                with _patch_lock:
                    if clean == 'STARTED':
                        self._started_event.set()
                    elif clean.startswith('ERROR:') and not self._worker_error:
                        self._worker_error = clean
            except Exception:
                try:
                    _orig_print(*args, **kwargs)
                except Exception:
                    pass

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

        except SystemExit as e:
            # FIX: worker gọi sys.exit(2/3) khi lỗi thiết bị — `except Exception`
            # không bắt SystemExit → thread chết mà không restore print/argv.
            code_val = e.code if e.code is not None else 0
            if code_val != 0:
                if not self._worker_error:
                    self._worker_error = f"ERROR: Worker thoát với exit code {code_val}"
                _orig_print(f"[RECORDER] Inline worker exited: code={code_val}", flush=True)
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
