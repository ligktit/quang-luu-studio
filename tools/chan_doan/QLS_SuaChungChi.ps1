#Requires -Version 5.1
<#
    Quang Lưu Studio — Sửa lỗi kết nối máy chủ do thiếu chứng chỉ gốc (SSL)
    -------------------------------------------------------------------------------
    Triệu chứng: không kích hoạt được / báo "không kết nối được máy chủ", app.log ghi
        core.licensing.client | License server unreachable: <urlopen error
        [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed:
        unable to get local issuer certificate (_ssl.c:1032)>
    trong khi trình duyệt vẫn vào mạng bình thường.

    Nguyên nhân (đã gặp thật 14/10 và 24/10/2026):
      1. Kho chứng chỉ gốc của Windows thiếu ISRG Root X1/X2 (gốc Let's Encrypt của
         máy chủ). Trình duyệt tự tải gốc còn thiếu, còn Python trong app thì không.
      2. Đã có gốc rồi mà app VẪN lỗi: app mở TRƯỚC khi gốc được thêm vào kho giữ
         nguyên kho cũ tới khi tắt hẳn → phải mở lại app.
      Hiếm hơn: giờ máy sai, hoặc phần mềm diệt virus/thiết bị mạng chặn HTTPS.

    Script làm lần lượt:
      1. Kiểm giờ máy, chứng chỉ máy chủ gửi về (có bị chặn giữa đường không),
         ISRG Root X1/X2 trong kho, lỗi SSL trong app.log.
      2. Nhờ Windows tự tải gốc còn thiếu (không cần quyền admin).
      3. Vẫn thiếu thì nạp ISRG Root X1/X2 nhúng sẵn trong script (đã đối chiếu
         thumbprint). Có quyền admin → kho máy; không → kho người dùng (Windows hiện
         hộp "Security Warning", bấm YES).
      4. Tắt và mở lại app nếu app đang chạy.

    Cách dùng (khách hàng): bấm đúp SuaChungChi.bat.
    Cách dùng (kỹ thuật):
        powershell -ExecutionPolicy Bypass -File QLS_SuaChungChi.ps1
            [-Auto] [-ChiKiem] [-KhongMoLaiApp] [-Server "https://..."]
            [-AppDir "D:\QuangLuuStudio"] [-OutFile "..."] [-NoOpen]

    ⚠ $DEFAULT_SERVER, $INNO_APPID phải khớp core/config.py và bộ cài.
      Bản app có core/net_tls.py (nạp certifi, dựng context mới mỗi lần gọi) không
      còn dính lỗi này — script vẫn chạy được, chỉ để kiểm.

    Mã thoát: 0 = máy chủ xác minh được, không còn việc gì; 1 = còn việc phải làm tay
    (giờ máy, chặn HTTPS, chưa mở lại app); 2 = sửa thất bại / không có gốc ISRG.
#>
param(
    # Không hỏi C/K — làm hết, kể cả tắt/mở lại app
    [switch]$Auto,
    # Chỉ kiểm, không sửa gì
    [switch]$ChiKiem,
    # Không tắt/mở lại app
    [switch]$KhongMoLaiApp,
    # Máy chủ cần kiểm; bỏ trống → đọc license_server_url trong app_config.json, không có thì mặc định
    [string]$Server = "",
    # Thư mục cài đặt app (chỉ cần khi cài ở chỗ lạ)
    [string]$AppDir = "",
    # Nơi ghi nhật ký; bỏ trống -> Desktop
    [string]$OutFile = "",
    # Không tự mở nhật ký sau khi chạy
    [switch]$NoOpen
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# ══════════════════════════════════════════════════════════════════════════
#  Hằng số — giữ khớp với core/config.py, bộ cài .iss
# ══════════════════════════════════════════════════════════════════════════
$EXE_NAME       = "QuangLuuStudio.exe"
$PROC_NAME      = "QuangLuuStudio"
$DATA_FOLDER    = "QuangLuuStudio"
$INNO_APPID     = "{B8F3E2A1-5D6C-4E7F-9A0B-1C2D3E4F5A6B}_is1"
$DEFAULT_SERVER = "https://qlstudio.duckdns.org"
$LECH_GIO_TOI_DA_PHUT = 5

# Gốc Let's Encrypt — lấy từ certifi, thumbprint SHA-1 đối chiếu trước khi nạp.
$ISRG = @(
    @{ Ten = "ISRG Root X1"; Thumb = "CABD2A79A1076A31F21D253635CB039D4329A5E8"; Pem = @"
-----BEGIN CERTIFICATE-----
MIIFazCCA1OgAwIBAgIRAIIQz7DSQONZRGPgu2OCiwAwDQYJKoZIhvcNAQELBQAw
TzELMAkGA1UEBhMCVVMxKTAnBgNVBAoTIEludGVybmV0IFNlY3VyaXR5IFJlc2Vh
cmNoIEdyb3VwMRUwEwYDVQQDEwxJU1JHIFJvb3QgWDEwHhcNMTUwNjA0MTEwNDM4
WhcNMzUwNjA0MTEwNDM4WjBPMQswCQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJu
ZXQgU2VjdXJpdHkgUmVzZWFyY2ggR3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBY
MTCCAiIwDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAK3oJHP0FDfzm54rVygc
h77ct984kIxuPOZXoHj3dcKi/vVqbvYATyjb3miGbESTtrFj/RQSa78f0uoxmyF+
0TM8ukj13Xnfs7j/EvEhmkvBioZxaUpmZmyPfjxwv60pIgbz5MDmgK7iS4+3mX6U
A5/TR5d8mUgjU+g4rk8Kb4Mu0UlXjIB0ttov0DiNewNwIRt18jA8+o+u3dpjq+sW
T8KOEUt+zwvo/7V3LvSye0rgTBIlDHCNAymg4VMk7BPZ7hm/ELNKjD+Jo2FR3qyH
B5T0Y3HsLuJvW5iB4YlcNHlsdu87kGJ55tukmi8mxdAQ4Q7e2RCOFvu396j3x+UC
B5iPNgiV5+I3lg02dZ77DnKxHZu8A/lJBdiB3QW0KtZB6awBdpUKD9jf1b0SHzUv
KBds0pjBqAlkd25HN7rOrFleaJ1/ctaJxQZBKT5ZPt0m9STJEadao0xAH0ahmbWn
OlFuhjuefXKnEgV4We0+UXgVCwOPjdAvBbI+e0ocS3MFEvzG6uBQE3xDk3SzynTn
jh8BCNAw1FtxNrQHusEwMFxIt4I7mKZ9YIqioymCzLq9gwQbooMDQaHWBfEbwrbw
qHyGO0aoSCqI3Haadr8faqU9GY/rOPNk3sgrDQoo//fb4hVC1CLQJ13hef4Y53CI
rU7m2Ys6xt0nUW7/vGT1M0NPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNV
HRMBAf8EBTADAQH/MB0GA1UdDgQWBBR5tFnme7bl5AFzgAiIyBpY9umbbjANBgkq
hkiG9w0BAQsFAAOCAgEAVR9YqbyyqFDQDLHYGmkgJykIrGF1XIpu+ILlaS/V9lZL
ubhzEFnTIZd+50xx+7LSYK05qAvqFyFWhfFQDlnrzuBZ6brJFe+GnY+EgPbk6ZGQ
3BebYhtF8GaV0nxvwuo77x/Py9auJ/GpsMiu/X1+mvoiBOv/2X/qkSsisRcOj/KK
NFtY2PwByVS5uCbMiogziUwthDyC3+6WVwW6LLv3xLfHTjuCvjHIInNzktHCgKQ5
ORAzI4JMPJ+GslWYHb4phowim57iaztXOoJwTdwJx4nLCgdNbOhdjsnvzqvHu7Ur
TkXWStAmzOVyyghqpZXjFaH3pO3JLF+l+/+sKAIuvtd7u+Nxe5AW0wdeRlN8NwdC
jNPElpzVmbUq4JUagEiuTDkHzsxHpFKVK7q4+63SM1N95R1NbdWhscdCb+ZAJzVc
oyi3B43njTOQ5yOf+1CceWxG1bQVs5ZufpsMljq4Ui0/1lvh+wjChP4kqKOJ2qxq
4RgqsahDYVvTH9w7jXbyLeiNdd8XM2w9U/t7y0Ff/9yi0GE44Za4rF2LN9d11TPA
mRGunUHBcnWEvgJBQl9nJEiU0Zsnvgc/ubhPgXRR4Xq37Z0j4r7g1SgEEzwxA57d
emyPxgcYxn/eR44/KJ4EBs+lVDR3veyJm+kXQ99b21/+jh5Xos1AnX5iItreGCc=
-----END CERTIFICATE-----
"@ },
    @{ Ten = "ISRG Root X2"; Thumb = "BDB1B93CD5978D45C6261455F8DB95C75AD153AF"; Pem = @"
-----BEGIN CERTIFICATE-----
MIICGzCCAaGgAwIBAgIQQdKd0XLq7qeAwSxs6S+HUjAKBggqhkjOPQQDAzBPMQsw
CQYDVQQGEwJVUzEpMCcGA1UEChMgSW50ZXJuZXQgU2VjdXJpdHkgUmVzZWFyY2gg
R3JvdXAxFTATBgNVBAMTDElTUkcgUm9vdCBYMjAeFw0yMDA5MDQwMDAwMDBaFw00
MDA5MTcxNjAwMDBaME8xCzAJBgNVBAYTAlVTMSkwJwYDVQQKEyBJbnRlcm5ldCBT
ZWN1cml0eSBSZXNlYXJjaCBHcm91cDEVMBMGA1UEAxMMSVNSRyBSb290IFgyMHYw
EAYHKoZIzj0CAQYFK4EEACIDYgAEzZvVn4CDCuwJSvMWSj5cz3es3mcFDR0HttwW
+1qLFNvicWDEukWVEYmO6gbf9yoWHKS5xcUy4APgHoIYOIvXRdgKam7mAHf7AlF9
ItgKbppbd9/w+kHsOdx1ymgHDB/qo0IwQDAOBgNVHQ8BAf8EBAMCAQYwDwYDVR0T
AQH/BAUwAwEB/zAdBgNVHQ4EFgQUfEKWrt5LSDv6kviejM9ti6lyN5UwCgYIKoZI
zj0EAwMDaAAwZQIwe3lORlCEwkSHRhtFcP9Ymd70/aTSVaYgLXTWNLxBo1BfASdW
tL4ndQavEi51mI38AjEAi/V3bNTIZargCyzuFJ0nN6T5U6VR5CmD1/iQMVtCnwr1
/q4AaOeMSQ+2b1tbFfLn
-----END CERTIFICATE-----
"@ }
)

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

function Enable-Tls12 {
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    } catch { }
}

function Test-Admin {
    try {
        $id = [Security.Principal.WindowsIdentity]::GetCurrent()
        return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } catch { return $false }
}

function New-CertFromPem {
    param([string]$Pem)
    $b64 = ($Pem -replace "-----(BEGIN|END) CERTIFICATE-----", "") -replace "\s", ""
    return New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(,[Convert]::FromBase64String($b64))
}

# Gốc ISRG đang có ở đâu: trả bảng Thumb -> danh sách kho ("LocalMachine\Root", ...)
function Get-IsrgState {
    $state = @{}
    foreach ($r in $ISRG) { $state[$r.Thumb] = New-Object System.Collections.ArrayList }
    foreach ($loc in @("LocalMachine", "CurrentUser")) {
        foreach ($name in @("Root", "Disallowed")) {
            foreach ($r in $ISRG) {
                if (Test-Path -LiteralPath ("Cert:\" + $loc + "\" + $name + "\" + $r.Thumb)) {
                    [void]$state[$r.Thumb].Add($loc + "\" + $name)
                }
            }
        }
    }
    return $state
}

function Test-IsrgTrusted {
    param($State)
    foreach ($r in $ISRG) {
        $where = @($State[$r.Thumb])
        if (($where | Where-Object { $_ -like "*\Root" }) -and -not ($where | Where-Object { $_ -like "*\Disallowed" })) { return $true }
    }
    return $false
}

function Show-IsrgState {
    param($State)
    foreach ($r in $ISRG) {
        $where = @($State[$r.Thumb])
        if ($where | Where-Object { $_ -like "*\Disallowed" }) {
            Say-Bad ($r.Ten + " nằm trong kho BỊ CẤM (" + ($where -join ", ") + ")")
        } elseif ($where.Count -gt 0) {
            Say-Good ($r.Ten + " có trong " + ($where -join ", "))
        } else {
            Say-Bad ($r.Ten + " KHÔNG có trong kho gốc")
        }
    }
}

# Bắt tay TLS với máy chủ, nhận mọi chứng chỉ (chỉ để xem), dựng chuỗi bằng Windows,
# rồi gửi HEAD / để đọc giờ máy chủ. Không phụ thuộc kho gốc có đủ hay chưa.
function Get-ServerInfo {
    param([string]$Url)
    $info = @{ Ok = $false; Err = ""; Leaf = $null; Chain = @(); ChainStatus = @(); Root = $null; ServerTime = $null }
    $u = [Uri]$Url
    $port = if ($u.Port -gt 0) { $u.Port } else { 443 }
    $tcp = $null
    try {
        $tcp = New-Object Net.Sockets.TcpClient
        $ar = $tcp.BeginConnect($u.Host, $port, $null, $null)
        if (-not $ar.AsyncWaitHandle.WaitOne(10000)) { throw "quá 10 giây không kết nối được " + $u.Host + ":" + $port }
        $tcp.EndConnect($ar)
        $tcp.ReceiveTimeout = 10000; $tcp.SendTimeout = 10000
        $ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, { $true })
        $ssl.AuthenticateAsClient($u.Host)
        $leaf = New-Object Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
        $info.Leaf = $leaf
        $ch = New-Object Security.Cryptography.X509Certificates.X509Chain
        # Python không kiểm thu hồi → bỏ qua ở đây, kẻo máy không tới được CRL bị báo oan.
        $ch.ChainPolicy.RevocationMode = [Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
        [void]$ch.Build($leaf)          # Windows tự tải gốc còn thiếu (nếu được phép) ngay ở bước này
        $info.Chain = @($ch.ChainElements | ForEach-Object { $_.Certificate })
        $info.ChainStatus = @($ch.ChainStatus | ForEach-Object { [string]$_.Status })
        if ($info.Chain.Count -gt 0) { $info.Root = $info.Chain[$info.Chain.Count - 1] }
        $req = [Text.Encoding]::ASCII.GetBytes("HEAD / HTTP/1.1`r`nHost: " + $u.Host + "`r`nConnection: close`r`n`r`n")
        $ssl.Write($req); $ssl.Flush()
        $buf = New-Object byte[] 4096
        $n = $ssl.Read($buf, 0, $buf.Length)
        $head = [Text.Encoding]::ASCII.GetString($buf, 0, $n)
        $m = [regex]::Match($head, "(?im)^Date:\s*(.+?)\s*$")
        if ($m.Success) {
            $t = [DateTime]::MinValue
            if ([DateTime]::TryParse($m.Groups[1].Value, [Globalization.CultureInfo]::InvariantCulture,
                    [Globalization.DateTimeStyles]::AdjustToUniversal -bor [Globalization.DateTimeStyles]::AssumeUniversal, [ref]$t)) {
                $info.ServerTime = $t
            }
        }
        $info.Ok = $true
    } catch {
        $info.Err = $_.Exception.Message
        if ($_.Exception.InnerException) { $info.Err += " / " + $_.Exception.InnerException.Message }
    } finally {
        if ($tcp) { try { $tcp.Close() } catch { } }
    }
    return $info
}

function Read-ServerFromConfig {
    param([string[]]$Files)
    foreach ($f in $Files) {
        if (-not $f -or -not (Test-Path -LiteralPath $f)) { continue }
        try {
            $d = [System.IO.File]::ReadAllText($f).TrimStart([char]0xFEFF) | ConvertFrom-Json
            $s = [string]$d.license_server_url
            if ($s.Trim()) { return $s.Trim().TrimEnd('/') }
        } catch { }
    }
    return ""
}

# Tiến trình gốc của app (bản one-file đẻ 2 tiến trình cùng tên: lấy cái có cửa sổ/cha khác tên)
function Get-AppProcess {
    $all = @(Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue)
    if ($all.Count -eq 0) { return $null }
    $ids = $all | ForEach-Object { $_.Id }
    foreach ($p in $all) {
        $parent = $null
        try { $parent = (Get-CimInstance Win32_Process -Filter ("ProcessId=" + $p.Id) -ErrorAction Stop).ParentProcessId } catch { }
        if (-not ($ids -contains $parent)) { return $p }
    }
    return $all[0]
}

# ══════════════════════════════════════════════════════════════════════════
#  BẮT ĐẦU
# ══════════════════════════════════════════════════════════════════════════
W "QUANG LƯU STUDIO — SỬA LỖI CHỨNG CHỈ SSL (CERTIFICATE_VERIFY_FAILED)" "Cyan"
W ("Thời điểm : " + (Get-Date -Format "dd/MM/yyyy HH:mm:ss") + "   Máy: " + $env:COMPUTERNAME + "   Người dùng: " + $env:USERNAME)
W ("Windows   : " + [Environment]::OSVersion.VersionString + "   PowerShell " + $PSVersionTable.PSVersion)
$isAdmin = Test-Admin
W ("Quyền     : " + $(if ($isAdmin) { "Quản trị (admin)" } else { "Người dùng thường" }))
if ($ChiKiem) { W "Chế độ    : CHỈ KIỂM — không sửa gì" "DarkYellow" }

Enable-Tls12

# ── Tìm thư mục cài đặt ──
$AppRoot = ""
$candidates = New-Object System.Collections.ArrayList
if ($AppDir) { [void]$candidates.Add($AppDir.TrimEnd('\')) }
[void]$candidates.Add($PSScriptRoot)                      # bat/ps1 chép cạnh exe
$proc0 = Get-AppProcess
if ($proc0 -and $proc0.Path) { [void]$candidates.Add((Split-Path $proc0.Path -Parent)) }
# Bản cài Velopack (từ 1.9.0) — dò TRƯỚC Program Files: máy có thể còn cả bản Inno cũ.
[void]$candidates.Add((Join-Path $env:LOCALAPPDATA "QuangLuuStudio\current"))
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
$DataDir = Join-Path $env:APPDATA $DATA_FOLDER
$AppLog  = Join-Path $DataDir "logs\app.log"

if ($AppRoot) { W ("App       : " + $AppRoot) } else { W "App       : không tìm thấy (vẫn sửa kho chứng chỉ được)" "Yellow" }

if (-not $Server) {
    $Server = Read-ServerFromConfig @((Join-Path $DataDir "app_config.json"), $(if ($AppRoot) { Join-Path $AppRoot "app_config.json" } else { "" }))
}
if (-not $Server) { $Server = $DEFAULT_SERVER }
$Server = $Server.TrimEnd('/')
W ("Máy chủ   : " + $Server)

# ══════════════════════════════════════════════════════════════════════════
#  1. Nhật ký app
# ══════════════════════════════════════════════════════════════════════════
Section "1. Lỗi trong nhật ký app"
$lastSslErr = $null
if (Test-Path -LiteralPath $AppLog) {
    $hits = @(Select-String -LiteralPath $AppLog -Pattern "CERTIFICATE_VERIFY_FAILED" -ErrorAction SilentlyContinue)
    $blocked = @(Select-String -LiteralPath $AppLog -Pattern "WinError 10013" -ErrorAction SilentlyContinue)
    if ($hits.Count -gt 0) {
        $last = $hits[$hits.Count - 1].Line
        $m = [regex]::Match($last, "^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
        if ($m.Success) { $lastSslErr = [DateTime]::ParseExact($m.Groups[1].Value, "yyyy-MM-dd HH:mm:ss", $null) }
        Say-Bad ("app.log có " + $hits.Count + " dòng CERTIFICATE_VERIFY_FAILED, lần cuối " + $(if ($lastSslErr) { $lastSslErr.ToString("dd/MM HH:mm:ss") } else { "?" }))
        Say-Info ($last.Substring(0, [Math]::Min(180, $last.Length)))
    } else {
        Say-Good "app.log không có lỗi CERTIFICATE_VERIFY_FAILED"
    }
    if ($blocked.Count -gt 0) {
        Say-Need ("app.log có " + $blocked.Count + " dòng WinError 10013 — tường lửa/diệt virus CHẶN app ra mạng (lỗi khác, script này không sửa). Mở phần mềm diệt virus, cho phép " + $EXE_NAME + ".")
    }
} else {
    Say-Info ("Không có " + $AppLog)
}

# ══════════════════════════════════════════════════════════════════════════
#  2. Kiểm máy chủ + kho gốc
# ══════════════════════════════════════════════════════════════════════════
Section "2. Chứng chỉ máy chủ và kho gốc Windows"
$before = Get-IsrgState
Show-IsrgState $before
try {
    $policy = Get-ItemProperty "HKLM:\SOFTWARE\Policies\Microsoft\SystemCertificates\AuthRoot" -ErrorAction Stop
    if ($policy.DisableRootAutoUpdate -eq 1) {
        Say-Bad "Chính sách TẮT tự cập nhật gốc (DisableRootAutoUpdate=1) — Windows sẽ không tự tải gốc"
    }
} catch { }
$rootCount = @(Get-ChildItem Cert:\LocalMachine\Root -ErrorAction SilentlyContinue).Count
Say-Info ("Kho LocalMachine\Root có " + $rootCount + " chứng chỉ" + $(if ($rootCount -lt 40) { " (ít — Windows rút gọn/mới cài)" } else { "" }))

$srv = Get-ServerInfo $Server
$intercepted = $false
if (-not $srv.Ok) {
    Say-Bad ("Không bắt tay TLS được với máy chủ: " + $srv.Err)
    Say-Info "Kiểm mạng/DNS. Bước sửa kho gốc bên dưới vẫn làm được khi không có mạng."
} else {
    $leaf = $srv.Leaf
    Say-Info ("Chứng chỉ máy chủ: " + $leaf.Subject + "  ←  " + $leaf.Issuer)
    Say-Info ("Hiệu lực: " + $leaf.NotBefore.ToString("dd/MM/yyyy") + " → " + $leaf.NotAfter.ToString("dd/MM/yyyy"))
    if ($leaf.Issuer -notmatch "Let's Encrypt") {
        $intercepted = $true
        Say-Need ("Chứng chỉ KHÔNG do Let's Encrypt cấp mà do """ + $leaf.Issuer + """ — có phần mềm diệt virus/thiết bị mạng CHẶN HTTPS. Tắt tính năng quét HTTPS/SSL của phần mềm đó (hoặc thêm ngoại lệ " + ([Uri]$Server).Host + ").")
    } else {
        Say-Good "Chứng chỉ máy chủ đúng của Let's Encrypt (không bị chặn giữa đường)"
    }
    if ($srv.Root) { Say-Info ("Windows dựng chuỗi tới gốc: " + $srv.Root.Subject) }
    if ($srv.ServerTime) {
        $lech = ((Get-Date).ToUniversalTime() - $srv.ServerTime).TotalMinutes
        if ([Math]::Abs($lech) -gt $LECH_GIO_TOI_DA_PHUT) {
            Say-Need ("Giờ máy lệch " + [Math]::Round($lech) + " phút so với máy chủ — chỉnh ngày giờ Windows (Settings → Time → Set time automatically) rồi chạy lại.")
        } else {
            Say-Good ("Giờ máy đúng (lệch " + [Math]::Round($lech, 1) + " phút)")
        }
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  3. Sửa kho gốc
# ══════════════════════════════════════════════════════════════════════════
Section "3. Bổ sung gốc ISRG"
$state = Get-IsrgState
$changed = $false
$missingBefore = @($ISRG | Where-Object { -not (@($before[$_.Thumb]) | Where-Object { $_ -like "*\Root" }) })

if ($ChiKiem) {
    Say-Info "Bỏ qua (chế độ chỉ kiểm)."
} elseif ($missingBefore.Count -eq 0) {
    Say-Good "Đủ cả ISRG Root X1 và X2 — không cần sửa kho."
} else {
    # 3a. Để Windows tự tải (cách sạch nhất, không cần admin). Bước 2 đã dựng chuỗi một lần;
    #     thêm một yêu cầu qua SChannel cho chắc.
    if ($srv.Ok -and -not $intercepted) {
        W "   Nhờ Windows tự tải gốc còn thiếu..." "Gray"
        try { Invoke-WebRequest ($Server + "/") -UseBasicParsing -TimeoutSec 20 -Method Head | Out-Null } catch { }
        [void](Get-ServerInfo $Server)
        Start-Sleep -Seconds 2
    }
    $state = Get-IsrgState
    foreach ($r in $missingBefore) {
        if (@($state[$r.Thumb]) | Where-Object { $_ -like "*\Root" }) { Say-Ok ("Windows đã tự tải " + $r.Ten); $changed = $true }
    }

    # 3b. Vẫn chưa có gốc nào dùng được → nạp bản nhúng sẵn
    if (-not (Test-IsrgTrusted $state)) {
        $loc = if ($isAdmin) { "LocalMachine" } else { "CurrentUser" }
        if (-not $isAdmin) {
            Say-Info "Không có quyền admin → nạp vào kho của người dùng này. Windows sẽ hiện hộp"
            Say-Info """Security Warning — You are about to install a certificate..."": bấm YES."
        }
        if (Ask ("Nạp ISRG Root X1 + X2 (gốc Let's Encrypt) vào kho " + $loc + "\Root?")) {
            foreach ($r in $ISRG) {
                if (@($state[$r.Thumb]) | Where-Object { $_ -like "*\Root" }) { continue }
                try {
                    $cert = New-CertFromPem $r.Pem
                    if ($cert.Thumbprint -ne $r.Thumb) { throw ("thumbprint sai: " + $cert.Thumbprint) }
                    $store = New-Object Security.Cryptography.X509Certificates.X509Store("Root", $loc)
                    $store.Open("ReadWrite")
                    $store.Add($cert)
                    $store.Close()
                    if (Test-Path -LiteralPath ("Cert:\" + $loc + "\Root\" + $r.Thumb)) {
                        Say-Ok ("Đã nạp " + $r.Ten + " vào " + $loc + "\Root"); $changed = $true
                    } else {
                        Say-Fail ("Nạp " + $r.Ten + " không thành (có thể đã bấm NO ở hộp Security Warning)")
                    }
                } catch {
                    Say-Fail ("Nạp " + $r.Ten + " lỗi: " + $_.Exception.Message)
                }
            }
        } else {
            Say-Need "Chưa nạp gốc ISRG — app sẽ còn lỗi CERTIFICATE_VERIFY_FAILED."
        }
    }
    $state = Get-IsrgState
}
foreach ($r in $ISRG) {
    if (@($state[$r.Thumb]) | Where-Object { $_ -like "*\Disallowed" }) {
        Say-Need ($r.Ten + " đang nằm trong kho Disallowed (bị cấm) — xoá nó khỏi certmgr.msc → Untrusted Certificates.")
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  4. Mở lại app (app giữ kho cũ tới khi tắt hẳn)
# ══════════════════════════════════════════════════════════════════════════
Section "4. Mở lại app"
$app = Get-AppProcess
$restarted = $false
if (-not $app) {
    Say-Good "App không chạy — lần mở tới sẽ nạp kho chứng chỉ mới."
} else {
    $start = $null
    try { $start = $app.StartTime } catch { }
    $stale = $changed -or ($lastSslErr -and $start -and $lastSslErr -gt $start)
    Say-Info ("App đang chạy từ " + $(if ($start) { $start.ToString("dd/MM HH:mm:ss") } else { "?" }) + " (PID " + $app.Id + ")")
    if (-not $stale) {
        Say-Good "Không cần mở lại app."
    } elseif ($ChiKiem -or $KhongMoLaiApp) {
        Say-Need "TẮT HẲN rồi mở lại Quang Lưu Studio — app đang chạy chưa thấy gốc chứng chỉ mới."
    } elseif (Ask "Tắt và mở lại Quang Lưu Studio ngay? (đang hát/phát nhạc thì chọn k)") {
        $exe = $app.Path
        $stub = Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA "QuangLuuStudio") -Filter "*.exe" -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -ne "Update.exe" } | Select-Object -First 1
        if ($exe -and $exe -like "*\QuangLuuStudio\current\*" -and $stub) { $exe = $stub.FullName }   # Velopack: mở qua stub
        [void]$app.CloseMainWindow()
        $deadline = (Get-Date).AddSeconds(15)
        while ((Get-Date) -lt $deadline -and (Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue)) { Start-Sleep -Milliseconds 500 }
        if (Get-Process -Name $PROC_NAME -ErrorAction SilentlyContinue) {
            Say-Need "App chưa tắt (có thể đang hỏi lưu) — tự tắt hẳn rồi mở lại."
        } elseif ($exe) {
            Start-Process -FilePath $exe -WorkingDirectory $env:USERPROFILE
            Say-Ok "Đã tắt và mở lại app"; $restarted = $true
        } else {
            Say-Need "Đã tắt app nhưng không biết đường dẫn để mở lại — tự mở lại."
        }
    } else {
        Say-Need "TẮT HẲN rồi mở lại Quang Lưu Studio sau khi hát xong."
    }
}

# ══════════════════════════════════════════════════════════════════════════
#  TỔNG KẾT
# ══════════════════════════════════════════════════════════════════════════
Section "TỔNG KẾT"
$final = Get-ServerInfo $Server
$trusted = Test-IsrgTrusted (Get-IsrgState)
$chainOk = $final.Ok -and $final.ChainStatus.Count -eq 0 -and $final.Root -and ($ISRG | Where-Object { $_.Thumb -eq $final.Root.Thumbprint })
foreach ($m in $script:Done)   { W ("  ✔ " + $m) "Green" }
foreach ($m in $script:Need)   { W ("  ! " + $m) "Yellow" }
foreach ($m in $script:Failed) { W ("  ✘ " + $m) "Red" }
if ($script:Done.Count + $script:Need.Count + $script:Failed.Count -eq 0) { W "  Không có thay đổi nào." }
if ($trusted) { W "  Gốc ISRG trong kho: CÓ" "Green" } else { W "  Gốc ISRG trong kho: KHÔNG" "Red" }
if ($chainOk) { W ("  Xác minh máy chủ: ĐẠT (gốc " + $final.Root.Subject + ")") "Green" }
elseif ($final.Ok) { W ("  Xác minh máy chủ: CHƯA ĐẠT (" + (($final.ChainStatus) -join ", ") + ")") "Red" }
else { W ("  Xác minh máy chủ: không kết nối được (" + $final.Err + ")") "Yellow" }
if ($restarted) { W "  Thử kích hoạt / đồng bộ lại trong app vừa mở." "Cyan" }

if ($script:Failed.Count -gt 0 -or -not $trusted) { $rc = 2 }
elseif ($script:Need.Count -gt 0 -or -not $chainOk) { $rc = 1 }
else { $rc = 0 }

if (-not $OutFile) {
    $desk = [Environment]::GetFolderPath("Desktop")
    if (-not $desk) { $desk = $env:TEMP }
    $OutFile = Join-Path $desk ("QLS_SuaChungChi_" + $env:COMPUTERNAME + "_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".txt")
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
