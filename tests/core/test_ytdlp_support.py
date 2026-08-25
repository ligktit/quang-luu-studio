import pytest
from unittest.mock import patch, MagicMock
from core.ytdlp_support import (
    make_ydl_opts, 
    _is_bot_challenge, 
    _is_cookie_db_access_error, 
    _describe_auth,
    run_with_auth_fallback,
    _map_browser_path_to_cookie_source,
    _is_format_unavailable,
    _expand_attempts,
    _apply_player_clients,
    _allow_missing_pot,
    _caller_player_clients,
    _is_terminal_error,
    _no_cookie_ladder,
    NO_COOKIE_PLAYER_CLIENTS,
    POT_PLAYER_CLIENTS,
    PURPOSE_VIDEO,
    YouTubeAuthenticationRequiredError
)

import sys


@pytest.fixture(autouse=True)
def no_helper_binaries():
    """Mặc định: máy KHÔNG có qjs.exe lẫn PO Token provider.

    Nếu không chốt, kết quả test đổi theo việc máy chạy test đã tải bộ sinh PO
    Token về hay chưa — thang client có thêm/bớt nấc. Test nào cần bật thì tự
    patch lại.
    """
    with patch("core.ytdlp_support.find_js_runtime", return_value=None), \
            patch("core.ytdlp_support.pot_provider.is_available", return_value=False), \
            patch("core.ytdlp_support.pot_provider.plugin_dir", return_value=None), \
            patch("core.ytdlp_support.pot_provider.cli_path", return_value=None):
        yield

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

def test_is_bot_challenge_curly_apostrophe():
    # yt-dlp in dấu nháy cong: "you’re" (U+2019)
    exc = Exception("ERROR: [youtube] abc: Sign in to confirm you\u2019re not a bot.")
    assert _is_bot_challenge(exc) is True


def test_is_cookie_db_access_error_dpapi():
    # Chrome >= 127 (App-Bound Encryption) — phải coi là lỗi NGUỒN cookie để
    # còn thử tiếp Firefox, không được làm chết cả chuỗi.
    exc = Exception("ERROR: Failed to decrypt with DPAPI. See https://... for more info")
    assert _is_cookie_db_access_error(exc) is True


def test_is_cookie_db_access_error_firefox_missing():
    exc = Exception("could not find firefox cookies database in 'C:\\Users\\a\\Profiles'")
    assert _is_cookie_db_access_error(exc) is True


def test_is_format_unavailable():
    exc = Exception("ERROR: [youtube] abc: Requested format is not available. Use --list-formats")
    assert _is_format_unavailable(exc) is True
    assert _is_format_unavailable(Exception("Video unavailable")) is False


def test_make_ydl_opts_does_not_force_player_clients():
    """Client phụ thuộc lần thử có cookie hay không → không ép ở đây nữa."""
    opts = make_ydl_opts()
    assert "player_client" not in (opts.get("extractor_args", {}).get("youtube") or {})


def test_expand_attempts_puts_android_first():
    attempts = _expand_attempts([{"kind": "none"}, {"kind": "browser", "browser": "firefox"}])
    assert attempts[0]["player_clients"][0] == "android"
    # None = để yt-dlp tự chọn client (khác với "ép danh sách rỗng")
    assert attempts[1]["kind"] == "none" and not attempts[1].get("player_clients")
    # lượt có cookie KHÔNG được ép client android (android không dùng được cookie)
    assert attempts[2]["kind"] == "browser"
    assert not attempts[2].get("player_clients")


@patch("core.ytdlp_support._configured_player_clients", return_value=["web_safari"])
def test_expand_attempts_respects_override(_mock):
    attempts = _expand_attempts([{"kind": "none"}, {"kind": "browser", "browser": "firefox"}])
    assert len(attempts) == 2
    assert all(a["player_clients"] == ["web_safari"] for a in attempts)


def test_apply_player_clients_sets_and_clears():
    opts = {}
    _apply_player_clients(opts, ["android"])
    assert opts["extractor_args"]["youtube"]["player_client"] == ["android"]
    _apply_player_clients(opts, None)
    assert "extractor_args" not in opts


# ── Tải được mà KHÔNG cần tài khoản: runtime JS + PO Token ──────────────────

def test_js_runtimes_declared_when_qjs_present():
    """Phải là DICT {ten: {config}} — truyền list vào là yt-dlp ném ValueError."""
    with patch("core.ytdlp_support.find_js_runtime", return_value=r"C:\app\qjs.exe"):
        opts = make_ydl_opts()
    assert opts["js_runtimes"] == {"deno": {}, "quickjs": {"path": r"C:\app\qjs.exe"}}


