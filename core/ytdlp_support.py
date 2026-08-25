"""
Shared yt-dlp helpers for YouTube requests that may require browser cookies.
"""
import json
import logging
import os

from core.config import AppConfig, DATA_DIR, FFMPEG_LOCATION, SETTINGS_FILE
from core.utils import find_js_runtime
from core import pot_provider, ytdlp_update

log = logging.getLogger(__name__)

# Ưu tiên bản yt-dlp nạp ngoài NGAY khi module này được nạp — mọi `import yt_dlp`
# trong app đều nằm bên trong hàm nên tới đây vẫn còn kịp.
ytdlp_update.activate_override()

# Firefox first: its cookie DB is NOT locked while the browser is running.
# Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi) lock the
# SQLite Cookies file, so they will fail with "Could not copy ... cookie database"
# whenever the browser is open.
DEFAULT_COOKIE_BROWSERS = ("firefox", "edge", "chrome", "brave", "opera", "vivaldi")

# Auto-snapshot saved here so the app can use it on next run after export
_AUTO_COOKIE_FILE = os.path.join(DATA_DIR, "youtube_cookies.txt")

# Danh sách player_client dùng cho lần thử KHÔNG cookie.
#
# Vì sao lại là android: từ 2025 YouTube bắt buộc "GVS PO Token" cho mọi client
# họ web/tv. Không có PO Token thì yt-dlp bỏ hết định dạng → "Requested format is
# not available", còn ép lấy (formats=missing_pot) thì tải về dính 403 Forbidden.
# Các client họ android KHÔNG cần PO Token — nhưng cũng KHÔNG dùng được cookie
# (SUPPORTS_COOKIES=False), nên chúng chỉ có tác dụng ở lần thử không cookie.
#
# Đo ngày 17/08/2026 trên IP đã bị YouTube gắn cờ nghi ngờ (mọi client web đều bị
# "Sign in to confirm you're not a bot"): 3 video của khách × cả tải đủ lẫn tải
# 50 giây đầu = 9/9 lần thành công trong ~2,5 giây, không cần cookie.
#
# Danh sách cũ ("tv_embedded", "web_safari", "default", "ios") đã hỏng: yt-dlp
# 2026.07 báo thẳng `Skipping unsupported client "tv_embedded"`, còn web_safari
# và ios đều đòi PO Token.
#
# ⚠️ Cập nhật 18/08/2026: bảng chính thức của yt-dlp (PO Token Guide) cho thấy
# đường android cũng đang mục — `android`/`ios` nay đòi CẢ GVS lẫn Player PO
# Token, `tv_simply` đòi GVS, còn `android_vr` chỉ còn format 18 nếu thiếu token.
# Nó vẫn chạy hôm nay nên giữ làm đường nhanh, nhưng lời giải THẬT là tự sinh PO
# Token bằng `core/pot_provider.py` — xem `_no_cookie_ladder()` bên dưới.
#
# ⚠️ `tv_simply` ĐÃ BỊ LOẠI khỏi nấc này (18/08/2026). Nó đòi GVS PO Token, nên
# khi máy đã có bộ sinh token thì yt-dlp gọi bgutil ở MỌI lần bóc thông tin —
# đo được +9 giây mỗi lần, mà dò tone thì chạy trên từng bài. Bỏ đi:
#   nấc 1 gồm tv_simply : 11,5s / 12,6s / 11,4s
#   nấc 1 không tv_simply:  2,6s /  1,8s /  1,9s   ← cùng y hệt danh sách định
# dạng audio (itag 140 @129,5k / itag 251 @130,9k), không mất gì.
# Thiếu token thì `tv_simply` vốn cũng vô dụng; có token thì đã có nấc
# POT_PLAYER_CLIENTS lo.
NO_COOKIE_PLAYER_CLIENTS = ("android", "android_vr")

# Có PO Token thì các client này dùng được ĐẦY ĐỦ định dạng mà vẫn không cookie.
# Đo 18/08/2026 (có PO Token, KHÔNG cookie) trên cùng một video:
#   web_safari → 11 định dạng, 7 luồng progressive, tới 1080p
#   mweb       → 34 định dạng, 1 progressive, tới 2160p
#   mặc định   → 37 định dạng, 7 progressive, tới 2160p (7,9 giây)
#   android    →  5 định dạng, 1 progressive, 360p (2,2 giây — nhanh nhất)
# `tv` bị loại: trả thẳng "The page needs to be reloaded" / "DRM protected".
POT_PLAYER_CLIENTS = ("web_safari", "mweb")

