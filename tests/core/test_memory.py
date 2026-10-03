import pytest
import os
import sys
import time
from unittest.mock import patch, MagicMock
from core.memory import MemoryProfiler, MemoryGuard

@pytest.fixture(autouse=True)
def reset_tone_jobs():
    """Bộ đếm phiên dò là trạng thái CẤP LỚP: luồng dò tone rò từ test khác
    (test_engine) có thể vẫn đang chạy → reset để test ở đây độc lập."""
    MemoryGuard._active_tone_jobs = 0
    yield
    MemoryGuard._active_tone_jobs = 0


@pytest.fixture
def mock_psutil():
    mock_psutil_module = MagicMock()
    mock_proc = MagicMock()
    mock_mem_info = MagicMock()
    mock_mem_info.rss = 100 * 1024 * 1024  # 100MB
    mock_proc.memory_info.return_value = mock_mem_info
    mock_psutil_module.Process.return_value = mock_proc
    sys.modules['psutil'] = mock_psutil_module
    yield mock_proc, mock_mem_info
    del sys.modules['psutil']

def test_checkpoint_logs(mock_psutil, capsys):
    # MM-01
    mock_proc, mock_mem_info = mock_psutil
    profiler = MemoryProfiler("TEST")
    
    # Tăng 30MB (vượt ngưỡng log 20MB)
    mock_mem_info.rss += 30 * 1024 * 1024
    profiler.checkpoint("label")
    
    captured = capsys.readouterr()
    assert "[TEST]" in captured.out
    assert "label" in captured.out

def test_checkpoint_no_log(mock_psutil, capsys):
    # MM-02
    mock_proc, mock_mem_info = mock_psutil
    profiler = MemoryProfiler("TEST")
    
    # Tăng 2MB
    mock_mem_info.rss += 2 * 1024 * 1024
    profiler.checkpoint("label")
    
    captured = capsys.readouterr()
    assert captured.out == ""

def test_summary_no_raise(mock_psutil):
    # MM-03
    profiler = MemoryProfiler("TEST")
    profiler.checkpoint()
    profiler.summary()  # Should not raise

def test_guard_start_stop():
    # MM-04
    guard = MemoryGuard(interval=0.1)
    guard.start()
    assert guard._running is True
    assert guard._thread is not None
    assert guard._thread.is_alive()
    
    guard.stop()
    assert guard._running is False
    assert guard._thread is None or not guard._thread.is_alive()

@patch("core.memory.gc.collect")
def test_force_cleanup(mock_gc_collect):
    # MM-05
    MemoryGuard.force_cleanup()
    mock_gc_collect.assert_called_with(2)

def test_cleanup_temp_files(tmp_path):
    # MM-06
    # Patch RECORDINGS_DIR to use tmp_path
    with patch("core.config.RECORDINGS_DIR", str(tmp_path)):
        guard = MemoryGuard(cache_ttl_seconds=1)

        # File tạm của app (prefix qls_tmp_) → bị xóa
        temp_file = tmp_path / "qls_tmp_abc123.wav"
        temp_file.write_text("dummy", encoding="utf-8")

        # Recording của user (KHÔNG có prefix) → phải được giữ lại
        user_file = tmp_path / "recording_12345.wav"
        user_file.write_text("dummy", encoding="utf-8")

        # Set mtime to past
        os.utime(temp_file, (time.time() - 10, time.time() - 10))
        os.utime(user_file, (time.time() - 10, time.time() - 10))

        guard._cleanup_temp_files()
        assert not temp_file.exists()
        assert user_file.exists()

def test_get_status(mock_psutil):
    # MM-07
    guard = MemoryGuard()
    status = guard.get_status()

    assert "running" in status
    assert status["rss_mb"] == 100
    assert status["active_tone_jobs"] == 0
    # Không còn ngưỡng RAM (gc/khẩn cấp)
    assert "emergency_threshold_mb" not in status
    assert "gc_threshold_mb" not in status


@pytest.fixture
def no_real_cleanup():
    """Không GC/compact/trim thật."""
    with patch("core.memory.gc.collect") as gc_mock,          patch.object(MemoryGuard, "_compact_heap") as heap_mock,          patch.object(MemoryGuard, "_trim_working_set") as trim_mock:
        yield gc_mock, heap_mock, trim_mock


def test_cleanup_after_tone_job(no_real_cleanup):
    # MM-08: dò tone xong → dọn RAM (GC + compact heap + trim)
    gc_mock, heap_mock, trim_mock = no_real_cleanup
    MemoryGuard.begin_tone_job()
    gc_mock.assert_not_called()
    MemoryGuard.end_tone_job()
    gc_mock.assert_called_once_with(2)
    heap_mock.assert_called_once()
    trim_mock.assert_called_once()
    assert MemoryGuard.active_tone_jobs() == 0


def test_cleanup_deferred_while_tone_job_running(no_real_cleanup):
    # MM-09: dọn giữa chừng bị hoãn; chỉ phiên dò CUỐI CÙNG mới dọn
    gc_mock, _, trim_mock = no_real_cleanup
    MemoryGuard.begin_tone_job()
    MemoryGuard.begin_tone_job()

    assert MemoryGuard.force_cleanup() is False  # đang dò → bỏ qua
    MemoryGuard.end_tone_job()                    # còn 1 phiên → chưa dọn
    gc_mock.assert_not_called()
    trim_mock.assert_not_called()

    MemoryGuard.end_tone_job()                    # phiên cuối xong → dọn
    gc_mock.assert_called_once_with(2)
    trim_mock.assert_called_once()


def test_end_tone_job_never_negative(no_real_cleanup):
    # MM-10: end thừa không làm bộ đếm âm (nếu âm sẽ không bao giờ hoãn được nữa)
    MemoryGuard.end_tone_job()
    assert MemoryGuard.active_tone_jobs() == 0
    MemoryGuard.begin_tone_job()
    assert MemoryGuard.force_cleanup() is False


def test_monitor_loop_has_no_ram_threshold(mock_psutil, no_real_cleanup):
    # MM-11: daemon KHÔNG dọn RAM theo ngưỡng, kể cả khi RSS rất lớn
    gc_mock, _, trim_mock = no_real_cleanup
    _, mock_mem_info = mock_psutil
    mock_mem_info.rss = 4 * 1024 * 1024 * 1024  # 4GB

    guard = MemoryGuard(interval=1)
    calls = {"n": 0}

    def _one_pass():
        calls["n"] += 1
        guard._running = False

    with patch.object(guard, "_cleanup_caches", side_effect=_one_pass),          patch.object(guard, "_cleanup_temp_files"):
        guard._running = True
        guard._monitor_loop()

    assert calls["n"] == 1
    gc_mock.assert_not_called()
    trim_mock.assert_not_called()


def test_end_tone_job_never_raises(no_real_cleanup):
    # MM-12: end_tone_job nằm trong finally của luồng dò, TRƯỚC khi đóng phiên
    # tone — lỗi dọn RAM không được làm luồng dò bỏ dở phần đóng phiên.
    MemoryGuard.begin_tone_job()
    with patch.object(MemoryGuard, "force_cleanup", side_effect=RuntimeError("x")):
        MemoryGuard.end_tone_job()  # không ném
    assert MemoryGuard.active_tone_jobs() == 0
