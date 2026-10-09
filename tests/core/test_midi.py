import pytest
import sys
from unittest.mock import patch, MagicMock
from core.midi import MidiHandler

@pytest.fixture
def mock_mido():
    mock_mido_module = MagicMock()
    sys.modules['mido'] = mock_mido_module
    yield mock_mido_module
    del sys.modules['mido']

def test_connect_success(mock_mido):
    # M-01
    mock_mido.get_output_names.return_value = ["QuangLuuMIDI"]
    handler = MidiHandler()
    assert handler.connect() is True
    assert handler.outport is not None
    mock_mido.open_output.assert_called_once_with("QuangLuuMIDI")

def test_connect_fail(mock_mido):
    # M-02
    mock_mido.get_output_names.return_value = ["OtherPort"]
    handler = MidiHandler()
    assert handler.connect() is False
    assert handler.outport is None

def test_send_cc_connected(mock_mido):
    # M-03
    mock_mido.get_output_names.return_value = ["QuangLuuMIDI"]
    
    mock_outport = MagicMock()
    mock_mido.open_output.return_value = mock_outport
    
    mock_msg = MagicMock()
    mock_mido.Message.return_value = mock_msg
    
    handler = MidiHandler()
    handler.connect()
    
    handler.send_cc(34, 64)
    mock_mido.Message.assert_called_once_with('control_change', channel=0, control=34, value=64)
    mock_outport.send.assert_called_once_with(mock_msg)

def test_send_cc_not_connected(mock_mido):
    # M-04
    handler = MidiHandler()
    # Should not raise exception
    handler.send_cc(34, 64)
    mock_mido.Message.assert_not_called()

def test_send_cc_with_channel(mock_mido):
    # M-05
    mock_mido.get_output_names.return_value = ["QuangLuuMIDI"]
    mock_outport = MagicMock()
    mock_mido.open_output.return_value = mock_outport
    
    handler = MidiHandler()
    handler.connect()
    
    handler.send_cc(34, 64, channel=1)
    mock_mido.Message.assert_called_once_with('control_change', channel=1, control=34, value=64)


def test_start_listening_mo_cong_phan_hoi(mock_mido):
    mock_mido.get_input_names.return_value = ["QuangLuuMIDI 0", "QLS_PhanHoi 1"]
    handler = MidiHandler()
    try:
        assert handler.start_listening() is True
        mock_mido.open_input.assert_called_once_with("QLS_PhanHoi 1")
    finally:
        handler.stop_listening()


def test_ensure_listening_mo_lai_khi_inport_mat(mock_mido):
    mock_mido.get_input_names.return_value = ["QLS_PhanHoi"]
    handler = MidiHandler()
    try:
        assert handler.ensure_listening() is True
        assert handler.ensure_listening() is True          # đang nghe → không mở lại
        assert mock_mido.open_input.call_count == 1
        handler.inport = None                              # loopMIDI khởi động lại
        assert handler.ensure_listening() is True
        assert mock_mido.open_input.call_count == 2
    finally:
        handler.stop_listening()


def test_ensure_listening_mo_lai_khi_cong_phan_hoi_bien_mat(mock_mido):
    mock_mido.get_input_names.return_value = ["QLS_PhanHoi"]
    handler = MidiHandler()
    try:
        assert handler.ensure_listening() is True
        mock_mido.get_input_names.return_value = []          # loopMIDI tắt / mất cổng
        assert handler.ensure_listening() is False
        mock_mido.get_input_names.return_value = ["QLS_PhanHoi"]
        assert handler.ensure_listening() is True
        assert mock_mido.open_input.call_count == 2
    finally:
        handler.stop_listening()
