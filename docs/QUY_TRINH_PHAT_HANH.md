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
