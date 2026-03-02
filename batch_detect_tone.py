"""
Script tự động dò tone cho danh sách bài hát YouTube.
Phân tích từng đoạn 15 giây và lưu timeline vào manual_timelines.json.
"""
import sys
import os
import time
import json
import shutil

sys.path.insert(0, '.')

# Setup FFmpeg
def setup_ffmpeg():
    if shutil.which("ffmpeg"):
        return
    # Thử tìm ffmpeg.exe cùng thư mục
    local_ffmpeg = os.path.join(os.path.dirname(__file__), "ffmpeg.exe")
    if os.path.exists(local_ffmpeg):
        os.environ["PATH"] = os.path.dirname(local_ffmpeg) + os.pathsep + os.environ["PATH"]
        return
    try:
        import imageio_ffmpeg
        ffmpeg_path = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
        os.environ["PATH"] += os.pathsep + ffmpeg_path
    except Exception:
        pass

setup_ffmpeg()

from backend import ToneDetector, ManualToneTimeline, ToneCacheManager

SEGMENT_DURATION = 15  # Phân tích mỗi đoạn 15 giây

# Danh sách bài hát (đã loại trùng)
SONGS = [
    "https://www.youtube.com/watch?v=mrnJjMbkFls",
    "https://www.youtube.com/watch?v=xmneAJY0ZLQ",
    "https://www.youtube.com/watch?v=_b71xMUCZ-Q",
    "https://www.youtube.com/watch?v=Z7LYhsjwswU",
    "https://www.youtube.com/watch?v=U7eRMafKNC8",
    "https://www.youtube.com/watch?v=sZTp5X9JKqE",
    "https://youtu.be/sqsWXJI4iZ0",
    "https://youtu.be/_R8ECYoR1Fw",
]


def get_video_info(url):
    """Lấy title và duration của video YouTube"""
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown"),
                "duration": info.get("duration", 0),
                "id": info.get("id", ""),
            }
    except Exception as e:
        print(f"  ❌ Lỗi lấy info: {e}")
        return None


def download_audio(url, output_dir="temp_audio"):
    """Tải audio từ YouTube về WAV"""
    try:
        import yt_dlp
        import tempfile

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        temp_file = tempfile.NamedTemporaryFile(
            delete=False, suffix='.wav', dir=output_dir
        )
        temp_path = temp_file.name
        temp_file.close()

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_path.replace('.wav', '.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Tìm file
        base_path = temp_path.replace('.wav', '')
        for ext in ['.wav', '.mp3', '.m4a', '.webm']:
            candidate = base_path + ext
            if os.path.exists(candidate):
                return candidate

        return None
    except Exception as e:
        print(f"  ❌ Lỗi tải audio: {e}")
        return None


def analyze_full_song(audio_path, segment_sec=SEGMENT_DURATION):
    """
    Phân tích tone toàn bài theo từng segment.
    Trả về timeline: [{time, key_display, key_index, scale, confidence}, ...]
    """
    import librosa
    import numpy as np

    print(f"  📂 Loading audio: {audio_path}")
    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    total_duration = len(y) / sr
    print(f"  ⏱️  Duration: {total_duration:.1f}s ({total_duration/60:.1f} phút)")

    timeline = ToneDetector.detect_timeline_advanced(y, sr)

    return timeline, total_duration


def process_song(url, index, total):
    """Xử lý 1 bài hát: download → analyze → save timeline"""
    print(f"\n{'='*70}")
    print(f"📀 [{index}/{total}] {url}")
    print(f"{'='*70}")

    # 1. Lấy info
    print("  📋 Đang lấy thông tin video...")
    info = get_video_info(url)
    if not info:
        print("  ❌ Không thể lấy thông tin video!")
        return None

    title = info["title"]
    duration = info["duration"]
    print(f"  📌 Title: {title}")
    print(f"  ⏱️  Duration: {duration}s ({duration/60:.1f} phút)")

    # 2. Tải audio
    print("  ⬇️  Đang tải audio từ YouTube...")
    audio_path = download_audio(url)
    if not audio_path:
        print("  ❌ Không thể tải audio!")
        return None

    print(f"  ✅ Đã tải: {audio_path}")

    # 3. Phân tích tone
    print(f"  🎵 Đang phân tích tone (mỗi {SEGMENT_DURATION}s)...")
    try:
        timeline, actual_duration = analyze_full_song(audio_path)
    except Exception as e:
        print(f"  ❌ Lỗi phân tích: {e}")
        import traceback
        traceback.print_exc()
        return None

    # 4. Lưu timeline
    if timeline:
        success = ManualToneTimeline.save_timeline(url, title, timeline)
        if success:
            print(f"  ✅ Đã lưu timeline: {len(timeline)} entries")
        else:
            print(f"  ❌ Lỗi lưu timeline!")
    else:
        print(f"  ⚠️  Không có tone nào được phát hiện!")

    # 5. Cleanup audio file
    try:
        os.remove(audio_path)
        print(f"  🗑️  Đã xóa file tạm")
    except:
        pass

    return {
        "url": url,
        "title": title,
        "duration": duration,
        "timeline": timeline
    }


def main():
    print("=" * 70)
    print("🎵 BATCH TONE DETECTION - Dò Tone Thủ Công Hàng Loạt")
    print("=" * 70)
    print(f"📝 Tổng số bài: {len(SONGS)}")
    print(f"⏱️  Segment duration: {SEGMENT_DURATION}s")
    print()

    results = []
    start_time = time.time()

    for i, url in enumerate(SONGS, 1):
        result = process_song(url, i, len(SONGS))
        if result:
            results.append(result)

    elapsed = time.time() - start_time

    # Tổng kết
    print(f"\n{'='*70}")
    print(f"🏁 TỔNG KẾT")
    print(f"{'='*70}")
    print(f"⏱️  Thời gian: {elapsed:.1f}s ({elapsed/60:.1f} phút)")
    print(f"✅ Thành công: {len(results)}/{len(SONGS)} bài")
    print()

    for r in results:
        timeline = r["timeline"]
        tones = " → ".join(
            f"{ManualToneTimeline.seconds_to_time_str(e['time'])}:{e['key_display']}"
            for e in timeline[:8]
        )
        if len(timeline) > 8:
            tones += f" ... (+{len(timeline)-8})"
        print(f"  📀 {r['title']}")
        print(f"     {len(timeline)} entries | {tones}")
        print()

    print(f"💾 Tất cả đã lưu vào: manual_timelines.json")
    print("=" * 70)


if __name__ == "__main__":
    main()
