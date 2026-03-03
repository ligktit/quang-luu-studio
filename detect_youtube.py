"""
YouTube Song Analyzer — Detects the YouTube URL currently open in the browser,
downloads the audio, and analyzes it for Key, Scale, and Tempo (BPM).

Supports: Google Chrome, Microsoft Edge, Mozilla Firefox, Brave, Opera, Vivaldi.
"""

import re
import os
import sys
import ctypes
import ctypes.wintypes
import tempfile
import warnings

import uiautomation as auto
import numpy as np

warnings.filterwarnings("ignore")

# Ensure ffmpeg is available (downloads a static binary if needed)
try:
    import static_ffmpeg
    static_ffmpeg.add_paths()
except ImportError:
    pass  # Will rely on system ffmpeg


# ──────────────────────────────────────────────────────────────
# Music theory constants (same as audio_processor.py)
# ──────────────────────────────────────────────────────────────

MAJOR_KEY_NAMES = ["C", "Db", "D", "Eb", "E", "F",
                   "Gb", "G", "Ab", "A", "Bb", "B"]
MINOR_KEY_NAMES = ["C", "C#", "D", "Eb", "E", "F",
                   "F#", "G", "G#", "A", "Bb", "B"]

MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                           2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                           2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


# ──────────────────────────────────────────────────────────────
# Browser detection
# ──────────────────────────────────────────────────────────────

def get_browser_windows():
    """Find all open browser windows and their handles."""
    browser_keywords = [
        "Google Chrome", "Microsoft​ Edge", "Mozilla Firefox",
        "Brave", "Opera", "Vivaldi", "Edge",
    ]

    results = []
    windows = []

    def enum_callback(hwnd, _):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                windows.append((hwnd, buf.value))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

    for hwnd, title in windows:
        for keyword in browser_keywords:
            if keyword.lower() in title.lower():
                results.append({"hwnd": hwnd, "title": title, "browser": keyword})
                break

    return results


def get_url_from_browser(hwnd):
    """Read the URL from a browser window's address bar using UI Automation."""
    try:
        control = auto.ControlFromHandle(hwnd)
        if control is None:
            return None

        edits = control.GetChildren()
        for child in edits:
            try:
                edit = child.EditControl(searchDepth=8)
                if edit and edit.Exists(0.1):
                    value = ""
                    try:
                        pattern = edit.GetValuePattern()
                        if pattern:
                            value = pattern.Value
                    except Exception:
                        pass
                    if not value:
                        try:
                            value = edit.GetWindowText() or ""
                        except Exception:
                            pass
                    if value and ("youtube.com" in value or "youtu.be" in value):
                        return _normalize_url(value)
            except Exception:
                continue

        edit = control.EditControl(searchDepth=10)
        if edit and edit.Exists(0.5):
            value = ""
            try:
                pattern = edit.GetValuePattern()
                if pattern:
                    value = pattern.Value
            except Exception:
                pass
            if not value:
                try:
                    value = edit.GetWindowText() or ""
                except Exception:
                    pass
            if value and ("youtube.com" in value or "youtu.be" in value):
                return _normalize_url(value)

    except Exception:
        pass

    return None


def _normalize_url(url):
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def extract_video_id(url):
    """Extract the YouTube video ID from a URL."""
    patterns = [
        r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def clean_video_url(url):
    """Strip playlist/radio params — keep only the single video URL."""
    video_id = extract_video_id(url)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return url


def detect_youtube_url():
    """Detect YouTube URL from open browser windows."""
    browsers = get_browser_windows()
    if not browsers:
        return None, None

    for bw in browsers:
        url = get_url_from_browser(bw["hwnd"])
        if url:
            video_id = extract_video_id(url)
            return url, bw["title"]

    return None, None


# ──────────────────────────────────────────────────────────────
# Audio download
# ──────────────────────────────────────────────────────────────

def download_audio(url, output_dir):
    """Download audio from YouTube URL using yt-dlp."""
    import yt_dlp
    import shutil

    output_path = os.path.join(output_dir, "audio.%(ext)s")

    # Try with ffmpeg conversion first, fall back to raw download
    has_ffmpeg = shutil.which("ffmpeg") is not None

    if has_ffmpeg:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_path,
            "noplaylist": True,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "192",
            }],
            "quiet": True,
            "no_warnings": True,
        }
    else:
        # No ffmpeg: download best audio as-is (webm/m4a)
        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": output_path,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "Unknown")

        # Find the downloaded file
        for f in os.listdir(output_dir):
            if f.startswith("audio."):
                return os.path.join(output_dir, f), title

    except Exception as e:
        print(f"  ❌ Download error: {e}")

    return None, None


