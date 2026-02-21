"""
Test dò tone với YouTube audio - Kiểm tra thuật toán trên audio thực tế.
Sử dụng ToneDetector.detect_key_from_youtube() để tải và phân tích.

Test case: Bài hát có key đã biết trước.
"""
import sys
sys.path.insert(0, '.')

from backend import ToneDetector

# Test cases: các bài hát nổi tiếng với key đã biết
# Format: (url, expected_key, expected_scale, description)
TEST_CASES = [
    # "Let It Be" - The Beatles → C Major
    # ("https://www.youtube.com/watch?v=QDYfEBY9NM4", "C", "Major", "Let It Be - The Beatles (C Major)"),
    # "Nơi Này Có Anh" - Sơn Tùng M-TP → Fm (F minor) ??? Check lại key chính xác
    # ("https://www.youtube.com/watch?v=FN7ALfpGxiI", "Fm", "Minor", "Nơi Này Có Anh - Sơn Tùng (F minor)"),
    
    # "Đừng Làm Trái Tim Anh Đau" - Sơn Tùng M-TP -> A Major
    # Kết quả thực tế là Fm (relative minor của Ab Major)
    ("https://www.youtube.com/watch?v=Llh9aT3nSMo&list=RDLlh9aT3nSMo&start_radio=1", "A", "Major", "Đừng Làm Trái Tim Anh Đau - Sơn Tùng (A Major)"),
]

def setup_ffmpeg():
    """Setup FFmpeg path using imageio-ffmpeg"""    
    try:
        import imageio_ffmpeg
        import os
        import shutil
        
        src_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        print(f"📦 Found FFmpeg at: {src_ffmpeg}")
        
        # Copy to current dir as ffmpeg.exe so yt-dlp can find it by name
        cwd = os.getcwd()
        dest_ffmpeg = os.path.join(cwd, "ffmpeg.exe")
        
        if not os.path.exists(dest_ffmpeg):
            print(f"📋 Copying to: {dest_ffmpeg}")
            shutil.copy2(src_ffmpeg, dest_ffmpeg)
            
        # Also try to find ffprobe if possible, or just hope ffmpeg is enough for audio extraction (usually is)
        # yt-dlp often needs ffprobe for post-processing. imageio-ffmpeg DOES NOT bundle ffprobe usually. 
        # But let's try.
        
        os.environ["PATH"] += os.pathsep + cwd
        print(f"✅ Setup FFmpeg in PATH: {cwd}")
        
    except ImportError:
        print("⚠️ Không thể import imageio-ffmpeg. Hãy chạy pip install imageio-ffmpeg")
    except Exception as e:
        print(f"⚠️ Error setting up ffmpeg: {e}")

def test_youtube_tone():
    setup_ffmpeg()
    print("=" * 70)
    print("TEST DO TONE - YOUTUBE AUDIO")
    print("=" * 70)
    
    for url, expected_key, expected_scale, description in TEST_CASES:
        print(f"\n--- Testing: {description} ---")
        print(f"URL: {url}")
        print(f"Expected: {expected_key} ({expected_scale})")
        
        result = ToneDetector.detect_key_from_youtube(url, duration_limit=30)
        
        if result:
            detected = result['key_display']
            confidence = result['confidence']
            scale = result['scale']
            print(f"Detected: {detected} ({scale}), confidence={confidence:.4f}")
            
            if detected == expected_key:
                print(f">>> PASS <<<")
            else:
                print(f">>> FAIL: Expected {expected_key} but got {detected} <<<")
                # Show top 5
                for r in result.get('top_results', []):
                    print(f"    {r['key']}: {r['correlation']:.4f}")
        else:
            print(f">>> FAIL: No result <<<")
    
    print("\n" + "=" * 70)

if __name__ == "__main__":
    test_youtube_tone()
