"""
ui.responsive
=============
Kích thước cửa sổ/dialog co giãn theo màn hình thật, thay cho số px fix cứng.

Vì sao cần: app CHỦ ĐỘNG tắt high-DPI scaling của Qt (main.py đặt
``QT_ENABLE_HIGHDPI_SCALING=0`` + per-monitor DPI aware) nên 1 px trong code =
1 px vật lý trên mọi máy. Cùng một con số 850x560 vừa vặn trên 1920x1080 nhưng
chật trên 1366x768 và bé xíu trên 4K/ultrawide. Module này quy mọi kích thước về
MỘT hệ số tính từ màn hình đang dùng, rồi luôn kẹp lại cho vừa vùng làm việc
(availableGeometry — đã trừ taskbar).

Hệ số lấy theo chiều BỊ BÓ nhất (min của tỉ lệ ngang và dọc) nên tự đúng với mọi
tỉ lệ màn: 16:9, 16:10, 4:3 hay ultrawide 21:9 đều không bị kéo méo.

Không đụng tới cỡ chữ: QSS của app dùng px cố định ở rất nhiều nơi, phóng chữ
phải làm ở tầng QSS chứ không phải ở đây.

Dùng:
    from ui import responsive as rp

    rp.apply_dialog_size(self, 860, 720, min_w=820, min_h=700)   # dialog co giãn
    rp.apply_dialog_size(self, 520, 510, fixed=True)             # dialog khoá cỡ
    rp.apply_window_size(win, ratio=(0.58, 0.42),
                         min_size=(780, 420), max_size=(1500, 900))
"""
from PySide6.QtCore import QRect
from PySide6.QtGui import QCursor, QGuiApplication

# Màn hình tham chiếu lúc thiết kế UI (vùng làm việc ~1600x900 của một máy 1080p).
DESIGN_W, DESIGN_H = 1600, 900

# Không bao giờ THU NHỎ dưới cỡ thiết kế (chữ và nút bên trong là px cố định, thu
# lại chỉ làm chật chội chứ không gọn hơn) — màn nhỏ đã có bước kẹp theo
# availableGeometry lo. Phóng thì tối đa 60%, quá nữa chỉ tổ thừa khoảng trống.
MIN_SCALE, MAX_SCALE = 1.0, 1.60

# Dialog phóng dè dặt hơn cửa sổ chính: ruột dialog là px cố định, phóng quá tay
# chỉ tạo khoảng trống. (apply_dialog_size dùng khi không truyền max_scale.)
DIALOG_MAX_SCALE = 1.35

# Dialog không chiếm quá 94% vùng làm việc; cửa sổ chính rộng tay hơn một chút.
DIALOG_MARGIN = 0.94
WINDOW_MARGIN = 0.96


# ── Màn hình đang dùng ────────────────────────────────────────────────────────
def target_screen(widget=None):
    """QScreen mà widget đang (hoặc sắp) nằm trên đó.

    Dialog chưa show thì chưa có windowHandle → leo lên parent để bám đúng màn
    hình của cửa sổ chính, tránh cảnh dialog tính theo màn chính trong khi app
    đang chạy ở màn phụ có độ phân giải khác hẳn.
    """
    w = widget
    while w is not None:
        try:
            handle = w.windowHandle()
        except Exception:
            handle = None
        if handle is not None and handle.screen() is not None:
            return handle.screen()
        try:
            w = w.parentWidget()
        except Exception:
            break
    try:
        scr = QGuiApplication.screenAt(QCursor.pos())
    except Exception:
        scr = None
    return scr or QGuiApplication.primaryScreen()


def available_rect(widget=None) -> QRect:
    """Vùng làm việc (đã trừ taskbar) của màn hình đang dùng."""
    scr = target_screen(widget)
    if scr is None:
        return QRect(0, 0, DESIGN_W, DESIGN_H)
    rect = scr.availableGeometry()
    if rect.width() < 320 or rect.height() < 240:   # driver lỗi → dùng số an toàn
        return QRect(0, 0, DESIGN_W, DESIGN_H)
    return rect


# ── Hệ số co giãn ─────────────────────────────────────────────────────────────
def scale(widget=None) -> float:
    """Hệ số nhân cho mọi kích thước thiết kế, đã kẹp trong [MIN_SCALE, MAX_SCALE]."""
    rect = available_rect(widget)
    factor = min(rect.width() / DESIGN_W, rect.height() / DESIGN_H)
    return max(MIN_SCALE, min(MAX_SCALE, factor))


def px(value, widget=None) -> int:
    """Đổi một số px thiết kế sang px thật của màn hình hiện tại."""
    return max(1, round(value * scale(widget)))


def fit(width, height, widget=None, margin=DIALOG_MARGIN):
    """Kẹp (width, height) cho vừa vùng làm việc."""
    rect = available_rect(widget)
    return (
        max(200, min(int(width), int(rect.width() * margin))),
        max(150, min(int(height), int(rect.height() * margin))),
    )


