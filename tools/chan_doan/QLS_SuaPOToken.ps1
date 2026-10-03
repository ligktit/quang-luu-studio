#Requires -Version 5.1
<#
    Quang Lưu Studio — Sửa lỗi "PO Token provider: CHUA co (binary)" + thử tải YouTube
    -------------------------------------------------------------------------------
    Triệu chứng: nhật ký / báo cáo thu_tai.txt ghi
        PO Token provider: CHUA co (binary) - tam dung client android
    nghĩa là plugin bgutil đã có nhưng tệp bgutil-pot.exe KHÔNG có (hoặc không chạy
    được). Thiếu nó, app chỉ còn client android (tối đa 360p) và dễ dính
    "Sign in to confirm you're not a bot" / "Requested format is not available".

    Các nguyên nhân hay gặp, script này kiểm và xử lý lần lượt:
      1. App tải plugin xong nhưng tải binary (~44 MB) đứt giữa chừng — app chỉ
         thử lại sau 24 giờ.
      2. Phần mềm diệt virus (thường là Windows Defender) xoá/cách ly
         bgutil-pot.exe ngay sau khi ghi xuống đĩa.
      3. Windows cũ chưa bật TLS 1.2 cho PowerShell/.NET → không tải được từ GitHub.
      4. Tường lửa chặn bgutil-pot.exe ra Internet → chạy được nhưng không sinh
         được token.

    Sau khi sửa, script chạy "QuangLuuStudio.exe --thu-tai" (đúng đường tải của
    app) để xác nhận tải YouTube được thật.

    Cách dùng (khách hàng): bấm đúp SuaPOToken.bat.
    Cách dùng (kỹ thuật):
        powershell -ExecutionPolicy Bypass -File QLS_SuaPOToken.ps1
            [-Auto] [-Link "https://youtu.be/..."] [-ExeFile "C:\...\bgutil-pot-windows-x86_64.exe"]
            [-AppDir "D:\QuangLuuStudio"] [-DataDir "..."] [-BatBuoc]
            [-KhongThuTai] [-ChiThuTai] [-OutFile "..."] [-NoOpen]

    ⚠ Phiên bản, mã băm và bố cục thư mục phải khớp core/pot_provider.py (nguồn sự thật).

    Mã thoát: 0 = PO Token chạy + tải thử được; 1 = còn việc phải làm tay / tải thử
    chưa đạt; 2 = sửa thất bại.
#>
param(
    # Không hỏi C/K — làm hết (vẫn hiện hộp UAC nếu cần thêm loại trừ Defender)
    [switch]$Auto,
    # Link YouTube dùng để tải thử; bỏ trống thì hỏi (hoặc dùng video mẫu khi -Auto)
    [string]$Link = "",
    # Tệp bgutil-pot-windows-x86_64.exe chép sẵn (USB/Zalo) khi máy không tải được từ GitHub
    [string]$ExeFile = "",
    # Thư mục cài đặt app (chỉ cần khi cài ở chỗ lạ)
    [string]$AppDir = "",
    # Thư mục dữ liệu; mặc định %APPDATA%\QuangLuuStudio
    [string]$DataDir = "",
    # Cài lại binary kể cả khi đang chạy tốt
    [switch]$BatBuoc,
    # Chỉ sửa, không tải thử
    [switch]$KhongThuTai,
    # Chỉ tải thử, không sửa gì
    [switch]$ChiThuTai,
    # Nơi ghi nhật ký; bỏ trống -> Desktop
    [string]$OutFile = "",
    # Không tự mở nhật ký sau khi chạy
    [switch]$NoOpen
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ══════════════════════════════════════════════════════════════════════════
#  Hằng số — giữ khớp với core/pot_provider.py, core/config.py, bộ cài .iss
# ══════════════════════════════════════════════════════════════════════════
$EXE_NAME     = "QuangLuuStudio.exe"
$DATA_FOLDER  = "QuangLuuStudio"
$INNO_APPID   = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1"

$POT_VERSION  = "0.8.1"
$POT_BASE     = "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/v" + $POT_VERSION
$POT_EXE_URL  = $POT_BASE + "/bgutil-pot-windows-x86_64.exe"
$POT_EXE_SHA  = "25d6b05c79176aa792454c3d1727922ca47e56cf11cb1e866615d751819b14a0"
$POT_ZIP_URL  = $POT_BASE + "/bgutil-ytdlp-pot-provider-rs.zip"
$POT_ZIP_SHA  = "99fd83b98fa93b193d6a3b69dc74410d76e7a2b889868c54d16121cac9060344"

# Video mẫu — trùng core/download_check.py để so được với báo cáo cũ
$VIDEO_MAU    = "https://www.youtube.com/watch?v=QRwlhPUcc50"
$VIDEO_MAU_ID = "QRwlhPUcc50"

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
function Say-Fail { param([string]$m) W ("[ THẤT BẠI ] " + $m) "Red"; [void]$script:Failed.Add($m) }
function Say-Need { param([string]$m) W ("[ CẦN LÀM TAY ] " + $m) "Yellow"; [void]$script:Need.Add($m) }
function Say-Info { param([string]$m) W ("           " + $m) "Gray" }

function Ask {
    param([string]$Question)
    if ($Auto) { return $true }
    $a = Read-Host ("   → " + $Question + " [C/k]")
    return ([string]::IsNullOrWhiteSpace($a) -or $a -match '^[cCyY]')
}

function Get-Sha256 {
    param([string]$Path)
    try { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLower() }
    catch { return "" }
}

function New-TempPath {
    param([string]$Ext)
    return (Join-Path $env:TEMP ("qls_pot_" + [Guid]::NewGuid().ToString("N") + $Ext))
}

# JSON không BOM: Python đọc pot_provider.json bằng encoding="utf-8", gặp BOM là
# json.load ném lỗi → app coi như chưa cài → tải lại mỗi 24 giờ.
function Write-JsonNoBom {
    param([string]$Path, $Object)
    $text = $Object | ConvertTo-Json -Depth 5
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding($false)))
}

function Read-Stamp {
    param([string]$Path)
    $h = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $h }
    try {
        $obj = [System.IO.File]::ReadAllText($Path).TrimStart([char]0xFEFF) | ConvertFrom-Json
        foreach ($p in $obj.PSObject.Properties) { $h[$p.Name] = $p.Value }
    } catch { }
    return $h
}

# ══════════════════════════════════════════════════════════════════════════
#  Tải về: thử lần lượt 3 cách, mỗi cách một lần
#  (Invoke-WebRequest hay hỏng vì TLS/proxy trên Windows cũ; BITS và curl.exe
#   đi đường mạng khác nên thường cứu được)
# ══════════════════════════════════════════════════════════════════════════
function Enable-Tls12 {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch { }
}

function Download-Verified {
    param([string]$Url, [string]$Sha, [string]$Label)
    $dest = New-TempPath ([System.IO.Path]::GetExtension($Url))
    $methods = @("Invoke-WebRequest", "BITS", "curl.exe")
    foreach ($m in $methods) {
        Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
        W ("   Tải " + $Label + " bằng " + $m + "...") "Gray"
        $t0 = Get-Date
        try {
            switch ($m) {
                "Invoke-WebRequest" {
                    Invoke-WebRequest -Uri $Url -OutFile $dest -TimeoutSec 900 -UseBasicParsing -ErrorAction Stop
                }
                "BITS" {
                    Import-Module BitsTransfer -ErrorAction Stop
                    Start-BitsTransfer -Source $Url -Destination $dest -ErrorAction Stop
                }
                "curl.exe" {
                    $curl = Join-Path $env:SystemRoot "System32\curl.exe"
                    if (-not (Test-Path -LiteralPath $curl)) { throw "máy không có curl.exe" }
                    & $curl -L --fail --silent --show-error --retry 2 --connect-timeout 30 -o $dest $Url 2>&1 |
                        ForEach-Object { Say-Info ("curl: " + $_) }
                    if ($LASTEXITCODE -ne 0) { throw ("curl.exe thoát mã " + $LASTEXITCODE) }
                }
            }
        } catch {
            Say-Info ("→ không được: " + $_.Exception.Message)
            continue
        }
        if (-not (Test-Path -LiteralPath $dest)) {
            Say-Info "→ tải xong nhưng tệp biến mất (nghi phần mềm diệt virus xoá ngay trong TEMP)"
            continue
        }
        $size = (Get-Item -LiteralPath $dest).Length
        $h = Get-Sha256 $dest
        $sec = [int]((Get-Date) - $t0).TotalSeconds
        if ($h -eq $Sha) {
            Say-Info ("→ được: " + [math]::Round($size / 1MB, 1) + " MB trong " + $sec + " giây, mã băm khớp")
            return $dest
        }
        Say-Info ("→ sai mã băm SHA256 (" + [math]::Round($size / 1MB, 1) + " MB, nhận " + $h.Substring(0, [Math]::Min(16, $h.Length)) + "…) — bỏ")
    }
    Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
    return $null
}

