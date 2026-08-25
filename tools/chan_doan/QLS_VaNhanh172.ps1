# ============================================================================
#  Quang Luu Studio - VA NHANH cho may DANG CAI BAN 1.7.2
#
#  Muc dich: cho khach tai duoc YouTube tro lai NGAY, khong phai cai lai app.
#
#  Vi sao can: tu 18/08/2026 YouTube da chan duong client `android` ma 1.7.2 phu
#  thuoc vao (403 Forbidden / ffmpeg sap / SABR-only). Ban 1.7.3 sua tan goc.
#  Script nay dung nhung "cua hau" ma 1.7.2 VON DA CO de dat lai duong tai:
#
#    1. yt-dlp nap ngoai      -> %APPDATA%\QuangLuuStudio\ytdlp  (co tu 1.7.1)
#    2. plugin yt-dlp mac dinh-> %APPDATA%\yt-dlp\plugins        (yt-dlp tu do)
#    3. bgutil-pot.exe tren PATH -> plugin tu tim thay
#    4. deno.exe tren PATH    -> 1.7.2 chi bat `deno`, KHONG bat quickjs
#    5. app_config.json       -> khoa youtube_player_clients
#
#  ⚠ DAY LA GIAI PHAP TAM. Doc muc "HAN CHE" trong docs/PLAN_YOUTUBE_NO_ACCOUNT.md
#    truoc khi dung hang loat. Cach dut diem van la cai ban 1.7.3.
#
#  Chay:  VaNhanh172.bat          (hoac)  powershell -File QLS_VaNhanh172.ps1
#  Go bo: VaNhanh172.bat -GoBo
# ============================================================================
[CmdletBinding()]
param(
    # Go bo moi thu script nay da dat vao may, tra lai nguyen trang
    [switch]$GoBo,
    # Khong hoi, lam thang (dung khi trien khai hang loat)
    [switch]$KhongHoi,
    # Duong dan thu muc cai dat, neu script khong tu tim ra
    [string]$AppDir = ""
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest nhanh hon nhieu

# ── Hang so ghim ────────────────────────────────────────────────────────────
# Ghim cung phien ban + SHA-256: may khach tai tu Internet nen phai biet chinh
# xac minh mong doi cai gi. Doi phien ban thi phai doi ca ma bam.
$YTDLP_VERSION = "2026.07.04"
$YTDLP_EXE_URL = "https://github.com/yt-dlp/yt-dlp/releases/download/$YTDLP_VERSION/yt-dlp.exe"

$DENO_VERSION = "v2.9.5"
$DENO_URL     = "https://github.com/denoland/deno/releases/download/$DENO_VERSION/deno-x86_64-pc-windows-msvc.zip"
$DENO_SHA     = "171efab55ac6b9881fd53ee4c20f8bf3bb1340ffc618483746909014db12216a"

$POT_VERSION  = "0.8.1"
$POT_BASE     = "https://github.com/jim60105/bgutil-ytdlp-pot-provider-rs/releases/download/v$POT_VERSION"
$POT_EXE_URL  = "$POT_BASE/bgutil-pot-windows-x86_64.exe"
$POT_EXE_SHA  = "25d6b05c79176aa792454c3d1727922ca47e56cf11cb1e866615d751819b14a0"
$POT_ZIP_URL  = "$POT_BASE/bgutil-ytdlp-pot-provider-rs.zip"
$POT_ZIP_SHA  = "99fd83b98fa93b193d6a3b69dc74410d76e7a2b889868c54d16121cac9060344"

# Client duy nhat con tai duoc khi da co PO Token (do 18/08/2026):
#   web_safari -> 3,9 giay, tai ngon; android/mac dinh -> 403 / ffmpeg sap
$PIN_CLIENTS = @("web_safari")

# Video cong khai dung de nap san script giai thu thach + kiem chung.
# Nhieu hon mot cai: video nao cung co the bi go/khoa vung bat ky luc nao, ma
# script nay se con chay tren may khach nhieu thang sau. Tranh video qua cu
# (vd "Me at the zoo" 2005) - YouTube khong cap dinh dang thuong cho chung.
$PROBE_URLS = @(
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=kJQP7kiw5Fk",
    "https://www.youtube.com/watch?v=9bZkp7q19f0"
)

# ── Duong dan ───────────────────────────────────────────────────────────────
$DATA_DIR   = Join-Path $env:APPDATA "QuangLuuStudio"
$BIN_DIR    = Join-Path $env:LOCALAPPDATA "QuangLuuStudio\bin"
$PLUGIN_DIR = Join-Path $env:APPDATA "yt-dlp\plugins\bgutil"
$YTDLP_DIR  = Join-Path $DATA_DIR "ytdlp"
$MARKER     = Join-Path $DATA_DIR "vanhanh_172.json"

$script:Done   = New-Object System.Collections.ArrayList
$script:Failed = New-Object System.Collections.ArrayList

function W    { param([string]$t = "", [string]$c = "Gray") Write-Host $t -ForegroundColor $c }
function Head { param([string]$t) W ""; W ("=" * 72) "Cyan"; W ("  " + $t) "Cyan"; W ("=" * 72) "Cyan" }
function Ok   { param([string]$m) W ("[ XONG ]      " + $m) "Green"; [void]$script:Done.Add($m) }
function Info { param([string]$m) W ("              " + $m) "DarkGray" }
function Warn { param([string]$m) W ("[ CHU Y ]     " + $m) "Yellow" }
function Fail { param([string]$m) W ("[ THAT BAI ]  " + $m) "Red"; [void]$script:Failed.Add($m) }

function Hoi {
    param([string]$q)
    if ($KhongHoi) { return $true }
    W ""
    $a = Read-Host ("   " + $q + " [C/k]")
    return ($a -eq "" -or $a -match "^[cCyY]")
}

function TaiVaKiem {
    param([string]$Url, [string]$Dich, [string]$Sha = "")
    Invoke-WebRequest -Uri $Url -OutFile $Dich -TimeoutSec 900 -UseBasicParsing
    if ($Sha) {
        $h = (Get-FileHash -LiteralPath $Dich -Algorithm SHA256).Hash.ToLower()
        if ($h -ne $Sha.ToLower()) {
            Remove-Item -LiteralPath $Dich -Force -ErrorAction SilentlyContinue
            throw "sai ma bam SHA256 (nhan $($h.Substring(0,16))...)"
        }
    }
}

# ── Goi yt-dlp.exe an toan ──────────────────────────────────────────────────
function ChayYtDlp {
    <#
      Goi yt-dlp.exe va KHONG BAO GIO nem ngoai le.

      Vi sao phai boc: $ErrorActionPreference = "Stop" bien moi dong stderr cua
      chuong trinh ngoai thanh loi ket thuc - mot canh bao vo hai cua yt-dlp
      cung du giet ca script va bo do o giua chung.
    #>
    param(
        [string]$Exe, [string]$Deno, [string]$Url,
        [string[]]$Them = @()
    )
    $doi = @(
        "--skip-download", "--no-warnings",
        "--js-runtimes", "deno:$Deno",
        "--extractor-args", ("youtube:player_client=" + ($PIN_CLIENTS -join ",")),
        "--print", "%(title)s"
    ) + $Them + @($Url)

    $cu = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $ra = & $Exe @doi 2>&1
        $ma = $LASTEXITCODE
    } catch {
        $ra = $_.Exception.Message
        $ma = 1
    } finally {
        $ErrorActionPreference = $cu
    }
    $dong = @($ra | ForEach-Object { [string]$_ } | Where-Object { $_.Trim() -ne "" })
    $cuoi = ""
    if ($dong.Count) { $cuoi = $dong[-1] }
    if ($cuoi.Length -gt 110) { $cuoi = $cuoi.Substring(0, 107) + "..." }
    return [pscustomobject]@{ Ok = ($ma -eq 0); Cuoi = $cuoi }
}