# ── Áp cho dialog ─────────────────────────────────────────────────────────────
def apply_dialog_size(dlg, base_w, base_h, min_w=None, min_h=None,
                      fixed=False, max_scale=None, margin=DIALOG_MARGIN):
    """Đặt cỡ dialog theo cỡ thiết kế (base_w, base_h) đã nhân hệ số màn hình.

    - ``fixed=True``: khoá cỡ (dialog nhỏ, layout không co được) nhưng vẫn scale.
      Loại này nên kèm ``max_scale`` thấp (~1.25): nội dung bên trong là px cố
      định nên phóng quá tay chỉ tạo khoảng trống chứ chữ không to thêm.
    - Cỡ tối thiểu cũng bị kẹp cho vừa màn hình: min cứng 820x700 trên máy
      1280x720 sẽ khiến dialog tràn ra ngoài và KHÔNG thu lại được — nút Lưu
      nằm dưới đáy coi như mất.

    Trả về (width, height) thực sự đã đặt.
    """
    s = min(scale(dlg), DIALOG_MAX_SCALE if max_scale is None else float(max_scale))
    w, h = fit(round(base_w * s), round(base_h * s), dlg, margin)

    if fixed:
        dlg.setFixedSize(w, h)
        return w, h

    mw = base_w if min_w is None else min_w
    mh = base_h if min_h is None else min_h
    mw, mh = fit(min(mw, w), min(mh, h), dlg, margin)
    dlg.setMinimumSize(mw, mh)
    dlg.resize(w, h)
    return w, h


def set_min_width(widget, width, max_scale=1.25, margin=DIALOG_MARGIN):
    """Cỡ rộng tối thiểu có scale (cho dialog cao tự co theo nội dung)."""
    s = scale(widget)
    if max_scale is not None:
        s = min(s, float(max_scale))
    rect = available_rect(widget)
    widget.setMinimumWidth(max(200, min(round(width * s), int(rect.width() * margin))))


def set_fixed_width(widget, width, max_scale=1.25, margin=DIALOG_MARGIN):
    """setFixedWidth có scale + kẹp theo màn hình."""
    s = scale(widget)
    if max_scale is not None:
        s = min(s, float(max_scale))
    rect = available_rect(widget)
    widget.setFixedWidth(max(200, min(round(width * s), int(rect.width() * margin))))


def set_min_size(widget, min_w, min_h, margin=WINDOW_MARGIN):
    """setMinimumSize nhưng không bao giờ vượt quá màn hình đang dùng."""
    rect = available_rect(widget)
    widget.setMinimumSize(
        max(200, min(int(min_w), int(rect.width() * margin))),
        max(150, min(int(min_h), int(rect.height() * margin))),
    )


# ── Áp cho cửa sổ chính ───────────────────────────────────────────────────────
def apply_window_size(win, ratio=(0.58, 0.42), min_size=None, max_size=None,
                      center=True, margin=WINDOW_MARGIN):
    """Cỡ mặc định của cửa sổ = một TỈ LỆ của màn hình, kẹp giữa min và max.

    Nhờ đi theo tỉ lệ, cửa sổ giữ nguyên "cảm giác" chiếm bao nhiêu phần màn
    hình dù máy là 1366x768, 1920x1080, 2560x1440 hay 3840x2160.
    """
    rect = available_rect(win)
    w = int(rect.width() * ratio[0])
    h = int(rect.height() * ratio[1])

    if min_size:
        w = max(w, int(min_size[0]))
        h = max(h, int(min_size[1]))
    if max_size:
        w = min(w, int(max_size[0]))
        h = min(h, int(max_size[1]))

    w, h = fit(w, h, win, margin)
    win.resize(w, h)
    if center:
        center_on(win, rect)
    return w, h


def restore_geometry(win, geom) -> bool:
    """Khôi phục vị trí/kích thước đã lưu, có kiểm tra lại theo màn hình hiện tại.

    Trả về False (gọi apply_window_size thay thế) khi dữ liệu hỏng hoặc cửa sổ
    cũ nằm ngoài vùng nhìn thấy — ví dụ user rút màn phụ, hoặc đổi độ phân giải
    xuống thấp hơn. Không có bước này thì app "mất tích" ngoài màn hình.
    """
    if not isinstance(geom, dict):
        return False
    try:
        w = int(geom.get("width", 0))
        h = int(geom.get("height", 0))
        x = int(geom.get("x", 0))
        y = int(geom.get("y", 0))
    except (TypeError, ValueError):
        return False
    if w < 200 or h < 150:
        return False

    saved = QRect(x, y, w, h)
    best, best_area = None, 0
    for scr in QGuiApplication.screens():
        inter = scr.availableGeometry().intersected(saved)
        area = inter.width() * inter.height()
        if area > best_area:
            best, best_area = scr, area
    # Dưới 1/4 diện tích còn nằm trong màn nào đó → coi như lạc, dựng lại từ đầu.
    if best is None or best_area < 0.25 * w * h:
        return False

    rect = best.availableGeometry()
    w = min(w, rect.width())
    h = min(h, rect.height())
    x = max(rect.left(), min(x, rect.right() - w + 1))
    y = max(rect.top(), min(y, rect.bottom() - h + 1))
    win.resize(w, h)
    win.move(x, y)
    return True


def center_on(widget, rect=None):
    """Canh giữa widget trong vùng làm việc (hơi lệch lên trên cho thuận mắt)."""
    rect = rect if rect is not None else available_rect(widget)
    x = rect.left() + max(0, (rect.width() - widget.width()) // 2)
    y = rect.top() + max(0, int((rect.height() - widget.height()) * 0.42))
    widget.move(x, y)