# ══════════════════════════════════════════════════════════════════════════
#  Chạy thử binary
# ══════════════════════════════════════════════════════════════════════════
function Invoke-Exe {
    param([string]$Path, [string]$Arguments, [int]$TimeoutSec)
    $r = @{ Started = $false; ExitCode = -1; Out = ""; Err = ""; Error = ""; Code = 0; TimedOut = $false }
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Path
        $psi.Arguments = $Arguments
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.CreateNoWindow = $true
        $p = [System.Diagnostics.Process]::Start($psi)
        $r.Started = $true
        $outTask = $p.StandardOutput.ReadToEndAsync()
        $errTask = $p.StandardError.ReadToEndAsync()
        if (-not $p.WaitForExit($TimeoutSec * 1000)) {
            try { $p.Kill() } catch { }
            $r.TimedOut = $true
            return $r
        }
        $r.ExitCode = $p.ExitCode
        $r.Out = $outTask.Result
        $r.Err = $errTask.Result
    } catch {
        $ex = $_.Exception
        while ($ex.InnerException) { $ex = $ex.InnerException }
        $r.Error = $ex.Message
        if ($ex -is [System.ComponentModel.Win32Exception]) { $r.Code = $ex.NativeErrorCode }
    }
    return $r
}

# 225 = ERROR_VIRUS_INFECTED, 226 = ERROR_VIRUS_DELETED, 5 = ERROR_ACCESS_DENIED,
# 2 = file đã biến mất giữa chừng — cả bốn đều là dấu vân tay của diệt virus.
function Is-AvSign { param($r) return ($r.Code -in @(2, 5, 225, 226)) }

function Test-PotBinary {
    param([string]$Path)
    $res = @{ Exists = $false; HashOk = $false; Runs = $false; Version = ""; Token = $false; AvSign = $false; Detail = "" }
    if (-not (Test-Path -LiteralPath $Path)) { return $res }
    $res.Exists = $true
    $res.HashOk = ((Get-Sha256 $Path) -eq $POT_EXE_SHA)

    $v = Invoke-Exe $Path "--version" 20
    if (-not $v.Started) {
        $res.AvSign = (Is-AvSign $v)
        $res.Detail = "không khởi chạy được: " + $v.Error
        return $res
    }
    if ($v.TimedOut) { $res.Detail = "--version treo quá 20 giây (nghi diệt virus đang quét)"; return $res }
    if ($v.ExitCode -ne 0) { $res.Detail = "--version thoát mã " + $v.ExitCode + " " + $v.Err.Trim(); return $res }
    $res.Runs = $true
    $res.Version = $v.Out.Trim()

    # Sinh token thật: cần bgutil-pot.exe ra được Internet tới YouTube
    $t = Invoke-Exe $Path ("-c " + $VIDEO_MAU_ID + " --bypass-cache") 60
    if ($t.TimedOut) { $res.Detail = "sinh token quá 60 giây (nghi tường lửa/mạng chặn bgutil-pot.exe)"; return $res }
    if ($t.Started -and $t.ExitCode -eq 0 -and $t.Out -match '"poToken"\s*:\s*"[^"]{20,}"') {
        $res.Token = $true
        return $res
    }
    $msg = ($t.Err + " " + $t.Out + " " + $t.Error).Trim()
    if ($msg.Length -gt 300) { $msg = $msg.Substring(0, 300) + "…" }
    $res.Detail = "không sinh được token (mã " + $t.ExitCode + "): " + $msg
    return $res
}

# ══════════════════════════════════════════════════════════════════════════
#  Phần mềm diệt virus
# ══════════════════════════════════════════════════════════════════════════
function Get-ThirdPartyAv {
    try {
        $avs = Get-CimInstance -Namespace "root/SecurityCenter2" -ClassName AntiVirusProduct -ErrorAction Stop
        return @($avs | Where-Object { $_.displayName -notlike "*Defender*" } | ForEach-Object { $_.displayName })
    } catch { return @() }
}

function Get-DefenderPotDetections {
    try {
        return @(Get-MpThreatDetection -ErrorAction Stop |
            Where-Object { ($_.Resources -join ";") -match "bgutil" })
    } catch { return $null }   # null = không đọc được (thường do thiếu quyền admin)
}

