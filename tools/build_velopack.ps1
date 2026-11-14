# tools/build_velopack.ps1
# Đóng gói bản onedir (dist\QuangLuuStudio) thành bộ cài Velopack. Dùng chung cho
# máy dev (build_installer.bat) và CI (.github/workflows/release.yml).
#   1. chép tài nguyên cạnh exe (thay [Files] của bộ cài Inno cũ);
#   2. tải gói bản trước từ GitHub Release (prerelease) để vpk sinh gói delta;
#   3. vpk pack;
#   4. đổi tên Setup → QuangLuuStudio-CaiDat.exe (tên KHÔNG chứa "setup": bộ cập
#      nhật cũ ≤ 1.8 lấy file .exe đầu tiên có chữ "setup" trong release).
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [string]$OutputDir = "releases",
    [string]$GithubToken = "",
    [switch]$NoDelta
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$pack = Join-Path $root "dist\QuangLuuStudio"
if (-not (Test-Path (Join-Path $pack "QuangLuuStudio.exe"))) {
    throw "Thiếu dist\QuangLuuStudio\QuangLuuStudio.exe — chạy PyInstaller QuangLuuStudio.spec trước"
}

# 1. Tài nguyên cạnh exe
$files = @("app_icon.ico", "setup_all.bat", "setup_midi_ports.ps1", "configure_youtube_cookies.bat",
           "kiem_tra_tone.bat", "thu_tai_youtube.bat", "app_config.json", "binaries\qjs.exe")
$dirs = @(
    @("studio_one", "studio_one"),
    @("cubase", "cubase"),
    @("sfx", "sfx"),
    @("models", "models"),
    @("tools\piper", "tools\piper"),
    @("binaries\ffmpeg", "ffmpeg")
)
$missing = @($files | Where-Object { -not (Test-Path $_) }) + @($dirs | ForEach-Object { $_[0] } | Where-Object { -not (Test-Path $_) })
if ($missing.Count -gt 0) { throw ("Thiếu tài nguyên đóng gói: " + ($missing -join ", ")) }
foreach ($f in $files) { Copy-Item -LiteralPath $f -Destination $pack -Force }
foreach ($d in $dirs) {
    $dst = Join-Path $pack $d[1]
    if (Test-Path $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item -LiteralPath $d[0] -Destination $dst -Recurse -Force
}

# 2. Gói bản trước (delta). Bản đầu tiên chưa có gì để tải → chỉ có gói Full.
New-Item -ItemType Directory -Force $OutputDir | Out-Null
if (-not $NoDelta) {
    $dl = @("download", "github", "--repoUrl", "https://github.com/ligktit/quang-luu-studio", "--pre", "-o", $OutputDir)
    if ($GithubToken) { $dl += @("--token", $GithubToken) }
    & vpk @dl
    if ($LASTEXITCODE -ne 0) { Write-Host "[!] Không tải được bản trước — chỉ tạo gói Full" }
}

# 3. Pack (vpk 1.2.161 không có --noPortable → xoá file Portable.zip sau khi pack)
Remove-Item -LiteralPath (Join-Path $OutputDir "QuangLuuStudio-CaiDat.exe") -Force -ErrorAction SilentlyContinue
& vpk pack --packId QuangLuuStudio --packVersion $Version --packTitle "Quang Lưu Studio" `
    --packDir $pack --mainExe QuangLuuStudio.exe --icon app_icon.ico --outputDir $OutputDir
if ($LASTEXITCODE -ne 0) { throw "vpk pack lỗi (mã $LASTEXITCODE)" }
Remove-Item -LiteralPath (Join-Path $OutputDir "QuangLuuStudio-win-Portable.zip") -Force -ErrorAction SilentlyContinue

# 4. Đổi tên Setup
Move-Item -LiteralPath (Join-Path $OutputDir "QuangLuuStudio-win-Setup.exe") `
          -Destination (Join-Path $OutputDir "QuangLuuStudio-CaiDat.exe") -Force
Get-ChildItem $OutputDir | Format-Table Name, Length
