# Tone đã lưu không bị dò đè (1.7.5)

> **Triệu chứng khách báo:** bài hát đã lưu tone chỉnh tay (kể cả sửa bằng
> **"Sửa chuỗi tone"**), nhưng mở bài trên trình duyệt qua URL thì app vẫn dò
> tone lại và chạy tone nó tự dò, không chạy tone đã lưu.

Tài liệu này ghi lại 4 điểm mù đã tìm ra, cách vá, và cách kiểm chứng.
Sơ đồ luồng cập nhật nằm ở [TONE_FLOWS.md](TONE_FLOWS.md).

---

## 1. Bốn điểm mù

| # | Điểm mù | Hậu quả thực tế |
|---|---------|-----------------|
| 1 | **Tone của bài không nằm trong chuỗi resolve.** Tone khách chọn ở ô Tone ("Lưu bài hát" / "Sửa thông tin") ghi vào `saved_songs.json → tone`, nhưng `_resolve_tone` chỉ đọc `ManualToneTimeline` → `ToneCache` → thư viện cộng đồng. Lúc mở bài, ô tone lại được set trong `QSignalBlocker` nên **không gửi MIDI**. | Bài "đã có tone" nhưng với engine là bài trắng → tải audio dò lại từ đầu, rồi đè tone mới lên. |
| 2 | **Đệm resolve trong phiên không bao giờ hết hạn.** `_tone_resolve_cache_invalidate` chỉ được gọi khi CHÍNH engine lưu cache. Dialog "Sửa chuỗi tone" ghi thẳng xuống đĩa, không báo engine. Đệm còn khóa theo chuỗi URL thô. | Sửa chuỗi tone tay giữa phiên → mở lại bài vẫn chạy **tone tự động cũ** trong RAM; phải tắt/mở lại app mới đúng. |
| 3 | **Đường "dán link / ô tìm kiếm" không tra tone đã lưu.** `play_youtube_in_app` gọi `_clear_tone_timeline()` rồi `open_youtube_url(url)` **không** truyền `manual_timeline`. | Mở bài bằng link (đúng kịch bản khách báo) → không replay gì; tone có được áp hay không phụ thuộc may rủi vào watcher. |
| 4 | **Chế độ FULL bỏ qua cache + watcher so URL bằng chuỗi.** `auto_detect_youtube_timeline` chỉ xét timeline thủ công; watcher so `url != _last_watched_url` nguyên văn. | Chế độ "dò toàn bài": có cache vẫn tải + phân tích lại cả bài. Link chia sẻ `youtu.be/…?si=` bị coi là "bài mới" → hủy replay đang chạy để dò lại. |

**Bằng chứng (probe chạy trên code trước khi vá):**

```
CASE 1  bài lưu tone "Am" trong saved_songs.json
        resolve -> (None, None)          => engine tải audio dò lại

CASE 2  cùng phiên: resolve #1 -> cache C   (nạp vào RAM)
        khách sửa tay thành Am
        resolve #2 -> cache C            => SAI, vẫn tone cũ
CASE 3  mở lại app: resolve -> manual Am => đúng
```

---

## 2. Cách vá

### 2.1 Chuỗi resolve có thêm "tone của bài" (`core/tone_cache.py`)

```
đệm phiên → timeline thủ công → tone_cache → tone bài đã lưu → thư viện cộng đồng → DÒ
```

* `song_tone_entry(url)` — tra `saved_songs.json` theo `song_match_key` (video_id,
  nên link dạng nào cũng khớp) rồi dựng timeline 1 mốc.
* `make_timeline_entry(key_display, at=0)` — một chỗ duy nhất biến tên tone
  (`"Am"`) thành mốc đúng nốt/thể/`key_index`. Dùng lại ở `edit_song.py` để bỏ
  đoạn code trùng.
* `saved_tone_timeline(url)` — chuỗi tone khách đã lưu (thủ công → tone bài),
  dùng chung cho MỌI đường mở bài.
