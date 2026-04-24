import pytest
from unittest.mock import patch, MagicMock
import os
import sys

from core.utils import extract_video_id, find_ffmpeg

# --- 4.1 extract_video_id(url) ---

def test_extract_video_id_watch():
    # U-01: URL dạng watch?v=
    assert extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

def test_extract_video_id_youtu_be():
    # U-02: URL dạng youtu.be/
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

def test_extract_video_id_embed():
    # U-03: URL dạng embed/
    assert extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

def test_extract_video_id_shorts():
    # U-04: URL dạng shorts/
    assert extract_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

def test_extract_video_id_with_params():
    # U-05: URL có thêm params
    assert extract_video_id("https://youtu.be/dQw4w9WgXcQ?t=42") == "dQw4w9WgXcQ"

def test_extract_video_id_not_youtube():
    # U-06: URL không phải YouTube
    assert extract_video_id("https://vimeo.com/123456") is None

def test_extract_video_id_short_id():
    # U-07: Video ID ngắn hơn 11 ký tự
    assert extract_video_id("https://youtu.be/abc") is None

def test_extract_video_id_empty():
    # U-08: Chuỗi rỗng
    assert extract_video_id("") is None


# --- 4.2 find_ffmpeg() ---

@patch("shutil.which")
def test_find_ffmpeg_in_path(mock_which):
    # U-09: ffmpeg có trong PATH
    mock_which.return_value = "/usr/bin/ffmpeg"
    assert find_ffmpeg() == "/usr/bin"

@patch("shutil.which", return_value=None)
@patch("os.path.isfile", return_value=False)
@patch("glob.glob", return_value=[])
def test_find_ffmpeg_not_found(mock_glob, mock_isfile, mock_which):
    # U-10: ffmpeg không tồn tại
    assert find_ffmpeg() is None

@patch("shutil.which", return_value=None)
@patch("os.environ.get", return_value="C:\\FakeAppData")
@patch("glob.glob")
@patch("os.path.isdir", return_value=True)
def test_find_ffmpeg_winget(mock_isdir, mock_glob, mock_environ_get, mock_which):
    # U-11: ffmpeg tồn tại ở WinGet path
    mock_glob.return_value = ["C:\\FakeAppData\\Microsoft\\WinGet\\Packages\\ffmpeg\\ffmpeg.exe"]
    # os.path.isfile is used in subsequent checks, but we should return the WinGet dir
    # before reaching them. Wait, find_ffmpeg uses os.path.isfile in step 2.
    # Let's mock os.path.isfile carefully.
    
    def mock_isfile_side_effect(path):
        if path == "C:\\FakeAppData\\FFmpeg\\ffmpeg.exe":
            return False
        return False

    with patch("os.path.isfile", side_effect=mock_isfile_side_effect):
        assert find_ffmpeg() == "C:\\FakeAppData\\Microsoft\\WinGet\\Packages\\ffmpeg"