# ── Tim thu muc cai dat ─────────────────────────────────────────────────────
function TimAppDir {
    if ($AppDir -and (Test-Path (Join-Path $AppDir "QuangLuuStudio.exe"))) { return $AppDir }
    $ung = @()
    $p = Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($p -and $p.Path) { $ung += (Split-Path $p.Path -Parent) }
    $ung += (Join-Path $env:ProgramFiles "QuangLuuStudio")
    $ung += (Join-Path ${env:ProgramFiles(x86)} "QuangLuuStudio")
    $ung += (Join-Path $env:LOCALAPPDATA "Programs\QuangLuuStudio")
    foreach ($c in $ung) {
        if ($c -and (Test-Path (Join-Path $c "QuangLuuStudio.exe"))) { return $c }
    }
    return ""
}

# ── PATH nguoi dung ─────────────────────────────────────────────────────────
function ThemVaoPath {
    param([string]$Dir)
    $cur = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($null -eq $cur) { $cur = "" }
    $phan = $cur -split ";" | Where-Object { $_ -ne "" }
    if ($phan -contains $Dir) { return $false }
    [Environment]::SetEnvironmentVariable("PATH", (@($Dir) + $phan) -join ";", "User")
    $env:PATH = $Dir + ";" + $env:PATH
    return $true
}