function Test-DefenderExcluded {
    param([string]$Dir)
    try {
        $ex = (Get-MpPreference -ErrorAction Stop).ExclusionPath
        foreach ($e in @($ex)) {
            if ($e -and $Dir.TrimEnd('\').StartsWith($e.TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) { return $true }
        }
    } catch { }
    return $false
}

# Thêm loại trừ CHỈ cho thư mục pot\ (không phải cả ổ, không phải cả app).
# Chạy tiến trình admin riêng qua UAC; truyền đường dẫn tuyệt đối vì tài khoản
# admin có thể khác tài khoản đang dùng (APPDATA khác nhau).
function Add-DefenderExclusion {
    param([string]$Dir)
    $cmd = "Add-MpPreference -ExclusionPath '" + $Dir.Replace("'", "''") + "' -ErrorAction Stop"
    $enc = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($cmd))
    try {
        $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $enc) -ErrorAction Stop
        return ($p.ExitCode -eq 0 -and (Test-DefenderExcluded $Dir))
    } catch {
        Say-Info ("Không thêm được loại trừ: " + $_.Exception.Message)
        return $false
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  BẮT ĐẦU
# ══════════════════════════════════════════════════════════════════════════
W "QUANG LƯU STUDIO — SỬA LỖI PO TOKEN (bgutil-pot.exe) + THỬ TẢI YOUTUBE" "White"
W ("Thời điểm : " + (Get-Date -Format "dd/MM/yyyy HH:mm:ss") + "   Máy: " + $env:COMPUTERNAME)
W ("Windows   : " + [Environment]::OSVersion.VersionString + "   PowerShell " + $PSVersionTable.PSVersion)

Enable-Tls12

# ── Tìm thư mục cài đặt ──
$AppRoot = ""
$candidates = New-Object System.Collections.ArrayList
if ($AppDir) { [void]$candidates.Add($AppDir.TrimEnd('\')) }
[void]$candidates.Add($PSScriptRoot)                      # bat/ps1 chép cạnh exe
$proc0 = Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($proc0 -and $proc0.Path) { [void]$candidates.Add((Split-Path $proc0.Path -Parent)) }
foreach ($hive in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")) {
    $k = Join-Path $hive $INNO_APPID
    if (Test-Path $k) {
        $p = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
        if ($p.InstallLocation) { [void]$candidates.Add($p.InstallLocation.TrimEnd('\')) }
    }
}
foreach ($c in @($env:ProgramFiles, ${env:ProgramFiles(x86)}, (Join-Path $env:LOCALAPPDATA "Programs"))) {
    if ($c) { [void]$candidates.Add((Join-Path $c "QuangLuuStudio")) }
}
foreach ($c in $candidates) {
    if ($c -and (Test-Path -LiteralPath (Join-Path $c $EXE_NAME))) { $AppRoot = $c; break }
}

# Chế độ dev: chạy từ repo mã nguồn, chưa cài app → dùng python main.py, dữ liệu ở gốc repo
$RepoRoot = ""
if (-not $AppRoot) {
    $r = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
    if ($r -and (Test-Path -LiteralPath (Join-Path $r "main.py")) -and (Test-Path -LiteralPath (Join-Path $r "core\pot_provider.py"))) {
        $RepoRoot = $r
    }
}

if (-not $DataDir) {
    if ($RepoRoot) { $DataDir = $RepoRoot } else { $DataDir = Join-Path $env:APPDATA $DATA_FOLDER }
}
$DataDir = $DataDir.TrimEnd('\')

$POT_DIR      = Join-Path $DataDir "pot"
$POT_EXE      = Join-Path $POT_DIR "bgutil-pot.exe"
$POT_PLUG_DIR = Join-Path $POT_DIR "plugins\bgutil"
$POT_MARKER   = Join-Path $POT_PLUG_DIR "yt_dlp_plugins\extractor\getpot_bgutil.py"
$POT_STAMP    = Join-Path $DataDir "pot_provider.json"

if ($AppRoot)      { W ("App       : " + $AppRoot) }
elseif ($RepoRoot) { W ("App       : (chế độ dev) " + $RepoRoot) "DarkYellow" }
else               { W "App       : KHÔNG TÌM THẤY — vẫn sửa được, nhưng không tải thử được. Dùng -AppDir ""D:\...""" "Yellow" }
W ("Dữ liệu   : " + $DataDir)
W ("Bộ PO     : " + $POT_DIR)

# ══════════════════════════════════════════════════════════════════════════
#  1. KIỂM TRA
# ══════════════════════════════════════════════════════════════════════════
Section "1. KIỂM TRA HIỆN TRẠNG"

$appConfig = ""
if ($AppRoot) { $appConfig = Join-Path $AppRoot "app_config.json" } elseif ($RepoRoot) { $appConfig = Join-Path $RepoRoot "app_config.json" }
$potDisabled = $false
if ($appConfig -and (Test-Path -LiteralPath $appConfig)) {
    try {
        $cfg = [System.IO.File]::ReadAllText($appConfig).TrimStart([char]0xFEFF) | ConvertFrom-Json
        if ($cfg.PSObject.Properties["youtube_pot_enabled"] -and $cfg.youtube_pot_enabled -eq $false) {
            $potDisabled = $true
            Say-Bad "app_config.json đang TẮT PO Token (youtube_pot_enabled = false)."
            Say-Need ("Sửa ""youtube_pot_enabled"": true trong " + $appConfig + " (cần quyền admin nếu cài ở Program Files).")
        }
    } catch { Say-Info ("Không đọc được app_config.json: " + $_.Exception.Message) }
}

$plugOk = Test-Path -LiteralPath $POT_MARKER
$stamp  = Read-Stamp $POT_STAMP
if ($plugOk) { Say-Good "Plugin bgutil cho yt-dlp: có" } else { Say-Bad "Plugin bgutil cho yt-dlp: THIẾU" }
if ($stamp.ContainsKey("version")) { Say-Info ("pot_provider.json ghi phiên bản: " + $stamp["version"]) }
else { Say-Info "pot_provider.json: chưa có / không đọc được phiên bản" }

$bin = Test-PotBinary $POT_EXE
if (-not $bin.Exists) {
    Say-Bad "bgutil-pot.exe: KHÔNG CÓ  ← đúng lỗi ""CHUA co (binary)"""
} elseif (-not $bin.HashOk) {
    Say-Bad "bgutil-pot.exe: có nhưng SAI mã băm (tải dở hoặc bị sửa)"
} elseif ($bin.Token) {
    Say-Good ("bgutil-pot.exe: chạy tốt (" + $bin.Version + "), sinh được PO Token")
} elseif ($bin.Runs) {
    Say-Bad ("bgutil-pot.exe: chạy được (" + $bin.Version + ") nhưng " + $bin.Detail)
} else {
    Say-Bad ("bgutil-pot.exe: " + $bin.Detail)
}

$thirdAv = @(Get-ThirdPartyAv)
if ($thirdAv.Count -gt 0) { Say-Info ("Diệt virus khác Defender: " + ($thirdAv -join ", ")) }
$dets = Get-DefenderPotDetections
if ($null -eq $dets) {
    Say-Info "Lịch sử Windows Defender: không đọc được (cần quyền admin hoặc Defender đang tắt)"
} elseif ($dets.Count -gt 0) {
    Say-Bad ("Windows Defender ĐÃ TỪNG CHẶN bgutil-pot.exe (" + $dets.Count + " lần) — gần nhất " + $dets[-1].InitialDetectionTime)
} else {
    Say-Info "Lịch sử Windows Defender: không có lần chặn bgutil nào"
}
$excluded = Test-DefenderExcluded $POT_DIR
if ($excluded) { Say-Info "Thư mục pot\ đã nằm trong danh sách loại trừ của Defender" }

$healthy = $plugOk -and $bin.Token -and $bin.HashOk -and $stamp["version"] -eq $POT_VERSION

# ══════════════════════════════════════════════════════════════════════════
#  2. SỬA
# ══════════════════════════════════════════════════════════════════════════
$tmpExe = $null
if ($ChiThuTai) {
    W ""
    W "(-ChiThuTai: bỏ qua phần sửa)" "DarkGray"
} elseif ($healthy -and -not $BatBuoc) {
    W ""
    Say-Good "Bộ sinh PO Token đang chạy tốt — không cần sửa."
} elseif ($bin.Runs -and $bin.HashOk -and $plugOk -and -not $BatBuoc) {
    # Binary đúng + chạy được: cài lại vô ích. Hoặc chỉ thiếu dấu phiên bản,
    # hoặc không ra token → vấn đề mạng.
    Section "2. SỬA"
    if (-not $bin.Token) {
        Say-Need "bgutil-pot.exe đúng bản và chạy được nhưng không sinh được token."
        Say-Info "Kiểm tra: tường lửa / phần mềm diệt virus có chặn bgutil-pot.exe ra Internet không,"
        Say-Info "máy có vào được youtube.com và www.google.com không, có đang dùng proxy/VPN không."
    }
    if ($stamp["version"] -ne $POT_VERSION) {
        $stamp["version"] = $POT_VERSION
        $stamp["last_check"] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
        try { Write-JsonNoBom $POT_STAMP $stamp; Say-Ok "Ghi lại phiên bản vào pot_provider.json (app sẽ thôi tải lại)" }
        catch { Say-Fail ("Không ghi được pot_provider.json: " + $_.Exception.Message) }
    }
} else {
    Section "2. SỬA — CÀI LẠI BỘ SINH PO TOKEN $POT_VERSION"
    if (-not (Ask "Cài lại bộ sinh PO Token (tải ~44 MB từ GitHub)?")) {
        Say-Need "Đã bỏ qua bước sửa theo lựa chọn."
    } else {
        try { New-Item -ItemType Directory -Path $POT_DIR -Force -ErrorAction Stop | Out-Null }
        catch { Say-Fail ("Không tạo được thư mục " + $POT_DIR + ": " + $_.Exception.Message) }

        # ── 2a. Plugin (nếu thiếu hoặc lệch phiên bản) ──
        if (-not $plugOk -or $stamp["version"] -ne $POT_VERSION -or $BatBuoc) {
            $zip = Download-Verified $POT_ZIP_URL $POT_ZIP_SHA "plugin"
            if (-not $zip) {
                if ($plugOk) { Say-Info "Không tải được plugin mới — giữ plugin đang có." }
                else { Say-Fail "Không tải được plugin bgutil." }
            } else {
                $stage = Join-Path $env:TEMP ("qls_pot_" + [Guid]::NewGuid().ToString("N"))
                try {
                    Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force -ErrorAction Stop
                    if (-not (Test-Path -LiteralPath (Join-Path $stage "yt_dlp_plugins\extractor\getpot_bgutil.py"))) {
                        throw "gói plugin thiếu getpot_bgutil.py"
                    }
                    if (Test-Path -LiteralPath $POT_PLUG_DIR) { Remove-Item -LiteralPath $POT_PLUG_DIR -Recurse -Force -ErrorAction Stop }
                    New-Item -ItemType Directory -Path $POT_PLUG_DIR -Force | Out-Null
                    Move-Item -LiteralPath (Join-Path $stage "yt_dlp_plugins") -Destination $POT_PLUG_DIR -Force -ErrorAction Stop
                    Get-ChildItem -LiteralPath $POT_PLUG_DIR -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
                    $plugOk = Test-Path -LiteralPath $POT_MARKER
                    if ($plugOk) { Say-Ok "Cài plugin bgutil" } else { Say-Fail "Cài plugin xong nhưng không thấy getpot_bgutil.py" }
                } catch {
                    Say-Fail ("Cài plugin thất bại: " + $_.Exception.Message)
                } finally {
                    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
                    Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
                }
            }
        }

        # ── 2b. Lấy binary: tệp chép tay hoặc tải ──
        if ($ExeFile) {
            if (-not (Test-Path -LiteralPath $ExeFile)) {
                Say-Fail ("Không thấy tệp -ExeFile: " + $ExeFile)
            } elseif ((Get-Sha256 $ExeFile) -ne $POT_EXE_SHA) {
                Say-Fail "Tệp -ExeFile SAI mã băm — không phải bgutil-pot $POT_VERSION bản Windows x64, không dùng."
            } else {
                $tmpExe = New-TempPath ".exe"
                Copy-Item -LiteralPath $ExeFile -Destination $tmpExe -Force
                Say-Info "Dùng tệp chép tay (mã băm khớp)."
            }
        } else {
            $tmpExe = Download-Verified $POT_EXE_URL $POT_EXE_SHA "bgutil-pot.exe"
            if (-not $tmpExe) {
                Say-Fail "Không tải được bgutil-pot.exe bằng cả 3 cách."
                Say-Need "Tải tay trên máy khác rồi chép sang và chạy lại với -ExeFile:"
                Say-Info $POT_EXE_URL
            }
        }

        # ── 2c. Đặt binary vào chỗ, rồi đợi xem diệt virus có xoá không ──
        function Install-Binary {
            param([string]$Src)
            try {
                Unblock-File -LiteralPath $Src -ErrorAction SilentlyContinue
                $staging = Join-Path $POT_DIR (".bgutil_new_" + [Guid]::NewGuid().ToString("N") + ".exe")
                Copy-Item -LiteralPath $Src -Destination $staging -Force -ErrorAction Stop
                if (Test-Path -LiteralPath $POT_EXE) {
                    $old = $POT_EXE + ".cu"
                    Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
                    Move-Item -LiteralPath $POT_EXE -Destination $old -Force -ErrorAction Stop
                }
                Move-Item -LiteralPath $staging -Destination $POT_EXE -Force -ErrorAction Stop
                Remove-Item -LiteralPath ($POT_EXE + ".cu") -Force -ErrorAction SilentlyContinue
            } catch {
                Say-Info ("Ghi tệp lỗi: " + $_.Exception.Message)
            }
            Start-Sleep -Seconds 4   # cho Defender quét xong lần ghi
            return (Test-PotBinary $POT_EXE)
        }

        if ($tmpExe) {
            $bin = Install-Binary $tmpExe
            $avBlocked = (-not $bin.Exists) -or $bin.AvSign -or ($bin.Exists -and -not $bin.Runs -and -not $bin.HashOk)

            if ($avBlocked) {
                Say-Bad "bgutil-pot.exe bị xoá/chặn ngay sau khi ghi — phần mềm diệt virus đang chặn."
                if ($bin.Detail) { Say-Info $bin.Detail }
                if ($thirdAv.Count -gt 0) {
                    Say-Need ("Mở " + ($thirdAv -join ", ") + " → khôi phục bgutil-pot.exe khỏi vùng cách ly và thêm loại trừ cho thư mục:")
                    Say-Info $POT_DIR
                    Say-Info "Rồi chạy lại file này."
                } else {
                    Say-Info "Tệp đã được kiểm mã băm SHA256 khớp bản phát hành chính thức (mã nguồn mở, GPL-3.0)."
                    Say-Info "Cách chữa: cho Windows Defender bỏ qua RIÊNG thư mục:"
                    Say-Info $POT_DIR
                    if (Ask "Thêm loại trừ Defender cho thư mục trên (Windows sẽ hỏi quyền admin)?") {
                        if (Add-DefenderExclusion $POT_DIR) {
                            Say-Ok "Thêm loại trừ Defender cho thư mục pot\"
                            $bin = Install-Binary $tmpExe
                        } else {
                            Say-Fail "Không thêm được loại trừ Defender (bị từ chối quyền admin hoặc Defender do tổ chức quản lý)."
                            Say-Need "Mở Bảo mật Windows → Bảo vệ khỏi virus → Quản lý cài đặt → Loại trừ → thêm thư mục trên."
                        }
                    } else {
                        Say-Need "Tự thêm loại trừ: Bảo mật Windows → Bảo vệ khỏi virus → Quản lý cài đặt → Loại trừ."
                    }
                }
            }

            if ($bin.Exists -and $bin.HashOk -and $bin.Runs) {
                Say-Ok ("Cài bgutil-pot.exe (" + $bin.Version + ") vào " + $POT_DIR)
                if ($bin.Token) {
                    Say-Good "Sinh thử PO Token: ĐƯỢC"
                } else {
                    Say-Bad ("Sinh thử PO Token: " + $bin.Detail)
                    Say-Need "Cho bgutil-pot.exe ra Internet (tường lửa / diệt virus), kiểm tra proxy/VPN."
                }
                if ($plugOk) {
                    $stamp["version"] = $POT_VERSION
                    $stamp["last_check"] = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
                    try { Write-JsonNoBom $POT_STAMP $stamp }
                    catch { Say-Info ("Không ghi được pot_provider.json: " + $_.Exception.Message) }
                }
            } elseif (-not $avBlocked) {
                Say-Fail ("bgutil-pot.exe vẫn không chạy được: " + $bin.Detail)
            } elseif ($script:Need.Count -eq 0) {
                Say-Fail "bgutil-pot.exe vẫn bị chặn sau khi thêm loại trừ."
            }
            Remove-Item -LiteralPath $tmpExe -Force -ErrorAction SilentlyContinue
        }

        if (-not $potDisabled -and $bin.Runs -and $plugOk) {
            $running = Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue
            if ($running) {
                Say-Need "App đang mở: TẮT HẲN rồi mở lại app thì bộ PO Token mới có hiệu lực (yt-dlp chỉ nạp plugin một lần)."
            }
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3. THỬ TẢI YOUTUBE
#
#  Bài học 17/09/2026: bản cũ tựa vào "QuangLuuStudio.exe --thu-tai" và chờ vô
#  hạn. Bản app KHÔNG có tham số đó (mọi bản phát hành tới 1.7.5) sẽ lặng lẽ mở
#  giao diện thường → script đứng im "Đang tải thử" hàng chục phút.
#  Nay tải thử bằng yt-dlp.exe BẢN ĐỘC LẬP (chính thức, kiểm mã băm) dùng chung
#  PO Token / qjs.exe / ffmpeg của app: chạy được với mọi bản app, có tiến độ
#  từng vài giây, và mỗi lượt đều có trần thời gian + tự diệt khi đứng.
# ══════════════════════════════════════════════════════════════════════════
$YTDLP_API      = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
$TRY_TIMEOUT    = 100   # giây cho mỗi lượt (app cho dò tone 90 giây)
$STALL_TIMEOUT  = 45    # giây không có byte/dòng mới nào → coi là đứng
$HOTFIX_CLIENTS = @("web_embedded", "android", "android_vr")
$HOTFIX_FLAG    = "youtube_player_clients_vanhanh_web_embedded"

function Quote-Arg {
    param([string]$s)
    if ($s -notmatch '[\s"]') { return $s }
    return '"' + ($s -replace '(\\*)"', '$1$1\"' -replace '(\\+)$', '$1$1') + '"'
}

# Diệt cả cây tiến trình (yt-dlp.exe onefile đẻ tiến trình con, rồi con đẻ ffmpeg)
function Stop-Tree {
    param([int]$ProcId)
    try { & "$env:SystemRoot\System32\taskkill.exe" /PID $ProcId /T /F 2>&1 | Out-Null } catch { }
}

# Chạy một tiến trình với tiến độ sống + trần thời gian + phát hiện đứng.
# Trả @{ ExitCode; Seconds; Reason ('xong'|'het-gio'|'dung'|'khong-chay'); OutFile }
function Invoke-Watched {
    param([string]$FilePath, [string]$Arguments, [string]$WorkDir, [int]$Timeout,
          [int]$Stall, [string]$WatchDir = "", [string]$Label = "")
    $res = @{ ExitCode = -1; Seconds = 0; Reason = "khong-chay"; OutFile = "" }
    $outFile = New-TempPath ".out.txt"; $errFile = New-TempPath ".err.txt"
    $res.OutFile = $outFile
    try {
        $p = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkDir `
            -NoNewWindow -PassThru -RedirectStandardOutput $outFile -RedirectStandardError $errFile -ErrorAction Stop
    } catch {
        Say-Info ("Không chạy được: " + $_.Exception.Message)
        return $res
    }
    # PS 5.1: không giữ Handle ngay thì ExitCode sau này trả rỗng
    $null = $p.Handle
    $t0 = Get-Date; $lastChange = $t0; $lastSig = ""; $lastPrint = $t0.AddSeconds(-10); $shown = 0
    while (-not $p.HasExited) {
        Start-Sleep -Milliseconds 1000
        $now = Get-Date
        $sec = [int]($now - $t0).TotalSeconds
        $bytes = 0
        if ($WatchDir -and (Test-Path -LiteralPath $WatchDir)) {
            $bytes = (Get-ChildItem -LiteralPath $WatchDir -File -Recurse -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
            if (-not $bytes) { $bytes = 0 }
        }
        $lines = @()
        foreach ($f in @($outFile, $errFile)) {
            try {
                $fs = [System.IO.File]::Open($f, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                try { $lines += ((New-Object System.IO.StreamReader($fs, [Text.Encoding]::UTF8)).ReadToEnd() -split "`r?`n" | Where-Object { $_.Trim() }) }
                finally { $fs.Dispose() }
            } catch { }
        }
        $sig = [string]$bytes + "|" + $lines.Count
        if ($sig -ne $lastSig) { $lastSig = $sig; $lastChange = $now }
        if (($now - $lastPrint).TotalSeconds -ge 5) {
            $lastPrint = $now
            $tail = ""
            if ($lines.Count -gt $shown) {
                $tail = ($lines[-1] -replace '\s+', ' ').Trim()
                if ($tail.Length -gt 90) { $tail = $tail.Substring(0, 90) + "…" }
                $shown = $lines.Count
            }
            if (-not $tail) {
                $idle = [int]($now - $lastChange).TotalSeconds
                $tail = if ($idle -ge 10) { "chưa có gì mới trong " + $idle + " giây…" } else { "đang chạy…" }
            }
            $mb = if ($bytes -gt 0) { " | đã tải " + [math]::Round($bytes / 1MB, 2) + " MB" } else { "" }
            Write-Host ("     [" + $sec.ToString().PadLeft(3) + "s" + $mb + "] " + $tail) -ForegroundColor DarkGray
        }
        if ($sec -ge $Timeout) {
            Stop-Tree $p.Id; $res.Reason = "het-gio"; $res.Seconds = $sec
            break
        }
        if (($now - $lastChange).TotalSeconds -ge $Stall) {
            Stop-Tree $p.Id; $res.Reason = "dung"; $res.Seconds = $sec
            break
        }
    }
    if ($res.Reason -eq "khong-chay") {
        $p.WaitForExit()
        $res.Reason = "xong"
        $res.ExitCode = $p.ExitCode
        $res.Seconds = [int]((Get-Date) - $t0).TotalSeconds
    }
    # gộp stderr vào stdout để lưu một chỗ
    try { Add-Content -LiteralPath $outFile -Value ([System.IO.File]::ReadAllText($errFile)) -Encoding UTF8 } catch { }
    Remove-Item -LiteralPath $errFile -Force -ErrorAction SilentlyContinue
    return $res
}

function Find-Ffmpeg {
    $roots = @()
    if ($AppRoot)  { $roots += @((Join-Path $AppRoot "ffmpeg\bin"), (Join-Path $AppRoot "ffmpeg"), $AppRoot) }
    if ($RepoRoot) { $roots += @((Join-Path $RepoRoot "binaries\ffmpeg\bin"), (Join-Path $RepoRoot "binaries\ffmpeg"), (Join-Path $RepoRoot "ffmpeg\bin")) }
    foreach ($r in $roots) { if (Test-Path -LiteralPath (Join-Path $r "ffmpeg.exe")) { return $r } }
    $c = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return (Split-Path $c.Source -Parent) }
    return ""
}

function Find-Qjs {
    foreach ($r in @($AppRoot, $RepoRoot, $(if ($RepoRoot) { Join-Path $RepoRoot "binaries" }))) {
        if ($r -and (Test-Path -LiteralPath (Join-Path $r "qjs.exe"))) { return (Join-Path $r "qjs.exe") }
    }
    return ""
}

# yt-dlp.exe chính thức, cache trong %TEMP% để lần sau khỏi tải lại
function Get-YtDlpExe {
    $cacheDir = Join-Path $env:TEMP "qls_ytdlp"
    New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
    $exe = Join-Path $cacheDir "yt-dlp.exe"
    $rel = $null
    try {
        $rel = Invoke-RestMethod -Uri $YTDLP_API -TimeoutSec 30 -UseBasicParsing -Headers @{ "User-Agent" = "QuangLuuStudio-SuaPOToken" } -ErrorAction Stop
    } catch { Say-Info ("Không hỏi được GitHub bản yt-dlp mới nhất: " + $_.Exception.Message) }
    if (-not $rel) {
        if (Test-Path -LiteralPath $exe) { Say-Info "Dùng yt-dlp.exe đã tải từ lần trước."; return $exe }
        return ""
    }
    $sumsAsset = @($rel.assets | Where-Object { $_.name -eq "SHA2-256SUMS" }) | Select-Object -First 1
    $exeAsset  = @($rel.assets | Where-Object { $_.name -eq "yt-dlp.exe" }) | Select-Object -First 1
    if (-not $sumsAsset -or -not $exeAsset) { return "" }
    $sha = ""
    try {
        $txt = (Invoke-WebRequest -Uri $sumsAsset.browser_download_url -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop).Content
        if ($txt -is [byte[]]) { $txt = [Text.Encoding]::UTF8.GetString($txt) }
        $line = $txt -split "`n" | Where-Object { $_ -match '\syt-dlp\.exe\s*$' } | Select-Object -First 1
        if ($line) { $sha = ($line -split '\s+')[0].ToLower() }
    } catch { }
    if (-not $sha) { Say-Info "Không lấy được mã băm của yt-dlp.exe."; return "" }
    if ((Test-Path -LiteralPath $exe) -and (Get-Sha256 $exe) -eq $sha) {
        Say-Info ("yt-dlp " + $rel.tag_name + " (đã có sẵn)"); return $exe
    }
    $tmp = Download-Verified $exeAsset.browser_download_url $sha ("yt-dlp " + $rel.tag_name)
    if (-not $tmp) { return "" }
    try { Move-Item -LiteralPath $tmp -Destination $exe -Force -ErrorAction Stop; Unblock-File -LiteralPath $exe -ErrorAction SilentlyContinue }
    catch { Say-Info ("Không chép được yt-dlp.exe: " + $_.Exception.Message); return "" }
    return $exe
}

# ── Mạng ──
# Gọi bằng .NET (đúng kiểu app/yt-dlp: KHÔNG tự lùi IPv6 → IPv4). -FreshProcess
# chạy trong tiến trình PowerShell mới để không dính bộ nhớ đệm kết nối/DNS cũ.
function Test-DefaultRoute {
    param([string]$Url, [switch]$FreshProcess)
    $t0 = Get-Date
    if ($FreshProcess) {
        $cmd = "try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}; " +
               "try { `$r = Invoke-WebRequest -Uri '" + $Url + "' -TimeoutSec 15 -UseBasicParsing; exit 0 } catch { exit 1 }"
        $p = Start-Process powershell.exe -ArgumentList @("-NoProfile", "-Command", $cmd) -NoNewWindow -Wait -PassThru
        $ok = ($p.ExitCode -eq 0)
        Say-Info ($Url + " (tiến trình mới) → " + $(if ($ok) { "ĐƯỢC" } else { "KHÔNG" }) + " (" + [int]((Get-Date) - $t0).TotalSeconds + " giây)")
        return $ok
    }
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 15 -UseBasicParsing -ErrorAction Stop
        Say-Info ($Url + " → " + $r.StatusCode + " (" + [int]((Get-Date) - $t0).TotalMilliseconds + " ms)")
        return $true
    } catch {
        Say-Bad ($Url + " → KHÔNG VÀO ĐƯỢC sau " + [int]((Get-Date) - $t0).TotalSeconds + " giây: " + $_.Exception.Message)
        return $false
    }
}

function Test-CurlIp {
    param([string]$Flag)
    $res = @{ Ok = $false; Text = "" }
    $curl = Join-Path $env:SystemRoot "System32\curl.exe"
    if (-not (Test-Path -LiteralPath $curl)) { $res.Text = "máy không có curl.exe"; return $res }
    $out = & $curl $Flag -s -o NUL -w "%{http_code} %{time_total}" --connect-timeout 8 --max-time 12 "https://www.youtube.com/generate_204" 2>&1
    $code = $LASTEXITCODE
    $parts = ([string]$out).Trim() -split '\s+'
    if ($code -eq 0 -and $parts[0] -eq "204") {
        $res.Ok = $true
        $res.Text = "ĐƯỢC (" + [int]([double]::Parse($parts[1], [Globalization.CultureInfo]::InvariantCulture) * 1000) + " ms)"
    } else {
        $why = switch ($code) { 6 { "không phân giải được tên" } 7 { "không kết nối được" } 28 { "quá giờ" } default { "lỗi curl " + $code } }
        $res.Text = "KHÔNG (" + $why + ")"
    }
    return $res
}

# Độ ưu tiên của một tiền tố trong bảng chính sách địa chỉ (đọc được không cần admin)
function Get-PrefixPrecedence {
    param([string]$Prefix)
    foreach ($line in @(netsh interface ipv6 show prefixpolicies 2>$null)) {
        $cols = ([string]$line).Trim() -split '\s+'
        if ($cols.Count -ge 3 -and $cols[2] -eq $Prefix) { return [int]$cols[0] }
    }
    return $null
}

# Đưa ::ffff:0:0/96 (IPv4) lên trên ::/0 (IPv6) trong bảng ưu tiên địa chỉ.
# Mặc định Windows 10: ::/0 = 40, ::ffff:0:0/96 = 35. Đặt 50 → IPv4 đứng trước
# (đúng mức Microsoft dùng cho chế độ "Prefer IPv4 over IPv6"). Không tắt IPv6.
# Đảo lại: netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 35 4
function Set-PreferIPv4 {
    $cmd = "netsh interface ipv6 set prefixpolicy prefix=::ffff:0:0/96 precedence=50 label=4 store=persistent | Out-Null; " +
           "netsh interface ipv6 set prefixpolicy prefix=::ffff:0:0/96 precedence=50 label=4 store=active | Out-Null; " +
           "if ((netsh interface ipv6 show prefixpolicies | Select-String '::ffff:0:0/96') -match '^\s*50\s') { exit 0 } else { exit 1 }"
    $enc = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($cmd))
    try {
        $p = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
            -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $enc) -ErrorAction Stop
        if ($p.ExitCode -eq 0) { return $true }
        Say-Fail "Đặt ưu tiên IPv4 không thành công (netsh báo lỗi)."
    } catch {
        Say-Need ("Không lấy được quyền admin để đặt ưu tiên IPv4: " + $_.Exception.Message)
    }
    return $false
}

# Ghi các khoá vào app_config.json (sao lưu, không BOM, xin admin nếu cần)
function Set-AppConfigValues {
    param([hashtable]$Values, [string]$Label)
    $cfgPath = Join-Path $AppRoot "app_config.json"
    $cfg = $null
    if (Test-Path -LiteralPath $cfgPath) {
        try { $cfg = [System.IO.File]::ReadAllText($cfgPath).TrimStart([char]0xFEFF) | ConvertFrom-Json -ErrorAction Stop }
        catch { Say-Fail ("app_config.json hỏng, không đọc được: " + $_.Exception.Message); return $false }
    }
    if ($null -eq $cfg) { $cfg = New-Object psobject }
    $same = $true
    foreach ($k in $Values.Keys) {
        $cur = if ($cfg.PSObject.Properties[$k]) { ($cfg.$k | ConvertTo-Json -Compress) } else { "<none>" }
        if ($cur -ne ($Values[$k] | ConvertTo-Json -Compress)) { $same = $false }
        $cfg | Add-Member -NotePropertyName $k -NotePropertyValue $Values[$k] -Force
    }
    if ($same) { Say-Info ("app_config.json đã " + $Label + " từ trước."); return $true }
    # KHÔNG BOM: core/config.py mở bằng encoding="utf-8", gặp BOM là json.load ném lỗi
    # và app lặng lẽ bỏ CẢ file cấu hình, dùng mặc định.
    $tmpCfg = New-TempPath ".json"
    [System.IO.File]::WriteAllText($tmpCfg, ($cfg | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))

    $backupDir = Join-Path $DataDir ("backup_sualoi\" + (Get-Date -Format "yyyyMMdd_HHmmss"))
    $written = $false
    try {
        if (Test-Path -LiteralPath $cfgPath) {
            New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
            Copy-Item -LiteralPath $cfgPath -Destination (Join-Path $backupDir "app_config.json") -Force -ErrorAction Stop
        }
        Copy-Item -LiteralPath $tmpCfg -Destination $cfgPath -Force -ErrorAction Stop
        $written = $true
    } catch [System.UnauthorizedAccessException] {
        $cmd = "Copy-Item -LiteralPath '" + $tmpCfg.Replace("'", "''") + "' -Destination '" + $cfgPath.Replace("'", "''") + "' -Force"
        $enc = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes("`$ErrorActionPreference='Stop'; try { " + $cmd + "; exit 0 } catch { exit 1 }"))
        try {
            $pe = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
                -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $enc) -ErrorAction Stop
            $written = ($pe.ExitCode -eq 0)
        } catch { Say-Info ("Không lấy được quyền admin: " + $_.Exception.Message) }
    } catch {
        Say-Info ("Ghi app_config.json lỗi: " + $_.Exception.Message)
    }
    Remove-Item -LiteralPath $tmpCfg -Force -ErrorAction SilentlyContinue
    if (-not $written) { Say-Fail "Không ghi được app_config.json (cần quyền admin)."; return $false }
    Say-Ok ("app_config.json: " + $Label)
    if (Test-Path -LiteralPath (Join-Path $backupDir "app_config.json")) { Say-Info ("Bản sao lưu: " + $backupDir) }
    return $true
}

function Set-ClientHotfix {
    $values = @{ "youtube_player_clients" = $HOTFIX_CLIENTS; $HOTFIX_FLAG = $true }
    return (Set-AppConfigValues $values "ép client web_embedded, android, android_vr")
}

$downloadOk = $null
if (-not $KhongThuTai) {
    Section "3. THỬ TẢI AUDIO TỪ YOUTUBE"
    if (-not $Link -and -not $Auto) {
        W "   Dán link YouTube của bài đang lỗi rồi bấm Enter (bỏ trống = video mẫu):"
        $Link = (Read-Host "   Link").Trim()
    }
    if (-not $Link) { $Link = $VIDEO_MAU }
    if ($Link -notmatch '^https?://') {
        Say-Info ("Link không hợp lệ, dùng video mẫu thay cho: " + $Link)
        $Link = $VIDEO_MAU
    }
    W ("   Link: " + $Link)

    # ── 3a. Mạng tới YouTube: tách IPv4 / IPv6 ──
    # Ca máy khách 17/09/2026: trình duyệt + bgutil-pot (Rust) vào YouTube bình
    # thường, GitHub tải 17 MB/2 giây, nhưng PowerShell và yt-dlp (Python) treo
    # khi gọi youtube.com/google.com. Dấu vân tay của IPv6 HỎNG: YouTube/Google có
    # địa chỉ IPv6 còn GitHub thì không; trình duyệt và Rust tự lùi về IPv4 sau
    # ~0,3 giây ("Happy Eyeballs"), còn .NET/Python đợi IPv6 tới hết giờ.
    W ""
    W "   Kiểm tra đường mạng tới YouTube (tách IPv4 / IPv6)..." "Gray"
    $netOk = (Test-DefaultRoute "https://www.youtube.com/generate_204") -and (Test-DefaultRoute "https://www.google.com/generate_204")
    $v4 = Test-CurlIp "-4"
    $v6 = Test-CurlIp "-6"
    $aaaa = @()
    try { $aaaa = @(Resolve-DnsName -Name "www.youtube.com" -Type AAAA -DnsOnly -ErrorAction Stop | Where-Object { $_.IPAddress }) } catch { }
    Say-Info ("IPv4 (curl -4): " + $v4.Text)
    Say-Info ("IPv6 (curl -6): " + $v6.Text)
    Say-Info ("DNS trả địa chỉ IPv6 cho youtube: " + $(if ($aaaa.Count) { "có (" + $aaaa[0].IPAddress + ")" } else { "không" }))

    $ipv6Broken = $v4.Ok -and (-not $v6.Ok) -and ($aaaa.Count -gt 0)
    $preferV4Applied = $false
    $precV4 = Get-PrefixPrecedence "::ffff:0:0/96"
    $precV6 = Get-PrefixPrecedence "::/0"
    $alreadyV4 = ($null -ne $precV4 -and $null -ne $precV6 -and $precV4 -gt $precV6)
    Say-Info ("Bảng ưu tiên địa chỉ: IPv4 = " + $precV4 + ", IPv6 = " + $precV6 + $(if ($alreadyV4) { " → Windows ĐÃ ưu tiên IPv4" } else { " → Windows ưu tiên IPv6" }))
    if ($netOk) {
        Say-Good "Chương trình thường (PowerShell/.NET) vào được YouTube."
    } elseif ($ipv6Broken) {
        Say-Bad "IPv6 HỎNG trên đường mạng này: IPv4 vào YouTube được, IPv6 thì không."
        Say-Info "Trình duyệt tự lùi về IPv4 nên vẫn xem được; app + yt-dlp thì đợi IPv6 tới hết giờ"
        Say-Info "→ đúng triệu chứng ""Đang dò vẫn quá lâu"". Đổi DNS KHÔNG chữa được (DNS vẫn trả IPv6)."
        Say-Info "Cách chữa: cho Windows ƯU TIÊN IPv4 (không tắt IPv6, đảo lại được bất cứ lúc nào)."
        if ($alreadyV4) {
            Say-Info "Windows đã ưu tiên IPv4 sẵn mà vẫn treo → không phải do thứ tự IPv6; gửi nhật ký cho kỹ thuật."
        } elseif (Ask "Đặt Windows ưu tiên IPv4 (Windows sẽ hỏi quyền admin)?") {
            if (Set-PreferIPv4) {
                Start-Sleep -Seconds 2
                if (Test-DefaultRoute "https://www.youtube.com/generate_204" -FreshProcess) {
                    Say-Ok "Windows ưu tiên IPv4 — chương trình thường đã vào được YouTube"
                    Say-Info "Đảo lại (nếu cần): netsh interface ipv6 set prefixpolicy ::ffff:0:0/96 35 4"
                    $preferV4Applied = $true
                    $netOk = $true
                    # Bản app có hỗ trợ khoá này sẽ tự ép IPv4 kể cả khi ai đó đảo lại cài đặt Windows
                    if ($AppRoot) { [void](Set-AppConfigValues @{ "youtube_force_ipv4" = $true } "bật youtube_force_ipv4") }
                } else {
                    Say-Fail "Đã đặt ưu tiên IPv4 nhưng vẫn chưa vào được — có thể cần khởi động lại máy."
                }
            }
        }
        if (-not $preferV4Applied) {
            Say-Need "Chưa ưu tiên IPv4 → app vẫn sẽ dò lâu. Chạy lại script và chọn C, hoặc tắt IPv6 trên card mạng / trên modem."
        }
    } elseif (-not $v4.Ok -and -not $v6.Ok) {
        Say-Bad "Cả IPv4 lẫn IPv6 đều không vào được YouTube bằng chương trình thường."
        Say-Info "Nếu trình duyệt vẫn xem được: phần mềm diệt virus/tường lửa/lọc web đang chặn riêng các"
        Say-Info "chương trình khác trình duyệt, hoặc trình duyệt đi qua proxy/VPN mà chương trình khác không dùng."
        Say-Need "Tạm tắt tính năng bảo vệ web của phần mềm diệt virus (hoặc VPN/proxy) rồi chạy lại để so sánh."
    } else {
        Say-Bad "PowerShell không vào được YouTube dù curl vào được — nghi proxy hệ thống hoặc lọc HTTPS của diệt virus."
        Say-Need "Kiểm tra Cài đặt → Mạng → Proxy, và tính năng quét HTTPS/Web của phần mềm diệt virus."
    }
    # Chưa sửa được ở mức Windows mà IPv4 dùng được → cho yt-dlp ép IPv4 để chứng minh
    $forceV4 = $ipv6Broken -and -not $preferV4Applied

    # ── 3b. Chuẩn bị bộ tải độc lập ──
    $ytdlp = Get-YtDlpExe
    $ffDir = Find-Ffmpeg
    $qjs   = Find-Qjs
    $plugRoot = Join-Path $POT_DIR "plugins"
    $potUsable = (Test-Path -LiteralPath $POT_EXE) -and (Test-Path -LiteralPath $POT_MARKER)
    Say-Info ("ffmpeg : " + $(if ($ffDir) { $ffDir } else { "KHÔNG THẤY — sẽ tải cả bài thay vì 45 giây đầu" }))
    Say-Info ("qjs    : " + $(if ($qjs) { $qjs } else { "KHÔNG THẤY" }))
    Say-Info ("PO Token: " + $(if ($potUsable) { "có" } else { "không" }))

    $results = New-Object System.Collections.ArrayList
    if (-not $ytdlp) {
        Say-Fail "Không có yt-dlp.exe để tải thử (không tải được từ GitHub)."
    } else {
        # Thứ tự = thang client của app, rồi tới bản vá. Mỗi dòng: tên hiển thị, player_client
        $plans = @(
            @("android (nấc đầu của app)", "android,android_vr"),
            @("web_embedded",              "web_embedded"),
            @("BẢN VÁ NHANH",              ($HOTFIX_CLIENTS -join ",")),
            @("mặc định của yt-dlp",       "default"),
            @("web_safari/mweb (PO Token)", "web_safari,mweb")
        )
        $base = Join-Path $env:TEMP ("qls_thutai_" + (Get-Date -Format "HHmmss"))
        foreach ($pl in $plans) {
            $name = $pl[0]; $clients = $pl[1]
            $out = Join-Path $base ($clients -replace '[^a-z_]', '_')
            New-Item -ItemType Directory -Path $out -Force | Out-Null
            $a = @("--no-config", "--no-playlist", "--newline", "--socket-timeout", "20", "--retries", "2",
                   "-f", "ba/b", "-o", (Join-Path $out "t.%(ext)s"),
                   "--extractor-args", ("youtube:player_client=" + $clients))
            if ($forceV4) { $a += "--force-ipv4" }
            if ($ffDir) { $a += @("--ffmpeg-location", $ffDir, "--download-sections", "*0-45") }
            if ($qjs)   { $a += @("--js-runtimes", ("quickjs:" + $qjs)) }
            if ($potUsable) {
                $a += @("--plugin-dirs", $plugRoot, "--extractor-args", ("youtubepot-bgutilcli:cli_path=" + $POT_EXE))
            }
            $a += $Link
            $argLine = ($a | ForEach-Object { Quote-Arg $_ }) -join " "

            W ""
            W ("   ▶ Thử client " + $name + $(if ($forceV4) { ", ép IPv4" } else { "" }) + " (tối đa " + $TRY_TIMEOUT + " giây)") "White"
            $env:PYTHONIOENCODING = "utf-8"
            $r = Invoke-Watched -FilePath $ytdlp -Arguments $argLine -WorkDir $out -Timeout $TRY_TIMEOUT -Stall $STALL_TIMEOUT -WatchDir $out
            $got = @(Get-ChildItem -LiteralPath $out -File -ErrorAction SilentlyContinue | Where-Object { $_.Length -gt 50000 -and $_.Name -notmatch '\.(part|ytdl)$' })
            $log = ""
            try { $log = [System.IO.File]::ReadAllText($r.OutFile) } catch { }
            [void]$script:Report.AppendLine(("----- yt-dlp, client " + $clients + " -----"))
            [void]$script:Report.AppendLine($log)
            Remove-Item -LiteralPath $r.OutFile -Force -ErrorAction SilentlyContinue

            $ok = ($r.Reason -eq "xong" -and $r.ExitCode -eq 0 -and $got.Count -gt 0)
            $why = ""
            if (-not $ok) {
                $errLine = ($log -split "`r?`n" | Where-Object { $_ -match "ERROR" } | Select-Object -Last 1)
                switch ($r.Reason) {
                    "het-gio"    { $why = "quá " + $TRY_TIMEOUT + " giây" }
                    "dung"       { $why = "đứng im " + $STALL_TIMEOUT + " giây" }
                    "khong-chay" { $why = "không chạy được yt-dlp.exe (diệt virus chặn?)" }
                    default      { $why = if ($errLine) { ($errLine -replace '^.*?ERROR:\s*', '').Trim() } else { "mã thoát " + $r.ExitCode } }
                }
                if ($why.Length -gt 100) { $why = $why.Substring(0, 100) + "…" }
            }
            [void]$results.Add([pscustomobject]@{ Name = $name; Clients = $clients; Ok = $ok; Sec = $r.Seconds; Why = $why
                                                  MB = $(if ($got.Count) { [math]::Round($got[0].Length / 1MB, 1) } else { 0 }) })
            if ($ok) { W ("     → ĐƯỢC: " + [math]::Round($got[0].Length / 1MB, 1) + " MB trong " + $r.Seconds + " giây") "Green" }
            else     { W ("     → HỎNG sau " + $r.Seconds + " giây: " + $why) "Red" }

            # Nấc đầu của app mà đã tải nhanh thì không cần thử tiếp
            if ($ok -and $clients -eq "android,android_vr" -and $r.Seconds -le 30) {
                Say-Info "Nấc đầu của app đã tải được nhanh — bỏ qua các lượt còn lại."
                break
            }
        }
        Remove-Item -LiteralPath $base -Recurse -Force -ErrorAction SilentlyContinue

        W ""
        W "   BẢNG KẾT QUẢ" "White"
        foreach ($x in $results) {
            $mark = if ($x.Ok) { "ĐƯỢC " } else { "hỏng " }
            W ("     " + $mark + $x.Name.PadRight(28) + (" " + $x.Sec + "s").PadLeft(6) + $(if ($x.Ok) { "  " + $x.MB + " MB" } else { "  " + $x.Why })) $(if ($x.Ok) { "Green" } else { "Gray" })
        }
    }

    $first  = $results | Where-Object { $_.Clients -eq "android,android_vr" } | Select-Object -First 1
    $hotfix = $results | Where-Object { $_.Clients -eq ($HOTFIX_CLIENTS -join ",") } | Select-Object -First 1
    if ($results.Count -gt 0) {
        $downloadOk = [bool]($results | Where-Object { $_.Ok })
    }

    # ── 3c. Kết luận + vá nhanh ──
    W ""
    if ($results.Count -eq 0) {
        # không làm gì — đã báo lỗi ở trên
    } elseif ($forceV4 -and $downloadOk) {
        W "   KẾT LUẬN: ép IPv4 thì TẢI ĐƯỢC → thủ phạm là IPv6 hỏng trên mạng này." "Yellow"
        Say-Need "Cho Windows ưu tiên IPv4: chạy lại script và chọn C ở câu hỏi ưu tiên IPv4 (hoặc tắt IPv6 trên modem)."
    } elseif ($first -and $first.Ok -and $first.Sec -le 30) {
        W ("   KẾT LUẬN: nấc đầu của app tải được nhanh — khâu tải trên máy này ĐANG ỔN" + $(if ($preferV4Applied) { " (sau khi ưu tiên IPv4)" } else { "" }) + ".") "Green"
        Say-Info "Nếu app vẫn báo dò lâu: lỗi chập chờn theo phiên của YouTube, hoặc nằm ở khâu phân tích (chạy kiem_tra_tone.bat)."
    } elseif ($hotfix -and $hotfix.Ok) {
        W ("   KẾT LUẬN: nấc đầu của app " + $(if ($first -and $first.Ok) { "chậm (" + $first.Sec + "s)" } else { "HỎNG" }) + ", nhưng BẢN VÁ NHANH tải được (" + $hotfix.Sec + "s).") "Yellow"
        if (-not $AppRoot) {
            Say-Info "(Chế độ dev: không ép app_config.json — thang client đã sửa trong core/ytdlp_support.py.)"
        } elseif (Ask "Áp bản vá nhanh vào app_config.json (ép client web_embedded, android, android_vr)?") {
            if (Set-ClientHotfix) {
                Say-Need "TẮT HẲN rồi mở lại app để bản vá có hiệu lực khi dò tone."
            }
        }
    } elseif ($downloadOk) {
        $best = $results | Where-Object { $_.Ok } | Sort-Object Sec | Select-Object -First 1
        W ("   KẾT LUẬN: chỉ client """ + $best.Name + """ tải được — gửi nhật ký cho kỹ thuật để chỉnh thang client.") "Yellow"
        Say-Need ("Gửi nhật ký cho kỹ thuật (client tải được: " + $best.Clients + ").")
    } else {
        W "   KẾT LUẬN: KHÔNG client nào tải được." "Red"
        $videoGone = @($results | Where-Object { $_.Why -match "unavailable|Private video|removed|not available in your country|members-only|age" }).Count -eq $results.Count
        if ($videoGone) { Say-Info "Lỗi nằm ở chính VIDEO (không tồn tại, bị gỡ, riêng tư, chặn vùng hoặc giới hạn tuổi) — thử một link khác." }
        elseif (-not $netOk) { Say-Info "Nguyên nhân gần như chắc chắn là mạng (xem kiểm tra mạng ở trên)." }
        elseif ($results | Where-Object { $_.Why -match "đứng|quá" }) {
            Say-Info "Các lượt đứng im / quá giờ → đường truyền tới máy chủ video YouTube (googlevideo.com) quá chậm hoặc bị chặn."
        } else {
            Say-Info "YouTube từ chối máy/địa chỉ mạng này — thử bằng mạng khác (phát 4G từ điện thoại) để so sánh."
        }
        Say-Need "Gửi nhật ký trên Desktop cho kỹ thuật."
    }

    # ── 3d. Đúng đường tải của app — CHỈ khi bản app có "--thu-tai" ──
    # Bộ cài chỉ đặt thu_tai_youtube.bat cạnh exe ở những bản có tham số này.
    if ($AppRoot -and (Test-Path -LiteralPath (Join-Path $AppRoot "thu_tai_youtube.bat"))) {
        W ""
        W "   ▶ Thử bằng chính app (--thu-tai, tối đa 240 giây)" "White"
        $reportFile = Join-Path $DataDir "logs\thu_tai.txt"
        $before = if (Test-Path -LiteralPath $reportFile) { (Get-Item -LiteralPath $reportFile).LastWriteTime } else { [datetime]::MinValue }
        $r = Invoke-Watched -FilePath (Join-Path $AppRoot $EXE_NAME) -Arguments ("--thu-tai " + (Quote-Arg $Link)) -WorkDir $AppRoot -Timeout 240 -Stall 120
        Remove-Item -LiteralPath $r.OutFile -Force -ErrorAction SilentlyContinue
        if ((Test-Path -LiteralPath $reportFile) -and (Get-Item -LiteralPath $reportFile).LastWriteTime -gt $before) {
            $text = [System.IO.File]::ReadAllText($reportFile)
            [void]$script:Report.AppendLine("===== BÁO CÁO thu_tai.txt (app) =====")
            [void]$script:Report.AppendLine($text)
            if ($text -match "(?m)^KẾT LUẬN:[^\r\n]*") { W ("     " + $Matches[0]) $(if ($r.ExitCode -eq 0) { "Green" } else { "Yellow" }) }
        } else {
            Say-Info ("App không ghi báo cáo (" + $r.Reason + ") — bỏ qua phần này, dùng bảng kết quả ở trên.")
        }
    } elseif ($AppRoot) {
        Say-Info "(Bản app này chưa có chế độ --thu-tai — chỉ dùng bộ tải độc lập ở trên.)"
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

$final = Test-PotBinary $POT_EXE
$potReady = $final.Runs -and $final.HashOk -and (Test-Path -LiteralPath $POT_MARKER) -and -not $potDisabled
if ($potReady -and $final.Token) { W "  PO Token: SẴN SÀNG" "Green" } else { W "  PO Token: CHƯA SẴN SÀNG" "Red" }

if ($script:Failed.Count -gt 0 -or -not $potReady) { $rc = 2 }
elseif ($script:Need.Count -gt 0 -or -not $final.Token -or $downloadOk -eq $false) { $rc = 1 }
else { $rc = 0 }

if (-not $OutFile) {
    $desk = [Environment]::GetFolderPath("Desktop")
    if (-not $desk) { $desk = $env:TEMP }
    $OutFile = Join-Path $desk ("QLS_SuaPOToken_" + $env:COMPUTERNAME + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt")
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
