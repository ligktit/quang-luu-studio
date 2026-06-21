# Quang Luu Studio - CDP Diagnostic
# Kiem tra vi sao den dong bo trinh duyet van do.
# Khong can Python - chay duoc tren may client.

$ErrorActionPreference = 'SilentlyContinue'

$PORT_START = 9222
$PORT_END   = 9232
$BROWSER_EXES = @('msedge.exe', 'chrome.exe', 'brave.exe')

function Write-Section($title) {
    Write-Host ""
    Write-Host "==== $title ====" -ForegroundColor Cyan
}

function Write-Pass($msg) { Write-Host "  [OK]   $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }
function Write-Info($msg) { Write-Host "         $msg" -ForegroundColor Gray }

# Ket qua tong hop
$result = [ordered]@{
    BrowserRunning      = $false
    BrowserHasFlag      = $false
    PortResponds        = $false
    YouTubeTabFound     = $false
    ShortcutHasFlag     = $false
    RespondingPort      = $null
}

Write-Host ""
Write-Host "=============================================================" -ForegroundColor White
Write-Host "  Quang Luu Studio - Chan doan dong bo trinh duyet (CDP)"   -ForegroundColor White
Write-Host "=============================================================" -ForegroundColor White

# -------------------------------------------------------------------
# 1. Process trinh duyet dang chay + co --remote-debugging-port chua
# -------------------------------------------------------------------
Write-Section "1. Process trinh duyet"
$procs = Get-CimInstance Win32_Process -Filter "Name='msedge.exe' OR Name='chrome.exe' OR Name='brave.exe'"
if (-not $procs) {
    Write-Warn "Khong co trinh duyet (Edge/Chrome/Brave) nao dang chay."
    Write-Info "Hay mo trinh duyet bang shortcut da duoc cai co, roi chay lai script nay."
} else {
    $result.BrowserRunning = $true
    $byName = $procs | Group-Object Name
    foreach ($g in $byName) {
        Write-Info "$($g.Name): $($g.Count) process"
    }
    $withFlag = $procs | Where-Object { $_.CommandLine -like '*remote-debugging-port*' }
    if ($withFlag) {
        $result.BrowserHasFlag = $true
        Write-Pass "Co process dang chay VOI co --remote-debugging-port:"
        foreach ($p in $withFlag) {
            $m = [regex]::Match($p.CommandLine, '--remote-debugging-port=(\d+)')
            $portTxt = if ($m.Success) { "port $($m.Groups[1].Value)" } else { "(khong ro port)" }
            Write-Info "PID $($p.ProcessId) [$($p.Name)] -> $portTxt"
        }
    } else {
        Write-Fail "Co trinh duyet chay nhung KHONG process nao co co --remote-debugging-port."
        Write-Info "=> Day la nguyen nhan pho bien nhat: trinh duyet duoc mo TU TRUOC khi cai co,"
        Write-Info "   hoac mo bang shortcut chua sua. Tat HOAN TOAN trinh duyet roi mo lai bang shortcut da cai."
    }
}

# -------------------------------------------------------------------
# 2. Quet port CDP 9222-9232 + liet ke tab
# -------------------------------------------------------------------
Write-Section "2. Quet cong CDP ($PORT_START-$PORT_END)"
$ytTabs = @()
for ($p = $PORT_START; $p -le $PORT_END; $p++) {
    $ver = $null
    try {
        $ver = Invoke-RestMethod -Uri "http://127.0.0.1:$p/json/version" -TimeoutSec 1 -ErrorAction Stop
    } catch { continue }

    $result.PortResponds = $true
    if (-not $result.RespondingPort) { $result.RespondingPort = $p }
    Write-Pass "Port $p phan hoi: $($ver.Browser)"

    $tabs = $null
    try { $tabs = Invoke-RestMethod -Uri "http://127.0.0.1:$p/json" -TimeoutSec 1 -ErrorAction Stop } catch {}
    $pages = @($tabs | Where-Object { $_.type -eq 'page' })
    Write-Info "So tab (page): $($pages.Count)"
    foreach ($t in $pages) {
        $u = "$($t.url)"
        if ($u -match 'youtube\.com|youtu\.be') {
            $result.YouTubeTabFound = $true
            $isWatch = ($u -match 'youtube\.com/watch' -or $u -match 'youtube\.com/shorts')
            $tag = if ($isWatch) { "[YOUTUBE - monitor doc duoc]" } else { "[youtube - KHONG phai /watch hay /shorts]" }
            $color = if ($isWatch) { 'Green' } else { 'Yellow' }
            Write-Host "         $tag $($u.Substring(0, [Math]::Min(70, $u.Length)))" -ForegroundColor $color
            $ytTabs += $t
        }
    }
}
if (-not $result.PortResponds) {
    Write-Fail "Khong port nao trong $PORT_START-$PORT_END phan hoi."
    Write-Info "=> Trinh duyet chua chay voi co CDP. Xem muc 1 va 4."
} elseif (-not $result.YouTubeTabFound) {
    Write-Warn "Port CDP OK nhung KHONG co tab YouTube nao dang mo."
    Write-Info "=> Hay mo mot video tai youtube.com/watch?... roi chay lai."
} elseif ($ytTabs.Count -gt 0) {
    $watchTabs = @($ytTabs | Where-Object { $_.url -match 'youtube\.com/watch' -or $_.url -match 'youtube\.com/shorts' })
    if ($watchTabs.Count -eq 0) {
        Write-Warn "Co tab YouTube nhung khong phai trang /watch hoac /shorts."
        Write-Info "=> Monitor chi bat trang xem video. Mo mot video cu the."
    }
}

# -------------------------------------------------------------------
# 3. Kiem tra shortcut da co co chua
# -------------------------------------------------------------------
Write-Section "3. Shortcut trinh duyet"
$searchPaths = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    (Join-Path $env:APPDATA   'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:PROGRAMDATA 'Microsoft\Windows\Start Menu\Programs'),
    (Join-Path $env:APPDATA   'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'),
    (Join-Path $env:APPDATA   'Microsoft\Internet Explorer\Quick Launch')
)
$shell = New-Object -ComObject WScript.Shell
$foundLnk = 0
foreach ($sp in $searchPaths) {
    if (-not (Test-Path $sp)) { continue }
    $lnks = Get-ChildItem -Path $sp -Filter '*.lnk' -Recurse -ErrorAction SilentlyContinue
    foreach ($lnk in $lnks) {
        $sc = $shell.CreateShortcut($lnk.FullName)
        $target = "$($sc.TargetPath)"
        $isBrowser = $false
        foreach ($exe in $BROWSER_EXES) { if ($target -like "*$exe*") { $isBrowser = $true; break } }
        if (-not $isBrowser) { continue }
        $foundLnk++
        if ($sc.Arguments -like '*remote-debugging-port*') {
            $result.ShortcutHasFlag = $true
            Write-Pass "$($lnk.Name) - DA co co"
        } else {
            Write-Fail "$($lnk.Name) - CHUA co co"
            Write-Info $lnk.FullName
        }
    }
}
if ($foundLnk -eq 0) {
    Write-Warn "Khong tim thay shortcut trinh duyet nao trong cac thu muc chuan."
    Write-Info "Co the ban mo trinh duyet bang cach khac (vd: go vao Start, hoac taskbar dac biet)."
}

# -------------------------------------------------------------------
# 4. Ket luan
# -------------------------------------------------------------------
Write-Section "KET LUAN"
if ($result.PortResponds -and $result.YouTubeTabFound) {
    $watchOk = $ytTabs | Where-Object { $_.url -match 'youtube\.com/watch' -or $_.url -match 'youtube\.com/shorts' }
    if ($watchOk) {
        Write-Pass "CDP HOAT DONG. Den trong app phai la XANH LA."
        Write-Info "Neu app van bao do: kiem tra app co cau hinh dung port $($result.RespondingPort) khong,"
        Write-Info "va thu vien 'websocket-client' da duoc cai trong moi truong cua app chua."
    } else {
        Write-Warn "CDP OK nhung tab YouTube khong phai trang xem video (/watch, /shorts)."
        Write-Info "Mo mot video cu the roi thu lai."
    }
} elseif ($result.PortResponds -and -not $result.YouTubeTabFound) {
    Write-Warn "Trinh duyet da bat CDP nhung chua mo video YouTube."
    Write-Info "=> Mo https://www.youtube.com/watch?... roi chay lai."
} elseif (-not $result.PortResponds) {
    if ($result.ShortcutHasFlag -and $result.BrowserRunning -and -not $result.BrowserHasFlag) {
        Write-Fail "Shortcut da co co, NHUNG trinh duyet dang chay khong co co."
        Write-Info "=> Trinh duyet duoc mo tu truoc. Tat HOAN TOAN (dong het cua so + kiem tra"
        Write-Info "   khong con process nen) roi mo lai bang dung shortcut da cai."
    } elseif ($result.ShortcutHasFlag -and -not $result.BrowserRunning) {
        Write-Warn "Shortcut da co co nhung chua mo trinh duyet."
        Write-Info "=> Mo trinh duyet bang shortcut do, vao mot video YouTube, roi chay lai."
    } elseif (-not $result.ShortcutHasFlag) {
        Write-Fail "Shortcut CHUA co co --remote-debugging-port."
        Write-Info "=> Chay 'enable_cdp_flag.bat' (Run as Administrator neu can), roi mo lai trinh duyet."
    } else {
        Write-Fail "Khong ket noi duoc CDP. Tat han trinh duyet va mo lai bang shortcut da cai."
    }
}

Write-Host ""
Write-Host "Nhan Enter de dong..." -ForegroundColor DarkGray
Read-Host | Out-Null
