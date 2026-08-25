#Requires -Version 5.1
<#
    Quang Lưu Studio — Bộ chẩn đoán máy khách (không cần Python)
    ------------------------------------------------------------
    Chạy trên máy khách hàng để tìm nguyên nhân các lỗi thường gặp:
      MIDI không ăn, không thu được tiếng, mất bản quyền, app không mở,
      cửa sổ biến mất, không tải được nhạc YouTube, Studio One sai bản mẫu...

    Cách dùng (khách hàng): bấm đúp file ChanDoan.bat
    Cách dùng (kỹ thuật):
        powershell -ExecutionPolicy Bypass -File QLS_ChanDoan.ps1 [-Zip] [-AppDir "C:\..."]

    Script chỉ ĐỌC, không sửa gì trên máy. Kết quả lưu ra file .txt trên Desktop.
#>
param(
    # Thư mục cài đặt app (chỉ cần khi cài ở chỗ lạ, script tự dò trước)
    [string]$AppDir = "",
    # Nơi ghi báo cáo; bỏ trống -> Desktop
    [string]$OutFile = "",
    # Gói báo cáo + nhật ký lỗi thành .zip để gửi cho kỹ thuật
    [switch]$Zip,
    # Bỏ qua các kiểm tra cần Internet (máy không nối mạng)
    [switch]$Offline,
    # Không tự mở file báo cáo sau khi chạy
    [switch]$NoOpen
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch { }

# ══════════════════════════════════════════════════════════════════════════
#  Hằng số — phải khớp với code app (core/config.py, core/version.py)
# ══════════════════════════════════════════════════════════════════════════
$APP_NAME          = "Quang Lưu Studio"
$EXE_NAME          = "QuangLuuStudio.exe"
$DATA_FOLDER       = "QuangLuuStudio"
$DEFAULT_SERVER    = "https://qlstudio.duckdns.org"
$GITHUB_API        = "https://api.github.com/repos/ligktit/quang-luu-studio/releases/latest"
$INNO_APPID        = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1"
$CDP_PORT          = 9222
$SCRIPT_VERSION    = "1.0"

$DATA_DIR       = Join-Path $env:APPDATA $DATA_FOLDER
$LOG_DIR        = Join-Path $DATA_DIR "logs"
$RECORDINGS_DIR = Join-Path ([Environment]::GetFolderPath('MyDocuments')) $DATA_FOLDER

# ══════════════════════════════════════════════════════════════════════════
#  Bộ khung báo cáo
# ══════════════════════════════════════════════════════════════════════════
$script:Report  = New-Object System.Text.StringBuilder
$script:Issues  = New-Object System.Collections.ArrayList
$script:Counts  = @{ "OK" = 0; "WARN" = 0; "FAIL" = 0; "INFO" = 0 }

function W {
    param([string]$Text = "", [string]$Color = "Gray")
    Write-Host $Text -ForegroundColor $Color
    [void]$script:Report.AppendLine($Text)
}

function Section {
    param([string]$Title)
    W ""
    W ("──────────────────────────────────────────────────────────────────") "DarkGray"
    W ("  " + $Title) "Cyan"
    W ("──────────────────────────────────────────────────────────────────") "DarkGray"
}

# Status: OK | WARN | FAIL | INFO
function Chk {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail = "",
        [string]$Fix = ""
    )
    $script:Counts[$Status] = $script:Counts[$Status] + 1

    switch ($Status) {
        "OK"   { $tag = "[ TỐT  ]"; $color = "Green" }
        "WARN" { $tag = "[ LƯU Ý]"; $color = "Yellow" }
        "FAIL" { $tag = "[ LỖI  ]"; $color = "Red" }
        default { $tag = "[ TIN  ]"; $color = "DarkGray" }
    }

    $line = "$tag $Name"
    if ($Detail) { $line = "$line" + ": " + $Detail }
    W $line $color

    if ($Fix) {
        W ("          → " + $Fix) "DarkYellow"
    }
    if ($Status -eq "FAIL" -or $Status -eq "WARN") {
        [void]$script:Issues.Add([pscustomobject]@{
            Status = $Status; Name = $Name; Detail = $Detail; Fix = $Fix
        })
    }
}

function Safe {
    param([string]$Name, [scriptblock]$Block)
    try { & $Block }
    catch { Chk $Name "INFO" ("không kiểm tra được (" + $_.Exception.Message + ")") }
}

function JP {
    # Join-Path an toàn: trả "" nếu gốc rỗng (VD %ProgramFiles(x86)% trên máy 32-bit)
    param([string]$Base, [string]$Child)
    if ([string]::IsNullOrWhiteSpace($Base)) { return "" }
    return (Join-Path $Base $Child)
}