function BoKhoiPath {
    param([string]$Dir)
    $cur = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($null -eq $cur) { return $false }
    $phan = $cur -split ";" | Where-Object { $_ -ne "" -and $_ -ne $Dir }
    [Environment]::SetEnvironmentVariable("PATH", ($phan -join ";"), "User")
    return $true
}

# ── app_config.json ─────────────────────────────────────────────────────────
function SuaAppConfig {
    param([string]$Duong, [switch]$HoanTac)
    if (-not (Test-Path -LiteralPath $Duong)) { throw "khong thay $Duong" }
    $goc = Get-Content -LiteralPath $Duong -Raw -Encoding UTF8
    $cfg = $goc | ConvertFrom-Json

    if ($HoanTac) {
        $cfg.youtube_player_clients = @()
        if ($cfg.PSObject.Properties.Name -contains "youtube_player_clients_hotfix") {
            $cfg.PSObject.Properties.Remove("youtube_player_clients_hotfix")
        }
        $cfg | Add-Member -NotePropertyName ytdlp_auto_update -NotePropertyValue $true -Force
    } else {
        # Sao luu mot lan, de con duong lui
        $bak = $Duong + ".truoc_vanhanh172.bak"
        if (-not (Test-Path -LiteralPath $bak)) { Set-Content -LiteralPath $bak -Value $goc -Encoding UTF8 }
        $cfg | Add-Member -NotePropertyName youtube_player_clients -NotePropertyValue $PIN_CLIENTS -Force
        # Co nay bao cho ban 1.7.3 tro len biet day la khoa TAM cua script va,
        # de no tu bo qua va dung lai thang client thong minh cua minh.
        $cfg | Add-Member -NotePropertyName youtube_player_clients_hotfix -NotePropertyValue $true -Force
        # Dong bang yt-dlp: script giai thu thach nap san gan chat voi so hieu
        # yt-dlp. De no tu cap nhat 24h/lan thi vai hom sau lai hong am tham.
        $cfg | Add-Member -NotePropertyName ytdlp_auto_update -NotePropertyValue $false -Force
    }
    $cfg | ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $Duong -Encoding UTF8
}

# ════════════════════════════════════════════════════════════════════════════
Head "QUANG LUU STUDIO - VA NHANH CHO BAN 1.7.2"

$app = TimAppDir
if (-not $app) {
    Fail "Khong tim thay thu muc cai dat Quang Luu Studio."
    W "   Chay lai voi: VaNhanh172.bat -AppDir ""D:\Duong\Dan""" "Yellow"
    exit 1
}
W ("   Thu muc cai dat : " + $app)
W ("   Du lieu nguoi dung: " + $DATA_DIR)

$cfgFile = Join-Path $app "app_config.json"

# ── Go bo ───────────────────────────────────────────────────────────────────
if ($GoBo) {
    Head "GO BO BAN VA"
    try { SuaAppConfig -Duong $cfgFile -HoanTac; Ok "Tra app_config.json ve mac dinh" }
    catch { Fail ("Khong sua duoc app_config.json: " + $_.Exception.Message) }
    if (Test-Path -LiteralPath $PLUGIN_DIR) {
        Remove-Item -LiteralPath $PLUGIN_DIR -Recurse -Force -ErrorAction SilentlyContinue
        Ok "Xoa plugin PO Token"
    }
    if (Test-Path -LiteralPath $BIN_DIR) {
        Remove-Item -LiteralPath $BIN_DIR -Recurse -Force -ErrorAction SilentlyContinue
        Ok "Xoa thu muc binary"
    }
    if (BoKhoiPath $BIN_DIR) { Ok "Bo thu muc binary khoi PATH nguoi dung" }
    Remove-Item -LiteralPath $MARKER -Force -ErrorAction SilentlyContinue
    W ""; W "   Da go bo. Mo lai app de co hieu luc." "Green"
    exit 0
}

