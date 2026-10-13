from core.audio_doctor.win_audio import Device, pick_virtual_device


def test_chon_thiet_bi_ao_theo_ten():
    devs = [Device("1", "Speakers (Realtek)"), Device("2", "CABLE Input (VB-Audio Virtual Cable)"),
            Device("3", "ASIOVADPRO Out")]
    assert pick_virtual_device(devs).id == "3"     # ASIOVADPRO ưu tiên hơn VB-Cable


def test_khong_co_thiet_bi_ao():
    assert pick_virtual_device([Device("1", "Speakers (Realtek)")]) is None