# ──────────────────────────────────────────────────────────────
# Music analysis
# ──────────────────────────────────────────────────────────────

def analyze_audio(filepath):
    """Analyze audio file for key, scale, and tempo."""
    import librosa

    print("  ⏳ Loading audio...")
    y, sr = librosa.load(filepath, sr=22050, mono=True)
    duration = len(y) / sr

    print(f"  ⏳ Analyzing {duration:.1f}s of audio...")

    # --- Key & Scale detection ---
    print("  ⏳ Detecting key & scale...")
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    chroma_mean = np.mean(chroma, axis=1)

    best_corr = -1.0
    best_key = 0
    best_scale = "Major"

    for shift in range(12):
        rolled = np.roll(chroma_mean, -shift)
        corr_major = float(np.corrcoef(rolled, MAJOR_PROFILE)[0, 1])
        corr_minor = float(np.corrcoef(rolled, MINOR_PROFILE)[0, 1])

        if corr_major > best_corr:
            best_corr = corr_major
            best_key = shift
            best_scale = "Major"
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = shift
            best_scale = "Minor"

    if best_scale == "Major":
        key_name = MAJOR_KEY_NAMES[best_key]
    else:
        key_name = MINOR_KEY_NAMES[best_key]

    confidence = best_corr

    # --- Tempo / BPM ---
    print("  ⏳ Detecting tempo...")
    tempo = librosa.beat.tempo(y=y, sr=sr)
    bpm = float(tempo[0]) if len(tempo) > 0 else 0.0

    # --- Additional info ---
    # Camelot notation (for DJs)
    camelot = _get_camelot(best_key, best_scale)

    return {
        "key": key_name,
        "scale": best_scale,
        "bpm": bpm,
        "confidence": confidence,
        "duration": duration,
        "camelot": camelot,
    }


def _get_camelot(key_idx, scale):
    """Convert key/scale to Camelot Wheel notation (used by DJs)."""
    # Camelot major keys (outer wheel): 8B=C, 3B=Db, 10B=D, ...
    major_camelot = ["8B", "3B", "10B", "5B", "12B", "7B",
                     "2B", "9B", "4B", "11B", "6B", "1B"]
    # Camelot minor keys (inner wheel): 5A=Cm, 12A=C#m, 7A=Dm, ...
    minor_camelot = ["5A", "12A", "7A", "2A", "9A", "4A",
                     "11A", "6A", "1A", "8A", "3A", "10A"]

    if scale == "Major":
        return major_camelot[key_idx]
    else:
        return minor_camelot[key_idx]


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    print()
    print("═" * 55)
    print("  🎵 YouTube Song Analyzer")
    print("═" * 55)
    print()

    # Step 1: Detect YouTube URL
    print("🔍 Scanning browser for YouTube...")
    url, page_title = detect_youtube_url()

    if not url:
        print("  ❌ No YouTube page found in any browser.")
        print("  💡 Open a YouTube video in your browser and try again.")
        print()
        input("Press Enter to exit...")
        return

    video_id = extract_video_id(url)
    url = clean_video_url(url)  # Strip playlist/radio params
    print(f"  ✅ Found: {url}")
    if video_id:
        print(f"  🎬 Video ID: {video_id}")
    print()

    # Step 2: Download audio
    print("📥 Downloading audio...")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path, song_title = download_audio(url, tmpdir)

        if not audio_path:
            print("  ❌ Failed to download audio.")
            print()
            input("Press Enter to exit...")
            return

        print(f"  ✅ Downloaded: {song_title}")
        print()

        # Step 3: Analyze
        print("🎶 Analyzing song...")
        result = analyze_audio(audio_path)

    # Step 4: Display results
    print()
    print("═" * 55)
    print("  📊 ANALYSIS RESULTS")
    print("═" * 55)
    print()
    print(f"  🎵 Song:       {song_title}")
    print(f"  🔗 URL:        {url}")
    print()
    print(f"  🎹 Key:        {result['key']} {result['scale']}")
    print(f"  🎯 Confidence: {result['confidence']:.1%}")
    print(f"  🥁 Tempo:      {result['bpm']:.0f} BPM")
    print(f"  🎧 Camelot:    {result['camelot']}")
    print(f"  ⏱  Duration:   {int(result['duration']//60)}:{int(result['duration']%60):02d}")
    print()
    print("═" * 55)
    print()
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
