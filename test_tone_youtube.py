"""
Dò tone từ YouTube URL.
Cách dùng: python test_tone_youtube.py <YouTube URL>
"""
import sys
import os
sys.path.insert(0, '.')


def setup_ffmpeg():
    """Setup FFmpeg từ imageio-ffmpeg nếu chưa có trong PATH"""
    try:
        import shutil
        if shutil.which("ffmpeg"):
            return  # Đã có sẵn
        import imageio_ffmpeg
        ffmpeg_path = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
        os.environ["PATH"] += os.pathsep + ffmpeg_path
    except Exception:
        pass


def main():
    setup_ffmpeg()

    if len(sys.argv) < 2:
        print("Cách dùng: python test_tone_youtube.py <YouTube URL>")
        print("Ví dụ:     python test_tone_youtube.py https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        sys.exit(1)

    url = sys.argv[1]
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    from backend import ToneDetector

    print("=" * 60)
    print(f"URL: {url}")
    print(f"Duration limit: {duration}s")
    print("=" * 60)

    result = ToneDetector.detect_key_from_youtube(url, duration_limit=duration)

    print("\n" + "=" * 60)
    if result:
        print(f"KET QUA: {result['key_display']} ({result['scale']})")
        print(f"Confidence: {result['confidence']:.4f}")
        print(f"Key index: {result['key_index']}")
        print()
        print("Top 5 keys:")
        for r in result.get('top_results', [])[:5]:
            marker = " <--" if r['key'] == result['key_display'] else ""
            print(f"  {r['key']:4s} ({r['scale']:5s}): {r['correlation']:.4f}{marker}")
    else:
        print("Khong the do tone!")
    print("=" * 60)


if __name__ == "__main__":
    main()
