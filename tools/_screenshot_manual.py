"""
Screenshot harness — chụp ảnh thật của UI để dựng hướng dẫn sử dụng.
Chạy: python tools/_screenshot_manual.py
Ảnh lưu vào docs/manual/img/*.png
"""
import os, sys, traceback

# project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

OUT = os.path.join(ROOT, "docs", "manual", "img")
os.makedirs(OUT, exist_ok=True)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication

import frontend_qt as fq


def pump(ms=400):
    app = QApplication.instance()
    import time
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def grab(widget, name):
    try:
        pump(350)
        pix = widget.grab()
        path = os.path.join(OUT, name + ".png")
        ok = pix.save(path, "PNG")
        print(f"[{'OK' if ok else 'FAIL'}] {name} -> {path} ({pix.width()}x{pix.height()})")
    except Exception:
        print(f"[ERR] grab {name}")
        traceback.print_exc()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(fq.APP_QSS)
    fq._load_fonts()

    # ── Main dashboard ──
    try:
        dash = fq.MainDashboard(settings={})
        dash.resize(960, 600)
        dash.show()
        grab(dash, "01_dashboard")
    except Exception:
        print("[FATAL] dashboard failed")
        traceback.print_exc()
        return

    # Dev mode ON (shows + Thêm buttons / right-click hints)
    try:
        dash.is_dev_mode = True
        dash.refresh_ui()
        grab(dash, "02_dashboard_devmode")
        dash.is_dev_mode = False
        dash.refresh_ui()
    except Exception:
        print("[ERR] devmode")
        traceback.print_exc()

    # ── Dialogs ──
    def show_dialog(factory, name, w=None, h=None):
        try:
            dlg = factory()
            if w and h:
                dlg.resize(w, h)
            dlg.setModal(False)
            dlg.show()
            grab(dlg, name)
            dlg.close()
        except Exception:
            print(f"[ERR] dialog {name}")
            traceback.print_exc()

    from ui.dialogs.settings_dialog import SettingsDialog
    from ui.dialogs.calibration import CalibrationWizardDialog
    from ui.dialogs.songs_list import SongsListDialog
    from ui.dialogs.edit_song import EditSongDialog
    from ui.dialogs.widget_builder import WidgetBuilderDialog
    from ui.dialogs.scoring_report import ScoringReportDialog

    # Settings — chụp từng tab
    try:
        s = SettingsDialog(dash)
        s.resize(860, 720)
        s.setModal(False)
        s.show()
        tab_names = ["10a_settings_system", "10b_settings_audio",
                     "10c_settings_tools", "10d_settings_accessibility"]
        for i, nm in enumerate(tab_names):
            try:
                s._tabs.setCurrentIndex(i)
                grab(s, nm)
            except Exception:
                print(f"[ERR] settings tab {nm}")
                traceback.print_exc()
        s.close()
    except Exception:
        print("[ERR] settings dialog")
        traceback.print_exc()

    show_dialog(lambda: CalibrationWizardDialog(dash), "11_calibration")
    show_dialog(lambda: SongsListDialog(dash), "12_songs_list")

    sample_song = {"id": 1, "title": "Bài hát mẫu - Demo", "url": "", "tone": "C"}
    show_dialog(lambda: EditSongDialog(dash, sample_song), "13_edit_song")

    show_dialog(lambda: WidgetBuilderDialog(dash, panel_name="tools", widget_type="button"),
                "14_widget_builder_button")
    show_dialog(lambda: WidgetBuilderDialog(dash, panel_name="mixer", widget_type="slider"),
                "15_widget_builder_slider")

    sample_result = {
        "total_score": 87.5,
        "feedback": {
            "rank": "Ca Sĩ Chuyên Nghiệp", "icon": "⭐",
            "main": "Giọng hát ổn định, đúng tone. Tiếp tục phát huy!",
            "tips": ["Giữ hơi đều ở các nốt cao", "Luyến láy mượt hơn ở điệp khúc"],
        },
        "pitch_score": 90, "rhythm_score": 85, "stability_score": 88,
        "duration": 215, "notes_hit": 142, "notes_total": 160,
    }
    show_dialog(lambda: ScoringReportDialog(dash, sample_result), "16_scoring_report")

    # Hỗ trợ — chụp tab "Gửi yêu cầu". Tab Hộp thư cần server nên để trống ở đây;
    # dialog vẫn gọi inbox() nền một lần (đọc, vô hại) rồi báo không tải được.
    from ui.dialogs.support_dialog import SupportDialog
    try:
        sup = SupportDialog(dash)
        sup.resize(640, 640)
        sup.setModal(False)
        sup.show()
        sup._tabs.setCurrentIndex(0)
        grab(sup, "17_support")
        sup.close()
    except Exception:
        print("[ERR] dialog 17_support")
        traceback.print_exc()

    print("DONE")


if __name__ == "__main__":
    main()
