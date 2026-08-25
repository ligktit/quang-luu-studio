#Requires -Version 5.1
<#
    Quang Lưu Studio — Script SỬA LỖI máy khách (không cần Python)
    --------------------------------------------------------------
    Đi kèm QLS_ChanDoan.ps1: bộ chẩn đoán CHỈ ĐỌC và báo lỗi, script này SỬA.

    Chỉ sửa những gì an toàn và có thể hoàn tác: mọi tệp bị sửa đều được sao lưu
    vào %APPDATA%\QuangLuuStudio\backup_sualoi\<ngày giờ>\ trước khi ghi đè.

    Cách dùng (khách hàng): bấm đúp SuaLoi.bat rồi trả lời C/K cho từng mục.
    Cách dùng (kỹ thuật):
        powershell -ExecutionPolicy Bypass -File QLS_SuaLoi.ps1 [-Auto] [-Xem]
                   [-AppDir "D:\QuangLuuStudio"] [-CookieFile "C:\...\cookies.txt"]
                   [-ChiYtDlp] [-Offline]
#>
param(
    # Sửa hết, không hỏi từng mục
    [switch]$Auto,
    # Chỉ xem sẽ sửa những gì, KHÔNG đụng vào máy
    [switch]$Xem,
    # Thư mục cài đặt (chỉ cần khi app cài ở chỗ lạ)
    [string]$AppDir = "",
    # Tệp cookies.txt (định dạng Netscape) để chữa lỗi YouTube chặn tải nhạc
    [string]$CookieFile = "",
    # Không dùng Internet (bỏ qua mục cập nhật yt-dlp)
    [switch]$Offline,
    # CHỈ làm mục 3B (nạp bản yt-dlp mới) — các mục khác chỉ xem, không sửa
    [switch]$ChiYtDlp,
    # Nơi ghi nhật ký sửa lỗi; bỏ trống -> Desktop
    [string]$OutFile = "",
    # Không tự mở nhật ký sau khi chạy
    [switch]$NoOpen
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ══════════════════════════════════════════════════════════════════════════
#  Hằng số — giữ khớp với core/config.py và QuangLuuStudio_Setup.iss
# ══════════════════════════════════════════════════════════════════════════
$EXE_NAME     = "QuangLuuStudio.exe"
$DATA_FOLDER  = "QuangLuuStudio"
$INNO_APPID   = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1"
$MIDI_PORT_DEFAULT = "QuangLuuMIDI"
$SCRIPT_VERSION = "1.0"

$DATA_DIR      = Join-Path $env:APPDATA $DATA_FOLDER
$SETTINGS_FILE = Join-Path $DATA_DIR "settings.json"
$COOKIE_TARGET = Join-Path $DATA_DIR "youtube_cookies.txt"   # _AUTO_COOKIE_FILE của app
$BACKUP_DIR    = Join-Path $DATA_DIR ("backup_sualoi\" + (Get-Date -Format "yyyyMMdd_HHmmss"))

# ══════════════════════════════════════════════════════════════════════════
#  Khung báo cáo
# ══════════════════════════════════════════════════════════════════════════
$script:Report = New-Object System.Text.StringBuilder
$script:Done   = New-Object System.Collections.ArrayList   # đã sửa
$script:Skip   = New-Object System.Collections.ArrayList   # bỏ qua / cần tay người
$script:Failed = New-Object System.Collections.ArrayList

function W {
    param([string]$Text = "", [string]$Color = "Gray")
    Write-Host $Text -ForegroundColor $Color
    [void]$script:Report.AppendLine($Text)
}

$script:CurrentSection = ""

function Section {
    param([string]$Title)
    $script:CurrentSection = ($Title -split '\.')[0]
    W ""
    W ("──────────────────────────────────────────────────────────────────") "DarkGray"
    W ("  " + $Title) "Cyan"
    W ("──────────────────────────────────────────────────────────────────") "DarkGray"
}

function Say-Ok   { param([string]$m) W ("[ ĐÃ SỬA ] " + $m) "Green";  [void]$script:Done.Add($m) }
function Say-Skip { param([string]$m) W ("[ BỎ QUA ] " + $m) "DarkGray"; [void]$script:Skip.Add($m) }
function Say-Fail { param([string]$m) W ("[ THẤT BẠI ] " + $m) "Red";  [void]$script:Failed.Add($m) }
function Say-Info { param([string]$m) W ("           " + $m) "Gray" }
function Say-Need { param([string]$m) W ("[ CẦN LÀM TAY ] " + $m) "Yellow"; [void]$script:Skip.Add($m) }

function Ask {
    param([string]$Question)
    if ($Xem)  { W ("   (chế độ chỉ xem — không sửa)") "DarkGray"; return $false }
    if ($ChiYtDlp -and $script:CurrentSection -ne "3B" -and $script:CurrentSection -ne "3C") {
        W ("   (chế độ -ChiYtDlp — chỉ xem mục này)") "DarkGray"; return $false
    }
    if ($Auto) { return $true }
    $a = Read-Host ("   → " + $Question + " [C/k]")
    return ([string]::IsNullOrWhiteSpace($a) -or $a -match '^[cCyY]')
}

function JP {
    param([string]$Base, [string]$Child)
    if ([string]::IsNullOrWhiteSpace($Base)) { return "" }
    return (Join-Path $Base $Child)
}

function Backup-File {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        if (-not (Test-Path -LiteralPath $BACKUP_DIR)) {
            New-Item -ItemType Directory -Path $BACKUP_DIR -Force | Out-Null
        }
        Copy-Item -LiteralPath $Path -Destination (Join-Path $BACKUP_DIR (Split-Path $Path -Leaf)) -Force
        return $true
    } catch {
        Say-Fail ("Không sao lưu được " + $Path + ": " + $_.Exception.Message)
        return $false
    }
}

function Read-JsonFile {
    param([string]$Path)
    $res = @{ Exists = $false; Valid = $false; Data = $null; Error = "" }
    if (-not (Test-Path -LiteralPath $Path)) { return $res }
    $res.Exists = $true
    try {
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) { $res.Error = "file rỗng"; return $res }
        $res.Data = $raw | ConvertFrom-Json
        $res.Valid = $true
    } catch { $res.Error = $_.Exception.Message }
    return $res
}

function Save-JsonFile {
    param([string]$Path, $Object)
    # Python đọc bằng open(..., encoding="utf-8") → BOM sẽ làm json.load VỠ.
    # Bắt buộc ghi UTF-8 KHÔNG BOM. Đồng thời trả \uXXXX về ký tự thật cho
    # kỹ thuật viên còn đọc/sửa tay được, rồi parse lại để chắc chắn hợp lệ.
    try {
        $json = $Object | ConvertTo-Json -Depth 30
        $json = [Regex]::Replace($json, '\\u([0-9a-fA-F]{4})', {
            param($m)
            $code = [Convert]::ToInt32($m.Groups[1].Value, 16)
            if ($code -ge 0x80) { [string][char]$code } else { $m.Value }
        })
        $null = $json | ConvertFrom-Json          # tự kiểm tra trước khi ghi
        [IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
        return $true
    } catch {
        Say-Fail ("Không ghi được " + (Split-Path $Path -Leaf) + ": " + $_.Exception.Message)
        return $false
    }
}

function Prop {
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p -or $null -eq $p.Value) { return $Default }
    return $p.Value
}

