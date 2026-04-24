"""
Shared yt-dlp helpers for YouTube requests that may require browser cookies.
"""
import json
import logging
import os

from core.config import AppConfig, DATA_DIR, FFMPEG_LOCATION, SETTINGS_FILE

log = logging.getLogger(__name__)

# Firefox first: its cookie DB is NOT locked while the browser is running.
# Chromium-based browsers (Chrome, Edge, Brave, Opera, Vivaldi) lock the
# SQLite Cookies file, so they will fail with "Could not copy ... cookie database"
# whenever the browser is open.
DEFAULT_COOKIE_BROWSERS = ("firefox", "edge", "chrome", "brave", "opera", "vivaldi")

# Auto-snapshot saved here so the app can use it on next run after export
_AUTO_COOKIE_FILE = os.path.join(DATA_DIR, "youtube_cookies.txt")

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


class YouTubeAuthenticationRequiredError(RuntimeError):
    """Raised when yt-dlp cannot bypass YouTube's anti-bot check."""


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
    }
    if FFMPEG_LOCATION:
        opts["ffmpeg_location"] = FFMPEG_LOCATION
    opts.update(extra_opts)
    return opts


def extract_info_with_auth(url, ydl_opts=None, download=False, log_prefix="[YTDLP]"):
    """Run `extract_info` with automatic auth fallback when YouTube blocks access."""
    return run_with_auth_fallback(
        url,
        ydl_opts=ydl_opts,
        log_prefix=log_prefix,
        operation=lambda ydl: ydl.extract_info(url, download=download),
    )


def download_with_auth(url, ydl_opts=None, log_prefix="[YTDLP]"):
    """Run `download` with automatic auth fallback when YouTube blocks access."""
    return run_with_auth_fallback(
        url,
        ydl_opts=ydl_opts,
        log_prefix=log_prefix,
        operation=lambda ydl: ydl.download([url]),
    )


def run_with_auth_fallback(url, ydl_opts=None, log_prefix="[YTDLP]", operation=None):
    """
    Execute a yt-dlp operation, retrying with cookies from browser / file if
    YouTube responds with a bot-confirmation challenge.
    """
    if operation is None:
        raise ValueError("operation is required")

    try:
        import yt_dlp
    except ImportError:
        raise ImportError("Thu vien 'yt-dlp' chua duoc cai dat. Vui long chay: pip install yt-dlp")

    base_opts = make_ydl_opts(**(ydl_opts or {}))
    attempts = _build_auth_attempts()
    last_error = None
    auth_blocked = False
    cookie_db_blocked = False

    for index, auth in enumerate(attempts):
        current_opts = dict(base_opts)
        _apply_auth(current_opts, auth)

        if index > 0:
            print(f"{log_prefix} Dang thu {_describe_auth(auth)}...")

        try:
            with yt_dlp.YoutubeDL(current_opts) as ydl:
                return operation(ydl)
        except yt_dlp.utils.DownloadError as exc:
            last_error = exc
            if _is_bot_challenge(exc):
                auth_blocked = True
                if index == 0:
                    print(f"{log_prefix} YouTube yeu cau xac thuc, chuyen sang thu cookie trinh duyet...")
                continue
            if auth.get("kind") != "none" and _is_cookie_db_access_error(exc):
                cookie_db_blocked = True
                print(
                    f"{log_prefix} Khong doc duoc {_describe_auth(auth)} "
                    f"(cookie database dang bi khoa), thu nguon khac..."
                )
                continue
            raise
        except Exception as exc:
            last_error = exc
            if auth.get("kind") != "none":
                print(f"{log_prefix} Khong dung duoc {_describe_auth(auth)} ({exc.__class__.__name__}), thu nguon khac...")
                continue
            raise

    if auth_blocked:
        raise YouTubeAuthenticationRequiredError(_build_auth_error_message()) from last_error
    if cookie_db_blocked:
        raise RuntimeError(_build_cookie_db_error_message()) from last_error
    if last_error:
        raise last_error
    raise RuntimeError("yt-dlp khong tra ve ket qua")


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


def _is_bot_challenge(exc):
    message = str(exc).lower()
    return any(marker in message for marker in BOT_CHALLENGE_MARKERS)


def _is_cookie_db_access_error(exc):
    message = str(exc).lower()
    if not any(marker in message for marker in COOKIE_DB_ACCESS_MARKERS):
        return False
    return "cookie database" in message or "network\\cookies" in message or "\\cookies" in message


def _build_auth_error_message():
    return (
        "YouTube dang yeu cau xac thuc va app khong lay duoc cookie hop le. "
        "Hay dang nhap YouTube tren Edge/Chrome/Brave/Firefox, roi thu lai. "
        "Neu can ep nguon cookie, dat `youtube_cookie_browser`, `youtube_cookie_profile` "
        "hoac `youtube_cookie_file` trong `app_config.json`."
    )


def _build_cookie_db_error_message():
    return (
        "yt-dlp khong doc duoc cookie database cua trinh duyet.\n\n"
        "Nguyen nhan: Chrome/Edge/Brave khoa file cookie khi dang chay.\n\n"
        "Cach khac phuc (chon 1):\n"
        f"  A. Chay tool\\export_youtube_cookies.bat de xuat cookie ra file mot lan.\n"
        f"     Cookie se duoc luu tu dong vao: {_AUTO_COOKIE_FILE}\n"
        "  B. Dung Firefox: khong bi khoa cookie khi dang mo.\n"
        "     Vao Settings → YouTube Cookie → chon Firefox.\n"
        "  C. Dong hoan toan Chrome/Edge/Brave roi thu lai.\n"
    )