# Tên cũ, giữ lại cho mã ngoài còn tham chiếu.
DEFAULT_PLAYER_CLIENTS = NO_COOKIE_PLAYER_CLIENTS

# Mục đích của lệnh gọi — quyết định thứ tự thang client ở lượt không cookie.
PURPOSE_AUDIO = "audio"   # chấm điểm, dò tone, lấy tiêu đề/thời lượng
PURPOSE_VIDEO = "video"   # trình phát karaoke nhúng (cần luồng progressive)


BOT_CHALLENGE_MARKERS = (
    "sign in to confirm you're not a bot",
    "sign in to confirm youre not a bot",
    "confirm you're not a bot",
    "use --cookies-from-browser or --cookies",
)
COOKIE_DB_ACCESS_MARKERS = (
    "could not copy chrome cookie database",
    "could not copy edge cookie database",
    "could not copy brave cookie database",
    "could not copy opera cookie database",
    "could not copy vivaldi cookie database",
    "permission denied",
)
# Lỗi thuộc về NGUỒN COOKIE chứ không phải video — phải thử nguồn kế tiếp, tuyệt
# đối không được dừng cả chuỗi. Ví dụ máy chỉ có Chrome ≥127 (App-Bound
# Encryption → "Failed to decrypt with DPAPI") mà Firefox mới là nguồn dùng được.
COOKIE_SOURCE_MARKERS = (
    "failed to decrypt with dpapi",
    "cookies database in",          # "could not find firefox cookies database in '...'"
    "unsupported browser",
    "no such file or directory",
)
# yt-dlp bóc được video nhưng KHÔNG còn định dạng nào chọn được. Gần như luôn là
# do bản yt-dlp quá cũ so với thay đổi mới nhất của YouTube. Đây cũng là lỗi phải
# thử tiếp nguồn khác chứ không phải lỗi chết người.
FORMAT_UNAVAILABLE_MARKERS = (
    "requested format is not available",
    "no video formats found",
    "unable to extract player response",
    "failed to extract any player response",
    "this video is drm protected",
    "only images are available",
)
# yt-dlp bóc được video và CÓ danh sách định dạng, nhưng link tải không dùng
# được. Ba biểu hiện của cùng một chuyện, đều gặp trên client android ngày
# 18/08/2026:
#   1. `HTTP Error 403: Forbidden` — link cấp cho client/PO Token khác.
#   2. `ffmpeg exited with code 3436169992` — khi tải 50 giây đầu
#      (`download_ranges`), yt-dlp giao việc cho ffmpeg; link rỗng/403 làm ffmpeg
#      sập với mã khó hiểu. Không phải lỗi ffmpeg: đã thử cả 8.0.1 lẫn 9.0.1,
#      sập y hệt.
#   3. `missing a URL ... SABR-only streaming experiment` (yt-dlp #12482) —
#      YouTube trả định dạng KHÔNG kèm link.
# Phải tách khỏi FORMAT_UNAVAILABLE_MARKERS vì cách chữa ngược nhau: lỗi hết
# định dạng thì lượt cuối nới `formats=missing_pot`, còn ở đây nới ra chính là
# thứ ĐẺ ra 403 — hỏng thêm mà còn tốn gấp đôi thời gian chờ.
STREAM_FORBIDDEN_MARKERS = (
    "http error 403",
    "403: forbidden",
    "unable to download video data",
    "ffmpeg exited with code",
    "missing a url",
    "sabr-only",
)
# Lỗi thuộc về BẢN THÂN VIDEO — thử nguồn/client khác cũng vô ích, dừng ngay cho
# nhanh. Mọi lỗi KHÔNG nằm trong danh sách này đều được coi là "có thể do client
# vừa dùng" và sẽ thử tiếp nấc sau: đã từng mất cả chuỗi chỉ vì client `tv` trả
# "The page needs to be reloaded" ngay ở nấc đầu.
TERMINAL_MARKERS = (
    "private video",
    "video unavailable",
    "this video has been removed",
    "removed by the uploader",
    "is not available in your country",
    "blocked it in your country",
    "sign in to confirm your age",
    "join this channel",
    "members-only",
    "video is unavailable",
    "incomplete youtube id",
    "unsupported url",
)


class YouTubeAuthenticationRequiredError(RuntimeError):
    """Raised when yt-dlp cannot bypass YouTube's anti-bot check."""


