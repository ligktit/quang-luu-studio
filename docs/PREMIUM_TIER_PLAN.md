# Kế hoạch: Hệ thống tính năng "Premium only" cho Quang Lưu Studio

## Context

App hiện chỉ gate **nhị phân**: *đã kích hoạt / trial / hết hạn* (`core/activation.py`, `main.py`). Không có khái niệm tier. Tuy nhiên server license **đã có sẵn** cột `License.plan` (default `"standard"`, `server/app/models.py:42`) và admin UI **đã** cho chọn plan khi tạo mã (`server/app/routers/admin.py:137`). Mắt xích còn thiếu: `plan` **không** được nhúng vào token/response → client không bao giờ biết mình là Standard hay Premium.

Mục tiêu: dựng tier **Standard / Premium**, khóa tính năng **Chấm điểm** (đã có) và xây **4 tính năng Premium mới** làm đòn bẩy bán hàng:
1. **Smart Recall** — preset tone/mix/mode tự áp dụng theo bài.
2. **Cloud Sync** — đồng bộ thư viện bài + timeline + tone cache qua server.
3. **Bảng tiến bộ luyện hát** — lịch sử điểm chấm + biểu đồ tiến bộ.
4. **Live Setlist / Auto-Pilot** — hàng đợi bài, tự dò tone & chuyển bài.

**Quyết định đã chốt với người dùng:**
- Mô hình **2 tầng** Standard + Premium (khớp default `"standard"`).
- Trial 3 ngày = **chỉ Standard** (Premium chỉ khi mua mã Premium).
- Enforce: **tin cache + verify online định kỳ** (không verify chữ ký JWT ở client — đã có `_background_maintenance` re-verify nền trong `main.py:149`).

---

## Phase 0 — Hạ tầng entitlement (nền tảng, BẮT BUỘC trước mọi thứ)

### Server (`server/`)
- `server/app/security.py:issue_license_token` — thêm tham số `plan` và nhúng claim `"plan": plan` vào JWT payload.
- `server/app/services/licensing.py` — `activate()` (dòng ~117) và `verify()` (dòng ~157): truyền `lic.plan` vào `issue_license_token(...)`, và thêm `"plan": lic.plan` vào dict trả về.
- `server/app/schemas.py:LicenseResponse` — thêm field `plan: str = "standard"`.
- `server/app/routers/admin.py` — đã có `plan` ở `generate_licenses`; kiểm tra `templates/licenses.html` có dropdown chọn `standard|premium` chưa, nếu chưa thì thêm. Thêm action POST `/licenses/{id}/set-plan` để đổi plan mã đã phát.
- Test: mở rộng `server/tests/test_activation.py` — assert response & token có `plan` đúng cho mã premium.

### Client (`core/licensing/client.py`)
- `_store_from_response()` — lưu thêm `"plan": body.get("plan") or claims.get("plan") or "standard"` vào cache `activation.json` (đọc cả từ response lẫn JWT claim để chống lệch).
- Thêm hàm `current_plan() -> str` đọc `plan` từ cache (mặc định `"standard"`).

### Lớp entitlement trung tâm (mới: `core/entitlements.py`)
- Nguồn chân lý duy nhất cho UI/engine. API:
  - `current_plan() -> str` — online: lấy từ `client.current_plan()` nếu `has_online_license()`; offline mode (chưa cấu hình server): `"standard"`.
  - `is_premium() -> bool` — `current_plan() == "premium"` **và** license còn hiệu lực (`ActivationManager.is_activated() and not is_expired()`). Trial → luôn `False` (trial = Standard).
  - `PREMIUM_FEATURES` — set tên feature đã khóa (vd `{"scoring", "smart_recall", "cloud_sync", "progress", "setlist"}`).
  - `has_feature(name) -> bool`.
- Lý do tách module riêng thay vì nhét vào `ActivationManager`: tránh phình class activation và để engine/UI import 1 chỗ.

### UX gate dùng chung (`frontend_qt.py`)
- Thêm helper `self._require_premium(feature, label) -> bool`: nếu `entitlements.has_feature` False → mở dialog upsell (mới: `ui/dialogs/premium_dialog.py` — `PremiumUpsellDialog`) giải thích tính năng + nút "Nâng cấp"/"Nhập mã" mở lại `ActivationDialog`, rồi `return False`. Mọi callback Premium gọi helper này ở dòng đầu.
- Badge "PRO": thêm tiện ích vẽ nhãn nhỏ (tái dùng `PainterButton`/SVG sẵn có) gắn lên nút Premium khi Standard, để hiện rõ tính năng bị khóa thay vì ẩn.

**Verify Phase 0:** chạy `pytest server/tests`; chỉnh tay `activation.json` thêm `"plan":"premium"` → `python -c "from core import entitlements; print(entitlements.is_premium())"` trả `True`.

---

## Phase 1 — Khóa "Chấm điểm" (tính năng sẵn có)

- `frontend_qt.py:_on_score()` (dòng ~1051): chèn `if not self._require_premium("scoring", "Chấm Điểm"): return` ngay đầu hàm.
- Nút Score (`ui/panels/bottom_bar.py:btn_score`): khi Standard → vẫn hiển thị + gắn badge PRO (không ẩn, để upsell).
- Voice command "chấm điểm" (`core/accessibility/voice_input.py`): khi Standard, route về cùng dialog upsell thay vì chạy.

**Verify:** Standard bấm Chấm điểm → hiện upsell, không ghi âm. Premium → chạy như cũ.

---

## Phase 2 — Smart Recall (preset theo bài)

Tự khôi phục **tone, scale, mức mixer, mode** đã dùng lần trước khi mở 1 bài đã lưu.

