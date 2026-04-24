import pytest
from unittest.mock import patch, MagicMock
from core.ytdlp_support import (
    make_ydl_opts, 
    _is_bot_challenge, 
    _is_cookie_db_access_error, 
    _describe_auth,
    run_with_auth_fallback,
    _map_browser_path_to_cookie_source,
    YouTubeAuthenticationRequiredError
)

import sys

@pytest.fixture(autouse=True)
def mock_yt_dlp():
    mock_yt_dlp_module = MagicMock()
    
    # We also need yt_dlp.utils.DownloadError
    class DownloadError(Exception):
        pass
        
    mock_utils = MagicMock()
    mock_utils.DownloadError = DownloadError
    mock_yt_dlp_module.utils = mock_utils
    mock_yt_dlp_module.DownloadError = DownloadError
    
    sys.modules['yt_dlp'] = mock_yt_dlp_module
    yield mock_yt_dlp_module
    if 'yt_dlp' in sys.modules:
        del sys.modules['yt_dlp']

# --- 13. Module: ytdlp_support.py ---

def test_make_ydl_opts_default():
    # Y-01
    opts = make_ydl_opts()
    assert "quiet" in opts
    assert "noplaylist" in opts

def test_make_ydl_opts_extra():
    # Y-02
    opts = make_ydl_opts(extra="value")
    assert opts["extra"] == "value"
    assert "quiet" in opts

def test_is_bot_challenge_true():
    # Y-03
    exc = Exception("ERROR: [youtube] 1234: Sign in to confirm you're not a bot. Use --cookies-from-browser.")
    assert _is_bot_challenge(exc) is True

def test_is_bot_challenge_false():
    # Y-04
    exc = Exception("ERROR: Video unavailable")
    assert _is_bot_challenge(exc) is False

def test_is_cookie_db_access_error():
    # Y-05
    exc = Exception("could not copy chrome cookie database")
    assert _is_cookie_db_access_error(exc) is True

def test_describe_auth_none():
    # Y-06
    assert _describe_auth({"kind": "none"}) == "khong dung cookie"

@patch("core.ytdlp_support._build_auth_attempts")
def test_run_with_auth_fallback_success_first(mock_build_auth, mock_yt_dlp):
    # Y-07
    mock_build_auth.return_value = [{"kind": "none"}]
    
    mock_ydl = MagicMock()
    mock_yt_dlp.YoutubeDL.return_value.__enter__.return_value = mock_ydl
    
    operation = MagicMock(return_value="SUCCESS")
    
    res = run_with_auth_fallback("http://yt.com", operation=operation)
    assert res == "SUCCESS"
    operation.assert_called_once_with(mock_ydl)

@patch("core.ytdlp_support._build_auth_attempts")
def test_run_with_auth_fallback_retry(mock_build_auth, mock_yt_dlp):
    # Y-08
    mock_build_auth.return_value = [{"kind": "none"}, {"kind": "browser", "browser": "chrome"}]
    
    import yt_dlp
    
    def operation(ydl):
        # Fail first time, succeed second
        if not ydl.params.get("cookiesfrombrowser"):
            raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
        return "SUCCESS"
    
    res = run_with_auth_fallback("http://yt.com", operation=operation)
    assert res == "SUCCESS"

@patch("core.ytdlp_support._build_auth_attempts")
def test_run_with_auth_fallback_fail_all(mock_build_auth, mock_yt_dlp):
    # Y-09
    mock_build_auth.return_value = [{"kind": "none"}]
    
    import yt_dlp
    
    def operation(ydl):
        raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")
    
    with pytest.raises(YouTubeAuthenticationRequiredError):
        run_with_auth_fallback("http://yt.com", operation=operation)

def test_map_browser_path_edge():
    # Y-10
    assert _map_browser_path_to_cookie_source("C:\\Program Files\\Microsoft\\Edge\\msedge.exe") == "edge"

def test_map_browser_path_chrome():
    # Y-11
    assert _map_browser_path_to_cookie_source("C:\\Program Files\\Google\\Chrome\\chrome.exe") == "chrome"