def test_js_runtimes_absent_when_no_runtime_found():
    """Không có runtime thì đừng khai báo gì — để yt-dlp tự tìm deno trên PATH."""
    assert "js_runtimes" not in make_ydl_opts()


def test_pot_provider_wired_when_installed():
    with patch("core.ytdlp_support.pot_provider.plugin_dir", return_value=r"C:\data\pot\plugins"), \
            patch("core.ytdlp_support.pot_provider.cli_path", return_value=r"C:\data\pot\bgutil-pot.exe"), \
            patch("core.ytdlp_support._register_plugin_dir") as register:
        opts = make_ydl_opts()
    assert opts["extractor_args"]["youtubepot-bgutilcli"]["cli_path"] == [r"C:\data\pot\bgutil-pot.exe"]
    register.assert_called_once_with(r"C:\data\pot\plugins")


def test_pot_provider_not_wired_when_binary_missing():
    """Chỉ có plugin mà thiếu binary thì đừng bật — sẽ chỉ tổ chậm."""
    with patch("core.ytdlp_support.pot_provider.plugin_dir", return_value=r"C:\data\pot\plugins"), \
            patch("core.ytdlp_support.pot_provider.cli_path", return_value=None):
        opts = make_ydl_opts()
    assert "youtubepot-bgutilcli" not in (opts.get("extractor_args") or {})


def test_ladder_without_pot_is_android_then_default():
    assert _no_cookie_ladder("audio") == [list(NO_COOKIE_PLAYER_CLIENTS), None]
    assert _no_cookie_ladder(PURPOSE_VIDEO) == [list(NO_COOKIE_PLAYER_CLIENTS), None]


def test_ladder_with_pot_puts_full_clients_first_for_video():
    """Có PO Token: video ưu tiên bộ client cho nhiều luồng progressive nét hơn;
    audio vẫn để android đứng đầu vì nhanh nhất và 360p đã thừa để phân tích."""
    with patch("core.ytdlp_support.pot_provider.is_available", return_value=True):
        assert _no_cookie_ladder(PURPOSE_VIDEO) == [
            None, list(POT_PLAYER_CLIENTS), list(NO_COOKIE_PLAYER_CLIENTS),
        ]
        assert _no_cookie_ladder("audio") == [
            list(NO_COOKIE_PLAYER_CLIENTS), None, list(POT_PLAYER_CLIENTS),
        ]


def test_expand_attempts_respects_caller_player_clients():
    """Bug cũ: danh sách client do caller đặt bị _apply_player_clients xoá sạch."""
    base_opts = {"extractor_args": {"youtube": {"player_client": ["web_safari"]}}}
    attempts = _expand_attempts(
        [{"kind": "none"}, {"kind": "browser", "browser": "firefox"}],
        base_opts=base_opts,
    )
    assert len(attempts) == 2
    assert all(a["player_clients"] == ["web_safari"] for a in attempts)


def test_caller_player_clients_reads_nested_key():
    assert _caller_player_clients(None) is None
    assert _caller_player_clients({}) is None
    assert _caller_player_clients(
        {"extractor_args": {"youtube": {"player_client": ["tv", " "]}}}
    ) == ["tv"]


def test_hotfix_pin_is_retired_on_this_version():
    """Khoá client do bản vá nhanh 1.7.2 để lại phải bị bỏ qua.

    Bộ cài đánh dấu app_config.json `onlyifdoesntexist` nên khoá đó sống sót qua
    lần cài đè — nếu không bỏ qua thì thang client thông minh chết ngay.
    """
    from core.ytdlp_support import _configured_player_clients

    values = {"youtube_player_clients": ["web_safari"],
              "youtube_player_clients_hotfix": True}
    with patch("core.ytdlp_support.AppConfig.get",
               side_effect=lambda k, d=None: values.get(k, d)):
        assert _configured_player_clients() is None

    # Không có cờ → khoá do kỹ thuật đặt tay vẫn phải được tôn trọng
    values.pop("youtube_player_clients_hotfix")
    with patch("core.ytdlp_support.AppConfig.get",
               side_effect=lambda k, d=None: values.get(k, d)):
        assert _configured_player_clients() == ["web_safari"]


def test_stream_forbidden_covers_all_three_faces():
    """403, ffmpeg sập, và SABR-missing-URL đều là 'link tải không dùng được'."""
    from core.ytdlp_support import _is_stream_forbidden
    assert _is_stream_forbidden(Exception("ERROR: unable to download video data: HTTP Error 403: Forbidden"))
    assert _is_stream_forbidden(Exception("ERROR: ffmpeg exited with code 3436169992"))
    assert _is_stream_forbidden(Exception(
        "Some android client https formats have been skipped as they are missing a URL"))
    assert not _is_stream_forbidden(Exception("Requested format is not available"))


