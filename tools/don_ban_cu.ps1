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

# 1. Thư mục cài — chỉ xoá khi đúng là thư mục của app (người dùng có thể đã chọn
#    thư mục khác lúc cài; khoá registry có thể trỏ sai) VÀ không phải gốc ổ đĩa /
#    thư mục hệ thống / hồ sơ người dùng: bản Inno cũ cho chọn thư mục tuỳ ý
#    (DisableDirPage=no), có thể là "D:\" — xoá đệ quy bằng quyền admin ở đó là thảm hoạ.
$dirIncomplete = $false
$dir = ""
try { $dir = [IO.Path]::GetFullPath($LegacyDir).TrimEnd('\') } catch { $dir = "" }
if ($dir) {
    $protected = @()
    foreach ($p in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:SystemRoot,
                     $env:SystemDrive, $env:USERPROFILE, $env:PUBLIC, $env:ProgramData) +
                   ($ProtectedDirs -split ';')) {
        if (-not $p) { continue }
        try { $protected += [IO.Path]::GetFullPath($p).TrimEnd('\') } catch { }
    }
    $root = [IO.Path]::GetPathRoot($dir + '\').TrimEnd('\')
    # Split-Path -Parent "D:" ném lỗi nên dùng GetDirectoryName (trả $null cho gốc ổ / gốc UNC).
    $isRoot = ($dir -ieq $root) -or (-not [IO.Path]::GetDirectoryName($dir))
    $isProtected = $isRoot -or ($protected -contains $dir)   # -contains không phân biệt hoa/thường
    if ($isProtected) {
        Write-Output "[BO QUA] $dir la goc o dia / thu muc he thong, khong xoa"
    } elseif (Test-Path -LiteralPath $dir) {
        $isApp = (Test-Path -LiteralPath (Join-Path $dir "QuangLuuStudio.exe")) -or
                 (Test-Path -LiteralPath (Join-Path $dir "unins000.exe"))
        if ($isApp) {
            Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $dir) {
                $dirIncomplete = $true
                Write-Output "[CANH BAO] Chua xoa het $dir (file dang bi khoa?)"
            } else { Write-Output "[OK] Da xoa $dir" }
        } else {
            Write-Output "[BO QUA] $dir khong phai thu muc cai Quang Luu Studio"
        }
    }
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
if (Test-Path -LiteralPath $UninstallKey) {
    Remove-Item -LiteralPath $UninstallKey -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $UninstallKey) { Write-Output "[LOI] Khong xoa duoc $UninstallKey"; exit 1 }
    Write-Output "[OK] Da xoa khoa go cai dat cu"
}
exit 0
