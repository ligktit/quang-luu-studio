"""Hồ sơ từng DAW mà app điều khiển được.

Mọi thứ "khác nhau giữa Studio One và Cubase" nằm ở đây, phần còn lại của app
chỉ hỏi `core.daw.active()`. Thêm DAW mới = thêm một DawProfile, không sửa logic.

Số đo Cubase lấy từ docs/NGHIEN_CUU_HO_TRO_CUBASE.md mục 7 (Cubase Pro 13.0.10):
fader 0 dB = CC 100; Pitch Correct: Scale Major 22–63 (tâm 43), Minor 64–105 (tâm 85);
Key trùng key_midi_map hiện có nên không ghi đè.
Plugin khác thì bảng Scale khác: Antares Auto-Tune Pro 11 trên Cubase (máy khách 2026-10-06)
tham số 162 "Modern Scale": Major 6–13 / Minor 14–22 → khách bắt Major=10, Minor=18 bằng Cân chỉnh Auto-Tune (override người dùng
thắng hồ sơ này). Script MIDI Remote tự chọn chỉ số Key/Scale theo plugin (HO_SO_PLUGIN).
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DawProfile:
    kind: str
    display_name: str
    process_keywords: tuple          # so chữ thường với tên process (chứa là trúng)
    main_title_requires: tuple       # MỌI từ phải có trong tiêu đề cửa sổ chính
    project_extensions: tuple        # đuôi file bài → mở bằng os.startfile
    template_extension: str          # đuôi file bản mẫu (snapshot/restore)
    file_dialog_filter: str
    fader_unity_cc: int              # giá trị CC ứng với fader 0 dB
    calibration: dict = field(default_factory=dict)
    remote_install_hint: str = ""
    # Class cửa sổ phải nhận WM_CLOSE để THOÁT hẳn DAW ("" = dùng cửa sổ chính).
    # Cubase: WM_CLOSE vào cửa sổ project chỉ đóng bài, app vẫn ở Steinberg Hub;
    # cửa sổ ứng dụng là class "SmtgMain Cubase13", tiêu đề "Cubase Pro" (đo 13.0.10).
    quit_window_class_prefix: str = ""


STUDIO_ONE = DawProfile(
    kind="studio_one",
    display_name="Studio One",
    process_keywords=("studio one",),
    main_title_requires=("studio one",),
    project_extensions=(
        ".song", ".songversion", ".soundset", ".instrument",
        ".multiinstrument", ".pedalboard", ".channel", ".macro", ".fxchain",
    ),
    template_extension=".song",
    file_dialog_filter=(
        "Studio One Files (*.song *.exe);;Song Files (*.song);;"
        "Executable (*.exe);;All Files (*.*)"
    ),
    fader_unity_cc=76,
    calibration={},
    remote_install_hint="Options → External Devices → Add → QuangLuuMIDI (Receive From: QuangLuuMIDI, Send To: QLS_PhanHoi)",
)

CUBASE = DawProfile(
    kind="cubase",
    display_name="Cubase",
    process_keywords=("cubase",),
    # Cubase còn có cửa sổ "Checking Licenses..." và cửa sổ "Cubase Pro"
    # (class SmtgMain) — chỉ cửa sổ project mới có chữ "Project".
    main_title_requires=("cubase", "project"),
    project_extensions=(".cpr",),
    template_extension=".cpr",
    file_dialog_filter=(
        "Cubase Files (*.cpr *.exe);;Cubase Project (*.cpr);;"
        "Executable (*.exe);;All Files (*.*)"
    ),
    fader_unity_cc=100,
    calibration={
        "scale_midi_map": {"Major": 43, "Minor": 85},
        "scale_values": {"major": 43, "minor": 85},
    },
    quit_window_class_prefix="SmtgMain",
    remote_install_hint="Script MIDI Remote tự nhận khi có cổng QuangLuuMIDI + QLS_PhanHoi (chạy setup_all.bat)",
)

PROFILES = {p.kind: p for p in (STUDIO_ONE, CUBASE)}
DEFAULT_KIND = STUDIO_ONE.kind