- **Data:** mở rộng schema bài trong `core/songs.py` — `add_song`/`update_song` thêm key tùy chọn `preset: {tone, scale, mixer:{music,mic,reverb,backing}, mode}`. Tương thích ngược (bài cũ không có `preset`).
- **Lưu preset:** thêm `SongManager.save_preset(song_id, preset_dict)`. Gọi từ nút mới "Lưu preset bài" (gate premium) hoặc tự bắt snapshot khi lưu bài.
- **Áp preset:** hàm `frontend_qt._apply_song_preset(song)` — đẩy MIDI CC qua engine (tái dùng `_on_tone_selected`, `_on_scale_selected`, mixer callbacks, `_on_mode_selected`). Gọi trong luồng mở bài từ `_show_songs_list` / double-click (`ui/dialogs/songs_list.py`).
- **Gate:** `_apply_song_preset` & nút lưu preset bọc `_require_premium("smart_recall", ...)`. Standard mở bài như cũ (không auto-apply).

**Verify:** Premium chỉnh tone/mixer → lưu preset → mở bài khác rồi quay lại → giá trị tự khôi phục (MIDI CC gửi đúng).

---

## Phase 3 — Bảng tiến bộ luyện hát (scoring history)

- **Data (mới `core/score_history.py`):** lưu mỗi lần chấm vào `score_history.json` — `{timestamp, song_title, url, overall, pitch, rhythm, tone}`. Atomic write (tái dùng `core/utils.atomic_write_json`).
- **Ghi điểm:** trong `_on_score` callback `on_ready` (dòng ~1095), sau khi có report → `ScoreHistory.add(report)`. (Chạy cho Premium vì Score đã gate.)
- **UI (mới `ui/dialogs/progress_dialog.py`):** biểu đồ điểm theo thời gian (QtCharts nếu có, fallback QPainter line chart), điểm TB, xu hướng pitch/rhythm, gợi ý. Mở từ nút mới ở bottom bar / songs list (gate premium).

**Verify:** Premium chấm 2–3 lần → mở Bảng tiến bộ thấy các mốc + đường xu hướng.

---

## Phase 4 — Cloud Sync thư viện bài

Đồng bộ `saved_songs.json`, `manual_timelines.json`, `tone_cache.json`, `score_history.json` qua server (tận dụng FastAPI + DB sẵn có).

- **Server:** model mới `UserData` (hoặc `SyncBlob`) khóa theo `license_code` lưu JSON blob + `updated_at` + version. Router mới `server/app/routers/sync.py`: `GET/PUT /api/v1/sync/{kind}` xác thực bằng license token (tái dùng `decode_license_token`). Last-write-wins theo `updated_at`, kèm cảnh báo xung đột.
- **Client (mới `core/licensing/sync.py`):** `push(kind)` / `pull(kind)` / `sync_all()` dùng `client._post` pattern (urllib). Chạy nền lúc khởi động (mở rộng `_background_maintenance` trong `main.py`) + nút "Đồng bộ ngay" trong Settings.
- **Gate:** toàn bộ sync bọc `is_premium()`. Standard không gọi server.
- **An toàn:** backup file local trước khi ghi đè khi pull; merge theo `id`/`video_id` (tái dùng `song_match_key`).

**Verify:** 2 máy cùng mã Premium → thêm bài máy A → "Đồng bộ ngay" → máy B pull thấy bài mới. Standard: nút sync hiện upsell.

---

## Phase 5 — Live Setlist / Auto-Pilot

Hàng đợi bài cho buổi live: tự dò tone trước, áp preset, hỗ trợ chuyển bài.

- **Data:** tái dùng `PlaylistManager` (đã có `playlists.json`, `song_ids`) làm nguồn setlist — không cần model mới.
- **UI (mới `ui/dialogs/setlist_dialog.py`):** chọn playlist → bảng hàng đợi (bài hiện tại/kế tiếp), nút "Bắt đầu Auto-Pilot", "Bài kế".
- **Engine:** tái dùng `engine.start_youtube_watcher` + tone detect để **prefetch** tone bài kế trong nền (đẩy vào `ToneCacheManager`), khi chuyển bài thì áp preset (tái dùng `_apply_song_preset` Phase 2) + mở URL YouTube.
- **Gate:** mở Setlist/Auto-Pilot bọc `_require_premium("setlist", ...)`.

**Verify:** Premium tạo setlist 3 bài → Auto-Pilot → bài kế đã có tone dò sẵn, chuyển bài áp đúng tone/mixer.

---

## Thứ tự triển khai đề xuất
**Phase 0 → 1** trước (nền + chốt mô hình gate qua 1 tính năng thật). Sau đó 2 (Smart Recall, độc lập, nền cho Phase 5) → 3 (Progress, nhẹ) → 4 (Cloud Sync, nặng server) → 5 (Setlist, phụ thuộc 2). Mỗi phase commit riêng trên branch mới `feat/premium-tier` (KHÔNG commit thẳng `main`).

## Rủi ro & lưu ý
- Enforce mềm (tin cache) → người rành có thể sửa `activation.json`. Chấp nhận theo quyết định; `_background_maintenance` re-verify nền giảm thiểu. Có thể nâng lên RS256 sau mà không phá kiến trúc.
- Tương thích ngược: mọi field mới (`plan`, `preset`) đều optional, default Standard — bản client/license cũ vẫn chạy.
- Trial phải trả Premium = False ở `entitlements.is_premium()` — viết test riêng cho nhánh trial.
- **Memory:** theo ghi nhớ dự án, copy bản kế hoạch này vào `docs/` khi bắt đầu implement (ngoài plan mode mới ghi được).
