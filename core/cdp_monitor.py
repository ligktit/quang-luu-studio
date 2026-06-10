"""
Quang Lưu Studio — CDP YouTube Monitor
Tracks media playback status precisely using Chrome DevTools Protocol (CDP) via websocket.
"""
import json
import time
import threading
import urllib.request
import urllib.error

try:
    import websocket
    from websocket import WebSocketException
    _WEBSOCKET_AVAILABLE = True
except ImportError:
    _WEBSOCKET_AVAILABLE = False
    print("[CDP] Vui lòng cài đặt websocket-client: pip install websocket-client")

from core.config import CDP_DEBUG_PORT, CDP_CONNECT_TIMEOUT, CDP_POLL_INTERVAL

class CDPYouTubeMonitor:
    def __init__(self, port=None):
        self.port = port or CDP_DEBUG_PORT
        self.current_position = 0.0
        self.is_playing = False
        self.duration = 0.0
        self.is_connected = False
        self.target_url = ""
        
        self._ws = None
        self._running = False
        self._thread = None
        self._message_id = 1
        self._lock = threading.Lock()

    def _get_youtube_ws_url(self):
        """Tìm WebSocket URL của tab YouTube bằng cách quét các cổng từ 9222 đến 9232.
        Hỗ trợ cả browser thông thường và PWA YouTube (Edge/Chrome App)."""
        start_port = self.port
        end_port = self.port + 10  # Quét từ 9222 đến 9232

        # Các path YouTube hợp lệ (thêm /shorts)
        _YT_PATHS = ("youtube.com/watch", "youtube.com/shorts")

        for p in range(start_port, end_port + 1):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{p}/json")
                # Dùng 0.3s thay vì 1.0s — localhost không cần timeout cao
                with urllib.request.urlopen(req, timeout=0.3) as response:
                    data = json.loads(response.read().decode('utf-8'))

                for target in data:
                    if target.get('type') != 'page':
                        continue
                    tab_url = target.get('url', '')
                    if any(path in tab_url for path in _YT_PATHS):
                        return target.get('webSocketDebuggerUrl'), tab_url
            except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
                continue
            except Exception:
                pass

        return None, None

    def close_all_youtube_tabs(self):
        """Quét mọi port CDP, gửi Page.close cho từng tab/PWA YouTube.
        Trả về số tab đã yêu cầu đóng. Mở WS riêng cho mỗi target — không
        phụ thuộc kết nối monitor đang chạy, không bị giới hạn bởi
        _YT_PATHS (vốn chỉ match /watch và /shorts cho mục đích monitor)."""
        if not _WEBSOCKET_AVAILABLE:
            return 0

        closed = 0
        for port in range(self.port, self.port + 11):
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/json")
                with urllib.request.urlopen(req, timeout=0.3) as response:
                    targets = json.loads(response.read().decode('utf-8'))
            except (urllib.error.URLError, ConnectionRefusedError, TimeoutError):
                continue
            except Exception:
                continue

            for target in targets:
                if target.get('type') != 'page':
                    continue
                url = target.get('url', '')
                if 'youtube.com' not in url and 'youtu.be' not in url:
                    continue
                ws_url = target.get('webSocketDebuggerUrl')
                if not ws_url:
                    continue
                try:
                    ws = websocket.create_connection(ws_url, timeout=1.0)
                    ws.settimeout(1.0)
                    ws.send(json.dumps({"id": 1, "method": "Page.close"}))
                    try:
                        ws.recv()
                    except Exception:
                        pass
                    try:
                        ws.close()
                    except Exception:
                        pass
                    closed += 1
                    print(f"[CDP] Đã yêu cầu đóng tab YouTube: {url[:60]}")
                except Exception as e:
                    print(f"[CDP] Lỗi đóng tab {url[:50]}: {e}")
        return closed

    def start(self):
        if not _WEBSOCKET_AVAILABLE:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        
    def stop(self):
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)

    def _send_command(self, method, params=None):
        if not self._ws or not self.is_connected:
            return None

        # FIX: giữ _lock suốt cả send + recv-loop — _send_command được gọi
        # từ cả monitor thread lẫn GUI thread (set_player_volume); nếu chỉ
        # lock id counter thì 2 thread recv() xen kẽ sẽ "cướp" response của nhau.
        with self._lock:
            msg_id = self._message_id
            self._message_id += 1

            payload = {
                "id": msg_id,
                "method": method,
                "params": params or {}
            }

            try:
                self._ws.send(json.dumps(payload))
                # Giới hạn số lần recv để tránh vòng lặp vô hạn khi response không đến
                for _ in range(50):
                    raw = self._ws.recv()
                    response = json.loads(raw)
                    if 'id' in response and response['id'] == msg_id:
                        return response
                    # CDP events (không có 'id') → bỏ qua, đọc tiếp
                return None
            except Exception:
                self.is_connected = False
                return None

    def _evaluate_js(self, expression):
        response = self._send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        })
        if response and 'result' in response and 'result' in response['result']:
            result_obj = response['result']['result']
            if result_obj.get('type') != 'undefined':
                return result_obj.get('value')
        return None

    def _monitor_loop(self):
        while self._running:
            try:
                if not self.is_connected or not self._ws:
                    ws_url, page_url = self._get_youtube_ws_url()
                    if ws_url:
                        self._ws = websocket.create_connection(ws_url, timeout=CDP_CONNECT_TIMEOUT)
                        # Đặt recv timeout sau khi connect: tránh block vô hạn khi tab hang
                        self._ws.settimeout(5.0)
                        self.is_connected = True
                        self.target_url = page_url
                        print(f"[CDP] Đã kết nối tới tab YouTube: {page_url[:50]}...")
                    else:
                        self.is_connected = False
                        time.sleep(1.0)
                        continue

                # Query media info + current URL trong 1 lần gọi CDP
                # getPlayerState(): -1 (unstarted), 0 (ended), 1 (playing), 2 (paused), 3 (buffering), 5 (video cued)
                script = """
                (function() {
                    var player = document.querySelector('#movie_player');
                    if (player && typeof player.getCurrentTime === 'function') {
                        return {
                            time: player.getCurrentTime(),
                            state: player.getPlayerState(),
                            duration: player.getDuration(),
                            url: window.location.href
                        };
                    }
                    return null;
                })();
                """

                result = self._evaluate_js(script)

                if result:
                    self.current_position = float(result.get('time', 0))
                    self.duration = float(result.get('duration', 0))
                    self.is_playing = (result.get('state') == 1)
                    # Cập nhật target_url động — xử lý khi user navigate sang video mới trong cùng tab
                    page_url = result.get('url', '')
                    if page_url and 'youtube.com' in page_url:
                        self.target_url = page_url
                else:
                    self.is_playing = False
                    
                time.sleep(CDP_POLL_INTERVAL)
                
            except (WebSocketException, ConnectionResetError, BrokenPipeError, TimeoutError):
                # Discarded tab or closed browser
                self.is_connected = False
                self.is_playing = False
                if self._ws:
                    try: self._ws.close()
                    except Exception: pass
                    self._ws = None
                time.sleep(1.0)
            except Exception as e:
                print(f"[CDP] Lỗi loop: {e}")
                self.is_connected = False
                self.is_playing = False
                time.sleep(1.0)

    def wait_for_playback(self, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.is_playing:
                return True
            time.sleep(0.5)
        return False

    def set_player_volume(self, volume_percent):
        """Đặt âm lượng cho trình phát YouTube (0-100)."""
        if not self.is_connected:
            return False
        
        # YouTube player API: setVolume(number) nhận giá trị 0-100
        vol = max(0, min(100, int(volume_percent)))
        script = f"""
        (function() {{
            var player = document.querySelector('#movie_player');
            if (player && typeof player.setVolume === 'function') {{
                player.setVolume({vol});
                return true;
            }}
            return false;
        }})();
        """
        return self._evaluate_js(script)
