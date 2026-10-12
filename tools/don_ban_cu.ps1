# tools/don_ban_cu.ps1
# Dọn bản Quang Lưu Studio cài bằng Inno (Program Files, quyền admin) sau khi đã
# có bản Velopack (%LocalAppData%). Dùng chung cho app (core/first_run.py, chạy
# nâng quyền) và bộ cài cầu nối.
#
# KHÔNG gọi unins000.exe cũ: nó hiện hộp "Xoá dữ liệu?" mà /SUPPRESSMSGBOXES
# không chặn được — khách bấm nhầm là mất bài hát. Dữ liệu ở %APPDATA% và
# Documents không bị đụng.
param(
    [Parameter(Mandatory = $true)][string]$LegacyDir,
    [string]$UninstallKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1",
    [string]$ShortcutDirs = "",
    # Ẩn (dùng cho test): thêm thư mục KHÔNG bao giờ được xoá, ngăn cách bằng ";".
    [string]$ProtectedDirs = ""
)
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if (-not $ShortcutDirs) {
    # Inno cài admin → shortcut nằm ở thư mục DÙNG CHUNG. Bản Velopack đặt shortcut
    # ở thư mục của người dùng nên không bị đụng.
    $ShortcutDirs = (Join-Path $env:PUBLIC "Desktop") + ";" +
                    (Join-Path $env:ProgramData "Microsoft\Windows\Start Menu\Programs")
}
$oldShortcuts = @(
    "Quang Luu Studio.lnk",
    "Gỡ cài đặt Quang Luu Studio.lnk",
    "Quang Luu Studio - Cấu hình YouTube Cookies.lnk",
    "Quang Luu Studio - Kiểm tra dò tone.lnk",
    "Quang Luu Studio Recordings.lnk"
)