function Set-Prop {
    param($Object, [string]$Name, $Value)
    if ($Object.PSObject.Properties[$Name]) { $Object.PSObject.Properties[$Name].Value = $Value }
    else { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force }
}

# ══════════════════════════════════════════════════════════════════════════
#  Mở đầu
# ══════════════════════════════════════════════════════════════════════════
Clear-Host
W ""
W "══════════════════════════════════════════════════════════════════" "Cyan"
W ("   QUANG LƯU STUDIO — SỬA LỖI MÁY (bản script " + $SCRIPT_VERSION + ")") "Cyan"
W "══════════════════════════════════════════════════════════════════" "Cyan"
W ("   Thời điểm      : " + (Get-Date -Format "dd/MM/yyyy HH:mm:ss"))
W ("   Máy / người dùng: " + $env:COMPUTERNAME + " \ " + $env:USERNAME)
if ($Xem)  { W "   CHẾ ĐỘ CHỈ XEM — sẽ liệt kê việc cần sửa nhưng KHÔNG đụng vào máy." "Yellow" }
elseif ($ChiYtDlp) { W "   CHẾ ĐỘ CHỈ YT-DLP — chỉ nạp bản yt-dlp mới, các mục khác chỉ xem." "Yellow" }
elseif ($Auto) { W "   CHẾ ĐỘ TỰ ĐỘNG — sửa hết, không hỏi." "Yellow" }
else { W "   Mỗi mục sẽ hỏi trước khi sửa. Gõ C (hoặc Enter) để đồng ý, K để bỏ qua." }
W ("   Bản sao lưu tại: " + $BACKUP_DIR)
W ""

