"""
Quang Lưu Studio — Lịch sử chấm điểm (Premium "Bảng tiến bộ luyện hát").

Lưu mỗi lần chấm điểm vào `score_history.json` (trong DATA_DIR) để dựng biểu
đồ tiến bộ theo thời gian. Tất cả API là staticmethod, fail-soft: lỗi đọc/ghi
file KHÔNG bao giờ làm vỡ luồng chấm điểm — load() trả [] khi hỏng.

Mỗi entry có shape:
    {
        "timestamp": <float epoch seconds>,
        "song_title": <str>,
        "url": <str>,
        "overall": <float>,   # map từ report["total_score"]
        "pitch": <float>,     # trung bình pitch_intonation & pitch_stability
        "rhythm": <float>,    # report["rhythm_score"]
        "tone": <float>,      # report["key_conformity"] (đúng tông)
    }
"""
import os
import json
import time
import logging

from core.config import DATA_DIR
from core.utils import atomic_write_json

log = logging.getLogger(__name__)

# File lưu lịch sử (user-writable → DATA_DIR).
HISTORY_FILE = os.path.join(DATA_DIR, "score_history.json")

# Giới hạn số entry giữ lại (cắt cũ nhất khi vượt).
MAX_ENTRIES = 500


def _num(v) -> float:
    """Ép giá trị về float an toàn (None/str lỗi → 0.0)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _entry_from_report(report: dict, song_title: str, url: str) -> dict:
    """Trích các chỉ số cần lưu từ dict report của ScoringEngine.

    Khóa thật trong report (xem core/scoring.py):
      total_score, pitch_intonation, pitch_stability, rhythm_score,
      key_conformity, volume_consistency, voiced_ratio.
    """
    report = report or {}
    pitch_intonation = _num(report.get("pitch_intonation"))
    pitch_stability = _num(report.get("pitch_stability"))
    # pitch tổng hợp: TB của intonation & stability nếu có, không thì lấy giá trị
    # nào > 0 (một số nhánh scoring chỉ có 1 trong 2).
    vals = [v for v in (pitch_intonation, pitch_stability) if v > 0]
    pitch = round(sum(vals) / len(vals), 1) if vals else 0.0

    return {
        "timestamp": time.time(),
        "song_title": str(song_title or ""),
        "url": str(url or ""),
        "overall": _num(report.get("total_score")),
        "pitch": pitch,
        "rhythm": _num(report.get("rhythm_score")),
        "tone": _num(report.get("key_conformity")),
    }


class ScoreHistory:
    """Kho lưu lịch sử chấm điểm (file JSON, fail-soft)."""

    @staticmethod
    def load() -> list:
        """Đọc toàn bộ lịch sử. Lỗi/thiếu file → []."""
        try:
            if not os.path.exists(HISTORY_FILE):
                return []
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            log.warning("score_history.json không phải list — bỏ qua")
            return []
        except Exception as e:
            log.warning("Lỗi đọc score_history.json: %s", e)
            return []

    @staticmethod
    def add(report: dict, song_title: str = "", url: str = "") -> bool:
        """Append 1 entry từ report. Trả True nếu ghi thành công.

        Fail-soft: mọi lỗi đều nuốt và trả False (không làm vỡ luồng chấm điểm).
        Cắt giữ tối đa MAX_ENTRIES entry mới nhất.
        """
        try:
            entry = _entry_from_report(report, song_title, url)
            history = ScoreHistory.load()
            history.append(entry)
            if len(history) > MAX_ENTRIES:
                history = history[-MAX_ENTRIES:]
            atomic_write_json(HISTORY_FILE, history)
            return True
        except Exception as e:
            log.warning("Lỗi lưu score_history: %s", e)
            return False

    @staticmethod
    def recent(n: int = 20) -> list:
        """Trả n entry mới nhất (cuối danh sách)."""
        if n <= 0:
            return []
        return ScoreHistory.load()[-n:]

    @staticmethod
    def summary() -> dict:
        """Tổng hợp thống kê cho Bảng tiến bộ.

        Trả dict:
            count        — tổng số lần chấm
            avg_overall  — điểm overall trung bình
            avg_pitch / avg_rhythm / avg_tone — TB từng chỉ số
            best         — điểm overall cao nhất
            latest       — điểm overall lần gần nhất
            trend        — "up" | "down" | "flat" (so 5 gần nhất với 5 trước đó)
            trend_delta  — chênh lệch điểm TB hai nửa (float)
        """
        history = ScoreHistory.load()
        count = len(history)
        if count == 0:
            return {
                "count": 0,
                "avg_overall": 0.0,
                "avg_pitch": 0.0,
                "avg_rhythm": 0.0,
                "avg_tone": 0.0,
                "best": 0.0,
                "latest": 0.0,
                "trend": "flat",
                "trend_delta": 0.0,
            }

        def _avg(key):
            return round(sum(_num(e.get(key)) for e in history) / count, 1)

        overalls = [_num(e.get("overall")) for e in history]

        # Xu hướng: so điểm TB của tối đa 5 entry gần nhất với 5 entry liền trước.
        window = min(5, count // 2) if count >= 2 else 0
        trend = "flat"
        trend_delta = 0.0
        if window > 0:
            recent_avg = sum(overalls[-window:]) / window
            prev_avg = sum(overalls[-2 * window:-window]) / window
            trend_delta = round(recent_avg - prev_avg, 1)
            if trend_delta > 1.0:
                trend = "up"
            elif trend_delta < -1.0:
                trend = "down"

        return {
            "count": count,
            "avg_overall": _avg("overall"),
            "avg_pitch": _avg("pitch"),
            "avg_rhythm": _avg("rhythm"),
            "avg_tone": _avg("tone"),
            "best": round(max(overalls), 1),
            "latest": round(overalls[-1], 1),
            "trend": trend,
            "trend_delta": trend_delta,
        }
