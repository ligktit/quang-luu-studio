import codecs
import re

file_path = r"d:\Projects\LiveStudio\quang-luu-studio\frontend_qt.py"

with codecs.open(file_path, "r", "utf-8") as f:
    content = f.read()

# Add register_shortcuts at the end of __init__
append_code = '''
        # Auto launch (Studio One + Browser theo settings)
        self._auto_launch_apps()

        # YouTube URL Watcher — tự động dò tone khi mở YouTube
        self._start_youtube_watcher()

        # Đăng ký phím tắt trợ năng (Phase 1)
        try:
            from core.accessibility.shortcuts import register_shortcuts
            register_shortcuts(self)
        except Exception as e:
            print(f"[ACCESSIBILITY] Error registering shortcuts: {e}")
'''

content = content.replace(
'''        # Auto launch (Studio One + Browser theo settings)
        self._auto_launch_apps()

        # YouTube URL Watcher — tự động dò tone khi mở YouTube
        self._start_youtube_watcher()''', append_code)

with codecs.open(file_path, "w", "utf-8") as f:
    f.write(content)
print("Updated frontend_qt.py")