* Đặt **sau** `tone_cache` (cache mới hơn, có timeline nhiều đoạn) và **trước**
  thư viện cộng đồng (dữ liệu của chính khách thắng dữ liệu người lạ).

### 2.2 Đệm phiên tự hết hạn theo thế hệ dữ liệu

* `core.tone_cache.data_version()` tăng ở **mọi** đường ghi: `save_tone`,
  `clear_cache`, `save_timeline`, `delete_timeline`.
* `_resolve_tone` so số này rồi bỏ sạch đệm — không call site nào "quên" được.
* Đệm khóa theo `song_match_key` cho khớp tầng đĩa.

### 2.3 Mọi đường mở bài dùng chung một nguồn

* `MainDashboard._saved_manual_timeline(url)` → `saved_tone_timeline(url)`.
* Dùng ở: `play_youtube_in_app` (dán link / tìm kiếm), `SongsListDialog._make_play`,
  `_setlist_play_song`.
* Khách đổi tone ở ô Tone ("Lưu bài hát" khác tone điền sẵn / vừa chỉnh tay, hoặc
  "Sửa thông tin") → `_save_single_tone_timeline` ghi chuỗi tone thủ công 1 mốc.
  **Không bao giờ đè** chuỗi nhiều mốc đã có.
* Auto-save sau khi dò xong lưu `key_display` (`"Am"`) thay vì nốt gốc (`"A"`) —
  mất chữ `m` là mất luôn thể thứ. Chỗ hiển thị ô tone tách lại nốt gốc.

### 2.4 Chế độ FULL + watcher

* `auto_detect_youtube_timeline` gọi `_resolve_tone` (dùng chung với chế độ nhanh);
  bản cache đi qua `_build_cache_result` để giữ bất biến *hiển thị = MIDI = cache*.
* `_same_song(a, b)` so theo video_id, dùng ở 3 chỗ so URL của watcher.
* **Hệ quả phải vá kèm:** bài CHƯA có tone trước đây được dò *nhờ may* — app mở
  link chia sẻ, trình duyệt hiện link chuẩn, watcher so chuỗi thấy khác nên tưởng
  "URL mới" rồi dò. So theo bài làm cú dò tình cờ đó biến mất, nên
  `open_youtube_url` gọi thẳng `_ensure_tone_for_url(url)` (bỏ qua nếu phiên
  dò/replay của chính bài đó đang chạy → không cắt ngang).
* "Dò Lại" (`skip_resolve=True`) vẫn bỏ qua toàn bộ chuỗi resolve — tone sai không
  bao giờ khóa cứng bài.

---

## 3. Kiểm thử

| File | Nội dung |
|------|----------|
| `tests/core/test_tone_resolve_saved.py` | 22 test: `make_timeline_entry`, `song_tone_entry`/`saved_tone_timeline`, resolve ra tone bài đã lưu, đệm phiên khóa theo video_id + tự bỏ khi sửa tay, `_ensure_tone_for_url`, `_same_song`, chế độ FULL replay cache thay vì dò lại, "Dò Lại" vẫn dò mới. |
| `tests/ui/test_open_song_tone.py` | 8 test: ghi tone khách tự chọn (và không đè chuỗi nhiều mốc), `play_youtube_in_app` truyền `manual_timeline`, nút Phát ở Danh sách bài hát hiện đúng "Am" → "A". |

```
python -m pytest tests/ -q     →  666 passed
```

---

## 4. Cách khách kiểm chứng nhanh

1. Mở một bài đã sửa chuỗi tone → **không** thấy "Đang dò tone…", tone lên ngay,
   chữ chạy có nhãn *(đã lưu — sai? bấm Dò Lại)*.
2. Đang trong phiên, sửa chuỗi tone rồi mở lại bài → chạy **tone vừa sửa** (trước
   đây phải tắt/mở app).
3. Dán link chia sẻ `youtu.be/…?si=…` của bài đã lưu → vẫn chạy tone đã lưu.
4. Muốn dò lại thật: bấm **Dò Lại** — nút này luôn bỏ qua tone đã lưu.