# 1. Thư mục cài — DANH SÁCH CHO PHÉP, vì bản Inno cũ cho chọn thư mục tuỳ ý
#    (DisableDirPage=no) và đây là xoá đệ quy bằng quyền admin. Chỉ xoá khi TẤT CẢ:
#      - đường dẫn tuyệt đối (không theo thư mục hiện hành của tiến trình);
#      - tên thư mục cuối đúng "QuangLuuStudio" (DefaultDirName cũ), không phải gốc ổ;
#      - có QuangLuuStudio.exe hoặc unins000.exe bên trong;
#      - không phải thư mục hệ thống / hồ sơ (danh sách đen + -ProtectedDirs);
#      - không có reparse point (junction/symlink) ở chính nó hay bên trong.
#    Có dấu hiệu bản cũ mà bị bỏ qua → $skipped: giữ khoá gỡ cài đặt, mã thoát 3
#    để người dùng gỡ tay qua "Apps & features".
#    Trong thư mục chỉ xoá các mục bộ cài cũ đặt ở cấp trên cùng ($known: [Files]
#    DestDir {app} và [UninstallDelete] của QuangLuuStudio_Setup.iss qua mọi phiên
#    bản, cộng unins000.*). Mục lạ là của khách → giữ lại.
$dirIncomplete = $false
$skipped = $false
$markers = @("QuangLuuStudio.exe", "unins000.exe", "unins000.dat")
$known = @(
    "QuangLuuStudio.exe", "app_icon.ico", "setup_all.bat", "setup_midi_ports.ps1",
    "configure_youtube_cookies.bat", "kiem_tra_tone.bat", "thu_tai_youtube.bat",
    "app_config.json", "qjs.exe", "studio_one", "cubase", "sfx", "models", "tools", "ffmpeg",
    "activation.json", "settings.json", "saved_songs.json", "tone_cache.json",
    "manual_timelines.json", "playlists.json", "temp_audio"
)
# Dấu hiệu chỉ tính khi là FILE: thư mục trùng tên không phải của bộ cài, và
# Remove-Item không -Recurse trên thư mục có nội dung sẽ hiện hộp xác nhận (ẩn khi chạy nâng quyền).
function Test-Known($item) {
    if ($markers -contains $item.Name) { return (-not $item.PSIsContainer) }
    return (($known -contains $item.Name) -or ($item.Name -like 'unins000.*'))
}
$raw = $LegacyDir.Trim()
$checkPath = $raw
$dir = ""
$reason = ""
if ($raw -match '^[A-Za-z]:[\\/]?$') {
    $reason = "goc o dia"
    $checkPath = $raw.Substring(0, 2) + "\"
} elseif ($raw -match '^[A-Za-z]:[\\/]' -or $raw -match '^\\\\[^\\]') {
    try { $dir = [IO.Path]::GetFullPath($raw).TrimEnd('\') } catch { $reason = "duong dan loi" }
} else {
    $reason = "duong dan khong tuyet doi"
}
if ($dir) {
    $checkPath = $dir
    $protected = @()
    foreach ($p in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:SystemRoot,
                     $env:SystemDrive, $env:USERPROFILE, $env:PUBLIC, $env:ProgramData) +
                   ($ProtectedDirs -split ';')) {
        if (-not $p) { continue }
        try { $protected += [IO.Path]::GetFullPath($p).TrimEnd('\') } catch { }
    }
    $root = [IO.Path]::GetPathRoot($dir + '\').TrimEnd('\')
    # Split-Path -Parent "D:" ném lỗi nên dùng GetDirectoryName (trả $null cho gốc ổ / gốc UNC).
    if (($dir -ieq $root) -or (-not [IO.Path]::GetDirectoryName($dir))) { $reason = "goc o dia" }
    elseif ($protected -contains $dir) { $reason = "thu muc he thong / duoc bao ve" }   # -contains không phân biệt hoa/thường
    elseif ((Split-Path -Leaf $dir) -ine "QuangLuuStudio") { $reason = "ten thu muc khong phai QuangLuuStudio" }
}
$hasMarker = $false
if ($checkPath -and (Test-Path -LiteralPath $checkPath -PathType Container)) {
    foreach ($m in $markers) {
        if (Test-Path -LiteralPath (Join-Path $checkPath $m) -PathType Leaf) { $hasMarker = $true; break }
    }
}
if (-not $reason -and $hasMarker) {
    # reparse point ở chính thư mục hoặc bất kỳ đâu bên trong → không đụng
    $item = Get-Item -LiteralPath $dir -Force -ErrorAction SilentlyContinue
    if (-not $item -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { $reason = "la lien ket (reparse point)" }
    else {
        $rp = @(Get-ChildItem -LiteralPath $dir -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue -ErrorVariable rpErr)
        if ($rp.Count -gt 0 -or $rpErr.Count -gt 0) { $reason = "chua lien ket (reparse point) hoac khong duyet duoc" }
    }
}
if ($reason) {
    if ($hasMarker) {
        $skipped = $true
        Write-Output "[BO QUA] $checkPath ($reason) - xoa tay qua Apps & features"
    } else {
        Write-Output "[BO QUA] $checkPath khong phai thu muc cai Quang Luu Studio ($reason)"
    }
} elseif (-not $hasMarker) {
    if (Test-Path -LiteralPath $dir) { Write-Output "[BO QUA] $dir khong phai thu muc cai Quang Luu Studio" }
} else {
    # Xoá các mục của bộ cài cũ trừ dấu hiệu; dấu hiệu đi SAU CÙNG để xoá dở vẫn
    # nhận ra được ở lần chạy lại.
    Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue |
        Where-Object { ($markers -notcontains $_.Name) -and (Test-Known $_) } |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $knownLeft = @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue |
                   Where-Object { ($markers -notcontains $_.Name) -and (Test-Known $_) })
    if ($knownLeft.Count -eq 0) {
        foreach ($m in $markers) {
            $mp = Join-Path $dir $m
            if (Test-Path -LiteralPath $mp -PathType Leaf) {
                Remove-Item -LiteralPath $mp -Force -ErrorAction SilentlyContinue
            }
        }
    }
    $rest = @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction SilentlyContinue)
    $knownLeft = @($rest | Where-Object { Test-Known $_ })
    if ($knownLeft.Count -eq 0 -and $rest.Count -gt 0) {
        # Bản cũ đã gỡ xong; phần còn lại là của khách.
        foreach ($i in $rest) { Write-Output "[GIU LAI] $($i.FullName) (khong phai file cua ban cai cu)" }
    } elseif ($knownLeft.Count -eq 0) {
        # Không -Recurse: thư mục phải rỗng, có gì mới xuất hiện thì lỗi chứ không xoá.
        try { [IO.Directory]::Delete($dir, $false) } catch { }
    }
    if ($knownLeft.Count -gt 0 -or ($rest.Count -eq 0 -and (Test-Path -LiteralPath $dir))) {
        $dirIncomplete = $true
        Write-Output "[CANH BAO] Chua xoa het $dir (file dang bi khoa?)"
    } elseif ($rest.Count -eq 0) { Write-Output "[OK] Da xoa $dir" }
    else { Write-Output "[OK] Da go ban cai cu trong $dir (giu lai file cua ban)" }
}

# 2. Shortcut cũ — đúng 5 tên, chỉ trong các thư mục dùng chung.
foreach ($d in ($ShortcutDirs -split ';')) {
    if (-not $d) { continue }
    foreach ($n in $oldShortcuts) {
        $p = Join-Path $d $n
        if (Test-Path -LiteralPath $p) {
            Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
            Write-Output "[OK] Da xoa shortcut $p"
        }
    }
}

# 3. Khoá gỡ cài đặt — để "Apps & features" không còn mục bản cũ. Xoá chưa hết
#    thư mục thì GIỮ khoá và trả mã 2 để app hỏi lại lần mở sau.
if ($dirIncomplete) {
    Write-Output "[CANH BAO] Giu khoa go cai dat cu vi thu muc cai chua xoa het"
    exit 2
}
if ($skipped) {
    Write-Output "[CANH BAO] Giu khoa go cai dat cu: thu muc cai bi bo qua, can go tay"
    exit 3
}
if (Test-Path -LiteralPath $UninstallKey) {
    Remove-Item -LiteralPath $UninstallKey -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $UninstallKey) { Write-Output "[LOI] Khong xoa duoc $UninstallKey"; exit 1 }
    Write-Output "[OK] Da xoa khoa go cai dat cu"
}
exit 0
