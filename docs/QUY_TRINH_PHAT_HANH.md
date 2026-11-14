# Quy trình phát hành (từ 1.9.0 — Velopack)

1. Sửa `core/version.py` (`__version__`, `VERSION_TUPLE`, `BUILD_DATE`) → `python sync_version.py`
   (cập nhật `QuangLuuStudio_Bridge.iss`, sổ tay, `BUNDLED_YTDLP_VERSION`).
   **Phải sửa `core/version.py` TRƯỚC khi chạy `sync_version.py`**: nếu không, bộ cài cầu nối
   được đặt tên theo số phiên bản cũ và trùng tên tệp với bộ cài cũ.
2. Viết `docs/release_notes/vX.Y.Z.md` (giọng cho ca sĩ/kỹ thuật viên).
3. Suite xanh → commit lên `main` → `git tag -a vX.Y.Z -m ...` → `git push origin vX.Y.Z`.
   CI build onedir, `vpk pack` (delta từ bản trước), bộ cài cầu nối, tạo GitHub Release **prerelease**.
4. Kiểm: `gh release view vX.Y.Z --json assets,isPrerelease` → `isPrerelease: true`, có
   `releases.win.json`, `QuangLuuStudio-X.Y.Z-full.nupkg`, `QuangLuuStudio-CaiDat.exe`,
   `Setup_QuangLuuStudio_vX.Y.Z.exe`.
5. Trang admin → Phiên bản → **Nhập từ GitHub** `X.Y.Z` → chờ trạng thái "xong" → bật, đặt
   rollout 10% → theo dõi log → mở rộng. `/tai-ve` chỉ trỏ bản này khi rollout 100%.
6. Máy còn 1.8.x: tải `Setup_QuangLuuStudio_vX.Y.Z.exe` từ GitHub Release rồi **upload qua
   `/admin/versions/upload`** như trước (đường `/api/v1/updates/check`). Làm ở mọi bản cho tới
   khi log server không còn máy 1.8.x.
7. Rút bản lỗi: tắt (`is_active`) trên admin để dừng phát tán; máy đã nhận thì phát hành bản vá số cao hơn.

Build tại máy dev (không tag): `build_installer.bat` → `releases\QuangLuuStudio-CaiDat.exe` +
`installer_output\Setup_QuangLuuStudio_v<ver>.exe`. Cần `vpk` 1.2.161 (`dotnet tool install -g vpk --version 1.2.161`).

## Việc treo: build lại 1.9.0 trước khi gửi khách (ghi 2026-11-10)

Bản 1.9.0 build tại máy dev ngày 2026-10-13 (`releases\QuangLuuStudio-CaiDat.exe`, gói
`QuangLuuStudio-1.9.0-full.nupkg`) đã **cũ**. Nó mang `cubase/QuangLuu_QuangLuuMIDI.js` có
`QLS_SCRIPT_VERSION = '2026-10-08'`, chưa có sửa ad5b745 (2026-10-28). Sửa này giữ hồ sơ plugin đã chọn theo
tên, để script không ghi Scale nhầm vào tham số 3 "Detune" của Auto-Tune Pro.

**Đừng gửi lại bộ cài/gói đó cho máy nào nữa.**

Chuyện đã xảy ra:

- Máy 3 DESKTOP-M21N7VP cài gói này lúc 2026-11-09 19:28. Velopack thay `current\` bằng nội dung gói, nên script
  kèm app quay về bản cũ.
- Tự sửa âm thanh báo «Bản điều khiển trong phần mềm thu âm — cần làm tay». Nếu nó chép được bản cũ đè lên
  Documents thì máy sẽ quay lại lỗi Scale→Detune.
- Đã chữa tay qua UltraViewer: đồng bộ Documents và `current\cubase` về bản HEAD, gỡ ReadOnly.
- Lần cài hoặc cập nhật kế tiếp bằng gói cũ sẽ làm lỗi quay lại.

Khi build lại:

1. Build từ HEAD của `feat/velopack-installer`. Commit trước các sửa đang ở working tree: Audio Doctor nhận
   file ReadOnly (`core/audio_doctor/*`) và hồ sơ Auto-Tune Artist trong script Cubase.
2. Kiểm script trong bản build trùng repo:
   `fc /b dist\QuangLuuStudio\cubase\QuangLuu_QuangLuuMIDI.js cubase\QuangLuu_QuangLuuMIDI.js`.
   Hoặc mở file trong gói và xem `QLS_SCRIPT_VERSION` ≥ `'2026-10-28'` và có dòng `if (hoSoHienTai.key_root === idx) return`.
3. Bộ cài/gói mới thay cho bản cũ ở mọi chỗ đã gửi khách. Xong thì xoá mục này.