class _YtdlpLogger:
    """Hứng mọi thông báo của yt-dlp, đẩy vào nhật ký thay vì in ra stderr.

    Vì sao cần: thang thử có nhiều nấc, nấc trượt là chuyện BÌNH THƯỜNG và đã
    được xử lý. Nhưng yt-dlp vẫn in thẳng `ERROR: ... HTTP Error 403: Forbidden`
    ra stderr ở từng nấc, kể cả khi nấc sau thành công — khách thấy một màn hình
    đầy chữ ERROR đỏ trong lúc app đang chạy đúng, còn kỹ thuật thì tưởng hỏng.
    `quiet=True` không chặn được vì lỗi đi qua `trouble()` chứ không qua
    `to_screen()`.

    Lỗi THẬT không mất đi: nó nằm trong ngoại lệ mà `run_with_auth_fallback` ném
    ra sau khi hết nấc, kèm hướng dẫn khắc phục.
    """

    __slots__ = ()

    def debug(self, message):
        log.debug("[yt-dlp] %s", message)

    def info(self, message):
        log.debug("[yt-dlp] %s", message)

    def warning(self, message):
        log.debug("[yt-dlp] %s", message)

    def error(self, message):
        log.debug("[yt-dlp] %s", message)


_YTDLP_LOGGER = _YtdlpLogger()


def export_cookies_to_file(browser="chrome", profile=None, output_path=None, log_prefix="[COOKIE]"):
    """
    Export browser cookies to a Netscape-format .txt file.

    The target browser MUST be fully closed before calling this — Chromium-based
    browsers lock their cookie DB while running.  Firefox is the exception and
    can be exported while open.

    Returns the output path on success, None on failure.
    """
    try:
        import yt_dlp
    except ImportError:
        log.error("yt-dlp not installed — cannot export cookies")
        return None

    if output_path is None:
        output_path = _AUTO_COOKIE_FILE

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cookie_source = (browser, profile) if profile else (browser,)
    opts = make_ydl_opts(
        cookiesfrombrowser=cookie_source,
        cookiefile=output_path,
        skip_download=True,
        quiet=True,
        no_warnings=True,
    )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info("https://www.youtube.com/", download=False)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            log.info("%s Cookies exported from %s → %s", log_prefix, browser, output_path)
            return output_path
        return None
    except Exception as exc:
        log.warning("%s Could not export cookies from %s: %s", log_prefix, browser, exc)
        return None


