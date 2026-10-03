#Requires -Version 5.1
<#
    Quang Lưu Studio — Sửa lỗi "nạp QtWebEngine thất bại" (màn hình karaoke nhúng)
    -------------------------------------------------------------------------------
    Triệu chứng: ô "Màn hình karaoke nhúng" trong Thiết lập bị mờ, và app.log ghi
        Biến thể build: Ban Heavy NHUNG nap QtWebEngine that bai: <lỗi>
    hoặc ghi "Ban Light" dù khách đã mua/cài bản đầy đủ.

    Script đọc LỖI THẬT trong app.log rồi chữa đúng ca (docs/BIEN_THE_BUILD_HEAVY_LIGHT.md):
      • No module named ...            → máy đang là bản Light → cài bản Heavy đè lên
      • DLL load failed / module could not be found / Access is denied / virus
                                        → diệt virus cách ly DLL trong %TEMP%\_MEIxxxx
                                          (exe onefile giải nén ra đó MỖI lần mở app)
                                        → loại trừ + dọn _MEI cũ + kiểm ổ đĩa
      • procedure could not be found / entry point
                                        → Visual C++ Redistributable quá cũ → cài bản mới
    Cuối cùng mở app và đọc lại app.log để xác nhận.

    Cách dùng (khách hàng): bấm đúp SuaManHinhNhung.bat.
    Cách dùng (kỹ thuật):
        powershell -ExecutionPolicy Bypass -File QLS_SuaManHinhNhung.ps1
            [-Auto] [-Xem] [-AppDir "D:\QuangLuuStudio"] [-DataDir "..."]
            [-LoaiTruTemp] [-KhongMoApp] [-OutFile "..."] [-NoOpen]

    Mã thoát: 0 = màn hình nhúng nạp được; 1 = còn việc làm tay / chưa xác nhận được;
    2 = sửa thất bại.
