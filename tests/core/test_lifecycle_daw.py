# tests/core/test_lifecycle_daw.py
"""launch_app / force kill đi theo hồ sơ DAW, không còn tên exe cứng."""
from unittest.mock import MagicMock, patch

import pytest

from core import daw
from core.engine._lifecycle import _LifecycleMixin


@pytest.fixture(autouse=True)
def _unbind():
    daw.bind(None)
    yield
    daw.bind(None)


def _engine():
    return _LifecycleMixin()


def test_mo_file_cpr_bang_startfile_khi_chon_cubase():
    daw.bind({"daw_kind": "cubase"})
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as startfile, \
         patch("subprocess.Popen") as popen:
        _engine().launch_app(r"D:\QLS\mau.cpr")
    startfile.assert_called_once_with(r"D:\QLS\mau.cpr")
    popen.assert_not_called()


def test_file_song_khi_chon_cubase_khong_phai_bai():
    # Người dùng chọn Cubase nhưng để đường dẫn .song cũ → không startfile,
    # cũng không Popen một file không chạy được.
    daw.bind({"daw_kind": "cubase"})
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as startfile, \
         patch("core.so_windows.is_running", return_value=True), \
         patch("subprocess.Popen") as popen:
        _engine().launch_app(r"D:\bai\mau.song")
    startfile.assert_not_called()
    popen.assert_not_called()


def test_mo_exe_chi_khi_daw_chua_chay():
    daw.bind({"daw_kind": "cubase"})
    with patch("os.path.exists", return_value=True), \
         patch("core.so_windows.is_running", return_value=False), \
         patch("threading.Thread") as thread:
        _engine().launch_app(r"C:\Program Files\Steinberg\Cubase 13\Cubase13.exe")
    thread.assert_called_once()


def test_force_kill_theo_pid_cua_daw():
    daw.bind({"daw_kind": "cubase"})
    proc = MagicMock()
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = proc
    with patch("core.so_windows.studio_one_pids", return_value={4132}), \
         patch("core.engine._lifecycle.psutil", fake_psutil):
        _engine()._force_kill_studio_one()
    fake_psutil.Process.assert_called_once_with(4132)
    proc.kill.assert_called_once()


def test_studio_one_van_dung_duoi_song():
    daw.bind({})
    with patch("os.path.exists", return_value=True), \
         patch("os.startfile", create=True) as startfile:
        _engine().launch_app(r"D:\bai\mau.songversion")
    startfile.assert_called_once()