# ── Tìm thư mục cài đặt ──
$script:AppRoot = ""
$candidates = New-Object System.Collections.ArrayList
if ($AppDir) { [void]$candidates.Add($AppDir) }
foreach ($hive in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")) {
    $k = Join-Path $hive $INNO_APPID
    if (Test-Path $k) {
        $p = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
        if ($p.InstallLocation) { [void]$candidates.Add($p.InstallLocation.TrimEnd('\')) }
    }
}
[void]$candidates.Add((JP $env:ProgramFiles "QuangLuuStudio"))
[void]$candidates.Add((JP ${env:ProgramFiles(x86)} "QuangLuuStudio"))
[void]$candidates.Add((JP $env:LOCALAPPDATA "Programs\QuangLuuStudio"))
$proc0 = Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc0 -and $proc0.Path) { [void]$candidates.Insert(0, (Split-Path $proc0.Path -Parent)) }
foreach ($c in $candidates) {
    if ($c -and (Test-Path (Join-Path $c $EXE_NAME))) { $script:AppRoot = $c; break }
}
$APP_CONFIG = ""
if ($script:AppRoot) {
    W ("   Thư mục cài đặt: " + $script:AppRoot)
    $APP_CONFIG = Join-Path $script:AppRoot "app_config.json"
} else {
    W "   [!] Không tìm thấy thư mục cài đặt — các mục liên quan app_config/Surface sẽ bỏ qua." "Yellow"
    W "       Chạy lại với: -AppDir ""D:\Đường\Dẫn""" "Yellow"
}

# ══════════════════════════════════════════════════════════════════════════
#  0. ĐÓNG APP TRƯỚC KHI SỬA
#     Dashboard ghi đè TOÀN BỘ settings.json lúc thoát → sửa khi app đang chạy
#     thì thay đổi bị bản trong RAM xoá mất.
# ══════════════════════════════════════════════════════════════════════════
Section "0. TÌNH TRẠNG ỨNG DỤNG"

$script:AppWasRunning = $false

function Get-AppInstances {
    # One-file build: mỗi bản chạy sinh 2 tiến trình cùng tên. Chỉ lấy tiến trình
    # GỐC (cha không cùng tên) để đếm đúng số bản app.
    $all = @(Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue)
    if ($all.Count -eq 0) { return @() }
    try {
        $wmi = @(Get-CimInstance Win32_Process -Filter "Name='QuangLuuStudio.exe'" -ErrorAction Stop)
        $pids = @{}
        foreach ($w in $wmi) { $pids[[int]$w.ProcessId] = $true }
        $roots = @($wmi | Where-Object { -not $pids.ContainsKey([int]$_.ParentProcessId) })
        return @($roots | ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
    } catch { return $all }
}

function Close-AppInstances {
    param([int]$KeepCount = 0)
    $inst = @(Get-AppInstances)
    if ($inst.Count -le $KeepCount) { return $true }
    # Đóng bản MỚI mở trước (giữ lại bản khách đang dùng dở)
    $order = @($inst | Sort-Object StartTime -Descending)
    $toClose = @($order | Select-Object -First ($order.Count - $KeepCount))
    foreach ($p in $toClose) {
        try {
            if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() }
        } catch { }
    }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (@(Get-AppInstances).Count -le $KeepCount) { return $true }
    }
    foreach ($p in $toClose) {
        try { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } catch { }
    }
    Start-Sleep -Seconds 1
    return (@(Get-AppInstances).Count -le $KeepCount)
}

$inst = @(Get-AppInstances)
$allProc = @(Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue)
if ($inst.Count -eq 0) {
    W "[ TỐT   ] App không chạy — sửa được mọi thứ."
} else {
    $script:AppWasRunning = $true
    W ("[ CHÚ Ý ] Có " + $inst.Count + " bản app đang chạy (" + $allProc.Count + " tiến trình).") "Yellow"
    if ($inst.Count -gt 1) {
        Say-Info "Nhiều bản chạy cùng lúc sẽ tranh nhau cổng MIDI và tệp cấu hình."
    }
    Say-Info "Phải ĐÓNG app trước khi sửa, nếu không app sẽ ghi đè lại cấu hình lúc thoát."
    if (Ask "Đóng toàn bộ app ngay bây giờ?") {
        if (Close-AppInstances -KeepCount 0) { Say-Ok "Đã đóng toàn bộ app" }
        else { Say-Fail "Không đóng được app — hãy tắt tay rồi chạy lại script" }
    } else {
        Say-Need "App vẫn đang chạy — các sửa đổi trong settings.json có thể bị mất khi đóng app"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  1. TỆP CẤU HÌNH HỎNG / RÁC
# ══════════════════════════════════════════════════════════════════════════
Section "1. TỆP CẤU HÌNH HỎNG VÀ TỆP RÁC"

if (-not (Test-Path -LiteralPath $DATA_DIR)) {
    Say-Skip "Chưa có thư mục dữ liệu — app chưa từng chạy trên tài khoản này"
} else {
    $jsonFiles = @("settings.json", "saved_songs.json", "activation.json", "tone_cache.json",
                   "manual_timelines.json", "ui_config.json", "playlists.json",
                   "accessibility_overrides.json", "calibration_overrides.json", "crash_queue.json")
    $anyBroken = $false
    foreach ($n in $jsonFiles) {
        $p = Join-Path $DATA_DIR $n
        $r = Read-JsonFile $p
        if (-not $r.Exists -or $r.Valid) { continue }
        $anyBroken = $true
        W ("[ LỖI   ] " + $n + " hỏng: " + $r.Error) "Red"
        if (Ask ("Đổi tên " + $n + " thành bản .bak để app tạo lại tệp mới?")) {
            if (Backup-File $p) {
                try {
                    $bak = $p + ".bak-" + (Get-Date -Format "yyyyMMdd_HHmmss")
                    Move-Item -LiteralPath $p -Destination $bak -Force
                    Say-Ok ($n + " → " + (Split-Path $bak -Leaf))
                } catch { Say-Fail ($n + ": " + $_.Exception.Message) }
            }
        } else { Say-Skip ($n + " (giữ nguyên tệp hỏng)") }
    }
    if (-not $anyBroken) { W "[ TỐT   ] Mọi tệp cấu hình đều đọc được" }

    $tmps = @(Get-ChildItem -LiteralPath $DATA_DIR -Filter ".tmp_*" -Force -ErrorAction SilentlyContinue)
    if ($tmps.Count -gt 0) {
        W ("[ CHÚ Ý ] Còn " + $tmps.Count + " tệp tạm .tmp_* (dấu vết app bị tắt đột ngột lúc đang lưu)") "Yellow"
        if (Ask "Xoá các tệp tạm này?") {
            $n = 0
            foreach ($t in $tmps) {
                try { Remove-Item -LiteralPath $t.FullName -Force; $n++ } catch { }
            }
            Say-Ok ("Đã xoá " + $n + " tệp tạm")
        } else { Say-Skip "Tệp tạm .tmp_*" }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  2. settings.json — ĐƯỜNG DẪN & CỬA SỔ
# ══════════════════════════════════════════════════════════════════════════
Section "2. CÀI ĐẶT NGƯỜI DÙNG (settings.json)"

$sRes = Read-JsonFile $SETTINGS_FILE
if (-not $sRes.Valid) {
    Say-Skip "Không có settings.json hợp lệ để sửa"
} else {
    $s = $sRes.Data
    $changed = $false

    # ── 2.1 Đường dẫn trình duyệt ──
    # Lỗi hay gặp: giá trị lấy từ Target của shortcut nên DÍNH THAM SỐ
    # (…chrome_proxy.exe --app-id=…) hoặc trỏ tới trình duyệt đã gỡ.
    $bp = [string](Prop $s "browser_path" "")
    if ($bp) {
        $clean = $bp.Trim().Trim('"')
        # Cắt tham số: giữ tới ".exe" đầu tiên
        $m = [Regex]::Match($clean, '^(?<exe>.*?\.exe)(\s|$)', 'IgnoreCase')
        if ($m.Success) { $clean = $m.Groups['exe'].Value.Trim('"').Trim() }
        $clean = $clean.Replace('/', '\')

        $bad = (-not (Test-Path -LiteralPath $clean)) -or ($clean -match 'chrome_proxy\.exe$')
        if (-not $bad -and $clean -ne $bp) {
            W ("[ CHÚ Ý ] browser_path dính tham số thừa: " + $bp) "Yellow"
            if (Ask ("Rút gọn về: " + $clean + " ?")) { Set-Prop $s "browser_path" $clean; $changed = $true; Say-Ok "Đã rút gọn đường dẫn trình duyệt" }
            else { Say-Skip "browser_path" }
        } elseif ($bad) {
            W ("[ LỖI   ] browser_path không dùng được: " + $bp) "Red"
            if ($clean -match 'chrome_proxy\.exe$') {
                Say-Info "chrome_proxy.exe là lối tắt 'ứng dụng web' của Brave — app không mở YouTube qua đó được."
            }
            $found = ""
            foreach ($cand in @(
                (JP $env:ProgramFiles "Google\Chrome\Application\chrome.exe"),
                (JP ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"),
                (JP $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe"),
                (JP ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
                (JP $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
                (JP $env:ProgramFiles "BraveSoftware\Brave-Browser\Application\brave.exe"),
                (JP ${env:ProgramFiles(x86)} "BraveSoftware\Brave-Browser\Application\brave.exe")
            )) {
                if ($cand -and (Test-Path -LiteralPath $cand)) { $found = $cand; break }
            }
            if ($found) {
                if (Ask ("Đổi sang trình duyệt có thật: " + $found + " ?")) {
                    Set-Prop $s "browser_path" $found; $changed = $true
                    Say-Ok ("browser_path → " + $found)
                } else { Say-Skip "browser_path" }
            } else {
                Say-Need "Máy không có Chrome/Edge/Brave — hãy cài Google Chrome rồi chạy lại"
            }
        } else {
            W "[ TỐT   ] Đường dẫn trình duyệt hợp lệ"
        }
    }

    # ── 2.2 Vị trí cửa sổ nằm ngoài màn hình ──
    $geom = Prop $s "window_geometry" $null
    if ($geom) {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
        $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
        $x = [int](Prop $geom "x" 0); $y = [int](Prop $geom "y" 0)
        $w = [int](Prop $geom "width" 850); $h = [int](Prop $geom "height" 300)
        $visible = ($x + $w -gt $vs.Left + 50) -and ($x -lt $vs.Right - 50) -and ($y + $h -gt $vs.Top) -and ($y -lt $vs.Bottom - 50)
        if (-not $visible) {
            W ("[ LỖI   ] Cửa sổ đã lưu nằm ngoài màn hình (x=" + $x + " y=" + $y + ") → mở app không thấy gì") "Red"
            if (Ask "Xoá vị trí cửa sổ đã lưu để app mở lại ở giữa màn hình?") {
                $s.PSObject.Properties.Remove("window_geometry"); $changed = $true
                Say-Ok "Đã xoá window_geometry"
            } else { Say-Skip "window_geometry" }
        } else {
            W "[ TỐT   ] Vị trí cửa sổ nằm trong màn hình"
        }
    }

    # ── 2.3 Màn hình phụ không tồn tại ──
    $mi = Prop $s "display_monitor_index" $null
    if ($null -ne $mi) {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
        $mc = [System.Windows.Forms.Screen]::AllScreens.Count
        if ([int]$mi -ge $mc) {
            W ("[ LỖI   ] Màn hình hiển thị lời đang đặt số " + $mi + " nhưng máy chỉ có " + $mc) "Red"
            if (Ask "Đặt lại về màn hình chính (số 0)?") {
                Set-Prop $s "display_monitor_index" 0; $changed = $true
                Say-Ok "display_monitor_index → 0"
            } else { Say-Skip "display_monitor_index" }
        }
    }

    # ── 2.4 Đường dẫn Studio One ──
    $sop = [string](Prop $s "studio_one_path" "")
    if ($sop) {
        $sopClean = $sop.Replace('/', '\')
        if (-not (Test-Path -LiteralPath $sopClean)) {
            W ("[ LỖI   ] Đường dẫn Studio One không tồn tại: " + $sop) "Red"
            $song = $null
            if ($script:AppRoot) {
                $song = Get-ChildItem -LiteralPath $script:AppRoot -Filter "*.song" -File -ErrorAction SilentlyContinue |
                        Sort-Object LastWriteTime -Descending | Select-Object -First 1
            }
            if ($song) {
                if (Ask ("Dùng bài mẫu tìm thấy trong thư mục cài đặt: " + $song.Name + " ?")) {
                    Set-Prop $s "studio_one_path" $song.FullName; $changed = $true
                    Say-Ok ("studio_one_path → " + $song.FullName)
                } else { Say-Skip "studio_one_path" }
            } else {
                Say-Need "Vào ⚙️ Cài đặt trong app → chọn lại file .song (hoặc Studio One.exe)"
            }
        } elseif ($sopClean -ne $sop) {
            if (Ask "Chuẩn hoá dấu gạch trong đường dẫn Studio One?") {
                Set-Prop $s "studio_one_path" $sopClean; $changed = $true
                Say-Ok "Đã chuẩn hoá studio_one_path"
            }
        } else {
            W "[ TỐT   ] Đường dẫn Studio One hợp lệ"
        }
    }

    # ── 2.5 Khoá kỹ thuật bật nhưng không có PIN ──
    $tl = Prop $s "tech_lock" $null
    if ($tl -and [bool](Prop $tl "enabled" $false) -and -not [string](Prop $tl "pin_hash" "")) {
        W "[ LỖI   ] Chế độ khách đang bật nhưng KHÔNG có mã PIN — không ai mở khoá được" "Red"
        if (Ask "Gỡ chế độ khách (xoá mục tech_lock)?") {
            $s.PSObject.Properties.Remove("tech_lock"); $changed = $true
            Say-Ok "Đã gỡ khoá chế độ khách"
        } else { Say-Skip "tech_lock" }
    }

    if ($changed) {
        if (Backup-File $SETTINGS_FILE) {
            if (Save-JsonFile $SETTINGS_FILE $s) { Say-Info "Đã ghi settings.json (bản cũ nằm trong thư mục sao lưu)" }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3. YOUTUBE — COOKIE (nguyên nhân "Sign in to confirm you're not a bot")
# ══════════════════════════════════════════════════════════════════════════
Section "3. YOUTUBE — COOKIE ĐỂ TẢI ĐƯỢC NHẠC"

if (-not $APP_CONFIG -or -not (Test-Path -LiteralPath $APP_CONFIG)) {
    Say-Skip "Không tìm thấy app_config.json — bỏ qua phần cookie"
} else {
    $cRes = Read-JsonFile $APP_CONFIG
    if (-not $cRes.Valid) {
        W ("[ LỖI   ] app_config.json hỏng: " + $cRes.Error) "Red"
        Say-Need "Chép lại app_config.json từ bộ cài rồi chạy lại script"
    } else {
        $cfg = $cRes.Data
        $cfgChanged = $false

        $curFile    = [string](Prop $cfg "youtube_cookie_file" "")
        $curBrowser = ([string](Prop $cfg "youtube_cookie_browser" "auto")).ToLower()
        W ("        Đang đặt: youtube_cookie_browser = " + $curBrowser + " | youtube_cookie_file = " + $(if ($curFile) { $curFile } else { "(trống)" }))

        # 3.1 Dọn cấu hình trỏ tệp cookie không còn tồn tại
        if ($curFile -and -not (Test-Path -LiteralPath $curFile)) {
            W ("[ LỖI   ] youtube_cookie_file trỏ tệp không tồn tại: " + $curFile) "Red"
            if (Ask "Xoá cấu hình hỏng này?") {
                Set-Prop $cfg "youtube_cookie_file" ""; $cfgChanged = $true; $curFile = ""
                Say-Ok "Đã xoá youtube_cookie_file hỏng"
            }
        }

        # 3.2 Nạp tệp cookies.txt do kỹ thuật cung cấp
        if ($CookieFile) {
            if (-not (Test-Path -LiteralPath $CookieFile)) {
                Say-Fail ("Không thấy tệp cookie: " + $CookieFile)
            } else {
                $head = Get-Content -LiteralPath $CookieFile -TotalCount 40 -Encoding UTF8 -ErrorAction SilentlyContinue
                $text = ($head -join "`n")
                $looksNetscape = ($text -match "Netscape HTTP Cookie File") -or ($text -match "\t(TRUE|FALSE)\t")
                $hasYoutube = $false
                try {
                    $hasYoutube = (Select-String -LiteralPath $CookieFile -Pattern "youtube\.com" -Quiet -ErrorAction SilentlyContinue) -eq $true
                } catch { }
                if (-not $looksNetscape) {
                    Say-Fail "Tệp cookie không đúng định dạng Netscape (cần bản xuất từ tiện ích 'Get cookies.txt')"
                } elseif (-not $hasYoutube) {
                    Say-Fail "Tệp cookie không chứa dòng nào của youtube.com — xuất lại khi đang mở YouTube và đã đăng nhập"
                } else {
                    if (Ask ("Nạp tệp cookie này cho app?")) {
                        try {
                            if (-not (Test-Path -LiteralPath $DATA_DIR)) { New-Item -ItemType Directory -Path $DATA_DIR -Force | Out-Null }
                            Copy-Item -LiteralPath $CookieFile -Destination $COOKIE_TARGET -Force
                            Set-Prop $cfg "youtube_cookie_file" $COOKIE_TARGET
                            Set-Prop $cfg "youtube_cookie_browser" "none"   # đã có cookie file, khỏi dò trình duyệt
                            $cfgChanged = $true; $curFile = $COOKIE_TARGET
                            Say-Ok ("Đã nạp cookie → " + $COOKIE_TARGET)
                            Say-Info "Cookie YouTube thường sống vài tháng; khi lỗi 'not a bot' quay lại thì xuất tệp mới."
                        } catch { Say-Fail ("Chép tệp cookie thất bại: " + $_.Exception.Message) }
                    }
                }
            }
        }

        # 3.3 Chưa có cookie file → chọn nguồn cookie tốt nhất máy đang có
        if (-not $curFile) {
            $ffProfiles = Join-Path $env:APPDATA "Mozilla\Firefox\Profiles"
            $hasFirefox = $false
            if (Test-Path -LiteralPath $ffProfiles) {
                $hasFirefox = @(Get-ChildItem -LiteralPath $ffProfiles -Recurse -Filter "cookies.sqlite" -ErrorAction SilentlyContinue).Count -gt 0
            }
            if (Test-Path -LiteralPath $COOKIE_TARGET) {
                $age = ((Get-Date) - (Get-Item -LiteralPath $COOKIE_TARGET).LastWriteTime).TotalDays
                W ("[ TỐT   ] Đã có tệp cookie tự lưu (" + [math]::Round($age) + " ngày trước): " + $COOKIE_TARGET)
                if ($age -gt 60) { Say-Need "Tệp cookie đã cũ — nên xuất lại nếu YouTube vẫn chặn" }
            } elseif ($hasFirefox) {
                W "[ CHÚ Ý ] Máy có Firefox — đây là nguồn cookie đáng tin nhất (Firefox không khoá tệp cookie)" "Yellow"
                if ($curBrowser -ne "firefox") {
                    if (Ask "Đặt youtube_cookie_browser = firefox?") {
                        Set-Prop $cfg "youtube_cookie_browser" "firefox"; $cfgChanged = $true
                        Say-Ok "youtube_cookie_browser → firefox"
                        Say-Info "Nhớ đăng nhập YouTube trên Firefox một lần."
                    }
                }
            } else {
                W "[ LỖI   ] Không có nguồn cookie dùng được → YouTube sẽ chặn tải nhạc" "Red"
                Say-Info "Chrome/Edge/Brave từ bản 127 mã hoá cookie kiểu mới (App-Bound), yt-dlp báo"
                Say-Info "'Failed to decrypt with DPAPI' và không đọc được — đóng trình duyệt cũng không chữa được."
                Say-Need "Chọn MỘT trong hai cách:"
                Say-Info "  (1) Cài Firefox, đăng nhập YouTube một lần, rồi chạy lại script này."
                Say-Info "  (2) Trên Chrome cài tiện ích 'Get cookies.txt LOCALLY', mở youtube.com (đã đăng nhập),"
                Say-Info "      bấm Export → được tệp cookies.txt, rồi chạy:"
                Say-Info "      SuaLoi.bat -CookieFile ""C:\Users\...\Downloads\cookies.txt"""
            }
        }

        if ($cfgChanged) {
            if (Backup-File $APP_CONFIG) {
                if (Save-JsonFile $APP_CONFIG $cfg) { Say-Info "Đã ghi app_config.json (bản cũ nằm trong thư mục sao lưu)" }
            }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3B. YT-DLP — BỘ TẢI NHẠC BÊN TRONG APP
#      Cookie đúng mà vẫn "Requested format is not available" thì thủ phạm là
#      đây: bản yt-dlp bị đóng băng trong .exe từ lúc build, còn YouTube đổi cơ
#      chế phát video gần như hàng tháng. Nạp bản mới vào %APPDATA%\...\ytdlp,
#      app (từ bản có core/ytdlp_update.py) sẽ tự ưu tiên bản này.
# ══════════════════════════════════════════════════════════════════════════
Section "3B. YT-DLP — BỘ TẢI NHẠC BÊN TRONG APP"

$YTDLP_DIR = Join-Path $DATA_DIR "ytdlp"

function Get-YtDlpDirVersion {
    param([string]$Dir)
    $vf = Join-Path $Dir "yt_dlp\version.py"
    if (-not (Test-Path -LiteralPath $vf)) { return "" }
    try {
        $m = [Regex]::Match((Get-Content -LiteralPath $vf -Raw), "__version__\s*=\s*['""]([^'""]+)['""]")
        if ($m.Success) { return $m.Groups[1].Value }
    } catch { }
    return ""
}

function ToVer {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $clean = ($Text -replace '[^0-9\.]', '')
    try { return [version]$clean } catch { return $null }
}

# Phiên bản app đang dùng (đọc từ nhật ký — bản 1.7.1 trở lên có ghi dòng này)
$loggedVer = ""
$appLog = Join-Path $DATA_DIR "logs\app.log"
if (Test-Path -LiteralPath $appLog) {
    try {
        $hit = Select-String -LiteralPath $appLog -Pattern "yt-dlp đang dùng: *([0-9\.]+)" -ErrorAction SilentlyContinue |
               Select-Object -Last 1
        if ($hit) { $loggedVer = $hit.Matches[0].Groups[1].Value }
    } catch { }
}

$dirVer = Get-YtDlpDirVersion $YTDLP_DIR
if ($dirVer)   { W ("        Bản nạp ngoài hiện có: " + $dirVer) }
if ($loggedVer){ W ("        App đang dùng bản     : " + $loggedVer) }
if (-not $dirVer -and -not $loggedVer) { W "        Chưa có bản yt-dlp nạp ngoài." }

$ytNeeded = $true
if ($Offline) {
    Say-Skip "Chế độ -Offline — bỏ qua cập nhật yt-dlp"
    $ytNeeded = $false
}

if ($ytNeeded) {
    $latest = ""
    $wheelUrl = ""
    $wheelSha = ""
    try {
        try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }
        $meta = Invoke-RestMethod -Uri "https://pypi.org/pypi/yt-dlp/json" -TimeoutSec 30
        $latest = [string]$meta.info.version
        $wheel = @($meta.urls | Where-Object {
            $_.packagetype -eq 'bdist_wheel' -and $_.filename -like '*py3-none-any.whl'
        }) | Select-Object -First 1
        if ($wheel) { $wheelUrl = $wheel.url; $wheelSha = $wheel.digests.sha256 }
    } catch {
        Say-Fail ("Không hỏi được phiên bản yt-dlp mới nhất: " + $_.Exception.Message)
    }

    if (-not $wheelUrl) {
        if ($latest) { Say-Fail ("Không tìm thấy gói cài cho yt-dlp " + $latest) }
    } else {
        W ("        Bản mới nhất trên PyPI: " + $latest)
        $curVer = $dirVer
        if (-not $curVer) { $curVer = $loggedVer }
        $cmpNew = ToVer $latest
        $cmpCur = ToVer $curVer
        $needUpdate = $true
        if ($cmpCur -and $cmpNew -and $cmpNew -le $cmpCur) { $needUpdate = $false }

        if (-not $needUpdate) {
            W ("[ TỐT   ] yt-dlp đã là bản mới nhất (" + $curVer + ")")
        } else {
            if ($curVer) {
                W ("[ LỖI   ] yt-dlp đang dùng (" + $curVer + ") cũ hơn bản mới nhất (" + $latest + ")") "Red"
                Say-Info "Đây là nguyên nhân số 1 của lỗi 'Requested format is not available' và"
                Say-Info "'Sign in to confirm you're not a bot' dù cookie vẫn đúng."
            } else {
                W ("[ CHÚ Ý ] Nên nạp yt-dlp " + $latest + " để chắc chắn tải được video mới") "Yellow"
            }
            if (Ask ("Tải yt-dlp " + $latest + " về máy (khoảng 3 MB)?")) {
                $tmpZip  = Join-Path $env:TEMP ("qls_ytdlp_" + [Guid]::NewGuid().ToString("N") + ".zip")
                $staging = Join-Path $env:TEMP ("qls_ytdlp_" + [Guid]::NewGuid().ToString("N"))
                $ok = $false
                try {
                    Invoke-WebRequest -Uri $wheelUrl -OutFile $tmpZip -TimeoutSec 120 -UseBasicParsing
                    $hash = (Get-FileHash -LiteralPath $tmpZip -Algorithm SHA256).Hash.ToLower()
                    if ($wheelSha -and $hash -ne ([string]$wheelSha).ToLower()) {
                        Say-Fail "Tệp tải về sai mã băm SHA256 — huỷ để an toàn"
                    } else {
                        Expand-Archive -LiteralPath $tmpZip -DestinationPath $staging -Force
                        $src = Join-Path $staging "yt_dlp"
                        $need = @("version.py", "YoutubeDL.py", "extractor\youtube")
                        $good = (Test-Path -LiteralPath $src)
                        foreach ($n in $need) {
                            if (-not (Test-Path -LiteralPath (Join-Path $src $n))) { $good = $false }
                        }
                        if (-not $good) {
                            Say-Fail "Gói tải về không đầy đủ — huỷ"
                        } else {
                            if (-not (Test-Path -LiteralPath $DATA_DIR)) {
                                New-Item -ItemType Directory -Path $DATA_DIR -Force | Out-Null
                            }
                            if (Test-Path -LiteralPath $YTDLP_DIR) {
                                Remove-Item -LiteralPath $YTDLP_DIR -Recurse -Force -ErrorAction SilentlyContinue
                            }
                            New-Item -ItemType Directory -Path $YTDLP_DIR -Force | Out-Null
                            Move-Item -LiteralPath $src -Destination (Join-Path $YTDLP_DIR "yt_dlp") -Force
                            $ok = (Get-YtDlpDirVersion $YTDLP_DIR) -ne ""
                        }
                    }
                } catch {
                    Say-Fail ("Tải yt-dlp thất bại: " + $_.Exception.Message)
                } finally {
                    Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
                    Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
                }
                if ($ok) {
                    Say-Ok ("Đã nạp yt-dlp " + $latest + " vào " + $YTDLP_DIR)
                    Say-Info "Bản mới chỉ có hiệu lực từ LẦN MỞ APP KẾ TIẾP."
                    Say-Need "Cần app phiên bản 1.7.1 trở lên mới đọc được bản nạp ngoài này —"
                    Say-Info "  bản cũ hơn phải cài lại app mới thì mới hết lỗi."
                }
            }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3C. PO TOKEN — TẢI ĐƯỢC MÀ KHÔNG CẦN TÀI KHOẢN YOUTUBE
#
#  Từ 2025 YouTube đòi "PO Token" cho các client web/tv; thiếu nó thì app chỉ
#  còn đường client android (tối đa 360p) và sẽ hỏng hẳn khi YouTube siết tiếp.
#  PO Token KHÔNG phải cookie — nó chứng minh "yêu cầu đến từ trình duyệt thật",
#  không cần bất kỳ tài khoản nào. App tự tải bộ sinh token khi có mạng; mục này
#  để tải ngay hoặc sửa khi bản tải về bị hỏng.
#
#  ⚠ Bố cục thư mục dưới đây phải khớp với core/pot_provider.py (nguồn sự thật).
# ══════════════════════════════════════════════════════════════════════════
Section "3C. PO TOKEN — TẢI YOUTUBE KHÔNG CẦN TÀI KHOẢN"

$POT_VERSION  = "0.8.1"
$POT_BASE     = "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/v" + $POT_VERSION
$POT_EXE_URL  = $POT_BASE + "/bgutil-pot-windows-x86_64.exe"
$POT_EXE_SHA  = "25d6b05c79176aa792454c3d1727922ca47e56cf11cb1e866615d751819b14a0"
$POT_ZIP_URL  = $POT_BASE + "/bgutil-ytdlp-pot-provider-rs.zip"
$POT_ZIP_SHA  = "99fd83b98fa93b193d6a3b69dc74410d76e7a2b889868c54d16121cac9060344"

$POT_DIR      = Join-Path $DATA_DIR "pot"
$POT_EXE      = Join-Path $POT_DIR "bgutil-pot.exe"
$POT_PLUG_DIR = Join-Path $POT_DIR "plugins\bgutil"
$POT_MARKER   = Join-Path $POT_PLUG_DIR "yt_dlp_plugins\extractor\getpot_bgutil.py"
$POT_STAMP    = Join-Path $DATA_DIR "pot_provider.json"

$potExeOk  = Test-Path -LiteralPath $POT_EXE
$potPlugOk = Test-Path -LiteralPath $POT_MARKER

if ($potExeOk -and $potPlugOk) {
    W "[ ĐANG TỐT ] Bộ sinh PO Token đã có — app tải được YouTube không cần tài khoản." "Green"
    Say-Info ("Thư mục: " + $POT_DIR)
} else {
    W "[ THIẾU ] Chưa có bộ sinh PO Token." "Yellow"
    Say-Info "Không có nó, app chỉ tải được qua client android (tối đa 360p),"
    Say-Info "và sẽ hỏng hẳn khi YouTube siết tiếp đường này."
    if (Ask "Tải bộ sinh PO Token về máy (khoảng 44 MB)?") {
        $tmpExe = Join-Path $env:TEMP ("qls_pot_" + [Guid]::NewGuid().ToString("N") + ".exe")
        $tmpZip = Join-Path $env:TEMP ("qls_pot_" + [Guid]::NewGuid().ToString("N") + ".zip")
        $stage  = Join-Path $env:TEMP ("qls_pot_" + [Guid]::NewGuid().ToString("N"))
        $ok = $false
        try {
            Invoke-WebRequest -Uri $POT_ZIP_URL -OutFile $tmpZip -TimeoutSec 180 -UseBasicParsing
            $h = (Get-FileHash -LiteralPath $tmpZip -Algorithm SHA256).Hash.ToLower()
            if ($h -ne $POT_ZIP_SHA) {
                Say-Fail "Gói plugin tải về sai mã băm SHA256 — huỷ để an toàn"
            } else {
                Invoke-WebRequest -Uri $POT_EXE_URL -OutFile $tmpExe -TimeoutSec 600 -UseBasicParsing
                $h2 = (Get-FileHash -LiteralPath $tmpExe -Algorithm SHA256).Hash.ToLower()
                if ($h2 -ne $POT_EXE_SHA) {
                    Say-Fail "Tệp bgutil-pot.exe tải về sai mã băm SHA256 — huỷ để an toàn"
                } else {
                    Expand-Archive -LiteralPath $tmpZip -DestinationPath $stage -Force
                    if (-not (Test-Path -LiteralPath (Join-Path $stage "yt_dlp_plugins\extractor\getpot_bgutil.py"))) {
                        Say-Fail "Gói plugin không đầy đủ — huỷ"
                    } else {
                        if (Test-Path -LiteralPath $POT_PLUG_DIR) {
                            Remove-Item -LiteralPath $POT_PLUG_DIR -Recurse -Force -ErrorAction SilentlyContinue
                        }
                        New-Item -ItemType Directory -Path $POT_PLUG_DIR -Force | Out-Null
                        Move-Item -LiteralPath (Join-Path $stage "yt_dlp_plugins") -Destination $POT_PLUG_DIR -Force
                        Copy-Item -LiteralPath $tmpExe -Destination $POT_EXE -Force
                        $stamp = @{ version = $POT_VERSION; last_check = [int][double]::Parse((Get-Date -UFormat %s)) }
                        $stamp | ConvertTo-Json | Set-Content -LiteralPath $POT_STAMP -Encoding utf8
                        $ok = (Test-Path -LiteralPath $POT_EXE) -and (Test-Path -LiteralPath $POT_MARKER)
                    }
                }
            }
        } catch {
            Say-Fail ("Tải bộ sinh PO Token thất bại: " + $_.Exception.Message)
        } finally {
            Remove-Item -LiteralPath $tmpExe -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $tmpZip -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($ok) {
            Say-Ok ("Đã cài bộ sinh PO Token " + $POT_VERSION + " vào " + $POT_DIR)
            Say-Info "Có hiệu lực từ LẦN MỞ APP KẾ TIẾP."
            Say-Need "Cần app phiên bản 1.7.3 trở lên mới dùng được bộ này."
        }
    }
}

# Runtime JavaScript — đi kèm bộ cài, không tải rời được
if ($script:AppRoot) {
    if (Test-Path -LiteralPath (Join-Path $script:AppRoot "qjs.exe")) {
        W "[ ĐANG TỐT ] Runtime JavaScript (qjs.exe) có sẵn cạnh app." "Green"
    } else {
        W "[ THIẾU ] Không thấy qjs.exe cạnh app." "Yellow"
        Say-Need "Cài lại bản Quang Lưu Studio 1.7.3 trở lên — qjs.exe đi kèm bộ cài,"
        Say-Info "  không tải rời được. Thiếu nó thì YouTube bóp băng thông hoặc trả 403."
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  4. MIDI — loopMIDI
# ══════════════════════════════════════════════════════════════════════════
Section "4. MIDI — loopMIDI"

$portName = $MIDI_PORT_DEFAULT
if ($APP_CONFIG -and (Test-Path -LiteralPath $APP_CONFIG)) {
    $cR = Read-JsonFile $APP_CONFIG
    if ($cR.Valid) { $portName = [string](Prop $cR.Data "midi_port_name" $MIDI_PORT_DEFAULT) }
}

$loopExe = ""
foreach ($p in @((JP $env:ProgramFiles "Tobias Erichsen\loopMIDI\loopMIDI.exe"),
                 (JP ${env:ProgramFiles(x86)} "Tobias Erichsen\loopMIDI\loopMIDI.exe"),
                 (JP $env:LOCALAPPDATA "Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe"))) {
    if ($p -and (Test-Path -LiteralPath $p)) { $loopExe = $p; break }
}

if (-not $loopExe) {
    W "[ LỖI   ] Chưa cài loopMIDI → mọi nút bấm không tác động tới Studio One" "Red"
    if ($script:AppRoot -and (Test-Path (Join-Path $script:AppRoot "setup_all.bat"))) {
        if (Ask "Mở setup_all.bat để cài loopMIDI + Surface?") {
            try {
                Start-Process -FilePath (Join-Path $script:AppRoot "setup_all.bat") -WorkingDirectory $script:AppRoot
                Say-Ok "Đã mở setup_all.bat — làm theo hướng dẫn trên cửa sổ đó rồi chạy lại script này"
            } catch { Say-Fail ("Không mở được setup_all.bat: " + $_.Exception.Message) }
        } else { Say-Skip "Cài loopMIDI" }
    } else {
        Say-Need "Tải loopMIDI tại tobias-erichsen.de rồi chạy setup_all.bat trong thư mục cài đặt"
    }
} else {
    W ("[ TỐT   ] loopMIDI: " + $loopExe)

    # 4.1 Cổng trong cấu hình loopMIDI
    $portsKey = "HKCU:\Software\Tobias Erichsen\loopMIDI\Ports"
    $havePort = $false
    if (Test-Path $portsKey) {
        $props = Get-ItemProperty -Path $portsKey
        $names = @($props.PSObject.Properties | Where-Object { $_.Name -notlike "PS*" } | ForEach-Object { $_.Name })
        $havePort = $names -contains $portName
    }
    if (-not $havePort) {
        W ("[ LỖI   ] loopMIDI chưa khai báo cổng '" + $portName + "'") "Red"
        if (Ask ("Thêm cổng '" + $portName + "' vào cấu hình loopMIDI?")) {
            try {
                if (-not (Test-Path $portsKey)) { New-Item -Path $portsKey -Force | Out-Null }
                New-ItemProperty -Path $portsKey -Name $portName -Value $portName -PropertyType String -Force | Out-Null
                Say-Ok ("Đã thêm cổng " + $portName)
                # loopMIDI chỉ đọc cấu hình lúc khởi động
                $lp = Get-Process -Name "loopMIDI" -ErrorAction SilentlyContinue
                if ($lp) {
                    Stop-Process -Name "loopMIDI" -Force -ErrorAction SilentlyContinue
                    Start-Sleep -Seconds 2
                }
                Start-Process -FilePath $loopExe
                Start-Sleep -Seconds 3
                Say-Ok "Đã khởi động lại loopMIDI để nhận cổng mới"
            } catch { Say-Fail ("Thêm cổng thất bại: " + $_.Exception.Message) }
        } else { Say-Skip "Cổng loopMIDI" }
    } else {
        W ("[ TỐT   ] Cổng '" + $portName + "' đã khai báo")
    }

    # 4.2 loopMIDI đang chạy?
    if (-not (Get-Process -Name "loopMIDI" -ErrorAction SilentlyContinue)) {
        W "[ LỖI   ] loopMIDI chưa chạy → cổng MIDI không tồn tại" "Red"
        if (Ask "Khởi động loopMIDI ngay?") {
            try { Start-Process -FilePath $loopExe; Start-Sleep -Seconds 3; Say-Ok "Đã khởi động loopMIDI" }
            catch { Say-Fail ("Không khởi động được: " + $_.Exception.Message) }
        } else { Say-Skip "Khởi động loopMIDI" }
    } else {
        W "[ TỐT   ] loopMIDI đang chạy"
    }

    # 4.3 Tự khởi động cùng Windows
    $runKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run"
    $hasRun = (Get-ItemProperty -Path $runKey -Name "loopMIDI" -ErrorAction SilentlyContinue) -ne $null
    if (-not $hasRun) {
        W "[ CHÚ Ý ] loopMIDI chưa tự khởi động cùng Windows → khởi động lại máy là mất MIDI" "Yellow"
        if (Ask "Bật tự khởi động cho loopMIDI?") {
            try {
                New-ItemProperty -Path $runKey -Name "loopMIDI" -Value ('"' + $loopExe + '" /autostart') -PropertyType String -Force | Out-Null
                Say-Ok "Đã bật tự khởi động loopMIDI"
            } catch { Say-Fail ("Bật tự khởi động thất bại: " + $_.Exception.Message) }
        } else { Say-Skip "Tự khởi động loopMIDI" }
    } else {
        W "[ TỐT   ] loopMIDI đã tự khởi động cùng Windows"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  5. STUDIO ONE — SURFACE
# ══════════════════════════════════════════════════════════════════════════
Section "5. STUDIO ONE — BẢN MÔ TẢ ĐIỀU KHIỂN (Surface)"

if (-not $script:AppRoot) {
    Say-Skip "Chưa xác định được thư mục cài đặt"
} else {
    $srcSurface = Join-Path $script:AppRoot "studio_one\QuangLuuMIDI.surface.xml"
    $srcDevInfo = Join-Path $script:AppRoot "studio_one\deviceinfo.xml"
    $presAppData = Join-Path $env:APPDATA "PreSonus"
    if (-not (Test-Path -LiteralPath $srcSurface)) {
        Say-Need "Thiếu studio_one\QuangLuuMIDI.surface.xml trong thư mục cài đặt — cài lại app"
    } elseif (-not (Test-Path -LiteralPath $presAppData)) {
        Say-Skip "Studio One chưa từng chạy trên tài khoản này"
    } else {
        $vers = @(Get-ChildItem -LiteralPath $presAppData -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Studio One*" })
        if ($vers.Count -eq 0) { Say-Skip "Không thấy thư mục cấu hình Studio One" }
        foreach ($v in $vers) {
            $dir = Join-Path $v.FullName "User Devices\QuangLuuMIDI"
            $dst = Join-Path $dir "QuangLuuMIDI.surface.xml"
            $need = $false; $why = ""
            if (-not (Test-Path -LiteralPath $dst)) { $need = $true; $why = "chưa cài" }
            else {
                $h1 = (Get-FileHash -LiteralPath $srcSurface -Algorithm SHA256).Hash
                $h2 = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash
                if ($h1 -ne $h2) { $need = $true; $why = "là bản cũ, khác bản đi kèm app" }
            }
            if (-not $need) {
                W ("[ TỐT   ] Surface trong " + $v.Name + " đã đúng bản mới nhất")
                continue
            }
            W ("[ LỖI   ] Surface trong " + $v.Name + " " + $why + " → nút mới (Bè, Tắt Ồn...) không ăn") "Red"
            if (Ask ("Chép Surface mới vào " + $v.Name + "?")) {
                try {
                    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
                    if (Test-Path -LiteralPath $dst) { Backup-File $dst | Out-Null }
                    Copy-Item -LiteralPath $srcSurface -Destination $dir -Force
                    if (Test-Path -LiteralPath $srcDevInfo) { Copy-Item -LiteralPath $srcDevInfo -Destination $dir -Force }
                    Say-Ok ("Đã cập nhật Surface cho " + $v.Name)
                    Say-Info "Phải KHỞI ĐỘNG LẠI Studio One thì bản mô tả mới có hiệu lực."
                } catch { Say-Fail ("Chép Surface thất bại: " + $_.Exception.Message) }
            } else { Say-Skip ("Surface " + $v.Name) }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  6. QUYỀN MICRO & GHI ÂM
# ══════════════════════════════════════════════════════════════════════════
Section "6. QUYỀN MICRO & GHI ÂM"

$micKeys = @(
    @{ P = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"; L = "tài khoản này" },
    @{ P = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged"; L = "ứng dụng máy tính (.exe)" }
)
$micFixed = $false
foreach ($k in $micKeys) {
    if (-not (Test-Path $k.P)) { continue }
    $v = (Get-ItemProperty -Path $k.P -Name "Value" -ErrorAction SilentlyContinue).Value
    if ($v -eq "Deny") {
        W ("[ LỖI   ] Quyền micro cho " + $k.L + " đang bị CHẶN → bản thu không có tiếng hát") "Red"
        if (Ask ("Cho phép truy cập micro (" + $k.L + ")?")) {
            try {
                Set-ItemProperty -Path $k.P -Name "Value" -Value "Allow" -Force
                Say-Ok ("Đã cho phép micro — " + $k.L)
                $micFixed = $true
            } catch { Say-Fail ("Không đổi được quyền micro: " + $_.Exception.Message) }
        } else { Say-Skip ("Quyền micro — " + $k.L) }
    }
}
if (-not $micFixed) { W "[ TỐT   ] Quyền micro không bị chặn" }

# Dịch vụ âm thanh
foreach ($svc in @(@{N="Audiosrv"; L="Windows Audio"}, @{N="AudioEndpointBuilder"; L="Windows Audio Endpoint Builder"})) {
    $s2 = Get-Service -Name $svc.N -ErrorAction SilentlyContinue
    if ($s2 -and $s2.Status -ne "Running") {
        W ("[ LỖI   ] Dịch vụ " + $svc.L + " đang " + $s2.Status) "Red"
        if (Ask ("Khởi động dịch vụ " + $svc.L + "? (cần quyền Admin)")) {
            try { Start-Service -Name $svc.N -ErrorAction Stop; Say-Ok ("Đã khởi động " + $svc.L) }
            catch { Say-Fail ($svc.L + ": " + $_.Exception.Message + " — chạy lại script bằng quyền Admin") }
        } else { Say-Skip ("Dịch vụ " + $svc.L) }
    }
}

# Windows chặn ghi vào Documents
try {
    $cfa = (Get-MpPreference -ErrorAction Stop).EnableControlledFolderAccess
    if ($cfa -eq 1) {
        W "[ LỖI   ] 'Truy cập thư mục có kiểm soát' đang BẬT → app không lưu được bản thu vào Documents" "Red"
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($isAdmin -and $script:AppRoot) {
            if (Ask "Cho phép QuangLuuStudio.exe ghi vào thư mục được bảo vệ?") {
                try {
                    Add-MpPreference -ControlledFolderAccessAllowedApplications (Join-Path $script:AppRoot $EXE_NAME) -ErrorAction Stop
                    Say-Ok "Đã thêm app vào danh sách được phép"
                } catch { Say-Fail ("Không thêm được: " + $_.Exception.Message) }
            }
        } else {
            Say-Need "Chạy lại script này bằng quyền Admin để tự thêm ngoại lệ, hoặc tắt tính năng ở Bảo mật Windows → Bảo vệ khỏi ransomware"
        }
    }
} catch { }

# ══════════════════════════════════════════════════════════════════════════
#  7. TỔNG KẾT
# ══════════════════════════════════════════════════════════════════════════
Section "7. TỔNG KẾT"

W ""
W ("        Đã sửa: " + $script:Done.Count + "    Bỏ qua/cần làm tay: " + $script:Skip.Count + "    Thất bại: " + $script:Failed.Count) "White"
W ""
if ($script:Done.Count -gt 0) {
    W "  ✓ ĐÃ SỬA:" "Green"
    $i = 1; foreach ($d in $script:Done) { W ("    " + $i + ". " + $d) "Green"; $i++ }
    W ""
}
if ($script:Skip.Count -gt 0) {
    W "  ! CÒN LẠI / CẦN LÀM TAY:" "Yellow"
    $i = 1; foreach ($d in $script:Skip) { W ("    " + $i + ". " + $d) "Yellow"; $i++ }
    W ""
}
if ($script:Failed.Count -gt 0) {
    W "  ✗ THẤT BẠI:" "Red"
    $i = 1; foreach ($d in $script:Failed) { W ("    " + $i + ". " + $d) "Red"; $i++ }
    W ""
}

if (Test-Path -LiteralPath $BACKUP_DIR) {
    W ("  Bản sao lưu trước khi sửa: " + $BACKUP_DIR)
    W "  Muốn hoàn tác: chép ngược tệp trong thư mục đó về chỗ cũ."
    W ""
}
W "  BƯỚC TIẾP THEO: mở lại app, thử lại thao tác bị lỗi, rồi chạy ChanDoan.bat" "Cyan"
W "  để xác nhận báo cáo đã sạch." "Cyan"

# ── Ghi nhật ký ──
if (-not $OutFile) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) { $desktop = $env:USERPROFILE }
    $OutFile = Join-Path $desktop ("QLS_SuaLoi_" + $env:COMPUTERNAME + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt")
}
try {
    [IO.File]::WriteAllText($OutFile, $script:Report.ToString(), (New-Object System.Text.UTF8Encoding($true)))
    W ""
    W ("  Nhật ký sửa lỗi: " + $OutFile) "Green"
} catch {
    Write-Host ("Không ghi được nhật ký: " + $_.Exception.Message) -ForegroundColor Red
}

if (-not $NoOpen) {
    try { Start-Process notepad.exe -ArgumentList ('"' + $OutFile + '"') } catch { }
}

if ($script:Failed.Count -gt 0) { exit 2 }
elseif ($script:Skip.Count -gt 0) { exit 1 }
else { exit 0 }