#>
param(
    # Không hỏi C/K — làm hết (vẫn hiện hộp UAC khi cần quyền admin)
    [switch]$Auto,
    # Chỉ kiểm tra, KHÔNG sửa gì
    [switch]$Xem,
    # Thư mục cài đặt (chỉ cần khi cài ở chỗ lạ)
    [string]$AppDir = "",
    # Thư mục dữ liệu; mặc định %APPDATA%\QuangLuuStudio
    [string]$DataDir = "",
    # Loại trừ CẢ %TEMP% khỏi Defender (rộng hơn; chỉ dùng khi loại trừ theo tiến trình không đủ)
    [switch]$LoaiTruTemp,
    # Không mở app để xác nhận ở bước cuối
    [switch]$KhongMoApp,
    # Nơi ghi nhật ký; bỏ trống -> Desktop
    [string]$OutFile = "",
    # Không tự mở nhật ký sau khi chạy
    [switch]$NoOpen
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

# ══════════════════════════════════════════════════════════════════════════
#  Hằng số — giữ khớp core/version.py, core/capabilities.py, bộ cài .iss
# ══════════════════════════════════════════════════════════════════════════
$EXE_NAME      = "QuangLuuStudio.exe"
$PROC_NAME     = "QuangLuuStudio"
$DATA_FOLDER   = "QuangLuuStudio"
$INNO_APPID    = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1"
$RELEASES_API  = "https://api.github.com/repos/ligktit/quang-luu-studio/releases/latest"
$VCREDIST_URL  = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
# PySide6 6.8+ build bằng MSVC 2022 17.10+, cần runtime 14.40 trở lên
$VCREDIST_MIN  = [Version]"14.40.0.0"
$MIN_FREE_GB   = 1.5
$LOG_MARKER    = "Biến thể build:"

# ══════════════════════════════════════════════════════════════════════════
#  Khung báo cáo
# ══════════════════════════════════════════════════════════════════════════
$script:Report = New-Object System.Text.StringBuilder
$script:Done   = New-Object System.Collections.ArrayList
$script:Need   = New-Object System.Collections.ArrayList
$script:Failed = New-Object System.Collections.ArrayList

function W {
    param([string]$Text = "", [string]$Color = "Gray")
    Write-Host $Text -ForegroundColor $Color
    [void]$script:Report.AppendLine($Text)
}
function Section {
    param([string]$Title)
    W ""
    W "──────────────────────────────────────────────────────────────────" "DarkGray"
    W ("  " + $Title) "Cyan"
    W "──────────────────────────────────────────────────────────────────" "DarkGray"
}
function Say-Good { param([string]$m) W ("[ TỐT ] " + $m) "Green" }
function Say-Ok   { param([string]$m) W ("[ ĐÃ SỬA ] " + $m) "Green"; [void]$script:Done.Add($m) }
function Say-Bad  { param([string]$m) W ("[ LỖI ] " + $m) "Yellow" }
function Say-Warn { param([string]$m) W ("[ CHÚ Ý ] " + $m) "Yellow" }
function Say-Fail { param([string]$m) W ("[ THẤT BẠI ] " + $m) "Red"; [void]$script:Failed.Add($m) }
function Say-Need { param([string]$m) W ("[ CẦN LÀM TAY ] " + $m) "Yellow"; [void]$script:Need.Add($m) }
function Say-Info { param([string]$m) W ("           " + $m) "Gray" }

function Ask {
    param([string]$Question)
    if ($Xem)  { W "   (chế độ -Xem — không sửa)" "DarkGray"; return $false }
    if ($Auto) { return $true }
    $a = Read-Host ("   → " + $Question + " [C/k]")
    return ([string]::IsNullOrWhiteSpace($a) -or $a -match '^[cCyY]')
}

function Format-Size { param([double]$Bytes) if ($Bytes -ge 1GB) { "{0:N1} GB" -f ($Bytes / 1GB) } else { "{0:N0} MB" -f ($Bytes / 1MB) } }

# Chạy một khối lệnh PowerShell bằng quyền admin (hộp UAC). Trả mã thoát, -1 nếu bị từ chối.
function Invoke-Elevated {
    param([string]$Command)
    $enc = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes("`$ErrorActionPreference='Stop'; try { " + $Command + " ; exit 0 } catch { exit 1 }"))
    try {
        $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $enc) -ErrorAction Stop
        return $p.ExitCode
    } catch {
        Say-Info ("Không lấy được quyền admin: " + $_.Exception.Message)
        return -1
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  Đọc app.log — app GIỮ file mở nên phải mở kiểu chia sẻ
# ══════════════════════════════════════════════════════════════════════════
function Get-VariantLines {
    param([string]$LogDir)
    $found = New-Object System.Collections.ArrayList
    foreach ($name in @("app.log.1", "app.log")) {           # cũ → mới
        $path = Join-Path $LogDir $name
        if (-not (Test-Path -LiteralPath $path)) { continue }
        try {
            $fs = [System.IO.File]::Open($path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete)
            try {
                $sr = New-Object System.IO.StreamReader($fs, [System.Text.Encoding]::UTF8)
                while ($null -ne ($line = $sr.ReadLine())) {
                    $i = $line.IndexOf($LOG_MARKER)
                    if ($i -lt 0) { continue }
                    $t = [datetime]::MinValue
                    if ($line.Length -ge 19) { [void][datetime]::TryParseExact($line.Substring(0, 19), "yyyy-MM-dd HH:mm:ss", $null, 0, [ref]$t) }
                    [void]$found.Add([pscustomobject]@{ Time = $t; Text = $line.Substring($i + $LOG_MARKER.Length).Trim() })
                }
            } finally { $fs.Dispose() }
        } catch { }
    }
    return $found
}

# Phân loại đúng như core/capabilities.describe() + chuỗi lỗi Windows (Anh/Việt)
function Get-Category {
    param([string]$Text)
    if (-not $Text) { return "KHONG_RO" }
    if ($Text -match "^Ban Heavy - co QtWebEngine") { return "OK" }
    if ($Text -match "No module named") { return "LIGHT" }
    if ($Text -match "procedure could not be found|entry point|không tìm thấy thủ tục|điểm vào") { return "VCREDIST" }
    if ($Text -match "could not be found|Access is denied|virus|Permission|WinError 5|WinError 225|WinError 126|không tìm thấy mô-đun|truy cập bị từ chối") { return "DIET_VIRUS" }
    return "KHAC"
}

# ══════════════════════════════════════════════════════════════════════════
#  BẮT ĐẦU
# ══════════════════════════════════════════════════════════════════════════
W "QUANG LƯU STUDIO — SỬA LỖI MÀN HÌNH KARAOKE NHÚNG (QtWebEngine)" "White"
W ("Thời điểm : " + (Get-Date -Format "dd/MM/yyyy HH:mm:ss") + "   Máy: " + $env:COMPUTERNAME)
W ("Windows   : " + [Environment]::OSVersion.VersionString + "   PowerShell " + $PSVersionTable.PSVersion)

# ── Thư mục cài đặt: ưu tiên tiến trình đang chạy (shortcut có thể trỏ bản khác) ──
$appRoot = ""
$installedVer = ""
$regInstallLoc = ""
$cands = New-Object System.Collections.ArrayList
if ($AppDir) { [void]$cands.Add($AppDir.TrimEnd('\')) }
$runningProc = @(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue)
foreach ($p in $runningProc) { if ($p.Path) { [void]$cands.Add((Split-Path $p.Path -Parent)) } }
[void]$cands.Add($PSScriptRoot)
foreach ($hive in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")) {
    $k = Join-Path $hive $INNO_APPID
    if (Test-Path $k) {
        $reg = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
        if ($reg.InstallLocation) {
            [void]$cands.Add($reg.InstallLocation.TrimEnd('\'))
            if (-not $regInstallLoc) { $regInstallLoc = $reg.InstallLocation.TrimEnd('\') }
        }
        if ($reg.DisplayVersion -and -not $installedVer) { $installedVer = [string]$reg.DisplayVersion }
    }
}
foreach ($c in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs"))) {
    if ($c) { [void]$cands.Add((Join-Path $c "QuangLuuStudio")) }
}
foreach ($c in $cands) {
    if ($c -and (Test-Path -LiteralPath (Join-Path $c $EXE_NAME))) { $appRoot = $c; break }
}
$appExe = if ($appRoot) { Join-Path $appRoot $EXE_NAME } else { "" }
if ($appExe -and -not $installedVer) {
    try { $installedVer = (Get-Item -LiteralPath $appExe).VersionInfo.ProductVersion } catch { }
}

if (-not $DataDir) { $DataDir = Join-Path $env:APPDATA $DATA_FOLDER }
$logDir = Join-Path $DataDir "logs"

if ($appRoot) { W ("App       : " + $appExe + $(if ($installedVer) { "  (phiên bản " + $installedVer + ")" } else { "" })) }
else          { W "App       : KHÔNG TÌM THẤY QuangLuuStudio.exe — chạy lại với -AppDir ""D:\...""" "Yellow" }
W ("Nhật ký   : " + $logDir)

# ══════════════════════════════════════════════════════════════════════════
#  1. KIỂM TRA
# ══════════════════════════════════════════════════════════════════════════
Section "1. KIỂM TRA HIỆN TRẠNG"

# ── 1a. Lỗi thật trong app.log ──
$lines = @(Get-VariantLines $logDir)
$category = "KHONG_RO"
if ($lines.Count -eq 0) {
    Say-Warn "app.log chưa có dòng ""Biến thể build"" (app bản cũ hơn 1.7.5, hoặc chưa mở app lần nào)."
} else {
    $last = $lines[-1]
    $category = Get-Category $last.Text
    Say-Info ("Lần mở app gần nhất (" + $last.Time.ToString("dd/MM/yyyy HH:mm") + "):")
    Say-Info ("  " + $last.Text)
    switch ($category) {
        "OK"         { Say-Good "QtWebEngine nạp ĐƯỢC ở lần mở gần nhất." }
        "LIGHT"      { Say-Bad  "Máy đang chạy BẢN LIGHT (không kèm bộ hiển thị web)." }
        "DIET_VIRUS" { Say-Bad  "Thiếu/bị chặn DLL lúc nạp — dấu hiệu phần mềm diệt virus cách ly file." }
        "VCREDIST"   { Say-Bad  "Lệch phiên bản DLL — dấu hiệu Visual C++ Redistributable quá cũ." }
        default      { Say-Bad  "Nạp thất bại với lỗi lạ — script sẽ thử các cách chữa chung." }
    }
    $okCount = @($lines | Where-Object { (Get-Category $_.Text) -eq "OK" }).Count
    if ($category -ne "OK" -and $okCount -gt 0) {
        Say-Info ("Trước đây đã từng nạp được " + $okCount + " lần → lỗi mới phát sinh (diệt virus cập nhật, cài đè...).")
    }
}

# ── 1b. Gói cài có kèm QtWebEngine không (đọc bảng mục lục trong exe) ──
$pkgHeavy = $null
if ($appExe) {
    W "   Đang đọc trong exe (vài giây)..." "DarkGray"
    try {
        $fs = [System.IO.File]::Open($appExe, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            $buf = New-Object byte[] (4MB); $tail = ""; $pkgHeavy = $false
            while (($n = $fs.Read($buf, 0, $buf.Length)) -gt 0) {
                $chunk = $tail + [Text.Encoding]::ASCII.GetString($buf, 0, $n)
                if ($chunk.Contains("Qt6WebEngineCore.dll")) { $pkgHeavy = $true; break }
                $tail = $chunk.Substring([Math]::Max(0, $chunk.Length - 32))
            }
        } finally { $fs.Dispose() }
    } catch { Say-Info ("Không đọc được exe: " + $_.Exception.Message) }
    if ($pkgHeavy -eq $true)      { Say-Good "Gói cài là bản HEAVY (có Qt6WebEngineCore.dll)" }
    elseif ($pkgHeavy -eq $false) { Say-Bad  "Gói cài là bản LIGHT (không có Qt6WebEngineCore.dll)"; if ($category -ne "OK") { $category = "LIGHT" } }
}

# ── 1c. %TEMP%: ổ đĩa + thư mục _MEI cũ của app ──
$tempRoot = [System.IO.Path]::GetTempPath().TrimEnd('\')
$freeGb = $null
try {
    $drv = New-Object System.IO.DriveInfo ([System.IO.Path]::GetPathRoot($tempRoot))
    $freeGb = [math]::Round($drv.AvailableFreeSpace / 1GB, 1)
    if ($freeGb -lt $MIN_FREE_GB) { Say-Bad ("Ổ " + $drv.Name + " chỉ còn " + $freeGb + " GB — bản Heavy giải nén vài trăm MB mỗi lần mở, thiếu chỗ là nạp hỏng.") }
    else { Say-Good ("Ổ " + $drv.Name + " còn trống " + $freeGb + " GB") }
} catch { }

# Chỉ nhận _MEI của CHÍNH app này (có studio_one\ + app_config.json) — _MEI của
# app PyInstaller khác đang chạy mà xoá bừa là làm hỏng app đó.
$meiOld = New-Object System.Collections.ArrayList
$meiBytes = 0
foreach ($d in @(Get-ChildItem -LiteralPath $tempRoot -Directory -Filter "_MEI*" -Force -ErrorAction SilentlyContinue)) {
    if ((Test-Path -LiteralPath (Join-Path $d.FullName "studio_one")) -and (Test-Path -LiteralPath (Join-Path $d.FullName "app_config.json"))) {
        [void]$meiOld.Add($d)
        try { $meiBytes += (Get-ChildItem -LiteralPath $d.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum } catch { }
    }
}
if ($meiOld.Count -gt 0) {
    Say-Info ("Thư mục giải nén _MEI của app trong %TEMP%: " + $meiOld.Count + " cái, " + (Format-Size $meiBytes))
    if ($runningProc.Count -eq 0 -and $meiOld.Count -gt 0) { Say-Warn "App đang tắt mà vẫn còn _MEI → sót lại từ các lần tắt đột ngột." }
}

# ── 1d. Visual C++ Redistributable ──
$vcVer = $null
foreach ($k in @("HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64", "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64")) {
    try {
        $r = Get-ItemProperty -Path $k -ErrorAction Stop
        if ($r.Installed -eq 1) { $vcVer = [Version]("{0}.{1}.{2}.0" -f $r.Major, $r.Minor, $r.Bld); break }
    } catch { }
}
if (-not $vcVer) {
    try {
        $fv = (Get-Item -LiteralPath (Join-Path $env:SystemRoot "System32\msvcp140.dll") -ErrorAction Stop).VersionInfo
        $vcVer = [Version]("{0}.{1}.{2}.0" -f $fv.FileMajorPart, $fv.FileMinorPart, $fv.FileBuildPart)
    } catch { }
}
$vcOld = (-not $vcVer) -or ($vcVer -lt $VCREDIST_MIN)
if (-not $vcVer)  { Say-Bad "Visual C++ Redistributable x64: KHÔNG CÓ" }
elseif ($vcOld)   { Say-Bad ("Visual C++ Redistributable x64: " + $vcVer + " (cũ — cần " + $VCREDIST_MIN + " trở lên)") }
else              { Say-Good ("Visual C++ Redistributable x64: " + $vcVer) }

# ── 1e. Phần mềm diệt virus ──
$thirdAv = @()
try {
    $thirdAv = @(Get-CimInstance -Namespace "root/SecurityCenter2" -ClassName AntiVirusProduct -ErrorAction Stop |
        Where-Object { $_.displayName -notlike "*Defender*" } | ForEach-Object { $_.displayName })
} catch { }
if ($thirdAv.Count -gt 0) { Say-Warn ("Có phần mềm diệt virus khác Defender: " + ($thirdAv -join ", ")) }

$defenderOn = $false
$exclPaths = @(); $exclProcs = @()
try {
    $st = Get-MpComputerStatus -ErrorAction Stop
    $defenderOn = [bool]$st.RealTimeProtectionEnabled
    $pref = Get-MpPreference -ErrorAction Stop
    $exclPaths = @($pref.ExclusionPath | Where-Object { $_ })
    $exclProcs = @($pref.ExclusionProcess | Where-Object { $_ })
} catch { }
function Test-Excluded {
    param([string]$Path, [string[]]$List)
    foreach ($e in $List) {
        if ($e -and $Path.TrimEnd('\').StartsWith($e.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}
# Loại trừ ExclusionPath/ExclusionProcess là thông tin bị ẩn với tài khoản thường
# trên Windows mới → danh sách rỗng KHÔNG có nghĩa là chưa loại trừ.
$exclHidden = ($exclPaths.Count -eq 1 -and $exclPaths[0] -match "^N/A")
if ($defenderOn) {
    Say-Info "Windows Defender: đang BẬT bảo vệ thời gian thực"
    if ($appRoot -and -not $exclHidden) {
        $okApp  = Test-Excluded $appRoot $exclPaths
        $okProc = [bool]($exclProcs | Where-Object { $_ -ieq $appExe -or $_ -ieq $EXE_NAME })
        $okTemp = Test-Excluded $tempRoot $exclPaths
        Say-Info ("  Loại trừ thư mục cài đặt: " + $(if ($okApp) { "có" } else { "chưa" }) +
                  " | tiến trình app: " + $(if ($okProc) { "có" } else { "chưa" }) +
                  " | %TEMP%: " + $(if ($okTemp) { "có" } else { "chưa" }))
    }
}
$dets = $null
try {
    $dets = @(Get-MpThreatDetection -ErrorAction Stop | Where-Object { ($_.Resources -join ";") -match "_MEI|QtWebEngine|Qt6|PySide6|QuangLuuStudio" })
} catch { }
if ($null -eq $dets) { Say-Info "Lịch sử Defender: không đọc được (cần quyền admin)" }
elseif ($dets.Count -gt 0) {
    Say-Bad ("Defender ĐÃ CHẶN file của app " + $dets.Count + " lần:")
    foreach ($d in ($dets | Select-Object -Last 5)) { Say-Info ("  " + $d.InitialDetectionTime + "  " + (($d.Resources | Select-Object -First 1) -replace '^file:_', '')) }
    if ($category -in @("KHAC", "KHONG_RO")) { $category = "DIET_VIRUS" }
} else { Say-Info "Lịch sử Defender: không có lần chặn nào liên quan app" }

if ($runningProc.Count -gt 0) { Say-Info ("App đang chạy (" + $runningProc.Count + " tiến trình)") }

# ══════════════════════════════════════════════════════════════════════════
#  2. SỬA
# ══════════════════════════════════════════════════════════════════════════
$needFix = ($category -ne "OK") -or ($pkgHeavy -eq $false)
if (-not $needFix) {
    Section "2. SỬA"
    Say-Good "Lần mở gần nhất đã nạp được màn hình nhúng — không cần sửa."
    if ($vcOld) { Say-Info "(Nên cập nhật Visual C++ Redistributable khi tiện, nhưng hiện không gây lỗi.)" }
} elseif (-not $appRoot) {
    Section "2. SỬA"
    Say-Need "Không tìm thấy app nên không sửa được. Chạy lại với -AppDir ""D:\Đường\Dẫn"""
} else {
    Section "2. SỬA"

    # ── 2a. Tắt app: _MEI của lần chạy hiện tại bị khoá, bộ cài cũng không ghi đè được exe ──
    $runningProc = @(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue)
    if ($runningProc.Count -gt 0) {
        W "App đang mở — cần TẮT trước khi sửa."
        if (Ask "Đóng app ngay bây giờ (app tự lưu thiết lập khi đóng)?") {
            foreach ($p in $runningProc) { try { [void]$p.CloseMainWindow() } catch { } }
            $deadline = (Get-Date).AddSeconds(25)
            while ((Get-Date) -lt $deadline -and @(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue).Count -gt 0) { Start-Sleep -Milliseconds 500 }
            $left = @(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue)
            if ($left.Count -gt 0) {
                Say-Warn "App không tự đóng sau 25 giây (có thể đang hiện hộp thoại hỏi)."
                if (Ask "Buộc tắt app (thiết lập chưa lưu của phiên này có thể mất)?") {
                    $left | Stop-Process -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 2
                }
            }
            if (@(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue).Count -eq 0) { Say-Ok "Đã tắt app" }
            else { Say-Need "Tắt app bằng tay rồi chạy lại script." }
        } elseif (-not $Xem) {
            Say-Need "Tắt app rồi chạy lại script."
        }
    }
    $appClosed = (@(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue).Count -eq 0)

    # ── 2b. Bản Light → cài bản Heavy ──
    if ($category -eq "LIGHT" -or $pkgHeavy -eq $false) {
        W ""
        W "• Máy đang là bản Light → cần cài bản Heavy đè lên (giữ nguyên thiết lập, bài hát, kích hoạt)." "White"
        $rel = $null; $asset = $null
        try {
            $rel = Invoke-RestMethod -Uri $RELEASES_API -TimeoutSec 30 -UseBasicParsing -Headers @{ "User-Agent" = "QuangLuuStudio-SuaManHinhNhung" } -ErrorAction Stop
            $asset = @($rel.assets | Where-Object { $_.name -match "(?i)^setup.*heavy.*\.exe$" }) | Select-Object -First 1
        } catch { Say-Info ("Không hỏi được GitHub Releases: " + $_.Exception.Message) }
        $relVer = if ($rel) { ([string]$rel.tag_name).TrimStart("v") } else { "" }
        $older = $false
        try { if ($relVer -and $installedVer) { $older = ([Version]$relVer -lt [Version]($installedVer -replace '[^0-9.].*$', '')) } } catch { }

        # Bộ cài luôn cài vào chỗ ghi trong registry. App không cài bằng bộ cài
        # (chép tay, bản build thử) hoặc không rõ phiên bản → KHÔNG tự cài: có thể
        # hạ cấp, hoặc đẻ ra bản thứ hai song song mà shortcut vẫn trỏ bản cũ.
        $sameInstall = $regInstallLoc -and ($regInstallLoc -ieq $appRoot)
        if (-not $sameInstall) {
            Say-Need ("App ở " + $appRoot + " không phải bản cài bằng bộ cài (hoặc cài ở chỗ khác) — tự chạy bộ cài Heavy đúng phiên bản.")
        } elseif (-not $installedVer) {
            Say-Need "Không xác định được phiên bản đang cài — xin kỹ thuật bộ cài Heavy đúng phiên bản rồi cài đè."
        } elseif (-not $asset) {
            Say-Need "Không tìm thấy bộ cài Heavy trên GitHub — xin kỹ thuật file Setup_QuangLuuStudio_Heavy_v*.exe rồi cài đè."
        } elseif ($older) {
            Say-Need ("Bộ cài Heavy trên GitHub (" + $relVer + ") CŨ hơn bản đang cài (" + $installedVer + ") — xin kỹ thuật bộ cài Heavy đúng phiên bản.")
        } elseif (-not $appClosed) {
            Say-Need "App vẫn đang mở nên chưa cài được bản Heavy."
        } elseif (Ask ("Tải và cài " + $asset.name + " (" + (Format-Size $asset.size) + ")?")) {
            $setup = Join-Path $env:TEMP $asset.name
            try {
                W ("   Đang tải " + $asset.name + "...") "Gray"
                Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $setup -TimeoutSec 1800 -UseBasicParsing -ErrorAction Stop
                $shaOk = $null
                $sums = @($rel.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" }) | Select-Object -First 1
                if ($sums) {
                    $txt = (Invoke-WebRequest -Uri $sums.browser_download_url -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop).Content
                    if ($txt -is [byte[]]) { $txt = [Text.Encoding]::UTF8.GetString($txt) }
                    $want = ($txt -split "`n" | Where-Object { $_ -match [regex]::Escape($asset.name) } | Select-Object -First 1)
                    if ($want) { $shaOk = (($want -split '\s+')[0].ToLower() -eq (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLower()) }
                }
                if ($shaOk -eq $false) {
                    Say-Fail "Bộ cài tải về SAI mã băm SHA256 — không chạy."
                } else {
                    if ($null -eq $shaOk) { Say-Info "(Release không có SHA256SUMS.txt — bỏ qua kiểm mã băm)" }
                    W "   Đang cài (Windows có thể hỏi quyền admin)..." "Gray"
                    $p = Start-Process -FilePath $setup -ArgumentList "/SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS" -Wait -PassThru -ErrorAction Stop
                    # Mã thoát Inno Setup: 2/5 = bị huỷ (thường do bấm "Không" ở hộp UAC), 8 = cần khởi động lại
                    $ec = $p.ExitCode
                    if ($ec -eq 0) { Say-Ok ("Cài bản Heavy " + $relVer); $category = "KHONG_RO"; $pkgHeavy = $null }
                    elseif ($ec -eq 8) { Say-Ok ("Cài bản Heavy " + $relVer); Say-Need "KHỞI ĐỘNG LẠI máy để hoàn tất cài đặt."; $pkgHeavy = $null }
                    elseif ($ec -in @(2, 5)) { Say-Need "Bộ cài bị huỷ (có thể do bấm ""Không"" ở hộp hỏi quyền admin) — chạy lại script." }
                    else { Say-Fail ("Bộ cài thoát mã " + $ec) }
                }
            } catch {
                Say-Fail ("Tải/cài bản Heavy thất bại: " + $_.Exception.Message)
            } finally {
                Remove-Item -LiteralPath $setup -Force -ErrorAction SilentlyContinue
            }
        }
    }

    # ── 2c. Dọn _MEI cũ (chỉ khi app đã tắt) ──
    if ($meiOld.Count -gt 0) {
        W ""
        W ("• Dọn " + $meiOld.Count + " thư mục giải nén _MEI cũ (" + (Format-Size $meiBytes) + ") — có thể đang chứa file hỏng dở.") "White"
        if (-not $appClosed) {
            Say-Info "Bỏ qua vì app còn mở."
        } elseif (Ask "Xoá các thư mục _MEI cũ của app?") {
            $del = 0; $kept = 0
            foreach ($d in $meiOld) {
                try { Remove-Item -LiteralPath $d.FullName -Recurse -Force -ErrorAction Stop; $del++ } catch { $kept++ }
            }
            if ($del -gt 0) { Say-Ok ("Xoá " + $del + " thư mục _MEI cũ") }
            if ($kept -gt 0) { Say-Info ($kept.ToString() + " thư mục đang bị khoá, để lại (sẽ tự dọn lần sau).") }
        }
    }
    if ($null -ne $freeGb -and $freeGb -lt $MIN_FREE_GB) {
        Say-Need ("Giải phóng ổ đĩa chứa %TEMP% lên ít nhất " + $MIN_FREE_GB + " GB trống (Cài đặt → Hệ thống → Lưu trữ → Tệp tạm thời).")
    }

    # ── 2d. Diệt virus ──
    if ($category -in @("DIET_VIRUS", "KHAC", "KHONG_RO") -and $pkgHeavy -ne $false) {
        W ""
        W "• Phần mềm diệt virus: cho app được giải nén và nạp DLL của nó." "White"
        if ($thirdAv.Count -gt 0) {
            Say-Need ("Mở " + ($thirdAv -join ", ") + " → khôi phục các file bị cách ly của QuangLuuStudio và thêm loại trừ cho:")
            Say-Info ("  " + $appRoot)
            Say-Info ("  " + $appExe + "   (loại trừ theo tiến trình, nếu phần mềm có mục này)")
            Say-Info ("  " + $tempRoot + "   (nếu không có loại trừ theo tiến trình)")
        }
        if ($defenderOn) {
            # Mặc định: thư mục cài đặt + TIẾN TRÌNH app. Loại trừ tiến trình phủ luôn
            # các file app tự giải nén ra %TEMP%\_MEI mà không phải mở cả %TEMP%.
            $cmds = @(
                "Add-MpPreference -ExclusionPath '" + $appRoot.Replace("'", "''") + "'",
                "Add-MpPreference -ExclusionProcess '" + $appExe.Replace("'", "''") + "'"
            )
            $desc = "thư mục cài đặt + tiến trình " + $EXE_NAME
            if ($LoaiTruTemp) {
                $cmds += "Add-MpPreference -ExclusionPath '" + $tempRoot.Replace("'", "''") + "'"
                $desc += " + cả %TEMP%"
            }
            Say-Info ("Sẽ thêm loại trừ Defender cho: " + $desc)
            if (Ask "Thêm loại trừ Windows Defender (Windows sẽ hỏi quyền admin)?") {
                $rc = Invoke-Elevated ($cmds -join "; ")
                if ($rc -eq 0) { Say-Ok ("Thêm loại trừ Defender: " + $desc) }
                elseif ($rc -eq -1) { Say-Need "Không có quyền admin — nhờ người có quyền chạy lại, hoặc tự thêm trong Bảo mật Windows → Loại trừ." }
                else { Say-Fail "Defender từ chối thêm loại trừ (có thể do tổ chức quản lý / Tamper Protection)." }
            }
        } elseif ($thirdAv.Count -eq 0) {
            Say-Info "Defender không bật bảo vệ thời gian thực và không thấy phần mềm diệt virus khác."
        }
    }

    # ── 2e. Visual C++ Redistributable ──
    if ($vcOld -and ($category -in @("VCREDIST", "KHAC", "KHONG_RO", "DIET_VIRUS"))) {
        W ""
        W "• Cập nhật Visual C++ Redistributable 2015–2022 x64 (Microsoft)." "White"
        if (Ask "Tải và cài vc_redist.x64.exe (~25 MB, Windows sẽ hỏi quyền admin)?") {
            $vc = Join-Path $env:TEMP ("vc_redist_" + [Guid]::NewGuid().ToString("N") + ".exe")
            try {
                Invoke-WebRequest -Uri $VCREDIST_URL -OutFile $vc -TimeoutSec 600 -UseBasicParsing -ErrorAction Stop
                $sig = Get-AuthenticodeSignature -LiteralPath $vc
                if ($sig.Status -ne "Valid" -or $sig.SignerCertificate.Subject -notmatch "O=Microsoft Corporation") {
                    Say-Fail "vc_redist tải về không có chữ ký hợp lệ của Microsoft — không chạy."
                } else {
                    $p = Start-Process -FilePath $vc -ArgumentList "/install /passive /norestart" -Verb RunAs -Wait -PassThru -ErrorAction Stop
                    switch ($p.ExitCode) {
                        0     { Say-Ok "Cài Visual C++ Redistributable mới" }
                        3010  { Say-Ok "Cài Visual C++ Redistributable mới"; Say-Need "KHỞI ĐỘNG LẠI máy để hoàn tất Visual C++ Redistributable." }
                        1638  { Say-Info "Máy đã có bản Visual C++ Redistributable mới hơn." }
                        default { Say-Fail ("vc_redist thoát mã " + $p.ExitCode) }
                    }
                }
            } catch {
                Say-Fail ("Cài Visual C++ Redistributable thất bại: " + $_.Exception.Message)
            } finally {
                Remove-Item -LiteralPath $vc -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3. XÁC NHẬN — mở app, đọc dòng "Biến thể build" MỚI trong app.log
#  (dòng này ghi từ luồng nền sau khi tự cập nhật yt-dlp/PO Token, nên có thể
#   mất tới vài phút ở lần mở đầu tiên có mạng)
# ══════════════════════════════════════════════════════════════════════════
$verified = $null
$restartPending = [bool]($script:Need | Where-Object { $_ -match "KHỞI ĐỘNG LẠI" })
# Vẫn là bản Light (chưa cài được Heavy) thì mở app kiểm lại cũng vô ích
$stillLight = ($pkgHeavy -eq $false)
if (-not $KhongMoApp -and -not $Xem -and $appExe -and ($needFix -or $script:Done.Count -gt 0) -and -not $restartPending -and -not $stillLight) {
    Section "3. XÁC NHẬN"
    $alreadyRunning = @(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue).Count -gt 0
    if ($alreadyRunning) {
        Say-Info "App đang mở từ trước — tắt hẳn rồi mở lại app, sau đó chạy lại script để xác nhận."
    } elseif (Ask "Mở app để kiểm tra lại?") {
        $t0 = (Get-Date).AddSeconds(-2)
        $appExeNow = Join-Path $appRoot $EXE_NAME
        try {
            Start-Process -FilePath $appExeNow -WorkingDirectory $appRoot -ErrorAction Stop | Out-Null
            W "   Đang chờ app ghi kết quả vào nhật ký (tối đa 3 phút)..." "Gray"
            $deadline = (Get-Date).AddMinutes(3)
            $newLine = $null
            while ((Get-Date) -lt $deadline) {
                Start-Sleep -Seconds 3
                $newLine = @(Get-VariantLines $logDir | Where-Object { $_.Time -ge $t0 }) | Select-Object -Last 1
                if ($newLine) { break }
                if (@(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue).Count -eq 0) {
                    Say-Bad "App tắt ngay sau khi mở (xem errors.log)."
                    break
                }
            }
            if ($newLine) {
                Say-Info ("  " + $newLine.Text)
                $verified = ((Get-Category $newLine.Text) -eq "OK")
                if ($verified) { W "[ ĐẠT ] Màn hình karaoke nhúng NẠP ĐƯỢC — bật lại trong Thiết lập." "Green" }
                else {
                    W "[ CHƯA ĐẠT ] QtWebEngine vẫn nạp thất bại." "Red"
                    if ((Get-Category $newLine.Text) -eq "LIGHT") {
                        Say-Need "App vẫn là bản Light — cần cài bộ cài Setup_QuangLuuStudio_Heavy_v*.exe."
                    } elseif (-not $LoaiTruTemp -and $defenderOn -and (Get-Category $newLine.Text) -eq "DIET_VIRUS") {
                        Say-Need "Chạy lại với tham số -LoaiTruTemp (loại trừ cả %TEMP%), hoặc gửi nhật ký cho kỹ thuật."
                    } else {
                        Say-Need "Gửi nhật ký trên Desktop cho kỹ thuật."
                    }
                }
            } else {
                $verified = $false
                Say-Need "Hết 3 phút chưa thấy app ghi kết quả — để app mở thêm ít phút rồi chạy lại script (không sửa gì nữa)."
            }
        } catch {
            Say-Fail ("Không mở được app: " + $_.Exception.Message)
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  TỔNG KẾT
# ══════════════════════════════════════════════════════════════════════════
Section "TỔNG KẾT"
foreach ($m in $script:Done)   { W ("  ✔ " + $m) "Green" }
foreach ($m in $script:Need)   { W ("  ! " + $m) "Yellow" }
foreach ($m in $script:Failed) { W ("  ✘ " + $m) "Red" }
if ($script:Done.Count + $script:Need.Count + $script:Failed.Count -eq 0) { W "  Không có thay đổi nào." }

$isOk = ($verified -eq $true) -or ($null -eq $verified -and -not $needFix)
if ($isOk) { W "  Màn hình karaoke nhúng: DÙNG ĐƯỢC" "Green" }
elseif ($stillLight) { W "  Màn hình karaoke nhúng: CHƯA DÙNG ĐƯỢC — máy đang là bản Light" "Red" }
elseif ($null -eq $verified) { W "  Màn hình karaoke nhúng: CHƯA XÁC NHẬN — mở app rồi chạy lại script" "Yellow" }
else { W "  Màn hình karaoke nhúng: CHƯA DÙNG ĐƯỢC" "Red" }

if ($script:Failed.Count -gt 0) { $rc = 2 }
elseif ($isOk -and $script:Need.Count -eq 0) { $rc = 0 }
else { $rc = 1 }

if (-not $OutFile) {
    $desk = [Environment]::GetFolderPath("Desktop")
    if (-not $desk) { $desk = $env:TEMP }
    $OutFile = Join-Path $desk ("QLS_SuaManHinhNhung_" + $env:COMPUTERNAME + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt")
}
try {
    [System.IO.File]::WriteAllText($OutFile, $script:Report.ToString(), (New-Object System.Text.UTF8Encoding($true)))
    W ""
    W ("Nhật ký: " + $OutFile)
    if (-not $NoOpen -and $rc -ne 0) { Start-Process notepad.exe -ArgumentList ('"' + $OutFile + '"') -ErrorAction SilentlyContinue }
} catch {
    W ("(Không lưu được nhật ký: " + $_.Exception.Message + ")") "Yellow"
}

exit $rc
