# Phase 4 — Cloud Sync: ghi chú tích hợp

Đồng bộ thư viện bài + timeline + tone cache + lịch sử điểm qua licensing server.
Toàn bộ tính năng **chỉ chạy khi `entitlements.is_premium()`** — Standard luôn nhận
`{"skipped": "not_premium"}`.

## Thành phần đã thêm (Phase 4 này)

### Server (`server/`)
- `server/app/models.py` — model `SyncBlob` (unique `(license_code, kind)`, cột
  `data` Text, `version` Int, `updated_at` DateTime). Bảng tạo qua
  `Base.metadata.create_all` (router import model ⇒ tự đăng ký).
- `server/app/schemas.py` — `SyncPutRequest`, `SyncGetRequest`, `SyncResponse`.
- `server/app/routers/sync.py` — prefix `/api/v1/sync`:
  - `PUT /{kind}` — xác thực token (fp khớp), upsert, last-write-wins theo
    `updated_at`, trả `version` mới. Nếu server có bản mới hơn → `stale=True`,
    không ghi đè.
  - `POST /{kind}/get` — token trong body (khuyến nghị), trả blob + version.
  - `GET /{kind}?token=...&device_fingerprint=...` — tiện debug.
  - `kind ∈ {songs, timelines, tones, scores}`. Rate-limit `rate_limit_verify`.
- `server/app/main.py` — `app.include_router(sync.router)`.
- `server/tests/test_sync.py` — round-trip, version/last-write-wins, từ chối token
  sai thiết bị, 2 máy cùng mã chia sẻ blob.

### Client (`core/licensing/sync.py`)
- `push(kind)`, `pull(kind)`, `sync_all()`.
- `KIND_FILES`: `songs→saved_songs.json`, `timelines→manual_timelines.json`,
  `tones→tone_cache.json`, `scores→score_history.json` (lấy `HISTORY_FILE` từ
  `core.score_history`).
- urllib helper `_request(method, path, payload)` (timeout 10s, fail-soft `status=0`
  khi mạng lỗi/chưa cấu hình server).
- Auth đọc từ activation cache qua `client._load()` (token/code/fingerprint).
- An toàn pull: backup `.bak` trước khi ghi đè; **songs** merge theo
  `song_match_key(url)` (bài chỉ có ở local KHÔNG bị mất; remote đè khi trùng key);
  các kind khác last-write-wins. Ghi bằng `atomic_write_json`.

## Việc agent chủ cần chèn (KHÔNG sửa trong Phase 4 này)

### 1. Sync nền lúc khởi động — `main.py` GỐC, `_background_maintenance()` (dòng ~149)

Thêm vào cuối hàm, sau khối re-verify license:

```python
    # Cloud Sync nền (Premium). Fail-soft: lỗi mạng/không cấu hình → bỏ qua.
    try:
        from core import entitlements
        if entitlements.is_premium():
            from core.licensing import sync as _sync
            res = _sync.sync_all()
            log.info("Cloud sync nền: %s", res.get("results", res))
    except Exception as e:
        log.debug("cloud sync skipped: %s", e)
```

Lưu ý: hàm này chạy trong daemon thread (`main.py:199`), nên gọi mạng ở đây an toàn,
không chặn UI.

### 2. Nút "Đồng bộ ngay" — `ui/dialogs/settings_dialog.py`

Trong `_build_*` của tab phù hợp (gợi ý: dưới phần "Đường dẫn ứng dụng" hoặc tạo
section mới "Đồng bộ đám mây"), thêm một section + nút. Mẫu:

```python
# Trong _build_app_tab (hoặc tab tài khoản/license), sau một section_header:
lay.addWidget(self._section_header(SVG_GLOBE, "Đồng bộ đám mây (Premium)"))
sync_btn = QPushButton("Đồng bộ ngay")
sync_btn.clicked.connect(self._on_cloud_sync)
lay.addWidget(sync_btn)
```

Callback (đặt làm method của dialog) — gate premium + chạy nền để không treo UI:

```python
def _on_cloud_sync(self):
    # Gate Premium: tái dùng helper upsell của frontend nếu có parent.
    try:
        from core import entitlements
        if not entitlements.is_premium():
            # Mở dialog upsell (Phase 0): self.parent()._require_premium("cloud_sync", "Đồng bộ đám mây")
            from ui.dialogs.premium_dialog import PremiumUpsellDialog
            PremiumUpsellDialog(self, feature="cloud_sync", label="Đồng bộ đám mây").exec()
            return
    except Exception:
        return

    import threading
    def _work():
        try:
            from core.licensing import sync as _sync
            res = _sync.sync_all()
            # Cập nhật UI phải về main thread (QTimer.singleShot / signal).
            log.info("Cloud sync thủ công: %s", res)
        except Exception as e:
            log.warning("Cloud sync lỗi: %s", e)
    threading.Thread(target=_work, daemon=True).start()
```

Lưu ý UI thread: `sync_all()` gọi mạng + ghi file ⇒ PHẢI chạy ở thread nền; mọi
cập nhật widget (toast/label kết quả) phải marshal về main thread (QTimer.singleShot
hoặc Qt signal). Sau pull "songs", thư viện cần reload (gọi lại loader bài của
dashboard) để thấy bài mới.

## Chạy test server

Server deps KHÔNG có trong venv app hiện tại. Cần cài riêng:

```bash
pip install -r server/requirements.txt
cd server && pytest tests/test_sync.py -v
```

(Hoặc `pytest server/tests` từ gốc nếu `server/` nằm trong path import — conftest
trong `server/tests` set env DB SQLite tạm.)

## Ghi chú thiết kế / hạn chế
- Server lưu blob mờ (opaque JSON string), không validate nội dung — đơn giản, an
  toàn schema-evolution; trade-off: không merge phía server.
- Merge chỉ áp cho `songs` (theo `song_match_key`). `timelines`/`tones`/`scores`
  là last-write-wins + backup `.bak`. Nếu cần merge sâu hơn (vd union score_history
  theo timestamp) có thể mở rộng `_merge_*` sau mà không đổi server.
- `updated_at` dùng mtime file local; nếu đồng hồ 2 máy lệch nhiều, last-write-wins
  có thể chọn sai bản — chấp nhận theo plan (kèm cờ `stale`).
```
