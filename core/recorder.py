"""
Quang Lưu Studio — Audio Recorder
Class: AudioRecorder
"""
import os
import sys
import subprocess
import threading
import tempfile


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
    
    def start_recording(self, output_dir="temp_audio"):
        """Bắt đầu thu âm"""
        if self.recording:
            return False
        
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
        
        # Chạy worker
        if getattr(sys, 'frozen', False):
            # Frozen mode: chạy worker code trong thread
            self._worker_thread = threading.Thread(
                target=self._run_worker_inline, daemon=True
            )
            self._worker_thread.start()
        else:
            # Dev mode: chạy subprocess
            worker_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "recorder_worker.py"
            )
            try:
                self._process = subprocess.Popen(
                    [sys.executable, worker_path, self.output_path, self._stop_flag_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                print(f"🎙️ [RECORDER] Started subprocess (PID={self._process.pid})")
            except Exception as e:
                print(f"❌ [RECORDER] Lỗi khởi tạo subprocess: {e}")
                self.recording = False
                return False
        
        return True
    
    def stop_recording(self):
        """Dừng thu âm"""
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
        
        return self.output_path
    
    def _run_worker_inline(self):
        """Chạy recorder worker inline (frozen mode)"""
        try:
            worker_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "recorder_worker.py"
            )
            # Fallback: try to find recorder_worker.py next to exe
            if not os.path.exists(worker_path):
                if getattr(sys, 'frozen', False):
                    worker_path = os.path.join(os.path.dirname(sys.executable), "recorder_worker.py")
            
            if os.path.exists(worker_path):
                with open(worker_path, 'r', encoding='utf-8') as f:
                    code = f.read()
                # Set sys.argv for the worker
                import sys as _sys
                old_argv = _sys.argv
                _sys.argv = ['recorder_worker.py', self.output_path, self._stop_flag_path]
                try:
                    exec(compile(code, worker_path, 'exec'))
                finally:
                    _sys.argv = old_argv
            else:
                print(f"❌ [RECORDER] recorder_worker.py not found")
        except Exception as e:
            print(f"❌ [RECORDER] Inline worker error: {e}")
    
    def cleanup(self):
        """Xóa file recording tạm"""
        if self.output_path and os.path.exists(self.output_path):
            try:
                os.remove(self.output_path)
            except Exception:
                pass
