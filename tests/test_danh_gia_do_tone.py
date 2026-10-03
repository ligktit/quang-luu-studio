"""
Công cụ chấm điểm dò tone (tools/danh_gia_do_tone.py) — phần chấm thuần.

Phần này quyết định con số mà mọi thay đổi thuật toán dò tone sẽ dựa vào, nên
sai ở đây là sai cả hướng đi. Không import librosa (xem ghi chú về pytest +
librosa thật trong repo).
"""
import importlib.util
import json
import os

import pytest

_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools", "danh_gia_do_tone.py")
_spec = importlib.util.spec_from_file_location("danh_gia_do_tone", _PATH)
dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dg)

C, G, F, Am, Cm, Em, D = (0, "Major"), (7, "Major"), (5, "Major"), (9, "Minor"), \
    (0, "Minor"), (4, "Minor"), (2, "Major")


class TestParseKey:
    @pytest.mark.parametrize("text,expected", [
        ("C", (0, "Major")), ("C#m", (1, "Minor")), ("Bb", (10, "Major")),
        ("Ebm", (3, "Minor")), ("A Minor", (9, "Minor")), ("C Major", (0, "Major")),
        ("f#m", (6, "Minor")),
    ])
    def test_doc_duoc_moi_cach_viet(self, text, expected):
        assert dg.parse_key(text) == expected

    @pytest.mark.parametrize("text", ["", "H", "Xm", None, "C Dorian"])
    def test_ten_la_tra_none(self, text):
        assert dg.parse_key(text) is None

    def test_dict_uu_tien_key_display(self):
        # key_display là thứ người dùng thấy và sửa — tin nó hơn key_index
        assert dg.parse_key({"key_display": "Am", "key_index": 0, "scale": "Major"}) == Am

    def test_dict_khong_co_display_thi_dung_index(self):
        assert dg.parse_key({"key_index": 7, "scale": "Major"}) == G


class TestClassify:
    def test_dung(self):
        assert dg.classify(C, C) == dg.DUNG

    def test_quang5_ca_hai_chieu(self):
        assert dg.classify(C, G) == dg.QUANG5
        assert dg.classify(C, F) == dg.QUANG5

    def test_song_song_ca_hai_chieu(self):
        assert dg.classify(C, Am) == dg.SONG_SONG
        assert dg.classify(Am, C) == dg.SONG_SONG

    def test_cung_ten(self):
        assert dg.classify(C, Cm) == dg.CUNG_TEN

    def test_khac(self):
        assert dg.classify(C, D) == dg.KHAC
        assert dg.classify(C, Em) == dg.KHAC  # khác mode, không song song, khác chủ âm

    def test_khong_ra(self):
        assert dg.classify(C, None) == dg.KHONG_RA

    def test_tap_not_auto_tune(self):
        """Giọng song song cùng 7 nốt → với Auto-Tune coi như đúng."""
        assert dg.same_pitch_set(dg.classify(C, Am))
        assert not dg.same_pitch_set(dg.classify(C, G))
        assert not dg.same_pitch_set(dg.classify(C, Cm))


class TestTimeline:
    TL = [(0.0, Am), (60.0, (11, "Minor"))]  # nâng 1 cung ở điệp khúc cuối

    def test_key_at(self):
        assert dg.key_at(self.TL, 10) == Am
        assert dg.key_at(self.TL, 60) == (11, "Minor")

    def test_moc_dau_phu_ca_doan_truoc(self):
        assert dg.key_at([(5.0, C)], 0) == C

    def test_dominant_key(self):
        assert dg.dominant_key(self.TL, 0, 45) == Am
        assert dg.dominant_key(self.TL, 0, 200) == (11, "Minor")

    def test_timeline_agreement(self):
        # dò đổi tone trễ 10s trên bài 100s → khớp 90%
        pred = [(0.0, Am), (70.0, (11, "Minor"))]
        exact, pitch = dg.timeline_agreement(self.TL, pred, 100.0)
        assert exact == pytest.approx(0.9)
        assert pitch == pytest.approx(0.9)

    def test_timeline_song_song_van_khop_tap_not(self):
        exact, pitch = dg.timeline_agreement([(0.0, Am)], [(0.0, C)], 50.0)
        assert exact == 0.0
        assert pitch == 1.0

    def test_count_changes(self):
        assert dg.count_changes(self.TL) == 1
        assert dg.count_changes([(0.0, C), (10.0, C)]) == 0


class TestLoadDataset:
    def test_file_xuat_tu_admin(self, tmp_path):
        p = tmp_path / "dap_an.json"
        p.write_text(json.dumps({"items": [{
            "song_key": "AAAAAAAAAAA", "title": "Bài A",
            "timeline": [{"time": 0, "key_display": "Am"}, {"time": 95, "key_display": "Bm"}],
        }]}), encoding="utf-8")
        items = dg.load_dataset(str(p))
        assert len(items) == 1
        assert items[0]["url"].endswith("AAAAAAAAAAA")
        assert items[0]["timeline"] == [(0.0, Am), (95.0, (11, "Minor"))]

    def test_manual_timelines_bo_ban_may_do(self, tmp_path):
        p = tmp_path / "manual_timelines.json"
        p.write_text(json.dumps({
            "AAAAAAAAAAA": {"url": "https://youtu.be/AAAAAAAAAAA", "source": "human",
                            "timeline": [{"time": 0, "key_display": "C"}]},
            "BBBBBBBBBBB": {"url": "https://youtu.be/BBBBBBBBBBB", "source": "auto",
                            "timeline": [{"time": 0, "key_display": "G"}]},
            # entry cũ không có source = người sửa tay (tương thích ngược của app)
            "CCCCCCCCCCC": {"url": "https://youtu.be/CCCCCCCCCCC",
                            "timeline": [{"time": 0, "key_display": "Em"}]},
        }), encoding="utf-8")
        ids = {it["id"] for it in dg.load_dataset(str(p))}
        assert ids == {"AAAAAAAAAAA", "CCCCCCCCCCC"}

    def test_json_tu_soan_va_bo_muc_hong(self, tmp_path):
        p = tmp_path / "tu_soan.json"
        p.write_text(json.dumps([
            {"path": "a.wav", "key": "F#m"},
            {"path": "b.wav", "key": "không phải tone"},
            {"key": "C"},  # không có nguồn audio
        ]), encoding="utf-8")
        items = dg.load_dataset(str(p))
        assert [it["path"] for it in items] == ["a.wav"]
        assert items[0]["timeline"] == [(0.0, (6, "Minor"))]


    def test_file_dap_an_kiem_chung_trong_repo_doc_duoc(self):
        """tools/dap_an_tone_kiem_chung.json: bài đã kiểm chứng tay, phải luôn hợp lệ."""
        p = os.path.join(os.path.dirname(_PATH), "dap_an_tone_kiem_chung.json")
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
        items = dg.load_dataset(p)
        assert len(items) == len(raw), "có mục không đọc được tone hoặc thiếu url/path"
        assert all(it["url"] or it["path"] for it in items)
        assert all(it["timeline"] for it in items)
        ids = [it["id"] for it in items]
        assert len(ids) == len(set(ids)), "trùng id"


def test_summarize_tinh_dung_ba_con_so(capsys):
    rows = [{"cls": dg.DUNG}, {"cls": dg.SONG_SONG}, {"cls": dg.QUANG5}, {"cls": dg.KHAC}]
    s = dg.summarize(rows, "thử")
    assert s["exact"] == 1
    assert s["pitch"] == 2
    assert s["mirex"] == pytest.approx((1 + 0.3 + 0.5 + 0) / 4)