# ── Kiem tra co dang chay khong ─────────────────────────────────────────────
$dangChay = Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue
if ($dangChay) {
    Warn "Quang Luu Studio dang chay - phai dong truoc khi va."
    if (Hoi "Dong app ngay bay gio?") {
        $dangChay | Stop-Process -Force
        Start-Sleep -Seconds 2
        Ok "Da dong app"
    } else {
        Fail "Nguoi dung tu choi dong app - dung lai."
        exit 1
    }
}

W ""
W "   Script se tai khoang 100 MB va dat vao may:" "White"
W "     - deno.exe        (~93 MB giai nen) : giai thu thach JavaScript"
W "     - bgutil-pot.exe  (~44 MB)          : sinh PO Token, KHONG can tai khoan"
W "     - plugin yt-dlp   (6 KB)"
W "     - yt-dlp.exe      (~17 MB, xoa sau khi dung)"
W ""
Warn "Day la giai phap TAM. Cach dut diem la cai ban 1.7.3."
if (-not (Hoi "Tiep tuc?")) { W "   Da huy." "Yellow"; exit 0 }

$tmp = Join-Path $env:TEMP ("qls_vanhanh_" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tmp -Force | Out-Null
New-Item -ItemType Directory -Path $BIN_DIR -Force | Out-Null

try {
    # ── 1. bgutil: plugin + binary ──────────────────────────────────────────
    Head "1/5  BO SINH PO TOKEN"
    $potExe = Join-Path $BIN_DIR "bgutil-pot.exe"
    if (Test-Path -LiteralPath $potExe) {
        Info "bgutil-pot.exe da co - bo qua"
    } else {
        W "   Dang tai bgutil-pot.exe (~44 MB)..."
        TaiVaKiem -Url $POT_EXE_URL -Dich (Join-Path $tmp "pot.exe") -Sha $POT_EXE_SHA
        Move-Item -LiteralPath (Join-Path $tmp "pot.exe") -Destination $potExe -Force
        Ok "bgutil-pot.exe -> $BIN_DIR"
    }

    W "   Dang tai plugin yt-dlp..."
    TaiVaKiem -Url $POT_ZIP_URL -Dich (Join-Path $tmp "pot.zip") -Sha $POT_ZIP_SHA
    $gz = Join-Path $tmp "plug"
    Expand-Archive -LiteralPath (Join-Path $tmp "pot.zip") -DestinationPath $gz -Force
    if (-not (Test-Path -LiteralPath (Join-Path $gz "yt_dlp_plugins\extractor\getpot_bgutil.py"))) {
        throw "goi plugin khong day du"
    }
    if (Test-Path -LiteralPath $PLUGIN_DIR) { Remove-Item -LiteralPath $PLUGIN_DIR -Recurse -Force }
    New-Item -ItemType Directory -Path $PLUGIN_DIR -Force | Out-Null
    Move-Item -LiteralPath (Join-Path $gz "yt_dlp_plugins") -Destination $PLUGIN_DIR -Force
    Ok "plugin -> $PLUGIN_DIR"

    # ── 2. Deno ─────────────────────────────────────────────────────────────
    Head "2/5  RUNTIME JAVASCRIPT (Deno)"
    Info "1.7.2 chi bat runtime 'deno', khong bat quickjs - nen phai la Deno."
    $denoExe = Join-Path $BIN_DIR "deno.exe"
    if (Test-Path -LiteralPath $denoExe) {
        Info "deno.exe da co - bo qua"
    } else {
        W "   Dang tai Deno $DENO_VERSION (~41 MB)..."
        TaiVaKiem -Url $DENO_URL -Dich (Join-Path $tmp "deno.zip") -Sha $DENO_SHA
        Expand-Archive -LiteralPath (Join-Path $tmp "deno.zip") -DestinationPath $BIN_DIR -Force
        if (-not (Test-Path -LiteralPath $denoExe)) { throw "giai nen xong khong thay deno.exe" }
        Ok "deno.exe -> $BIN_DIR"
    }
    if (ThemVaoPath $BIN_DIR) {
        Ok "Them $BIN_DIR vao PATH nguoi dung"
    } else {
        Info "$BIN_DIR da co trong PATH"
    }

    # ── 3. yt-dlp nap ngoai ─────────────────────────────────────────────────
    Head "3/5  YT-DLP $YTDLP_VERSION"
    W "   Dang tai yt-dlp.exe (~17 MB, dung de nap san script rồi xoa)..."
    $ytExe = Join-Path $tmp "yt-dlp.exe"
    TaiVaKiem -Url $YTDLP_EXE_URL -Dich $ytExe
    Ok "yt-dlp.exe $YTDLP_VERSION"

    # ── 4. Nap san script giai thu thach ────────────────────────────────────
    Head "4/5  NAP SAN SCRIPT GIAI THU THACH"
    Info "App 1.7.2 khong mang theo script nay, va cung khong biet tu tai."
    Info "Nap mot lan vao bo nho dem chung cua yt-dlp thi app dung lai duoc."
    $napXong = $false
    foreach ($u in $PROBE_URLS) {
        $r = ChayYtDlp -Exe $ytExe -Deno $denoExe -Url $u -Them @("--remote-components", "ejs:github")
        if ($r.Ok) {
            Ok ("Da nap san script (thu tren: " + $r.Cuoi + ")")
            $napXong = $true
            break
        }
        Info ("Video mau khong dung duoc, thu cai khac: " + $r.Cuoi)
    }
    if (-not $napXong) {
        Warn "Nap san khong tron ven - van tiep tuc, se kiem chung o buoc 5."
    }

    # ── 5. Khoa client + kiem chung ─────────────────────────────────────────
    Head "5/5  KHOA CLIENT VA KIEM CHUNG"
    SuaAppConfig -Duong $cfgFile
    Ok ("app_config.json: youtube_player_clients = " + ($PIN_CLIENTS -join ", "))
    Info "Da tat ytdlp_auto_update: script nap san gan chat voi so hieu yt-dlp,"
    Info "de no tu cap nhat thi vai hom sau se hong am tham."

    W ""
    W "   Dang kiem chung lai dung nhu app se lam (khong cookie, khong tai khoan)..."
    $daKiem = $false
    foreach ($u in $PROBE_URLS) {
        # KHONG truyen --remote-components: day chinh la canh app 1.7.2 chay
        $r = ChayYtDlp -Exe $ytExe -Deno $denoExe -Url $u
        if ($r.Ok) {
            Ok ("Tai duoc binh thuong: " + $r.Cuoi)
            $daKiem = $true
            break
        }
    }
    if (-not $daKiem) {
        Fail "Kiem chung that bai - may nay van chua tai duoc"
        Info "Chay ChanDoan.bat va gui nhat ky cho ky thuat."
    }

    # Dau vet, de biet may nao da duoc va va go bo cho dung.
    # Tu tao thu muc: may chua mo app lan nao thi DATA_DIR chua ton tai.
    New-Item -ItemType Directory -Path $DATA_DIR -Force | Out-Null
    @{
        version      = "1"
        ngay         = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        ytdlp        = $YTDLP_VERSION
        deno         = $DENO_VERSION
        bgutil       = $POT_VERSION
        clients      = $PIN_CLIENTS
        bin_dir      = $BIN_DIR
        plugin_dir   = $PLUGIN_DIR
    } | ConvertTo-Json | Set-Content -LiteralPath $MARKER -Encoding UTF8
}
catch {
    Fail ($_.Exception.Message)
}
finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# ── Tong ket ────────────────────────────────────────────────────────────────
Head "TONG KET"
foreach ($d in $script:Done) { W ("   + " + $d) "Green" }
foreach ($f in $script:Failed) { W ("   - " + $f) "Red" }
W ""
if ($script:Failed.Count -eq 0) {
    W "   XONG. Mo lai Quang Luu Studio va thu do tone mot bai." "Green"
    W ""
    Warn "Nho: day la ban va TAM."
    W "     - Da tat tu cap nhat yt-dlp de ban va khong bi ru." "Yellow"
    W "     - Khi cai ban 1.7.3, khoa client se tu duoc bo qua; chay" "Yellow"
    W "       VaNhanh172.bat -GoBo neu muon don sach hoan toan." "Yellow"
} else {
    W "   Con loi chua xu ly duoc. Gui man hinh nay cho ky thuat." "Red"
}
W ""