@patch("core.ytdlp_support._build_auth_attempts")
def test_forbidden_does_not_trigger_missing_pot_pass(mock_build_auth, mock_yt_dlp):
    """Nới `formats=missing_pot` chính là thứ ĐẺ ra 403 — chạy lại cả thang lần
    hai vừa vô ích vừa tốn gấp đôi thời gian chờ của khách."""
    mock_build_auth.return_value = [{"kind": "none"}]
    import yt_dlp

    seen = []

    def operation(ydl):
        youtube = (ydl.params.get("extractor_args") or {}).get("youtube") or {}
        seen.append("missing_pot" in (youtube.get("formats") or []))
        raise yt_dlp.utils.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    with pytest.raises(RuntimeError) as err:
        run_with_auth_fallback("http://yt.com", operation=operation)
    # chỉ đúng 2 nấc không-cookie, KHÔNG có lượt missing_pot nào
    assert seen == [False, False]
    assert "PO Token" in str(err.value)


def test_ydl_opts_route_ytdlp_output_into_the_log():
    """yt-dlp in thẳng ERROR ra stderr ở từng nấc dù nấc sau thành công."""
    from core.ytdlp_support import _YtdlpLogger
    assert isinstance(make_ydl_opts()["logger"], _YtdlpLogger)
    # Người gọi vẫn được quyền tự đặt logger riêng
    sentinel = object()
    assert make_ydl_opts(logger=sentinel)["logger"] is sentinel


def test_terminal_errors_stop_the_ladder():
    assert _is_terminal_error(Exception("ERROR: Private video. Sign in")) is True
    assert _is_terminal_error(Exception("Video unavailable")) is True
    # Lỗi lạ KHÔNG phải terminal → phải thử tiếp nấc sau
    assert _is_terminal_error(Exception("The page needs to be reloaded.")) is False


@patch("core.ytdlp_support._build_auth_attempts")
def test_unknown_error_falls_through_to_next_rung(mock_build_auth, mock_yt_dlp):
    """Client `tv` từng trả 'The page needs to be reloaded' ngay nấc đầu và giết
    cả chuỗi. Lỗi lạ phải cho đi tiếp, chỉ nấc cuối mới được ném."""
    mock_build_auth.return_value = [{"kind": "none"}]
    import yt_dlp

    seen = []

    def operation(ydl):
        clients = ((ydl.params.get("extractor_args") or {}).get("youtube") or {}).get("player_client")
        seen.append(clients)
        if clients:
            raise yt_dlp.utils.DownloadError("The page needs to be reloaded.")
        return "SUCCESS"

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    assert run_with_auth_fallback("http://yt.com", operation=operation) == "SUCCESS"
    assert seen == [list(NO_COOKIE_PLAYER_CLIENTS), None]


@patch("core.ytdlp_support._build_auth_attempts")
def test_terminal_error_raises_immediately(mock_build_auth, mock_yt_dlp):
    mock_build_auth.return_value = [{"kind": "none"}]
    import yt_dlp

    seen = []

    def operation(ydl):
        seen.append(1)
        raise yt_dlp.utils.DownloadError("ERROR: Private video. Sign in if you've been granted access")

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    with pytest.raises(yt_dlp.utils.DownloadError):
        run_with_auth_fallback("http://yt.com", operation=operation)
    assert len(seen) == 1


def test_allow_missing_pot():
    relaxed = _allow_missing_pot({"extractor_args": {"youtube": {"player_client": ["android"]}}})
    assert relaxed["extractor_args"]["youtube"]["formats"] == ["missing_pot"]
    assert relaxed["extractor_args"]["youtube"]["player_client"] == ["android"]


@patch("core.ytdlp_support._build_auth_attempts")
def test_cookie_source_error_does_not_kill_chain(mock_build_auth, mock_yt_dlp):
    """Chrome báo DPAPI thì Firefox phía sau vẫn phải được thử."""
    mock_build_auth.return_value = [
        {"kind": "none"},
        {"kind": "browser", "browser": "chrome"},
        {"kind": "browser", "browser": "firefox"},
    ]
    import yt_dlp

    tried = []

    def operation(ydl):
        source = ydl.params.get("cookiesfrombrowser")
        tried.append(source)
        if source is None:
            raise yt_dlp.utils.DownloadError("Sign in to confirm you\u2019re not a bot")
        if source[0] == "chrome":
            raise yt_dlp.utils.DownloadError("ERROR: Failed to decrypt with DPAPI. See ...")
        return "SUCCESS"

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    assert run_with_auth_fallback("http://yt.com", operation=operation) == "SUCCESS"
    # 2 lượt đầu là không cookie (client android rồi mặc định)
    assert tried == [None, None, ("chrome",), ("firefox",)]