function Fmt-Size {
    param([double]$Bytes)
    if ($Bytes -ge 1GB) { return ("{0:N2} GB" -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1MB) { return ("{0:N1} MB" -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1KB) { return ("{0:N0} KB" -f ($Bytes / 1KB)) }
    return ("{0:N0} B" -f $Bytes)
}

function Read-JsonFile {
    param([string]$Path)
    $res = @{ Exists = $false; Valid = $false; Data = $null; Error = ""; Size = 0; Modified = $null }
    if (-not (Test-Path -LiteralPath $Path)) { return $res }
    $res.Exists = $true
    try {
        $fi = Get-Item -LiteralPath $Path
        $res.Size = $fi.Length
        $res.Modified = $fi.LastWriteTime
        $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($raw)) { $res.Error = "file rỗng"; return $res }
        $res.Data = $raw | ConvertFrom-Json
        $res.Valid = $true
    } catch {
        $res.Error = $_.Exception.Message
    }
    return $res
}

function Prop {
    # Đọc thuộc tính của object JSON một cách an toàn (kể cả tên có dấu/khoảng trắng)
    param($Object, [string]$Name, $Default = $null)
    if ($null -eq $Object) { return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $Default }
    if ($null -eq $p.Value) { return $Default }
    return $p.Value
}

# ══════════════════════════════════════════════════════════════════════════
#  Mở đầu
# ══════════════════════════════════════════════════════════════════════════
Clear-Host
W ""
W "══════════════════════════════════════════════════════════════════" "Cyan"
W ("   $APP_NAME — CHẨN ĐOÁN MÁY (bản script " + $SCRIPT_VERSION + ")") "Cyan"
W "══════════════════════════════════════════════════════════════════" "Cyan"
W ("   Thời điểm chạy : " + (Get-Date -Format "dd/MM/yyyy HH:mm:ss"))
W ("   Máy / người dùng: " + $env:COMPUTERNAME + " \ " + $env:USERNAME)
W "   Script chỉ ĐỌC thông tin, không thay đổi gì trên máy."
W ""

# ══════════════════════════════════════════════════════════════════════════
#  1. THÔNG TIN MÁY
# ══════════════════════════════════════════════════════════════════════════
Section "1. THÔNG TIN MÁY"

Safe "Hệ điều hành" {
    $os = Get-CimInstance Win32_OperatingSystem
    W ("        Windows       : " + $os.Caption + " (build " + $os.BuildNumber + ", " + $os.OSArchitecture + ")")
    W ("        Khởi động lúc : " + $os.LastBootUpTime.ToString("dd/MM/yyyy HH:mm"))
    if ($os.OSArchitecture -notlike "*64*") {
        Chk "Kiến trúc Windows" "FAIL" "Windows 32-bit" "App chỉ chạy trên Windows 64-bit. Cần cài lại Windows 64-bit."
    } else {
        Chk "Kiến trúc Windows" "OK" "64-bit"
    }
    if ([int]$os.BuildNumber -lt 17763) {
        Chk "Phiên bản Windows" "WARN" ("build " + $os.BuildNumber + " quá cũ") "Nên cập nhật lên Windows 10 1809 trở lên."
    }
}

Safe "Cấu hình phần cứng" {
    $cs  = Get-CimInstance Win32_ComputerSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    W ("        CPU           : " + $cpu.Name.Trim() + " (" + $cpu.NumberOfCores + " nhân)")
    W ("        RAM           : " + $ramGB + " GB")
    if ($ramGB -lt 4) {
        Chk "RAM" "FAIL" ($ramGB.ToString() + " GB") "Dưới 4 GB — app sẽ treo/đơ khi dò tone. Cần nâng RAM."
    } elseif ($ramGB -lt 8) {
        Chk "RAM" "WARN" ($ramGB.ToString() + " GB") "Dưới 8 GB — nên dùng bản NHẸ (Light) và tắt bớt chương trình nền."
    } else {
        Chk "RAM" "OK" ($ramGB.ToString() + " GB")
    }

    $os = Get-CimInstance Win32_OperatingSystem
    $freeRamGB = [math]::Round($os.FreePhysicalMemory * 1KB / 1GB, 1)
    if ($freeRamGB -lt 1) {
        Chk "RAM còn trống" "WARN" ($freeRamGB.ToString() + " GB") "Máy gần hết RAM — đóng bớt Chrome/ứng dụng khác trước khi hát."
    } else {
        Chk "RAM còn trống" "OK" ($freeRamGB.ToString() + " GB")
    }
}

Safe "Dung lượng ổ đĩa" {
    foreach ($d in (Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3")) {
        $freeGB = [math]::Round($d.FreeSpace / 1GB, 1)
        W ("        Ổ " + $d.DeviceID + "         : trống " + $freeGB + " GB / " + [math]::Round($d.Size/1GB,1) + " GB")
    }
    $sys = Get-CimInstance Win32_LogicalDisk -Filter ("DeviceID='" + $env:SystemDrive + "'")
    $freeGB = [math]::Round($sys.FreeSpace / 1GB, 1)
    if ($freeGB -lt 2) {
        Chk "Ổ hệ thống" "FAIL" ("chỉ còn " + $freeGB + " GB") "Hết chỗ ghi file tạm/ghi âm → app lỗi lung tung. Dọn ổ đĩa ngay."
    } elseif ($freeGB -lt 10) {
        Chk "Ổ hệ thống" "WARN" ("còn " + $freeGB + " GB") "Nên giữ trên 10 GB trống cho file ghi âm và bản cập nhật."
    } else {
        Chk "Ổ hệ thống" "OK" ("còn " + $freeGB + " GB")
    }
}

Safe "Màn hình" {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
    $screens = [System.Windows.Forms.Screen]::AllScreens
    $script:MonitorCount = $screens.Count
    $i = 0
    foreach ($s in $screens) {
        $b = $s.Bounds
        W ("        Màn hình " + $i + "    : " + $b.Width + "x" + $b.Height + " tại (" + $b.X + "," + $b.Y + ")" + $(if ($s.Primary) { " [chính]" } else { "" }))
        $i++
    }
    $dpi = (Get-ItemProperty -Path "HKCU:\Control Panel\Desktop\WindowMetrics" -Name AppliedDPI -ErrorAction SilentlyContinue).AppliedDPI
    if ($dpi) {
        $scale = [math]::Round($dpi / 96 * 100)
        W ("        Tỉ lệ hiển thị: " + $scale + "%")
        if ($scale -gt 150) {
            Chk "Tỉ lệ hiển thị" "WARN" ($scale.ToString() + "%") "Trên 150% có thể làm chữ/nút bị cắt. Thử đặt về 100–125%."
        }
    }
}

Safe "Quyền quản trị" {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) { Chk "Đang chạy quyền Admin" "INFO" "có" }
    else { Chk "Đang chạy quyền Admin" "INFO" "không (bình thường — app không cần Admin)" }
}

Safe "Thư viện Visual C++" {
    $sys32 = Join-Path $env:SystemRoot "System32"
    $missing = @()
    foreach ($dll in @("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")) {
        if (-not (Test-Path (Join-Path $sys32 $dll))) { $missing += $dll }
    }
    if ($missing.Count -gt 0) {
        Chk "Visual C++ Runtime" "FAIL" ("thiếu " + ($missing -join ", ")) "App sẽ không mở được. Cài 'Microsoft Visual C++ 2015-2022 Redistributable (x64)'."
    } else {
        Chk "Visual C++ Runtime" "OK" "đầy đủ"
    }
}

Safe "Ngôn ngữ & giờ hệ thống" {
    $tz = (Get-TimeZone).DisplayName
    W ("        Múi giờ       : " + $tz)
    W ("        Giờ máy       : " + (Get-Date -Format "dd/MM/yyyy HH:mm:ss"))
    $ci = Get-Culture
    W ("        Định dạng vùng: " + $ci.Name + " (" + $ci.DisplayName + ")")
}

# ══════════════════════════════════════════════════════════════════════════
#  2. CÀI ĐẶT ỨNG DỤNG
# ══════════════════════════════════════════════════════════════════════════
Section "2. CÀI ĐẶT ỨNG DỤNG"

$script:AppRoot = ""
$script:ExeInfo = $null

Safe "Tìm thư mục cài đặt" {
    $candidates = New-Object System.Collections.ArrayList
    if ($AppDir) { [void]$candidates.Add($AppDir) }

    foreach ($hive in @("HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")) {
        $k = Join-Path $hive $INNO_APPID
        if (Test-Path $k) {
            $p = Get-ItemProperty -Path $k -ErrorAction SilentlyContinue
            if ($p.InstallLocation) {
                [void]$candidates.Add($p.InstallLocation.TrimEnd('\'))
                W ("        Bản ghi cài đặt: " + $p.DisplayName + " " + $p.DisplayVersion)
                $script:RegVersion = $p.DisplayVersion
            }
        }
    }
    [void]$candidates.Add((JP $env:ProgramFiles "QuangLuuStudio"))
    [void]$candidates.Add((JP ${env:ProgramFiles(x86)} "QuangLuuStudio"))
    [void]$candidates.Add((JP $env:LOCALAPPDATA "Programs\QuangLuuStudio"))

    # Nếu app đang chạy, lấy luôn đường dẫn thật của tiến trình
    $proc = Get-Process -Name ($EXE_NAME -replace '\.exe$','') -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($proc -and $proc.Path) { [void]$candidates.Insert(0, (Split-Path $proc.Path -Parent)) }

    foreach ($c in $candidates) {
        if ($c -and (Test-Path (Join-Path $c $EXE_NAME))) { $script:AppRoot = $c; break }
    }

    if (-not $script:AppRoot) {
        Chk "Thư mục cài đặt" "FAIL" "không tìm thấy $EXE_NAME" "Chưa cài app, hoặc cài ở nơi khác — chạy lại script với: -AppDir ""D:\Duong\Dan"""
    } else {
        Chk "Thư mục cài đặt" "OK" $script:AppRoot
    }
}

if ($script:AppRoot) {
    Safe "Tệp chương trình" {
        $exe = Join-Path $script:AppRoot $EXE_NAME
        $fi = Get-Item -LiteralPath $exe
        $vi = $fi.VersionInfo
        $script:ExeInfo = $fi
        # Bản build hiện tại không nhúng version resource → FileVersion rỗng.
        # Lấy tạm số bản ghi trong registry của bộ cài để còn so với bản mới nhất.
        $script:ExeVersion = $vi.FileVersion
        if ([string]::IsNullOrWhiteSpace($script:ExeVersion)) {
            $script:ExeVersion = $script:RegVersion
            W ("        Phiên bản     : " + $(if ($script:RegVersion) { $script:RegVersion + " (theo bộ cài — exe không nhúng số hiệu)" } else { "không xác định" }))
        } else {
            W ("        Phiên bản exe : " + $vi.FileVersion + "  (" + $vi.ProductVersion + ")")
        }
        W ("        Kích thước    : " + (Fmt-Size $fi.Length))
        W ("        Sửa lần cuối  : " + $fi.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))

        # Bản Nặng (Heavy, có màn hình karaoke nhúng) lớn hơn bản Nhẹ rất nhiều
        if ($fi.Length -gt 300MB) { $variant = "NẶNG (Heavy — có màn hình karaoke nhúng)" }
        else { $variant = "NHẸ (Light — dùng trình duyệt ngoài)" }
        Chk "Biến thể bản cài" "INFO" $variant

        if ($script:RegVersion -and $vi.FileVersion -and ($vi.FileVersion -notlike ($script:RegVersion + "*"))) {
            Chk "Khớp phiên bản" "WARN" ("registry ghi " + $script:RegVersion + " nhưng exe là " + $vi.FileVersion) "Bản cài bị chép đè thủ công. Gỡ rồi cài lại bằng bộ cài chuẩn."
        }

        if ($fi.Length -lt 20MB) {
            Chk "Tệp exe" "FAIL" ("chỉ " + (Fmt-Size $fi.Length)) "File exe hỏng/thiếu (có thể bị diệt virus cắt xén). Cài lại app."
        }
    }

    Safe "Tệp đi kèm bắt buộc" {
        $required = @(
            @{ Path = "app_config.json";                        Why = "cấu hình MIDI — thiếu thì app dùng mặc định" ; Hard = $false },
            @{ Path = "studio_one\QuangLuuMIDI.surface.xml";    Why = "bản mô tả điều khiển cho Studio One"          ; Hard = $true  },
            @{ Path = "studio_one\deviceinfo.xml";              Why = "bản mô tả thiết bị cho Studio One"            ; Hard = $true  },
            @{ Path = "setup_all.bat";                          Why = "script cài loopMIDI + Surface"                ; Hard = $false }
        )
        foreach ($r in $required) {
            $full = Join-Path $script:AppRoot $r.Path
            if (Test-Path -LiteralPath $full) {
                Chk ("Tệp " + $r.Path) "OK" ""
            } elseif ($r.Hard) {
                Chk ("Tệp " + $r.Path) "FAIL" "không có" ("Thiếu " + $r.Why + ". Cài lại app.")
            } else {
                Chk ("Tệp " + $r.Path) "WARN" "không có" ("Thiếu " + $r.Why + ".")
            }
        }
        foreach ($opt in @(@{P="sfx"; N="hiệu ứng âm thanh"}, @{P="models"; N="model giọng nói offline"}, @{P="tools\piper"; N="giọng đọc Piper"})) {
            $full = Join-Path $script:AppRoot $opt.P
            if (Test-Path -LiteralPath $full) {
                $n = (Get-ChildItem -LiteralPath $full -Recurse -File -ErrorAction SilentlyContinue).Count
                Chk ("Thư mục " + $opt.P) "OK" ($n.ToString() + " tệp")
            } else {
                Chk ("Thư mục " + $opt.P) "INFO" ("không có — " + $opt.N + " sẽ tắt")
            }
        }
    }

    Safe "Quyền ghi vào thư mục cài đặt" {
        $probe = Join-Path $script:AppRoot ("_qls_probe_" + [guid]::NewGuid().ToString("N") + ".tmp")
        try {
            [IO.File]::WriteAllText($probe, "x")
            Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
            Chk "Thư mục cài đặt ghi được" "INFO" "có (bình thường nếu cài ngoài Program Files)"
        } catch {
            Chk "Thư mục cài đặt ghi được" "INFO" "không — app tự lưu cấu hình vào %APPDATA% (đúng thiết kế)"
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3. CẤU HÌNH app_config.json
# ══════════════════════════════════════════════════════════════════════════
Section "3. CẤU HÌNH MIDI (app_config.json)"

$script:MidiCC = $null
$script:MidiPortName = "QuangLuuMIDI"
$script:ServerUrl = $DEFAULT_SERVER

if ($script:AppRoot) {
    $cfgPath = Join-Path $script:AppRoot "app_config.json"
    $cfg = Read-JsonFile $cfgPath

    if (-not $cfg.Exists) {
        Chk "app_config.json" "WARN" "không có" "App chạy bằng cấu hình mặc định. Nếu MIDI sai, chép lại file này từ bộ cài."
    } elseif (-not $cfg.Valid) {
        Chk "app_config.json" "FAIL" ("hỏng JSON — " + $cfg.Error) "Ai đó sửa tay hỏng cú pháp. Chép lại file từ bộ cài (hoặc xoá đi, app dùng mặc định)."
    } else {
        Chk "app_config.json" "OK" ("hợp lệ, sửa lần cuối " + $cfg.Modified.ToString("dd/MM/yyyy HH:mm"))
        $d = $cfg.Data
        $script:MidiPortName = [string](Prop $d "midi_port_name" "QuangLuuMIDI")
        $srv = [string](Prop $d "license_server_url" "")
        if ($srv) { $script:ServerUrl = $srv.TrimEnd('/') }
        W ("        Cổng MIDI     : " + $script:MidiPortName)
        W ("        Máy chủ license: " + $script:ServerUrl)
        if ($script:ServerUrl -ne $DEFAULT_SERVER) {
            Chk "Máy chủ license" "WARN" ("trỏ sang " + $script:ServerUrl) ("Khác máy chủ chuẩn (" + $DEFAULT_SERVER + "). Nếu không cố ý, xoá dòng license_server_url.")
        }

        $cc = Prop $d "midi_cc" $null
        if ($null -eq $cc) {
            Chk "Bảng MIDI CC" "WARN" "không có mục midi_cc" "App dùng bảng mặc định."
        } else {
            $script:MidiCC = $cc
            $seen = @{}
            $dups = @()
            $bad  = @()
            foreach ($p in $cc.PSObject.Properties) {
                $v = $p.Value
                if ($v -isnot [int] -and -not ($v -match '^\d+$')) { $bad += ($p.Name + "=" + $v); continue }
                $v = [int]$v
                if ($v -lt 0 -or $v -gt 127) { $bad += ($p.Name + "=" + $v); continue }
                if ($seen.ContainsKey($v)) { $dups += ("CC " + $v + " dùng cho cả '" + $seen[$v] + "' và '" + $p.Name + "'") }
                else { $seen[$v] = $p.Name }
            }
            if ($bad.Count -gt 0) {
                Chk "Giá trị CC" "FAIL" (($bad -join "; ")) "CC phải là số 0–127. Sửa lại app_config.json."
            }
            if ($dups.Count -gt 0) {
                Chk "CC trùng nhau" "FAIL" (($dups -join "; ")) "Hai nút khác nhau gửi cùng một CC → bấm nút này lại đổi thứ khác. Đặt mỗi chức năng một số CC riêng."
            }
            if ($bad.Count -eq 0 -and $dups.Count -eq 0) {
                Chk "Bảng MIDI CC" "OK" (@($cc.PSObject.Properties).Count.ToString() + " chức năng, không trùng lặp")
            }

            # Các chế độ (Dân Ca / Lofi / Remix / Đa Thể Loại) có 2 nơi khai báo — phải khớp
            $modeCfg = Prop $d "mode_config" $null
            if ($modeCfg) {
                $pairs = @{ "Dân Ca" = "mode_danca"; "Lofi" = "mode_lofi"; "Remix" = "mode_remix"; "Đa Thể Loại" = "mode_datheloai" }
                # Sửa file bằng Notepad rồi lưu sai bảng mã (ANSI) làm hỏng tên có dấu
                $names = @($modeCfg.PSObject.Properties | ForEach-Object { $_.Name })
                if (($names -notcontains "Dân Ca") -and ($names -notcontains "Đa Thể Loại")) {
                    Chk "Bảng mã app_config.json" "FAIL" ("tên chế độ bị lỗi phông: " + ($names -join ", ")) "File đã bị lưu sai bảng mã (không phải UTF-8) → các nút chế độ không hoạt động. Chép lại app_config.json từ bộ cài, khi sửa hãy lưu dạng UTF-8."
                }
                foreach ($k in $pairs.Keys) {
                    $m = Prop $modeCfg $k $null
                    if ($null -eq $m) { continue }
                    $ccMode = Prop $m "cc" $null
                    $ccFlat = Prop $cc $pairs[$k] $null
                    if ($null -ne $ccMode -and $null -ne $ccFlat -and [int]$ccMode -ne [int]$ccFlat) {
                        Chk ("Chế độ " + $k) "WARN" ("mode_config dùng CC " + $ccMode + " nhưng midi_cc." + $pairs[$k] + " là CC " + $ccFlat) "Hai nơi lệch nhau → nút chế độ có thể không ăn. Chỉnh cho bằng nhau."
                    }
                }
            }

            # scale_values và scale_midi_map là 2 nguồn cùng dữ liệu — phải khớp
            $sv = Prop $d "scale_values" $null
            $sm = Prop $d "scale_midi_map" $null
            if ($sv -and $sm) {
                $a1 = Prop $sv "major" $null; $b1 = Prop $sm "Major" $null
                $a2 = Prop $sv "minor" $null; $b2 = Prop $sm "Minor" $null
                if (($null -ne $a1 -and $null -ne $b1 -and [int]$a1 -ne [int]$b1) -or
                    ($null -ne $a2 -and $null -ne $b2 -and [int]$a2 -ne [int]$b2)) {
                    Chk "Giá trị Major/Minor" "WARN" ("scale_values (" + $a1 + "/" + $a2 + ") lệch scale_midi_map (" + $b1 + "/" + $b2 + ")") "Dò tone gửi theo scale_midi_map, nút thủ công dùng scale_values → kết quả khác nhau. Chỉnh cho bằng."
                }
            }

            # CC phụ của mute không được đụng CC chính
            $mm = Prop $d "mute_multi_cc" $null
            if ($mm) {
                $conflict = @()
                foreach ($p in $mm.PSObject.Properties) {
                    foreach ($e in @($p.Value)) {
                        if ($null -eq $e) { continue }
                        $v = Prop $e "cc" $null
                        if ($null -ne $v -and $seen.ContainsKey([int]$v)) {
                            $conflict += ("CC " + $v + " (mute phụ của " + $p.Name + ") trùng '" + $seen[[int]$v] + "'")
                        }
                    }
                }
                if ($conflict.Count -gt 0) {
                    Chk "CC mute phụ" "WARN" (($conflict -join "; ")) "Tắt tiếng một kênh sẽ vô tình đổi thông số khác. Đổi sang số CC còn trống."
                }
            }
        }
    }
} else {
    Chk "app_config.json" "INFO" "bỏ qua (chưa xác định được thư mục cài đặt)"
}

# ══════════════════════════════════════════════════════════════════════════
#  4. DỮ LIỆU NGƯỜI DÙNG (%APPDATA%)
# ══════════════════════════════════════════════════════════════════════════
Section "4. DỮ LIỆU NGƯỜI DÙNG"

W ("        Thư mục dữ liệu: " + $DATA_DIR)
W ("        Thư mục ghi âm : " + $RECORDINGS_DIR)

$script:Settings = $null

Safe "Thư mục dữ liệu" {
    if (-not (Test-Path -LiteralPath $DATA_DIR)) {
        Chk "Thư mục dữ liệu" "WARN" "chưa có" "App chưa từng chạy thành công trên tài khoản Windows này."
    } else {
        $probe = Join-Path $DATA_DIR ("_qls_probe_" + [guid]::NewGuid().ToString("N") + ".tmp")
        try {
            [IO.File]::WriteAllText($probe, "x")
            Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
            Chk "Ghi được vào thư mục dữ liệu" "OK" ""
        } catch {
            Chk "Ghi được vào thư mục dữ liệu" "FAIL" $_.Exception.Message "App không lưu được cài đặt/bản quyền. Kiểm tra quyền thư mục hoặc phần mềm diệt virus đang chặn."
        }
    }
}

Safe "Các tệp cấu hình" {
    $files = @(
        @{ N = "settings.json";                  D = "cài đặt của người dùng"     },
        @{ N = "saved_songs.json";               D = "danh sách bài hát"          },
        @{ N = "activation.json";                D = "bản quyền đã kích hoạt"     },
        @{ N = "tone_cache.json";                D = "bộ nhớ tone đã dò"          },
        @{ N = "manual_timelines.json";          D = "mốc thời gian chỉnh tay"    },
        @{ N = "ui_config.json";                 D = "bố cục nút bấm"             },
        @{ N = "playlists.json";                 D = "danh sách phát"             },
        @{ N = "accessibility_overrides.json";   D = "tuỳ chỉnh trợ năng"         },
        @{ N = "calibration_overrides.json";     D = "cân chỉnh Auto-Tune"        }
    )
    foreach ($f in $files) {
        $p = Join-Path $DATA_DIR $f.N
        $r = Read-JsonFile $p
        if (-not $r.Exists) {
            Chk ("Tệp " + $f.N) "INFO" ("chưa có — " + $f.D + " (bình thường nếu chưa dùng tới)")
        } elseif (-not $r.Valid) {
            Chk ("Tệp " + $f.N) "FAIL" ("hỏng — " + $r.Error) ("Mất " + $f.D + ", app có thể không mở được. Đổi tên file thành ." + $f.N + ".bak rồi mở lại app để tạo file mới.")
        } else {
            Chk ("Tệp " + $f.N) "OK" ((Fmt-Size $r.Size) + ", sửa " + $r.Modified.ToString("dd/MM HH:mm"))
            if ($f.N -eq "settings.json") { $script:Settings = $r.Data }
        }
    }

    # File tạm còn sót = lần ghi trước bị cắt ngang (mất điện / tắt máy đột ngột)
    if (Test-Path -LiteralPath $DATA_DIR) {
        $tmps = Get-ChildItem -LiteralPath $DATA_DIR -Filter ".tmp_*" -Force -ErrorAction SilentlyContinue
        if ($tmps -and $tmps.Count -gt 0) {
            Chk "Tệp tạm còn sót" "WARN" ($tmps.Count.ToString() + " tệp .tmp_*") "Dấu hiệu app từng bị tắt đột ngột khi đang lưu. Có thể xoá các tệp .tmp_* này."
        }
    }
}

Safe "Cài đặt quan trọng trong settings.json" {
    if ($null -eq $script:Settings) {
        Chk "settings.json" "INFO" "chưa có dữ liệu để kiểm tra"
        return
    }
    $s = $script:Settings

    # Cửa sổ lưu ở vị trí ngoài màn hình -> mở app không thấy gì
    $geom = Prop $s "window_geometry" $null
    if ($geom) {
        $x = [int](Prop $geom "x" 0); $y = [int](Prop $geom "y" 0)
        $w = [int](Prop $geom "width" 850); $h = [int](Prop $geom "height" 300)
        W ("        Vị trí cửa sổ : x=" + $x + " y=" + $y + " " + $w + "x" + $h)
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
        $vs = [System.Windows.Forms.SystemInformation]::VirtualScreen
        $visible = ($x + $w -gt $vs.Left + 50) -and ($x -lt $vs.Right - 50) -and ($y + $h -gt $vs.Top) -and ($y -lt $vs.Bottom - 50)
        if (-not $visible) {
            Chk "Vị trí cửa sổ đã lưu" "FAIL" ("nằm ngoài vùng màn hình hiện tại (" + $vs.Left + "," + $vs.Top + " → " + $vs.Right + "," + $vs.Bottom + ")") "Mở app sẽ KHÔNG thấy cửa sổ. Xoá mục ""window_geometry"" trong settings.json rồi mở lại."
        } else {
            Chk "Vị trí cửa sổ đã lưu" "OK" "nằm trong màn hình"
        }
    }

    # Chỉ số màn hình phụ dùng cho màn karaoke
    $mi = Prop $s "display_monitor_index" $null
    if ($null -ne $mi) {
        $mc = 1
        if ($script:MonitorCount) { $mc = [int]$script:MonitorCount }
        if ([int]$mi -ge $mc) {
            Chk "Màn hình hiển thị lời" "FAIL" ("đang chọn màn hình số " + $mi + " nhưng máy chỉ có " + $mc) "Màn karaoke sẽ mở ra chỗ không tồn tại. Vào Cài đặt → chọn lại màn hình."
        } else {
            Chk "Màn hình hiển thị lời" "OK" ("màn hình số " + $mi + " / " + $mc + " màn hình")
        }
    }

    # Studio One
    $sop = [string](Prop $s "studio_one_path" "")
    if ($sop) {
        if (Test-Path -LiteralPath $sop) {
            Chk "Đường dẫn Studio One" "OK" $sop
            $script:SoPath = $sop
        } else {
            Chk "Đường dẫn Studio One" "FAIL" ("không tồn tại: " + $sop) "App không mở được Studio One. Vào Cài đặt → chọn lại file .song hoặc Studio One.exe."
        }
    } else {
        Chk "Đường dẫn Studio One" "WARN" "chưa đặt" "Vào Cài đặt → chọn file bài mẫu .song (hoặc Studio One.exe) để app tự mở."
    }

    # Trình duyệt
    $bp = [string](Prop $s "browser_path" "")
    if ($bp) {
        if (Test-Path -LiteralPath $bp) { Chk "Đường dẫn trình duyệt" "OK" $bp }
        else { Chk "Đường dẫn trình duyệt" "FAIL" ("không tồn tại: " + $bp) "Không mở được YouTube. Vào Cài đặt → chọn lại Chrome/Edge." }
    }

    # Thiết bị thu — chỉ số thiết bị đổi khi cắm/rút tai nghe, míc USB
    $rl = Prop $s "record_loopback_device" $null
    $rm = Prop $s "record_mic_device" $null
    if ($null -ne $rl -or $null -ne $rm) {
        W ("        Thiết bị thu  : nhạc(loopback)=" + $rl + "  míc=" + $rm)
        Chk "Thiết bị thu đã lưu" "INFO" "app lưu theo SỐ THỨ TỰ thiết bị — cắm/rút míc hay tai nghe USB là số này đổi, phải chọn lại trong Cài đặt → Nguồn thu"
    }

    # Khoá kỹ thuật / chế độ khách
    $tl = Prop $s "tech_lock" $null
    if ($tl) {
        $enabled = [bool](Prop $tl "enabled" $false)
        $restore = [bool](Prop $tl "restore_template" $false)
        $hasPin  = [bool](Prop $tl "pin_hash" "")
        W ("        Chế độ khách  : " + $(if ($enabled) { "ĐANG BẬT" } else { "tắt" }) + ", phục hồi bản mẫu=" + $restore)
        if ($enabled -and -not $hasPin) {
            Chk "Chế độ khách" "FAIL" "đang bật nhưng không có mã PIN" "Không ai mở khoá được. Xoá mục ""tech_lock"" trong settings.json để gỡ khoá."
        } elseif ($enabled) {
            Chk "Chế độ khách" "OK" "đang bật, có PIN"
        }
        if ($restore) {
            $tpl = Join-Path $DATA_DIR "so_template\template.song"
            if (Test-Path -LiteralPath $tpl) {
                $t = Get-Item -LiteralPath $tpl
                Chk "Bản mẫu Studio One" "OK" ((Fmt-Size $t.Length) + ", chốt lúc " + $t.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))
            } else {
                Chk "Bản mẫu Studio One" "FAIL" "bật phục hồi nhưng chưa chốt bản mẫu nào" "Mỗi lần mở app sẽ KHÔNG phục hồi được gì. Vào Cài đặt → Chốt bản mẫu."
            }
        }
    }
}

Safe "Thư mục ghi âm" {
    if (-not (Test-Path -LiteralPath $RECORDINGS_DIR)) {
        Chk "Thư mục ghi âm" "INFO" "chưa có (chưa thu bản nào)"
        return
    }
    $files = Get-ChildItem -LiteralPath $RECORDINGS_DIR -File -ErrorAction SilentlyContinue
    $total = 0
    foreach ($f in $files) { $total += $f.Length }
    Chk "Thư mục ghi âm" "OK" ($files.Count.ToString() + " tệp, tổng " + (Fmt-Size $total))
    if ($total -gt 20GB) {
        Chk "Dung lượng bản ghi" "WARN" (Fmt-Size $total) "Bản ghi chiếm nhiều chỗ. Chép ra ổ ngoài rồi xoá bớt."
    }
    # File 0 byte = lần thu thất bại
    $empty = @($files | Where-Object { $_.Length -eq 0 -and $_.Extension -eq ".wav" })
    if ($empty.Count -gt 0) {
        Chk "Bản ghi rỗng" "WARN" ($empty.Count.ToString() + " tệp .wav 0 byte") "Từng thu hụt (không bắt được tiếng). Xem mục ÂM THANH bên dưới."
    }
    $probe = Join-Path $RECORDINGS_DIR ("_qls_probe_" + [guid]::NewGuid().ToString("N") + ".tmp")
    try {
        [IO.File]::WriteAllText($probe, "x")
        Remove-Item -LiteralPath $probe -Force -ErrorAction SilentlyContinue
        Chk "Ghi được vào thư mục ghi âm" "OK" ""
    } catch {
        Chk "Ghi được vào thư mục ghi âm" "FAIL" $_.Exception.Message "Không thu âm được. Thường do Windows chặn ghi vào Documents (xem mục bảo mật bên dưới)."
    }
}

Safe "Windows chặn ghi vào Documents" {
    $cfa = (Get-MpPreference -ErrorAction Stop).EnableControlledFolderAccess
    if ($cfa -eq 1) {
        Chk "Truy cập thư mục có kiểm soát" "FAIL" "đang BẬT" "Windows Defender chặn app ghi vào Documents → không lưu được bản thu. Tắt ở: Bảo mật Windows → Bảo vệ khỏi ransomware, hoặc thêm QuangLuuStudio.exe vào danh sách cho phép."
    } else {
        Chk "Truy cập thư mục có kiểm soát" "OK" "đang tắt"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  5. MIDI (loopMIDI)
# ══════════════════════════════════════════════════════════════════════════
Section "5. MIDI — cầu nối tới Studio One"

Safe "loopMIDI đã cài" {
    $paths = @(
        (JP $env:ProgramFiles "Tobias Erichsen\loopMIDI\loopMIDI.exe"),
        (JP ${env:ProgramFiles(x86)} "Tobias Erichsen\loopMIDI\loopMIDI.exe"),
        (JP $env:LOCALAPPDATA "Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe")
    )
    $found = $null
    foreach ($p in $paths) { if ($p -and (Test-Path -LiteralPath $p)) { $found = $p; break } }
    if ($found) {
        Chk "loopMIDI đã cài" "OK" $found
    } else {
        Chk "loopMIDI đã cài" "FAIL" "không tìm thấy" "Không có cổng MIDI ảo → mọi nút bấm không tác động tới Studio One. Chạy setup_all.bat trong thư mục cài đặt."
    }
}

Safe "loopMIDI đang chạy" {
    $p = Get-Process -Name "loopMIDI" -ErrorAction SilentlyContinue
    if ($p) {
        Chk "loopMIDI đang chạy" "OK" ("PID " + ($p | Select-Object -First 1).Id)
    } else {
        Chk "loopMIDI đang chạy" "FAIL" "chưa chạy" "Cổng MIDI chỉ tồn tại khi loopMIDI đang chạy. Mở loopMIDI (nên bật chế độ tự khởi động cùng Windows)."
    }
    $run = Get-ItemProperty -Path "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" -Name "loopMIDI" -ErrorAction SilentlyContinue
    if ($run) { Chk "loopMIDI tự khởi động" "OK" "đã bật" }
    else { Chk "loopMIDI tự khởi động" "WARN" "chưa bật" "Khởi động lại máy là mất MIDI. Chạy setup_all.bat để bật tự khởi động." }
}

Safe "Cấu hình cổng MIDI trong registry" {
    $k = "HKCU:\Software\Tobias Erichsen\loopMIDI\Ports"
    if (Test-Path $k) {
        $props = Get-ItemProperty -Path $k
        $names = @($props.PSObject.Properties | Where-Object { $_.Name -notlike "PS*" } | ForEach-Object { $_.Name })
        W ("        Cổng đã khai báo: " + ($names -join ", "))
        if ($names -contains $script:MidiPortName) {
            Chk ("Cổng '" + $script:MidiPortName + "' trong cấu hình") "OK" ""
        } else {
            Chk ("Cổng '" + $script:MidiPortName + "' trong cấu hình") "FAIL" "chưa khai báo" "Chạy setup_all.bat, hoặc mở loopMIDI → gõ tên cổng vào ô 'New port-name' → bấm dấu +."
        }
    } else {
        Chk "Cấu hình cổng loopMIDI" "WARN" "chưa có khoá registry" "loopMIDI chưa từng được cấu hình. Chạy setup_all.bat."
    }
}

Safe "Cổng MIDI thực tế trên máy" {
    $csharp = @'
using System;
using System.Runtime.InteropServices;
using System.Collections.Generic;
public class QlsMidiProbe {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct MIDIOUTCAPS {
        public ushort wMid; public ushort wPid; public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public ushort wTechnology; public ushort wVoices; public ushort wNotes;
        public ushort wChannelMask; public uint dwSupport;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct MIDIINCAPS {
        public ushort wMid; public ushort wPid; public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public uint dwSupport;
    }
    [DllImport("winmm.dll")] public static extern uint midiOutGetNumDevs();
    [DllImport("winmm.dll")] public static extern uint midiInGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode, EntryPoint = "midiOutGetDevCapsW")]
    public static extern uint midiOutGetDevCaps(IntPtr id, ref MIDIOUTCAPS caps, uint size);
    [DllImport("winmm.dll", CharSet = CharSet.Unicode, EntryPoint = "midiInGetDevCapsW")]
    public static extern uint midiInGetDevCaps(IntPtr id, ref MIDIINCAPS caps, uint size);

    public static string[] Outputs() {
        List<string> list = new List<string>();
        uint n = midiOutGetNumDevs();
        for (uint i = 0; i < n; i++) {
            MIDIOUTCAPS c = new MIDIOUTCAPS();
            if (midiOutGetDevCaps(new IntPtr((int)i), ref c, (uint)Marshal.SizeOf(typeof(MIDIOUTCAPS))) == 0)
                list.Add(c.szPname);
        }
        return list.ToArray();
    }
    public static string[] Inputs() {
        List<string> list = new List<string>();
        uint n = midiInGetNumDevs();
        for (uint i = 0; i < n; i++) {
            MIDIINCAPS c = new MIDIINCAPS();
            if (midiInGetDevCaps(new IntPtr((int)i), ref c, (uint)Marshal.SizeOf(typeof(MIDIINCAPS))) == 0)
                list.Add(c.szPname);
        }
        return list.ToArray();
    }
}
'@
    Add-Type -TypeDefinition $csharp -ErrorAction Stop
    $outs = [QlsMidiProbe]::Outputs()
    $ins  = [QlsMidiProbe]::Inputs()
    W ("        MIDI Out      : " + $(if ($outs.Count) { $outs -join " | " } else { "(không có)" }))
    W ("        MIDI In       : " + $(if ($ins.Count)  { $ins  -join " | " } else { "(không có)" }))

    $hasOut = @($outs | Where-Object { $_ -like ("*" + $script:MidiPortName + "*") }).Count -gt 0
    if ($hasOut) {
        Chk ("Cổng gửi MIDI '" + $script:MidiPortName + "'") "OK" "máy đang thấy cổng này"
    } else {
        Chk ("Cổng gửi MIDI '" + $script:MidiPortName + "'") "FAIL" "KHÔNG thấy trên máy" "Đây là lý do bấm nút không ăn. Mở loopMIDI và tạo cổng đúng tên, hoặc chạy setup_all.bat."
    }
    $hasIn = @($ins | Where-Object { $_ -like ("*" + $script:MidiPortName + "*") }).Count -gt 0
    if (-not $hasIn) {
        Chk ("Cổng nhận MIDI '" + $script:MidiPortName + "'") "WARN" "không thấy" "App không nhận được tín hiệu ngược từ Studio One (bàn điều khiển vật lý). Thường vẫn hát bình thường."
    } else {
        Chk ("Cổng nhận MIDI '" + $script:MidiPortName + "'") "OK" ""
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  6. STUDIO ONE
# ══════════════════════════════════════════════════════════════════════════
Section "6. STUDIO ONE"

Safe "Studio One đã cài" {
    $found = @()
    foreach ($base in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $base) { continue }
        $pres = Join-Path $base "PreSonus"
        if (Test-Path -LiteralPath $pres) {
            foreach ($d in (Get-ChildItem -LiteralPath $pres -Directory -ErrorAction SilentlyContinue)) {
                if ($d.Name -like "Studio One*") { $found += $d.FullName }
            }
        }
    }
    if ($found.Count -gt 0) {
        Chk "Studio One đã cài" "OK" (($found | ForEach-Object { Split-Path $_ -Leaf }) -join ", ")
    } else {
        Chk "Studio One đã cài" "WARN" "không tìm thấy trong Program Files" "Nếu Studio One cài ở ổ khác thì bỏ qua. Nếu chưa cài thì mọi hiệu ứng giọng sẽ không hoạt động."
    }
}

Safe "Bản mô tả điều khiển (Surface) trong Studio One" {
    $presAppData = Join-Path $env:APPDATA "PreSonus"
    if (-not (Test-Path -LiteralPath $presAppData)) {
        Chk "Cấu hình Studio One" "WARN" "chưa có %APPDATA%\PreSonus" "Studio One chưa từng chạy trên tài khoản này."
        return
    }
    $vers = @(Get-ChildItem -LiteralPath $presAppData -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Studio One*" })
    if ($vers.Count -eq 0) {
        Chk "Cấu hình Studio One" "WARN" "không thấy thư mục Studio One nào" "Mở Studio One một lần rồi chạy setup_all.bat."
        return
    }
    foreach ($v in $vers) {
        $dir = Join-Path $v.FullName "User Devices\QuangLuuMIDI"
        $surface = Join-Path $dir "QuangLuuMIDI.surface.xml"
        $devinfo = Join-Path $dir "deviceinfo.xml"
        if (-not (Test-Path -LiteralPath $surface)) {
            Chk ("Surface trong " + $v.Name) "FAIL" "chưa cài" "Studio One không nhận nút bấm từ app. Chạy setup_all.bat rồi khởi động lại Studio One."
            continue
        }
        if (-not (Test-Path -LiteralPath $devinfo)) {
            Chk ("deviceinfo.xml trong " + $v.Name) "WARN" "thiếu" "Chạy lại setup_all.bat."
        }
        Chk ("Surface trong " + $v.Name) "OK" ((Get-Item -LiteralPath $surface).LastWriteTime.ToString("dd/MM/yyyy HH:mm"))

        # So bản đang cài trong Studio One với bản đi kèm app
        if ($script:AppRoot) {
            $src = Join-Path $script:AppRoot "studio_one\QuangLuuMIDI.surface.xml"
            if (Test-Path -LiteralPath $src) {
                $h1 = (Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
                $h2 = (Get-FileHash -LiteralPath $surface -Algorithm SHA256).Hash
                if ($h1 -ne $h2) {
                    Chk ("Surface trong " + $v.Name + " có mới nhất không") "WARN" "khác bản đi kèm app" "Bản trong Studio One là bản cũ → nút mới (Bè, Tắt Ồn...) không ăn. Chạy setup_all.bat rồi mở lại Studio One."
                } else {
                    Chk ("Surface trong " + $v.Name + " có mới nhất không") "OK" "khớp bản đi kèm app"
                }
            }
        }

        # So số CC trong surface với bảng CC của app
        if ($script:MidiCC) {
            try {
                [xml]$x = Get-Content -LiteralPath $surface -Raw -Encoding UTF8
                $addr = @{}
                foreach ($n in $x.SelectNodes("//MidiMessage")) {
                    $a = $n.GetAttribute("address")
                    if ($a -match '^\d+$') { $addr[[int]$a] = $true }
                }
                $missing = @()
                foreach ($p in $script:MidiCC.PSObject.Properties) {
                    $v2 = $p.Value
                    if ($v2 -isnot [int] -and -not ($v2 -match '^\d+$')) { continue }
                    if (-not $addr.ContainsKey([int]$v2)) { $missing += ($p.Name + " (CC " + $v2 + ")") }
                }
                if ($missing.Count -gt 0) {
                    Chk ("Số CC khớp giữa app và Surface") "WARN" ("Surface thiếu: " + ($missing -join ", ")) "Các chức năng này gửi lệnh đi nhưng Studio One không có chỗ nhận → bấm không ăn. Cập nhật Surface (setup_all.bat) hoặc sửa app_config.json cho khớp."
                } else {
                    Chk ("Số CC khớp giữa app và Surface") "OK" ($addr.Count.ToString() + " điều khiển trong Surface")
                }
            } catch {
                Chk "Đọc Surface" "WARN" ("không đọc được XML: " + $_.Exception.Message) "File surface có thể hỏng — chạy setup_all.bat để chép lại."
            }
        }
    }
}

Safe "Bài mẫu .song" {
    if ($script:SoPath -and $script:SoPath.ToLower().EndsWith(".song")) {
        $f = Get-Item -LiteralPath $script:SoPath -ErrorAction SilentlyContinue
        if ($f) {
            Chk "Bài mẫu .song" "OK" ($f.Name + " — " + (Fmt-Size $f.Length) + ", sửa " + $f.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))
            if ($f.Length -lt 1KB) {
                Chk "Kích thước bài mẫu" "WARN" (Fmt-Size $f.Length) "File .song quá nhỏ, có thể hỏng. Phục hồi từ bản mẫu đã chốt."
            }
        }
        $replaced = Join-Path $DATA_DIR "so_template\replaced.song"
        if (Test-Path -LiteralPath $replaced) {
            $r = Get-Item -LiteralPath $replaced
            W ("        Bản bị chép đè gần nhất: " + $r.LastWriteTime.ToString("dd/MM/yyyy HH:mm") + " (phao cứu sinh nếu khách lỡ lưu đè)")
        }
    } elseif ($script:SoPath) {
        Chk "Bài mẫu .song" "INFO" "đang trỏ tới file .exe, không dùng bản mẫu .song"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  7. ÂM THANH & GHI ÂM
# ══════════════════════════════════════════════════════════════════════════
Section "7. ÂM THANH & GHI ÂM"

Safe "Dịch vụ âm thanh Windows" {
    foreach ($svc in @(@{N="Audiosrv"; L="Windows Audio"}, @{N="AudioEndpointBuilder"; L="Windows Audio Endpoint Builder"})) {
        $s = Get-Service -Name $svc.N -ErrorAction SilentlyContinue
        if (-not $s) { Chk ("Dịch vụ " + $svc.L) "WARN" "không có" ; continue }
        if ($s.Status -eq "Running") { Chk ("Dịch vụ " + $svc.L) "OK" "đang chạy" }
        else { Chk ("Dịch vụ " + $svc.L) "FAIL" ("đang " + $s.Status) "Không có âm thanh và không thu được. Mở services.msc → khởi động dịch vụ này." }
    }
}

Safe "Thiết bị âm thanh" {
    $render = @(); $capture = @()
    try {
        # Hướng thiết bị nằm trong InstanceId chứ KHÔNG suy ra được từ tên:
        #   SWD\MMDEVAPI\{0.0.0.00000000}.{guid}  → phát (render)
        #   SWD\MMDEVAPI\{0.0.1.00000000}.{guid}  → thu  (capture)
        # Đoán theo tên là sai: "Digital Microphone (...)" vẫn là thiết bị PHÁT.
        $eps = Get-PnpDevice -Class AudioEndpoint -ErrorAction Stop
        foreach ($e in $eps) {
            $line = "        - " + $e.FriendlyName + "  [" + $e.Status + "]"
            if ($e.InstanceId -like "*{0.0.1.00000000}*") { $capture += $line }
            elseif ($e.InstanceId -like "*{0.0.0.00000000}*") { $render += $line }
            elseif ($e.FriendlyName -match "(Micro|Mic\b|Line In|Stereo Mix|Input)") { $capture += $line }
            else { $render += $line }
        }
    } catch {
        # Dự phòng: đọc thẳng registry MMDevices
        foreach ($kind in @("Render", "Capture")) {
            $base = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\" + $kind
            if (-not (Test-Path $base)) { continue }
            foreach ($k in (Get-ChildItem -Path $base -ErrorAction SilentlyContinue)) {
                $pk = Join-Path $k.PSPath "Properties"
                $nm = (Get-ItemProperty -Path $pk -Name "{a45c254e-df1c-4efd-8020-67d146a850e0},2" -ErrorAction SilentlyContinue)."{a45c254e-df1c-4efd-8020-67d146a850e0},2"
                $st = (Get-ItemProperty -Path $k.PSPath -Name "DeviceState" -ErrorAction SilentlyContinue).DeviceState
                $stTxt = switch ($st) { 1 { "hoạt động" } 2 { "đã tắt" } 4 { "chưa cắm" } 8 { "không có" } default { "?" } }
                if ($nm) {
                    if ($kind -eq "Render") { $render += ("        - " + $nm + "  [" + $stTxt + "]") }
                    else { $capture += ("        - " + $nm + "  [" + $stTxt + "]") }
                }
            }
        }
    }
    W "        Thiết bị PHÁT (loa/tai nghe):"
    if ($render.Count) { $render | ForEach-Object { W $_ } } else { W "        (không liệt kê được)" }
    W "        Thiết bị THU (míc/line in):"
    if ($capture.Count) { $capture | ForEach-Object { W $_ } } else { W "        (không liệt kê được)" }

    if ($render.Count -eq 0) {
        Chk "Thiết bị phát" "FAIL" "không có thiết bị phát nào" "Không có loa/tai nghe → không thu được nhạc nền (WASAPI Loopback cần thiết bị phát)."
    } else {
        Chk "Thiết bị phát" "OK" ($render.Count.ToString() + " thiết bị")
    }
    if ($capture.Count -eq 0) {
        Chk "Thiết bị thu" "FAIL" "không có míc nào" "Cắm míc vào máy, hoặc bật lại thiết bị thu đang bị Disable trong Sound settings."
    } else {
        Chk "Thiết bị thu" "OK" ($capture.Count.ToString() + " thiết bị")
    }
}

Safe "Quyền dùng micro" {
    $keys = @(
        @{ P = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"; L = "tài khoản này" },
        @{ P = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"; L = "toàn máy" }
    )
    foreach ($k in $keys) {
        if (-not (Test-Path $k.P)) { continue }
        $v = (Get-ItemProperty -Path $k.P -Name "Value" -ErrorAction SilentlyContinue).Value
        if ($v -eq "Deny") {
            Chk ("Quyền micro (" + $k.L + ")") "FAIL" "đang CHẶN" "Bản thu sẽ không có tiếng hát. Vào Cài đặt Windows → Quyền riêng tư → Micro → bật 'Cho phép ứng dụng máy tính truy nhập micro'."
        } elseif ($v) {
            Chk ("Quyền micro (" + $k.L + ")") "OK" $v
        }
    }
    $desktop = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged"
    if (Test-Path $desktop) {
        $v = (Get-ItemProperty -Path $desktop -Name "Value" -ErrorAction SilentlyContinue).Value
        if ($v -eq "Deny") {
            Chk "Quyền micro cho ứng dụng máy tính" "FAIL" "đang CHẶN" "Đây chính là mục chặn app dạng .exe. Bật 'Cho phép ứng dụng máy tính truy nhập micro'."
        } elseif ($v) {
            Chk "Quyền micro cho ứng dụng máy tính" "OK" $v
        }
    }
}

Safe "Tiến trình chiếm âm thanh độc quyền" {
    $hogs = @("VoiceMeeter", "voicemeeter8x64", "Voicemeeter", "ASIO4ALL", "asio4all", "OBS", "obs64")
    $running = @()
    foreach ($h in $hogs) {
        $p = Get-Process -Name $h -ErrorAction SilentlyContinue
        if ($p) { $running += $h }
    }
    if ($running.Count -gt 0) {
        Chk "Phần mềm âm thanh khác đang chạy" "WARN" ($running -join ", ") "Các phần mềm này có thể chiếm thiết bị ở chế độ độc quyền → app không thu được. Thử tắt rồi thu lại."
    } else {
        Chk "Phần mềm âm thanh khác" "OK" "không có xung đột rõ ràng"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  8. FFMPEG, TRÌNH DUYỆT & YOUTUBE
# ══════════════════════════════════════════════════════════════════════════
Section "8. FFMPEG, TRÌNH DUYỆT & YOUTUBE"

Safe "FFmpeg" {
    # Dò đúng thứ tự như app (core/utils.find_ffmpeg)
    $ff = $null
    $cmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($cmd) { $ff = Split-Path $cmd.Source -Parent }
    if (-not $ff) {
        $c = Join-Path $env:LOCALAPPDATA "FFmpeg\ffmpeg.exe"
        if (Test-Path -LiteralPath $c) { $ff = Split-Path $c -Parent }
    }
    if (-not $ff) {
        $wg = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        if (Test-Path -LiteralPath $wg) {
            $hit = Get-ChildItem -LiteralPath $wg -Filter "ffmpeg.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($hit) { $ff = $hit.DirectoryName }
        }
    }
    if (-not $ff) {
        foreach ($c in @("C:\ffmpeg\bin", "C:\Program Files\ffmpeg\bin", "C:\tools\ffmpeg\bin")) {
            if (Test-Path (Join-Path $c "ffmpeg.exe")) { $ff = $c; break }
        }
    }
    if (-not $ff -and $script:AppRoot -and (Test-Path (Join-Path $script:AppRoot "ffmpeg.exe"))) { $ff = $script:AppRoot }

    if ($ff) {
        $ver = ""
        try { $ver = (& (Join-Path $ff "ffmpeg.exe") -version 2>&1 | Select-Object -First 1) } catch { }
        Chk "FFmpeg" "OK" ($ff + $(if ($ver) { "  —  " + $ver } else { "" }))
    } else {
        Chk "FFmpeg" "FAIL" "không tìm thấy" "Không tải/xử lý được nhạc YouTube (dò tone, chấm điểm). Chạy setup_all.bat trong thư mục cài đặt để cài FFmpeg."
    }
}

Safe "Trình duyệt & cổng điều khiển (CDP)" {
    $browsers = @(
        @{ N = "Google Chrome";  P = @((JP $env:ProgramFiles "Google\Chrome\Application\chrome.exe"), (JP ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"), (JP $env:LOCALAPPDATA "Google\Chrome\Application\chrome.exe")) },
        @{ N = "Microsoft Edge"; P = @((JP ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"), (JP $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe")) }
    )
    $any = $false
    foreach ($b in $browsers) {
        foreach ($p in $b.P) {
            if ($p -and (Test-Path -LiteralPath $p)) {
                Chk ("Trình duyệt " + $b.N) "OK" $p
                $any = $true
                break
            }
        }
    }
    if (-not $any) {
        Chk "Trình duyệt" "FAIL" "không thấy Chrome/Edge" "App cần trình duyệt để phát YouTube. Cài Google Chrome."
    }

    # Cổng 9222 — app dùng để đọc tiến độ bài hát trên trình duyệt
    $listening = $false
    try {
        $conn = Get-NetTCPConnection -LocalPort $CDP_PORT -State Listen -ErrorAction SilentlyContinue
        if ($conn) { $listening = $true }
    } catch {
        $ns = netstat -ano | Select-String (":" + $CDP_PORT + "\s")
        if ($ns) { $listening = $true }
    }
    if ($listening) {
        Chk ("Cổng điều khiển trình duyệt " + $CDP_PORT) "OK" "đang mở (trình duyệt chạy đúng chế độ)"
    } else {
        Chk ("Cổng điều khiển trình duyệt " + $CDP_PORT) "INFO" "chưa mở — bình thường nếu trình duyệt chưa được app khởi động"
    }

    # Shortcut đã gắn cờ --remote-debugging-port chưa
    $shell = New-Object -ComObject WScript.Shell
    $searchPaths = @(
        [Environment]::GetFolderPath('Desktop'),
        [Environment]::GetFolderPath('CommonDesktopDirectory'),
        (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"),
        (Join-Path $env:PROGRAMDATA "Microsoft\Windows\Start Menu\Programs")
    )
    $withFlag = 0; $withoutFlag = 0
    foreach ($sp in $searchPaths) {
        if (-not $sp -or -not (Test-Path -LiteralPath $sp)) { continue }
        foreach ($lnk in (Get-ChildItem -LiteralPath $sp -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue)) {
            try {
                $sc = $shell.CreateShortcut($lnk.FullName)
                if ($sc.TargetPath -match "(chrome|msedge|brave)\.exe$") {
                    if ($sc.Arguments -like "*remote-debugging-port*") { $withFlag++ } else { $withoutFlag++ }
                }
            } catch { }
        }
    }
    if ($withFlag -gt 0) {
        Chk "Shortcut trình duyệt có cờ điều khiển" "OK" ($withFlag.ToString() + " shortcut đã gắn cờ, " + $withoutFlag + " chưa")
    } elseif ($withoutFlag -gt 0) {
        Chk "Shortcut trình duyệt có cờ điều khiển" "WARN" "chưa shortcut nào có cờ" "Nếu khách tự mở Chrome bằng shortcut, app không đọc được tiến độ bài hát. Chạy tools\enable_cdp_flag.bat."
    }
}

Safe "yt-dlp — bộ tải nhạc YouTube" {
    # yt-dlp bị đóng băng trong .exe từ lúc build, còn YouTube đổi cơ chế phát
    # video gần như hàng tháng. Bản cũ = "Sign in to confirm you're not a bot"
    # rồi "Requested format is not available" dù cookie hoàn toàn hợp lệ.
    $ytDir = Join-Path $DATA_DIR "ytdlp"
    $dirVer = ""
    $vf = Join-Path $ytDir "yt_dlp\version.py"
    if (Test-Path -LiteralPath $vf) {
        try {
            $m = [Regex]::Match((Get-Content -LiteralPath $vf -Raw), "__version__\s*=\s*['""]([^'""]+)['""]")
            if ($m.Success) { $dirVer = $m.Groups[1].Value }
        } catch { }
    }

    # Bản app đang thực sự dùng — bản 1.7.1 trở lên ghi dòng này vào nhật ký
    $useVer = ""
    $appLogF = Join-Path $LOG_DIR "app.log"
    if (Test-Path -LiteralPath $appLogF) {
        try {
            $hit = Select-String -LiteralPath $appLogF -Pattern "yt-dlp đang dùng: *([0-9\.]+)" -ErrorAction SilentlyContinue |
                   Select-Object -Last 1
            if ($hit) { $useVer = $hit.Matches[0].Groups[1].Value }
        } catch { }
    }
    if ($dirVer) { Chk "yt-dlp bản nạp ngoài" "INFO" $dirVer }

    $shown = $useVer
    if (-not $shown) { $shown = $dirVer }
    # Vừa nạp bản mới nhưng app chưa mở lại → nhật ký vẫn ghi bản cũ.
    if ($dirVer -and $useVer) {
        $vd = $null; $vu = $null
        try { $vd = [version]($dirVer -replace '[^0-9\.]', '') } catch { }
        try { $vu = [version]($useVer -replace '[^0-9\.]', '') } catch { }
        if ($vd -and $vu -and $vd -gt $vu) {
            $shown = $dirVer
            Chk "yt-dlp" "INFO" ("đã nạp " + $dirVer + " — có hiệu lực từ lần mở app kế tiếp")
        }
    }
    if (-not $shown) {
        Chk "yt-dlp" "INFO" "không xác định được phiên bản (bản app cũ chưa ghi vào nhật ký)" "Nếu khách báo không tải được nhạc YouTube, cài bản app mới nhất."
    } else {
        # Số hiệu yt-dlp chính là ngày phát hành: 2026.07.04
        $age = $null
        $mm = [Regex]::Match($shown, "^(\d{4})\.(\d{1,2})\.(\d{1,2})")
        if ($mm.Success) {
            try {
                $rel = Get-Date -Year ([int]$mm.Groups[1].Value) -Month ([int]$mm.Groups[2].Value) -Day ([int]$mm.Groups[3].Value)
                $age = [math]::Round(((Get-Date) - $rel).TotalDays)
            } catch { }
        }
        if ($null -eq $age) {
            Chk "yt-dlp" "INFO" $shown
        } elseif ($age -gt 120) {
            Chk "yt-dlp" "FAIL" ($shown + " — đã " + $age + " ngày tuổi") "Quá cũ so với thay đổi của YouTube: gây lỗi 'Requested format is not available' / 'not a bot' dù cookie đúng. Chạy SuaLoi.bat (mục 3B) hoặc cài bản app mới nhất."
        } elseif ($age -gt 60) {
            Chk "yt-dlp" "WARN" ($shown + " — đã " + $age + " ngày tuổi") "Nên cập nhật: chạy SuaLoi.bat (mục 3B)."
        } else {
            Chk "yt-dlp" "OK" ($shown + " — " + $age + " ngày tuổi")
        }
    }
}

Safe "Tải YouTube không cần tài khoản" {
    # Ba trụ, thiếu trụ nào cũng làm khách "lúc tải được lúc không":
    #   qjs.exe    — giải "n challenge"; thiếu thì link tải bị bóp / 403
    #   bgutil-pot — sinh PO Token; thiếu thì chỉ còn client android (360p)
    #   ffmpeg     — thiếu thì chấm điểm + dò tone hỏng hoàn toàn
    if ($script:AppRoot) {
        $qjs = Join-Path $script:AppRoot "qjs.exe"
        if (Test-Path -LiteralPath $qjs) {
            Chk "Runtime JavaScript (qjs.exe)" "OK" "có sẵn cạnh app"
        } else {
            Chk "Runtime JavaScript (qjs.exe)" "WARN" "không thấy" "Thiếu runtime JS thì YouTube bóp băng thông hoặc trả 403 dù bóc được video. Cài lại bản app 1.7.3 trở lên."
        }

        $ff = Join-Path $script:AppRoot "ffmpeg\ffmpeg.exe"
        if (Test-Path -LiteralPath $ff) {
            Chk "ffmpeg đi kèm app" "OK" "có sẵn trong thư mục cài đặt"
        } else {
            Chk "ffmpeg đi kèm app" "INFO" "không có bản đi kèm — app sẽ tìm ffmpeg cài sẵn trên máy"
        }
    }

    $potExe   = Join-Path $DATA_DIR "pot\bgutil-pot.exe"
    $potPlug  = Join-Path $DATA_DIR "pot\plugins\bgutil\yt_dlp_plugins\extractor\getpot_bgutil.py"
    $potStamp = Join-Path $DATA_DIR "pot_provider.json"
    $potVer = ""
    if (Test-Path -LiteralPath $potStamp) {
        try { $potVer = (Get-Content -LiteralPath $potStamp -Raw | ConvertFrom-Json).version } catch { }
    }
    if ((Test-Path -LiteralPath $potExe) -and (Test-Path -LiteralPath $potPlug)) {
        $d = "đã cài"
        if ($potVer) { $d = "bgutil " + $potVer }
        Chk "PO Token provider" "OK" $d
    } else {
        Chk "PO Token provider" "WARN" "chưa tải về" "Thiếu nó thì chỉ tải được qua client android (tối đa 360p) và sẽ hỏng hẳn khi YouTube siết tiếp. App tự tải (~44 MB) khi có mạng; muốn tải ngay thì chạy SuaLoi.bat (mục 3C)."
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  9. MẠNG & BẢN QUYỀN
# ══════════════════════════════════════════════════════════════════════════
Section "9. MẠNG & BẢN QUYỀN"

$script:ServerOk = $false

if ($Offline) {
    Chk "Kiểm tra mạng" "INFO" "bỏ qua theo yêu cầu (-Offline)"
} else {
    Safe "Kết nối máy chủ bản quyền" {
        $url = $script:ServerUrl + "/healthz"
        $sw = [Diagnostics.Stopwatch]::StartNew()
        try {
            $resp = Invoke-WebRequest -Uri $url -TimeoutSec 12 -UseBasicParsing -ErrorAction Stop
            $sw.Stop()
            $script:ServerOk = $true
            Chk "Máy chủ bản quyền" "OK" ("phản hồi HTTP " + [int]$resp.StatusCode + " trong " + $sw.ElapsedMilliseconds + " ms")
            if ($sw.ElapsedMilliseconds -gt 4000) {
                Chk "Tốc độ mạng tới máy chủ" "WARN" ($sw.ElapsedMilliseconds.ToString() + " ms") "Mạng chậm — app có thể báo 'không kết nối được máy chủ' lúc khởi động."
            }
            # Lệch giờ máy làm chữ ký bản quyền bị coi là hết hạn
            $dateHdr = $resp.Headers["Date"]
            if ($dateHdr) {
                $serverUtc = [datetime]::Parse($dateHdr, [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AdjustToUniversal)
                $skew = [math]::Abs(((Get-Date).ToUniversalTime() - $serverUtc).TotalSeconds)
                W ("        Giờ máy chủ   : " + $serverUtc.ToString("dd/MM/yyyy HH:mm:ss") + " UTC (lệch " + [math]::Round($skew) + " giây)")
                if ($skew -gt 300) {
                    Chk "Đồng hồ máy" "FAIL" ("lệch " + [math]::Round($skew/60) + " phút so với máy chủ") "Lệch giờ làm bản quyền bị coi là hết hạn / kích hoạt thất bại. Bật 'Tự động đặt giờ' trong Cài đặt Windows → Thời gian."
                } elseif ($skew -gt 60) {
                    Chk "Đồng hồ máy" "WARN" ("lệch " + [math]::Round($skew) + " giây") "Nên bật đồng bộ giờ tự động."
                } else {
                    Chk "Đồng hồ máy" "OK" ("lệch " + [math]::Round($skew) + " giây")
                }
            }
        } catch {
            $sw.Stop()
            Chk "Máy chủ bản quyền" "FAIL" ("không kết nối được: " + $_.Exception.Message) "App sẽ chạy bằng bản quyền lưu sẵn cho tới khi hết hạn ân hạn, sau đó bị khoá. Kiểm tra mạng/DNS/tường lửa cho phép QuangLuuStudio.exe."
        }
    }

    Safe "Phân giải tên miền" {
        $host2 = ([uri]$script:ServerUrl).Host
        try {
            $ips = [Net.Dns]::GetHostAddresses($host2) | ForEach-Object { $_.IPAddressToString }
            Chk ("DNS " + $host2) "OK" ($ips -join ", ")
        } catch {
            Chk ("DNS " + $host2) "FAIL" "không phân giải được" "Máy không ra được Internet hoặc DNS bị chặn. Thử đổi DNS sang 8.8.8.8."
        }
    }

    Safe "Kết nối GitHub (kiểm tra cập nhật)" {
        try {
            $r = Invoke-WebRequest -Uri $GITHUB_API -TimeoutSec 12 -UseBasicParsing -Headers @{ "User-Agent" = "QuangLuuStudio-Diag" } -ErrorAction Stop
            $j = $r.Content | ConvertFrom-Json
            Chk "Kênh cập nhật GitHub" "OK" ("bản mới nhất công bố: " + $j.tag_name)
            if ($script:ExeVersion) {
                $latest = ($j.tag_name -replace '^v', '')
                try {
                    $vLatest = [version]$latest
                    $vNow = [version]($script:ExeVersion -replace '[^0-9\.]', '')
                    if ($vNow -lt $vLatest) {
                        Chk "Phiên bản đang dùng" "WARN" ($script:ExeVersion + " — đã có bản " + $latest) "Nên cập nhật: lỗi khách đang gặp có thể đã được vá."
                    } else {
                        Chk "Phiên bản đang dùng" "OK" ($script:ExeVersion + " (mới nhất)")
                    }
                } catch { }
            }
        } catch {
            Chk "Kênh cập nhật GitHub" "WARN" ("không truy cập được: " + $_.Exception.Message) "Chỉ ảnh hưởng tính năng tự cập nhật."
        }
    }

    Safe "Proxy hệ thống" {
        $proxy = [Net.WebRequest]::GetSystemWebProxy()
        $u = [uri]$script:ServerUrl
        $via = $proxy.GetProxy($u)
        if ($via.AbsoluteUri.TrimEnd('/') -ne $u.AbsoluteUri.TrimEnd('/')) {
            Chk "Proxy" "WARN" ("đang đi qua " + $via.AbsoluteUri) "Proxy có thể chặn kết nối tới máy chủ bản quyền."
        } else {
            Chk "Proxy" "OK" "kết nối trực tiếp"
        }
    }
}

Safe "Trạng thái bản quyền trên máy" {
    $act = Read-JsonFile (Join-Path $DATA_DIR "activation.json")
    if (-not $act.Exists) {
        Chk "Bản quyền" "WARN" "chưa kích hoạt trên máy này" "Mở app → nhập mã kích hoạt (lần đầu cần Internet)."
        return
    }
    if (-not $act.Valid) {
        Chk "Bản quyền" "FAIL" ("activation.json hỏng — " + $act.Error) "App sẽ đòi kích hoạt lại. Xoá file rồi nhập lại mã."
        return
    }
    $a = $act.Data
    $code = [string](Prop $a "license_code" "")
    $token = [string](Prop $a "license_token" "")
    if ($code) { W ("        Mã bản quyền  : " + $code) }
    $lv = Prop $a "last_verify_ts" $null
    if ($lv) {
        $t = [DateTimeOffset]::FromUnixTimeSeconds([int64]$lv).LocalDateTime
        $days = ((Get-Date) - $t).TotalDays
        W ("        Đối chiếu lần cuối: " + $t.ToString("dd/MM/yyyy HH:mm") + " (" + [math]::Round($days) + " ngày trước)")
    }

    if (-not $token) {
        Chk "Giấy phép (token)" "FAIL" "không có token" "Máy chưa từng kích hoạt online thành công. Nối mạng rồi nhập lại mã."
        return
    }

    # Giải mã phần thông tin của token (không kiểm chữ ký — chỉ để xem hạn)
    try {
        $parts = $token.Split('.')
        if ($parts.Count -lt 2) { throw "định dạng token lạ" }
        $b64 = $parts[1].Replace('-', '+').Replace('_', '/')
        switch ($b64.Length % 4) { 2 { $b64 += '==' } 3 { $b64 += '=' } 1 { throw "token hỏng" } }
        $payload = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64)) | ConvertFrom-Json

        $plan = [string](Prop $payload "plan" "standard")
        W ("        Gói dịch vụ   : " + $plan.ToUpper())

        $now = [int]((Get-Date).ToUniversalTime() - [datetime]"1970-01-01").TotalSeconds
        $exp  = [int](Prop $payload "exp" 0)     # hạn ân hạn offline
        $lexp = [int](Prop $payload "lexp" 0)    # hạn của bản quyền

        if ($lexp -gt 0) {
            $lexpT = [DateTimeOffset]::FromUnixTimeSeconds($lexp).LocalDateTime
            $daysLeft = [math]::Floor(($lexp - $now) / 86400)
            if ($lexp -lt $now) {
                Chk "Hạn bản quyền" "FAIL" ("ĐÃ HẾT HẠN ngày " + $lexpT.ToString("dd/MM/yyyy")) "Gia hạn bản quyền để dùng tiếp."
            } elseif ($daysLeft -le 7) {
                Chk "Hạn bản quyền" "WARN" ("còn " + $daysLeft + " ngày (tới " + $lexpT.ToString("dd/MM/yyyy") + ")") "Sắp hết hạn — liên hệ gia hạn."
            } else {
                Chk "Hạn bản quyền" "OK" ("còn " + $daysLeft + " ngày (tới " + $lexpT.ToString("dd/MM/yyyy") + ")")
            }
        }
        if ($exp -gt 0) {
            $expT = [DateTimeOffset]::FromUnixTimeSeconds($exp).LocalDateTime
            $hoursLeft = [math]::Floor(($exp - $now) / 3600)
            if ($exp -lt $now) {
                Chk "Hạn chạy offline" "FAIL" ("hết từ " + $expT.ToString("dd/MM/yyyy HH:mm")) "Máy phải nối mạng một lần để app đối chiếu lại, nếu không sẽ bị khoá."
            } elseif ($hoursLeft -lt 48) {
                Chk "Hạn chạy offline" "WARN" ("còn " + $hoursLeft + " giờ") "Nối mạng cho app tự gia hạn ân hạn."
            } else {
                Chk "Hạn chạy offline" "OK" ("còn " + [math]::Floor($hoursLeft/24) + " ngày (tới " + $expT.ToString("dd/MM/yyyy HH:mm") + ")")
            }
        }

        # Token buộc theo máy — đổi bo mạch/cài lại Windows là fingerprint đổi
        $fpToken = [string](Prop $payload "fp" "")
        $fpCache = [string](Prop $a "device_fingerprint" "")
        if ($fpToken -and $fpCache) {
            if ($fpToken -ne $fpCache) {
                Chk "Ràng buộc máy" "FAIL" "vân tay máy trong token khác vân tay đã lưu" "App sẽ coi như chưa kích hoạt. Kích hoạt lại (có thể cần kỹ thuật gỡ ràng buộc máy cũ trên máy chủ)."
            } else {
                Chk "Ràng buộc máy" "OK" ("vân tay " + $fpToken.Substring(0, [math]::Min(12, $fpToken.Length)) + "...")
            }
        }
    } catch {
        Chk "Giấy phép (token)" "FAIL" ("không đọc được: " + $_.Exception.Message) "Token bị sửa tay hoặc hỏng → app coi như chưa kích hoạt. Xoá activation.json rồi nhập lại mã."
    }
}

Safe "Mốc dùng thử" {
    $k = "HKCU:\Software\QuangLuuStudio"
    if (Test-Path $k) {
        $v = (Get-ItemProperty -Path $k -Name "TrialStart" -ErrorAction SilentlyContinue).TrialStart
        if ($v) {
            try {
                $t = [DateTimeOffset]::FromUnixTimeSeconds([int64][double]$v).LocalDateTime
                Chk "Mốc dùng thử" "INFO" ("bắt đầu " + $t.ToString("dd/MM/yyyy HH:mm"))
            } catch { Chk "Mốc dùng thử" "INFO" ("giá trị: " + $v) }
        }
    } else {
        Chk "Mốc dùng thử" "INFO" "chưa có (máy chưa dùng thử)"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  10. TIẾN TRÌNH & BẢO MẬT
# ══════════════════════════════════════════════════════════════════════════
Section "10. TIẾN TRÌNH ĐANG CHẠY & PHẦN MỀM BẢO MẬT"

Safe "Tiến trình liên quan" {
    $names = @(
        @{ N = "QuangLuuStudio"; L = "Quang Lưu Studio" },
        @{ N = "Studio One";     L = "Studio One"       },
        @{ N = "loopMIDI";       L = "loopMIDI"         },
        @{ N = "chrome";         L = "Chrome"           },
        @{ N = "msedge";         L = "Edge"             }
    )
    foreach ($n in $names) {
        $ps = @(Get-Process -Name $n.N -ErrorAction SilentlyContinue)
        if ($ps.Count -eq 0) { continue }
        $mem = 0
        foreach ($p in $ps) { $mem += $p.WorkingSet64 }
        W ("        " + $n.L.PadRight(18) + ": " + $ps.Count + " tiến trình, RAM " + (Fmt-Size $mem))
    }
    $qls = @(Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue)
    # App đóng gói kiểu one-file: MỖI lần mở sinh 2 tiến trình cùng tên (bộ nạp
    # + tiến trình thật). Đếm thẳng số tiến trình sẽ báo động giả "2 bản đang
    # chạy". Chỉ đếm tiến trình GỐC — tiến trình cha không cùng tên.
    $instances = $qls
    try {
        $wmi = @(Get-CimInstance Win32_Process -Filter "Name='QuangLuuStudio.exe'" -ErrorAction Stop)
        if ($wmi.Count -gt 0) {
            $pids = @{}
            foreach ($w in $wmi) { $pids[[int]$w.ProcessId] = $true }
            $roots = @($wmi | Where-Object { -not $pids.ContainsKey([int]$_.ParentProcessId) })
            $instances = @($roots | ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
            if ($qls.Count -ne $instances.Count) {
                W ("        (" + $qls.Count + " tiến trình = " + $instances.Count + " bản app — kiểu đóng gói one-file luôn sinh 2 tiến trình/bản)")
            }
        }
    } catch { }

    if ($instances.Count -gt 1) {
        Chk "Số bản app đang chạy" "FAIL" ($instances.Count.ToString() + " bản cùng lúc") "Hai bản tranh nhau cổng MIDI và file cấu hình → lỗi lung tung. Tắt bớt (Ctrl+Shift+Esc → kết thúc tác vụ)."
    } elseif ($instances.Count -eq 1) {
        $p = $instances[0]
        $ram = Fmt-Size $p.WorkingSet64
        $upt = ((Get-Date) - $p.StartTime)
        Chk "App đang chạy" "INFO" ("RAM " + $ram + ", đã chạy " + [math]::Floor($upt.TotalHours) + "h" + $upt.Minutes + "p")
        if ($p.WorkingSet64 -gt 3GB) {
            Chk "RAM app dùng" "WARN" $ram "App phình RAM — khởi động lại app sau mỗi buổi hát dài."
        }
    } else {
        Chk "App đang chạy" "INFO" "không (một số kiểm tra về MIDI/cổng sẽ ít thông tin hơn)"
    }
}

Safe "Phần mềm diệt virus" {
    $avs = Get-CimInstance -Namespace "root\SecurityCenter2" -ClassName AntiVirusProduct -ErrorAction Stop
    foreach ($av in $avs) {
        W ("        " + $av.displayName)
    }
    $third = @($avs | Where-Object { $_.displayName -notlike "*Windows Defender*" -and $_.displayName -notlike "*Microsoft Defender*" })
    if ($third.Count -gt 0) {
        Chk "Diệt virus của hãng khác" "WARN" (($third | ForEach-Object { $_.displayName }) -join ", ") "Hay chặn app dạng đóng gói (PyInstaller) và chặn ghi file. Thêm thư mục cài đặt + %APPDATA%\QuangLuuStudio vào danh sách loại trừ."
    } else {
        Chk "Diệt virus" "OK" "chỉ có Windows Defender"
    }
}

Safe "Loại trừ trong Windows Defender" {
    $pref = Get-MpPreference -ErrorAction Stop
    $paths = @($pref.ExclusionPath)
    $hasApp = $false
    foreach ($p in $paths) {
        if ($p -and $script:AppRoot -and $p.TrimEnd('\') -ieq $script:AppRoot.TrimEnd('\')) { $hasApp = $true }
    }
    if ($script:AppRoot -and -not $hasApp) {
        Chk "Loại trừ Defender cho app" "INFO" "chưa thêm — chỉ cần thêm nếu app bị chặn/khởi động chậm bất thường"
    } elseif ($hasApp) {
        Chk "Loại trừ Defender cho app" "OK" "đã thêm thư mục cài đặt"
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  11. NHẬT KÝ LỖI
# ══════════════════════════════════════════════════════════════════════════
Section "11. NHẬT KÝ LỖI CỦA APP"

W ("        Thư mục nhật ký: " + $LOG_DIR)

$script:ErrorTail = ""

Safe "Tệp nhật ký" {
    if (-not (Test-Path -LiteralPath $LOG_DIR)) {
        Chk "Nhật ký" "WARN" "chưa có thư mục logs" "App chưa từng chạy thành công, hoặc không ghi được vào %APPDATA%."
        return
    }
    foreach ($f in (Get-ChildItem -LiteralPath $LOG_DIR -File -ErrorAction SilentlyContinue | Sort-Object Name)) {
        W ("        " + $f.Name.PadRight(20) + " " + (Fmt-Size $f.Length).PadLeft(10) + "   sửa " + $f.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))
    }

    $appLog = Join-Path $LOG_DIR "app.log"
    if (Test-Path -LiteralPath $appLog) {
        $fi = Get-Item -LiteralPath $appLog
        $ageH = ((Get-Date) - $fi.LastWriteTime).TotalHours
        if ($ageH -gt 24 * 30) {
            Chk "Hoạt động gần đây" "WARN" ("nhật ký cũ " + [math]::Round($ageH / 24) + " ngày") "App lâu rồi không chạy trên máy này."
        } else {
            Chk "Hoạt động gần đây" "OK" ("lần chạy gần nhất " + $fi.LastWriteTime.ToString("dd/MM/yyyy HH:mm"))
        }
    }
}

Safe "Thống kê lỗi" {
    $errLog = Join-Path $LOG_DIR "errors.log"
    if (-not (Test-Path -LiteralPath $errLog)) {
        Chk "Tệp errors.log" "OK" "không có lỗi nào được ghi"
        return
    }
    $lines = @(Get-Content -LiteralPath $errLog -Tail 3000 -Encoding UTF8 -ErrorAction SilentlyContinue)
    if ($lines.Count -eq 0) {
        Chk "Tệp errors.log" "OK" "rỗng"
        return
    }

    $cut7  = (Get-Date).AddDays(-7)
    $cut1  = (Get-Date).AddDays(-1)
    $n7 = 0; $n1 = 0
    $groups = @{}
    foreach ($l in $lines) {
        if ($l -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|\s*(\w+)\s*\|\s*([^|]+)\|\s*(.*)$') {
            $ts = [datetime]::ParseExact($Matches[1], "yyyy-MM-dd HH:mm:ss", $null)
            $msg = $Matches[4].Trim()
            if ($ts -gt $cut7) { $n7++ }
            if ($ts -gt $cut1) { $n1++ }
            # Gom nhóm: bỏ số và đường dẫn để các lần lỗi giống nhau chụm lại
            $key = $msg -replace '\d+', '#' -replace '[A-Za-z]:\\[^\s]+', '<đường dẫn>'
            if ($key.Length -gt 110) { $key = $key.Substring(0, 110) }
            if ($groups.ContainsKey($key)) { $groups[$key] = $groups[$key] + 1 } else { $groups[$key] = 1 }
        }
    }

    if ($n1 -gt 0) {
        Chk "Lỗi trong 24 giờ qua" "FAIL" ($n1.ToString() + " lỗi") "Xem chi tiết ở cuối báo cáo và gửi file này cho kỹ thuật."
    } elseif ($n7 -gt 0) {
        Chk "Lỗi trong 7 ngày qua" "WARN" ($n7.ToString() + " lỗi") "Chưa chắc còn ảnh hưởng, nhưng nên gửi báo cáo cho kỹ thuật xem."
    } else {
        Chk "Lỗi gần đây" "OK" "không có lỗi trong 7 ngày qua"
    }

    if ($groups.Count -gt 0) {
        W ""
        W "        Các lỗi lặp nhiều nhất:"
        $top = $groups.GetEnumerator() | Sort-Object -Property Value -Descending | Select-Object -First 8
        foreach ($g in $top) {
            W ("        " + ("{0,4}" -f $g.Value) + " lần │ " + $g.Key)
        }
    }

    # Giữ lại phần đuôi để đính vào cuối báo cáo
    $script:ErrorTail = ($lines | Select-Object -Last 60) -join "`r`n"
}

Safe "Báo cáo sự cố chờ gửi" {
    $cq = Join-Path $DATA_DIR "crash_queue.json"
    $r = Read-JsonFile $cq
    if (-not $r.Exists) { return }
    if (-not $r.Valid) {
        Chk "Hàng đợi báo cáo sự cố" "WARN" ("hỏng — " + $r.Error) "Xoá file crash_queue.json."
        return
    }
    $n = @($r.Data).Count
    if ($n -gt 0) {
        Chk "Sự cố chưa gửi được về máy chủ" "WARN" ($n.ToString() + " báo cáo đang chờ") "App từng gặp sự cố nhưng không gửi được (mất mạng). Gửi file báo cáo này cho kỹ thuật."
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  12. TỔNG KẾT
# ══════════════════════════════════════════════════════════════════════════
Section "12. TỔNG KẾT"

$fails = @($script:Issues | Where-Object { $_.Status -eq "FAIL" })
$warns = @($script:Issues | Where-Object { $_.Status -eq "WARN" })

W ""
W ("        Tốt: " + $script:Counts["OK"] + "    Lưu ý: " + $script:Counts["WARN"] + "    Lỗi: " + $script:Counts["FAIL"]) "White"
W ""

if ($fails.Count -gt 0) {
    W ("  ✗ CẦN XỬ LÝ NGAY (" + $fails.Count + " mục):") "Red"
    $i = 1
    foreach ($f in $fails) {
        W ("    " + $i + ". " + $f.Name + $(if ($f.Detail) { " — " + $f.Detail } else { "" })) "Red"
        if ($f.Fix) { W ("       Cách xử lý: " + $f.Fix) "DarkYellow" }
        $i++
    }
    W ""
}

if ($warns.Count -gt 0) {
    W ("  ! NÊN KIỂM TRA THÊM (" + $warns.Count + " mục):") "Yellow"
    $i = 1
    foreach ($f in $warns) {
        W ("    " + $i + ". " + $f.Name + $(if ($f.Detail) { " — " + $f.Detail } else { "" })) "Yellow"
        if ($f.Fix) { W ("       Cách xử lý: " + $f.Fix) "DarkYellow" }
        $i++
    }
    W ""
}

if ($fails.Count -eq 0 -and $warns.Count -eq 0) {
    W "  ✓ Không phát hiện vấn đề nào. Nếu app vẫn lỗi, hãy mô tả thao tác dẫn tới lỗi" "Green"
    W "    và gửi kèm file báo cáo này cho kỹ thuật." "Green"
    W ""
}

# Đuôi nhật ký lỗi — chỉ ghi vào FILE, không in ra màn hình cho đỡ rối
if ($script:ErrorTail) {
    [void]$script:Report.AppendLine("")
    [void]$script:Report.AppendLine("──────────────────────────────────────────────────────────────────")
    [void]$script:Report.AppendLine("  PHỤ LỤC: 60 DÒNG NHẬT KÝ LỖI GẦN NHẤT (errors.log)")
    [void]$script:Report.AppendLine("──────────────────────────────────────────────────────────────────")
    [void]$script:Report.AppendLine($script:ErrorTail)
}

# ══════════════════════════════════════════════════════════════════════════
#  Ghi báo cáo
# ══════════════════════════════════════════════════════════════════════════
if (-not $OutFile) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    if (-not $desktop -or -not (Test-Path -LiteralPath $desktop)) { $desktop = $env:USERPROFILE }
    $OutFile = Join-Path $desktop ("QLS_ChanDoan_" + $env:COMPUTERNAME + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt")
}

try {
    $utf8Bom = New-Object System.Text.UTF8Encoding($true)
    [IO.File]::WriteAllText($OutFile, $script:Report.ToString(), $utf8Bom)
    W ""
    W "══════════════════════════════════════════════════════════════════" "Cyan"
    W ("  ĐÃ LƯU BÁO CÁO: " + $OutFile) "Green"
    W "  Gửi file này cho kỹ thuật để được hỗ trợ nhanh nhất." "Green"
    W "══════════════════════════════════════════════════════════════════" "Cyan"
} catch {
    Write-Host ("Không ghi được báo cáo: " + $_.Exception.Message) -ForegroundColor Red
}

if ($Zip) {
    try {
        $zipPath = [IO.Path]::ChangeExtension($OutFile, ".zip")
        $stage = Join-Path $env:TEMP ("qls_diag_" + [guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $stage -Force | Out-Null
        Copy-Item -LiteralPath $OutFile -Destination $stage -Force
        foreach ($n in @("app.log", "errors.log")) {
            $p = Join-Path $LOG_DIR $n
            if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination $stage -Force }
        }
        foreach ($n in @("settings.json", "ui_config.json", "calibration_overrides.json")) {
            $p = Join-Path $DATA_DIR $n
            if (-not (Test-Path -LiteralPath $p)) { continue }
            if ($n -eq "settings.json") {
                # Bỏ phần khoá kỹ thuật (băm PIN) trước khi gửi ra ngoài
                $r = Read-JsonFile $p
                if ($r.Valid) {
                    $clean = $r.Data | Select-Object -Property * -ExcludeProperty tech_lock
                    [IO.File]::WriteAllText((Join-Path $stage $n), ($clean | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
                    continue
                }
            }
            Copy-Item -LiteralPath $p -Destination $stage -Force
        }
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
        Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath -Force
        Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host ("  ĐÃ GÓI KÈM NHẬT KÝ: " + $zipPath) -ForegroundColor Green
        Write-Host "  (Gói gồm: báo cáo + nhật ký + cài đặt. KHÔNG có mã bản quyền, không có mã PIN.)" -ForegroundColor DarkGray
    } catch {
        Write-Host ("Không tạo được gói .zip: " + $_.Exception.Message) -ForegroundColor Yellow
    }
}

if (-not $NoOpen) {
    try { Start-Process notepad.exe -ArgumentList ('"' + $OutFile + '"') } catch { }
}

# Mã thoát: 2 = có lỗi nặng, 1 = chỉ có cảnh báo, 0 = sạch
if ($fails.Count -gt 0) { exit 2 }
elseif ($warns.Count -gt 0) { exit 1 }
else { exit 0 }
