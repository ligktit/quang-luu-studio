import pytest

from core import daw


@pytest.fixture(autouse=True)
def _reset_daw_bind():
    """Cô lập hồ sơ DAW giữa các test.

    1) Dashboard dựng trong test bind settings sống vào core.daw; không reset
       thì test sau (dùng MagicMock, không bind) thấy nhầm hồ sơ DAW.
    2) daw.active() khi chưa bind sẽ đọc settings.json thật của máy dev; test
       không được phụ thuộc file đó. bind({}) cho hồ sơ Studio One mặc định và
       không đụng đĩa. Test cần DAW khác tự gọi daw.bind({...}).
    """
    daw.bind({})
    yield
    daw.bind(None)