@patch("core.ytdlp_support._build_auth_attempts")
def test_format_error_retries_without_pot_filter(mock_build_auth, mock_yt_dlp):
    """Hết định dạng ở mọi client → lượt cuối bỏ lọc PO Token."""
    mock_build_auth.return_value = [{"kind": "none"}]
    import yt_dlp

    seen = []

    def operation(ydl):
        youtube = (ydl.params.get("extractor_args") or {}).get("youtube") or {}
        allows_missing = "missing_pot" in (youtube.get("formats") or [])
        seen.append(allows_missing)
        if not allows_missing:
            raise yt_dlp.utils.DownloadError("Requested format is not available")
        return "SUCCESS"

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    # 2 lượt không cookie (android rồi mặc định) đều trượt, lượt cuối mới đậu
    assert run_with_auth_fallback("http://yt.com", operation=operation) == "SUCCESS"
    assert seen == [False, False, True]


@patch("core.ytdlp_support._build_auth_attempts")
def test_format_error_message_points_at_ytdlp(mock_build_auth, mock_yt_dlp):
    mock_build_auth.return_value = [{"kind": "none"}]
    import yt_dlp

    def operation(ydl):
        raise yt_dlp.utils.DownloadError("Requested format is not available")

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    with pytest.raises(RuntimeError, match="yt-dlp"):
        run_with_auth_fallback("http://yt.com", operation=operation)


def test_map_browser_path_edge():
    # Y-10
    assert _map_browser_path_to_cookie_source("C:\\Program Files\\Microsoft\\Edge\\msedge.exe") == "edge"

def test_map_browser_path_chrome():
    # Y-11
    assert _map_browser_path_to_cookie_source("C:\\Program Files\\Google\\Chrome\\chrome.exe") == "chrome"


@patch("core.ytdlp_support._build_auth_attempts")
def test_cookie_lock_khong_duoc_che_lap_ly_do_that(mock_build_auth, mock_yt_dlp):
    """Lượt KHÔNG cookie hỏng vì lý do riêng, sau đó mọi nguồn cookie tịt vì
    trình duyệt đang khoá file.

    Thông báo "Chrome/Edge/Brave khoa file cookie" khi đó là hệ quả phụ, không
    phải nguyên nhân: nấc không-cookie có dùng cookie đâu mà khoá ảnh hưởng.
    Báo nó ra là chỉ sai đường cho người dùng đi xuất cookie vô ích.
    """
    mock_build_auth.return_value = [{"kind": "none"},
                                    {"kind": "browser", "browser": "chrome"}]
    import yt_dlp

    def operation(ydl):
        if ydl.params.get("cookiesfrombrowser"):
            raise yt_dlp.utils.DownloadError(
                "ERROR: Could not copy Chrome cookie database. Permission denied")
        raise yt_dlp.utils.DownloadError("ERROR: The page needs to be reloaded.")

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    with pytest.raises(Exception) as err:
        run_with_auth_fallback("http://yt.com", operation=operation)
    msg = str(err.value)
    assert "khoa file cookie" not in msg, f"van con che lap ly do that: {msg}"
    assert "page needs to be reloaded" in msg


@patch("core.ytdlp_support._build_auth_attempts")
def test_cookie_lock_van_duoc_bao_khi_no_dung_la_nguyen_nhan(mock_build_auth, mock_yt_dlp):
    """Ngược lại: nấc không-cookie bị YouTube đòi xác thực (đúng lúc cookie mới
    cứu được) mà nguồn cookie nào cũng bị khoá → phải báo đúng lỗi cookie."""
    mock_build_auth.return_value = [{"kind": "none"},
                                    {"kind": "browser", "browser": "chrome"}]
    import yt_dlp

    def operation(ydl):
        if ydl.params.get("cookiesfrombrowser"):
            raise yt_dlp.utils.DownloadError(
                "ERROR: Could not copy Chrome cookie database. Permission denied")
        raise yt_dlp.utils.DownloadError(
            "ERROR: Sign in to confirm you're not a bot. Use --cookies-from-browser")

    def _fake_ydl(opts):
        holder = MagicMock()
        holder.params = opts
        ctx = MagicMock()
        ctx.__enter__.return_value = holder
        return ctx

    mock_yt_dlp.YoutubeDL.side_effect = _fake_ydl

    with pytest.raises(Exception) as err:
        run_with_auth_fallback("http://yt.com", operation=operation)
    # Bot-challenge vẫn là thông điệp ưu tiên (cookie chính là cách chữa nó)
    assert "xac thuc" in str(err.value).lower() or "cookie" in str(err.value).lower()