def make_ydl_opts(**extra_opts):
    """Create a baseline yt-dlp options dict used across the app."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # Cap per-connection read/connect ops so a stalled CDN or auth wall does
        # not hang the detection thread indefinitely. The engine-level watchdog
        # provides the outer deadline.
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
    }
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    opts.update(extra_opts)
    # Sau update: người gọi vẫn có quyền tự đặt logger riêng nếu cần.
    opts.setdefault("logger", _YTDLP_LOGGER)
    _apply_js_runtimes(opts)
    _apply_pot_provider(opts)
    _apply_default_extractor_args(opts)
    return opts


def _apply_js_runtimes(opts):
    """Chỉ cho yt-dlp biết runtime JavaScript đi kèm app.

    yt-dlp mặc định chỉ bật `deno` và tự tìm trên PATH. Máy khách không có Deno,
    nên phải khai báo thêm `quickjs` trỏ vào `qjs.exe` gói kèm. Giữ `deno` ở
    đầu (ưu tiên cao hơn) để máy nào sẵn Deno thì vẫn dùng bản tốt hơn.

    Định dạng tham số của thư viện là DICT `{ten: {config}}` — khác CLI
    (`--js-runtimes deno:/path`); truyền list vào là yt-dlp ném ValueError.
    """
    if "js_runtimes" in opts:
        return

    configured = (AppConfig.get("js_runtime_path", "") or "").strip()
    path = configured or find_js_runtime()
    if not path:
        return

    opts["js_runtimes"] = {"deno": {}, "quickjs": {"path": path}}


def _apply_pot_provider(opts):
    """Bật plugin sinh PO Token (nếu máy đã tải về) — xem core/pot_provider.py."""
    plugin_dir = pot_provider.plugin_dir()
    cli = pot_provider.cli_path()
    if not (plugin_dir and cli):
        return

    _register_plugin_dir(plugin_dir)

    extractor_args = dict(opts.get("extractor_args") or {})
    if "youtubepot-bgutilcli" not in extractor_args:
        extractor_args["youtubepot-bgutilcli"] = {"cli_path": [cli]}
    opts["extractor_args"] = extractor_args


def _register_plugin_dir(directory):
    """Đưa thư mục plugin vào `yt_dlp.globals.plugin_dirs`.

    Bản CLI của yt-dlp làm việc này từ tuỳ chọn `--plugin-dirs`; dùng qua thư
    viện thì không ai làm hộ, nên phải tự set — và phải set TRƯỚC khi khởi tạo
    `YoutubeDL()` đầu tiên vì plugin chỉ được nạp một lần.
    """
    try:
        from yt_dlp.globals import plugin_dirs
    except Exception as exc:      # bản yt-dlp quá cũ, chưa có khung plugin
        log.debug("yt-dlp khong ho tro plugin_dirs: %s", exc)
        return

    current = list(plugin_dirs.value or ["default"])
    if directory not in current:
        # Đặt TRƯỚC "default": nếu máy khách lỡ có một bản bgutil khác cài sẵn
        # (cùng tên module `getpot_bgutil*`), thư mục nào đứng trước sẽ thắng.
        # Phải là bản do app tải về thì `cli_path` mới trỏ đúng binary.
        plugin_dirs.value = [directory] + current


def _apply_default_extractor_args(opts):
    """Đưa danh sách player_client do người dùng ép (nếu có) vào opts.

    KHÔNG ép danh sách mặc định ở đây nữa: client dùng được phụ thuộc vào việc
    lần thử đó có cookie hay không (xem `NO_COOKIE_PLAYER_CLIENTS`), nên việc
    chọn được làm ở `_expand_attempts`.
    """
    override = _configured_player_clients()
    if not override:
        return

    existing = opts.get("extractor_args") or {}
    youtube = dict(existing.get("youtube") or {})
    if "player_client" not in youtube:
        youtube["player_client"] = list(override)

    merged = dict(existing)
    merged["youtube"] = youtube
    opts["extractor_args"] = merged


def _configured_player_clients():
    """Danh sách client do kỹ thuật ép trong app_config.json (nếu có).

    Cho phép chữa cháy trên một máy cụ thể mà không phải build lại app:
        "youtube_player_clients": ["android", "web_safari"]
    """
    # Máy từng chạy bản vá nhanh cho 1.7.2 (tools/chan_doan/VaNhanh172.bat) bị
    # khoá cứng một client. Bộ cài đánh dấu app_config.json `onlyifdoesntexist`
    # nên khoá đó SỐNG SÓT qua lần cài 1.7.3 và sẽ giết thang client thông minh
    # — đúng thứ 1.7.3 sinh ra để làm. Cờ này là dấu vết bản vá để lại; thấy nó
    # thì bỏ qua khoá và quay về hành vi mặc định.
    if AppConfig.get("youtube_player_clients_hotfix", False):
        log.info(
            "[YTDLP] Bo qua youtube_player_clients cua ban va nhanh 1.7.2 - "
            "ban nay da co thang client rieng"
        )
        return None

    value = AppConfig.get("youtube_player_clients", None)
    if isinstance(value, str):
        value = [part.strip() for part in value.split(",")]
    if not isinstance(value, (list, tuple)):
        return None
    clients = [str(item).strip() for item in value if str(item).strip()]
    return clients or None


def extract_info_with_auth(url, ydl_opts=None, download=False, log_prefix="[YTDLP]",
                           purpose=PURPOSE_AUDIO):
    """Run `extract_info` with automatic auth fallback when YouTube blocks access."""
    return run_with_auth_fallback(
        url,
        ydl_opts=ydl_opts,
        log_prefix=log_prefix,
        operation=lambda ydl: ydl.extract_info(url, download=download),
        purpose=purpose,
    )


def download_with_auth(url, ydl_opts=None, log_prefix="[YTDLP]", purpose=PURPOSE_AUDIO):
    """Run `download` with automatic auth fallback when YouTube blocks access."""
    return run_with_auth_fallback(
        url,
        ydl_opts=ydl_opts,
        log_prefix=log_prefix,
        operation=lambda ydl: ydl.download([url]),
        purpose=purpose,
    )


def run_with_auth_fallback(url, ydl_opts=None, log_prefix="[YTDLP]", operation=None,
                           purpose=PURPOSE_AUDIO):
    """
    Execute a yt-dlp operation, retrying with cookies from browser / file if
    YouTube responds with a bot-confirmation challenge.

    `purpose` quyết định thứ tự thang player_client ở lượt không cookie —
    xem `_no_cookie_ladder()`.
    """
    if operation is None:
        raise ValueError("operation is required")

    try:
        import yt_dlp
    except ImportError:
        raise ImportError("Thu vien 'yt-dlp' chua duoc cai dat. Vui long chay: pip install yt-dlp")

    base_opts = make_ydl_opts(**(ydl_opts or {}))
    attempts = _expand_attempts(_build_auth_attempts(), purpose=purpose,
                                base_opts=base_opts)
    state = {"last_error": None, "auth_blocked": False,
             "cookie_db_blocked": False, "format_blocked": False,
             "stream_forbidden": False, "no_cookie_error": None}

    found, result = _run_attempts(yt_dlp, base_opts, attempts, operation, log_prefix, state)
    if found:
        return result

    # Mọi client đều bị YouTube giấu định dạng vì thiếu PO Token. Lượt cuối: bảo
    # yt-dlp ĐỪNG loại các định dạng thiếu PO Token (`formats=missing_pot`). Tải
    # về vẫn có thể dính 403, nhưng ít nhất lấy được tiêu đề/thời lượng video —
    # đủ để app theo dõi thời điểm hết bài.
    if state["format_blocked"]:
        print(f"{log_prefix} Thu lai lan cuoi, khong loai dinh dang thieu PO Token...")
        found, result = _run_attempts(
            yt_dlp, _allow_missing_pot(base_opts), attempts, operation, log_prefix, state
        )
        if found:
            return result

    last_error = state["last_error"]
    if state["auth_blocked"]:
        raise YouTubeAuthenticationRequiredError(_build_auth_error_message()) from last_error
    if state["format_blocked"]:
        raise RuntimeError(_build_format_error_message()) from last_error
    if state["stream_forbidden"]:
        raise RuntimeError(_build_forbidden_error_message()) from last_error
    # Chi bao "trinh duyet khoa cookie" khi do THAT SU la thu chan duong. Nac
    # khong-cookie co dung toi cookie dau - neu chinh no hong vi ly do rieng thi
    # cai khoa cookie phia sau chi la he qua phu, bao ra la chi sai duong cho
    # nguoi dung di xuat cookie vo ich.
    if state["cookie_db_blocked"] and state["no_cookie_error"] is None:
        raise RuntimeError(_build_cookie_db_error_message()) from last_error
    if state["no_cookie_error"] is not None:
        raise state["no_cookie_error"]
    if last_error:
        raise last_error
    raise RuntimeError("yt-dlp khong tra ve ket qua")


def _run_attempts(yt_dlp, base_opts, attempts, operation, log_prefix, state):
    """Chạy hết chuỗi nguồn xác thực với một bộ tuỳ chọn.

    Trả `(True, ket_qua)` nếu có nguồn nào chạy được, `(False, None)` nếu hết
    nguồn. Chỉ ném ngoại lệ với lỗi thật sự không cứu được bằng nguồn khác
    (video riêng tư, mất mạng…). Mọi lỗi thuộc về cookie hay định dạng đều được
    ghi vào `state` rồi thử tiếp — bug cũ là `raise` ngay tại đây, nên chỉ cần
    Chrome báo "Failed to decrypt with DPAPI" là Firefox phía sau không bao giờ
    được thử.
    """
    for index, auth in enumerate(attempts):
        current_opts = dict(base_opts)
        _apply_auth(current_opts, auth)
        _apply_player_clients(current_opts, auth.get("player_clients"))

        if index > 0:
            print(f"{log_prefix} Dang thu {_describe_auth(auth)}...")

        try:
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                return True, operation(ydl)
        except yt_dlp.utils.DownloadError as exc:
            state["last_error"] = exc
            if _is_bot_challenge(exc):
                state["auth_blocked"] = True
                if index == 0:
                    print(f"{log_prefix} YouTube yeu cau xac thuc, chuyen sang thu cookie trinh duyet...")
                continue
            if _is_format_unavailable(exc):
                state["format_blocked"] = True
                print(
                    f"{log_prefix} {_describe_auth(auth)}: YouTube khong tra ve dinh dang "
                    f"tai duoc, thu nguon khac..."
                )
                continue
            if auth.get("kind") != "none" and _is_cookie_db_access_error(exc):
                state["cookie_db_blocked"] = True
                print(
                    f"{log_prefix} Khong doc duoc {_describe_auth(auth)} "
                    f"(cookie database dang bi khoa), thu nguon khac..."
                )
                continue
            if _is_stream_forbidden(exc):
                state["stream_forbidden"] = True
                print(
                    f"{log_prefix} {_describe_auth(auth)}: link tai khong dung duoc "
                    f"({_short_reason(exc)}), thu nguon khac..."
                )
                continue
            if _is_terminal_error(exc) or index == len(attempts) - 1:
                raise
            if auth.get("kind") == "none":
                # Giu lai ly do THAT cua nac khong-cookie: no khong duoc roi vao
                # last_error roi bi cac loi cookie phia sau ghi de.
                state["no_cookie_error"] = exc
            print(
                f"{log_prefix} {_describe_auth(auth)} bao loi la ({_short_reason(exc)}), "
                f"thu nguon khac..."
            )
            continue
        except Exception as exc:
            state["last_error"] = exc
            if auth.get("kind") != "none":
                print(f"{log_prefix} Khong dung duoc {_describe_auth(auth)} ({exc.__class__.__name__}), thu nguon khac...")
                continue
            raise

    return False, None


def _no_cookie_ladder(purpose):
    """Thứ tự thử player_client cho lượt KHÔNG cookie.

    Mỗi phần tử là một lượt riêng; `None` nghĩa là để yt-dlp tự chọn client.

    - Có PO Token (đã tải bgutil): bộ client mặc định của yt-dlp bung ra đầy đủ
      định dạng mà vẫn không cần cookie, nên với video nó đứng đầu — client
      android bị YouTube ghim ở 360p, xem quá xấu trên màn hình karaoke.
    - Không có PO Token: chỉ còn đường android, y như trước.

    Với audio (chấm điểm/dò tone) thì android luôn đứng đầu: nhanh nhất (~2,2s)
    và format 18 đã có sẵn AAC — thừa sức cho việc phân tích cao độ.
    """
    android = list(NO_COOKIE_PLAYER_CLIENTS)
    if not pot_provider.is_available():
        return [android, None]
    if purpose == PURPOSE_VIDEO:
        return [None, list(POT_PLAYER_CLIENTS), android]
    return [android, None, list(POT_PLAYER_CLIENTS)]


def _expand_attempts(attempts, purpose=PURPOSE_AUDIO, base_opts=None):
    """Nhân bản lần thử KHÔNG cookie thành nhiều lượt theo thang client.

    Client họ android không cần PO Token nên thường là thứ DUY NHẤT còn tải được
    trên máy bị YouTube gắn cờ — nhưng chúng không dùng được cookie, nên chỉ có
    nghĩa ở lượt không cookie. Các lượt cookie giữ nguyên (không ép client).
    """
    override = _configured_player_clients() or _caller_player_clients(base_opts)
    if override:
        # Kỹ thuật ép tay trong app_config, hoặc caller đã cố ý chọn client
        # → tôn trọng, không tự thêm lượt nào.
        return [dict(auth, player_clients=list(override)) for auth in attempts]

    ladder = _no_cookie_ladder(purpose)
    expanded = []
    for auth in attempts:
        if auth.get("kind") != "none":
            expanded.append(dict(auth))
            continue
        for clients in ladder:
            expanded.append(dict(auth, player_clients=list(clients) if clients else None))
    return expanded


def _caller_player_clients(opts):
    """Danh sách client do chính người gọi đặt trong extractor_args (nếu có).

    Bug cũ: `_apply_player_clients` xoá thẳng khoá này ở mọi lượt, nên tham số
    `extractor_args={"youtube": {"player_client": [...]}}` mà trình phát nhúng
    truyền vào chưa bao giờ có hiệu lực.
    """
    if not opts:
        return None
    clients = ((opts.get("extractor_args") or {}).get("youtube") or {}).get("player_client")
    if not clients:
        return None
    return [str(item).strip() for item in clients if str(item).strip()] or None


def _apply_player_clients(opts, clients):
    """Ép danh sách player_client cho một lần thử (None = để yt-dlp tự chọn)."""
    extractor_args = dict(opts.get("extractor_args") or {})
    youtube = dict(extractor_args.get("youtube") or {})

    if clients:
        youtube["player_client"] = list(clients)
    else:
        youtube.pop("player_client", None)

    if youtube:
        extractor_args["youtube"] = youtube
    else:
        extractor_args.pop("youtube", None)

    if extractor_args:
        opts["extractor_args"] = extractor_args
    else:
        opts.pop("extractor_args", None)


def _allow_missing_pot(opts):
    """Bảo yt-dlp giữ lại cả những định dạng thiếu PO Token."""
    relaxed = dict(opts)
    extractor_args = dict(relaxed.get("extractor_args") or {})
    youtube = dict(extractor_args.get("youtube") or {})
    formats = list(youtube.get("formats") or [])
    if "missing_pot" not in formats:
        formats.append("missing_pot")
    youtube["formats"] = formats
    extractor_args["youtube"] = youtube
    relaxed["extractor_args"] = extractor_args
    return relaxed


def _build_auth_attempts():
    attempts = [{"kind": "none"}]

    # 1. Explicit cookie file configured by user (highest priority after no-auth)
    cookie_file = (AppConfig.get("youtube_cookie_file", "") or "").strip()
    if cookie_file:
        if os.path.exists(cookie_file):
            attempts.append({"kind": "cookie_file", "path": cookie_file})
        else:
            log.warning("[YTDLP] Bo qua youtube_cookie_file vi khong ton tai: %s", cookie_file)

    # 2. Auto-snapshot file saved by export_cookies_to_file() on a previous run
    if (not cookie_file) and os.path.exists(_AUTO_COOKIE_FILE):
        attempts.append({"kind": "cookie_file", "path": _AUTO_COOKIE_FILE})

    cookie_browser = (AppConfig.get("youtube_cookie_browser", "auto") or "auto").strip().lower()
    cookie_profile = (AppConfig.get("youtube_cookie_profile", "") or "").strip() or None
    if cookie_browser == "none":
        return attempts

    browsers = []
    if cookie_browser and cookie_browser != "auto":
        browsers.append(cookie_browser)

    preferred_browser = _read_browser_preference_from_settings()
    if preferred_browser:
        browsers.append(preferred_browser)

    browsers.extend(DEFAULT_COOKIE_BROWSERS)

    seen = set()
    for browser in browsers:
        key = (browser, cookie_profile)
        if browser and key not in seen:
            attempts.append({
                "kind": "browser",
                "browser": browser,
                "profile": cookie_profile,
            })
            seen.add(key)

    return attempts


def _apply_auth(opts, auth):
    kind = auth.get("kind")
    if kind == "browser":
        profile = auth.get("profile")
        if profile:
            opts["cookiesfrombrowser"] = (auth["browser"], profile)
        else:
            opts["cookiesfrombrowser"] = (auth["browser"],)
    elif kind == "cookie_file":
        opts["cookiefile"] = auth["path"]


def _describe_auth(auth):
    kind = auth.get("kind")
    if kind == "browser":
        profile = auth.get("profile")
        if profile:
            return f"cookie tu {auth['browser']} (profile {profile})"
        return f"cookie tu {auth['browser']}"
    if kind == "cookie_file":
        return f"cookie file {auth['path']}"
    clients = auth.get("player_clients")
    if clients:
        return "khong dung cookie, client " + "/".join(clients)
    return "khong dung cookie"


def _read_browser_preference_from_settings():
    if not os.path.exists(SETTINGS_FILE):
        return None
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as handle:
            settings = json.load(handle)
    except Exception:
        return None
    return _map_browser_path_to_cookie_source(settings.get("browser_path", ""))


def _map_browser_path_to_cookie_source(browser_path):
    filename = os.path.basename(str(browser_path or "")).lower()
    if not filename:
        return None
    if "msedge" in filename or filename == "edge.exe":
        return "edge"
    if "chrome" in filename:
        return "chrome"
    if "brave" in filename:
        return "brave"
    if "firefox" in filename:
        return "firefox"
    if "opera" in filename:
        return "opera"
    if "vivaldi" in filename:
        return "vivaldi"
    return None


def _normalize_message(exc):
    """Chữ thường + nắn dấu nháy cong.

    yt-dlp in "you’re" (U+2019) chứ không phải "you're", nên so khớp thẳng chuỗi
    có dấu nháy thẳng sẽ trượt.
    """
    return str(exc).lower().replace("’", "'").replace("ʼ", "'")


def _is_bot_challenge(exc):
    message = _normalize_message(exc)
    return any(marker in message for marker in BOT_CHALLENGE_MARKERS)


def _is_format_unavailable(exc):
    message = _normalize_message(exc)
    return any(marker in message for marker in FORMAT_UNAVAILABLE_MARKERS)


def _short_reason(exc):
    """Mot dong ngan gon de ghi vao console khi thu nac ke tiep.

    Toan van loi da nam trong nhat ky (qua _YtdlpLogger) va trong ngoai le cuoi
    cung; o day chi can du de ky thuat doan huong.
    """
    text = " ".join(str(exc).split())
    text = text.replace("ERROR: ", "")
    if len(text) > 90:
        text = text[:87] + "..."
    return text or exc.__class__.__name__


def _is_stream_forbidden(exc):
    message = _normalize_message(exc)
    return any(marker in message for marker in STREAM_FORBIDDEN_MARKERS)


def _is_terminal_error(exc):
    message = _normalize_message(exc)
    return any(marker in message for marker in TERMINAL_MARKERS)


def _is_cookie_db_access_error(exc):
    message = _normalize_message(exc)
    if any(marker in message for marker in COOKIE_SOURCE_MARKERS):
        return True
    if not any(marker in message for marker in COOKIE_DB_ACCESS_MARKERS):
        return False
    return "cookie database" in message or "network\\cookies" in message or "\\cookies" in message


def _build_auth_error_message():
    return (
        "YouTube dang yeu cau xac thuc va app khong lay duoc cookie hop le. "
        "Hay dang nhap YouTube tren Edge/Chrome/Brave/Firefox, roi thu lai. "
        "Neu can ep nguon cookie, dat `youtube_cookie_browser`, `youtube_cookie_profile` "
        "hoac `youtube_cookie_file` trong `app_config.json`.\n"
        f"(yt-dlp dang dung: {ytdlp_update.active_version()})"
    )


def describe_stack():
    """Ba tru cot quyet dinh viec tai YouTube — dung cho log khoi dong + chan doan."""
    js = "co" if (AppConfig.get("js_runtime_path", "") or find_js_runtime()) else "KHONG"
    return (
        f"yt-dlp {ytdlp_update.active_version()} | "
        f"runtime JS: {js} | "
        f"{pot_provider.describe()}"
    )


def _build_format_error_message():
    pot_hint = (
        "  A. PO Token provider chua san sang tren may nay — mo lai app khi CO MANG\n"
        "     de app tu tai ve, hoac chay tools\\chan_doan\\SuaLoi.bat.\n"
        if not pot_provider.is_available() else
        "  A. Chay tools\\chan_doan\\SuaLoi.bat -ChiYtDlp de nap ban yt-dlp moi nhat,\n"
        "     roi mo lai app.\n"
    )
    return (
        "YouTube khong tra ve dinh dang tai duoc cho video nay.\n\n"
        "Nguyen nhan: YouTube doi 'PO Token' cho cac client web/tv. Client android "
        "(khong can PO Token) cung da duoc thu nhung khong an.\n\n"
        f"({describe_stack()})\n\n"
        "Cach khac phuc:\n"
        + pot_hint +
        "  B. Cai ban Quang Luu Studio moi nhat.\n"
        "  C. Kiem tra video co bi gioi han (rieng tu / tra phi / chan quoc gia) khong.\n"
        "  D. Neu chi may nay bi: dat \"youtube_player_clients\" trong app_config.json,\n"
        "     vi du [\"android\", \"android_vr\"]."
    )


def _build_forbidden_error_message():
    """403 = YouTube CO cap link tai nhung tu choi khi tai that.

    Khac han loi "het dinh dang": bong duoc video, thay du dinh dang, chi la
    khong tai noi. Gan nhu luon do thieu PO Token — link duoc cap cho mot client
    khac voi thu dang dung de tai.
    """
    if pot_provider.is_available():
        remedy = (
            "  A. Bo sinh PO Token DA co tren may. Neu van 403, chay\n"
            "     tools\\chan_doan\\SuaLoi.bat -ChiYtDlp de nap ban yt-dlp moi nhat.\n"
        )
    else:
        remedy = (
            "  A. May nay CHUA co bo sinh PO Token - day gan nhu chac chan la\n"
            "     nguyen nhan. Mo lai app khi CO MANG de app tu tai ve (~44MB),\n"
            "     hoac chay tools\\chan_doan\\SuaLoi.bat (muc 3C) de tai ngay.\n"
        )
    return (
        "YouTube tu choi cho tai video nay.\n\n"
        "Nguyen nhan: lay duoc danh sach dinh dang nhung link tai khong dung duoc "
        "(403 Forbidden, hoac link rong khien ffmpeg sap). Gan nhu luon do thieu "
        "'PO Token' - thu chung minh yeu cau den tu trinh duyet that. No KHONG "
        "phai cookie va KHONG can tai khoan YouTube.\n\n"
        f"({describe_stack()})\n\n"
        "Cach khac phuc:\n"
        + remedy +
        "  B. Cai ban Quang Luu Studio moi nhat.\n"
        "  C. Thu lai sau vai phut: YouTube co the dang chan tam thoi dia chi IP nay.\n"
    )


def _build_cookie_db_error_message():
    return (
        "yt-dlp khong doc duoc cookie database cua trinh duyet.\n\n"
        "Nguyen nhan: Chrome/Edge/Brave khoa file cookie khi dang chay.\n\n"
        "Cach khac phuc (chon 1):\n"
        f"  A. Chay tools\\export_youtube_cookies.bat de xuat cookie ra file mot lan,\n"
        "     hoac vao Settings -> YouTube Cookie -> nut xuat cookie.\n"
        f"     Cookie se duoc luu tu dong vao: {_AUTO_COOKIE_FILE}\n"
        "  B. Dung Firefox: khong bi khoa cookie khi dang mo.\n"
        "     Vao Settings → YouTube Cookie → chon Firefox.\n"
        "  C. Dong hoan toan Chrome/Edge/Brave roi thu lai.\n"
    )
