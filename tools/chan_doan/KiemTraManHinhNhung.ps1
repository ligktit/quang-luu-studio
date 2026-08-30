param(
    [string]$Exe,       # duong dan QuangLuuStudio.exe neu cai o cho la
    [switch]$NoPause    # khong dung cho bam Enter (dung khi chay tu dong)
)
# Kiem tra: may nay dung ban NANG hay NHE, va bo hien thi web co nap duoc khong.
#
# Vi sao can rieng cong cu nay: ban app truoc 1.7.5 KHONG ghi ket qua nay vao
# nhat ky, nen "trong log khong thay bao loi" hoan toan khong co nghia la khong
# co loi. Cong cu nay khong doc log, khong can cai gi, khong sua gi — chi doc.
#
# Nguyen tac: BAM VAO TIEN TRINH DANG CHAY, khong doan theo thu muc.
#   - Thu muc %TEMP%\_MEIxxxxxx cua lan chay truoc KHONG tu xoa khi app tat dot
#     ngot. Quet bua bai roi vo phai mot cai cu la bao "binh thuong" oan.
#   - Shortcut co the tro toi mot ban cai KHAC voi ban trong Program Files.
#     Quet nham file exe thi ket luan sai tu goc.
#
# Cach chay: chuot phai -> Run with PowerShell. Hoac bam doi vao file .bat canh ben.

$ErrorActionPreference = "Continue"

function W($s) { Write-Host $s }

W ""
W "==============================================="
W "  Quang Luu Studio - kiem tra man hinh nhung"
W "==============================================="
W ""

# ── 1. Tien trinh dang chay (nguon dang tin nhat) ────────────────────────────
$proc     = Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue | Select-Object -First 1
$procExe  = $null
$meiDir   = $null
if ($proc) {
    try { $procExe = $proc.Path } catch { }
    # Thu muc bung ra cua CHINH lan chay nay: doc tu danh sach module da nap.
    try {
        foreach ($m in $proc.Modules) {
            if ($m.FileName -match '\\_MEI[^\\]+\\') {
                $meiDir = [regex]::Match($m.FileName, '^(.*\\_MEI[^\\]+)\\').Groups[1].Value
                break
            }
        }
    } catch {
        W "[!] Khong doc duoc danh sach module cua tien trinh (thieu quyen?)."
    }
}

# ── 2. Chon file exe de doc ──────────────────────────────────────────────────
# Luu y: bien PowerShell KHONG phan biet hoa thuong. Dat bien cuc bo la `$exe`
# se xoa luon tham so `$Exe` truyen vao — script bao "khong tim thay exe" du
# nguoi dung da chi dung duong dan. Dung han mot ten khac.
$targetExe = $null
if ($Exe -and (Test-Path -LiteralPath $Exe)) { $targetExe = (Resolve-Path -LiteralPath $Exe).Path }
if (-not $targetExe -and $procExe) { $targetExe = $procExe }

$caiDat = $null
foreach ($p in @(
    "$env:ProgramFiles\QuangLuuStudio\QuangLuuStudio.exe",
    "${env:ProgramFiles(x86)}\QuangLuuStudio\QuangLuuStudio.exe",
    "$env:LOCALAPPDATA\Programs\QuangLuuStudio\QuangLuuStudio.exe")) {
    if (Test-Path -LiteralPath $p) { $caiDat = $p; break }
}
if (-not $targetExe) { $targetExe = $caiDat }

if (-not $targetExe) {
    W "[LOI] Khong tim thay QuangLuuStudio.exe."
    W "      Mo app len roi chay lai, hoac chi dung duong dan:"
    W "      .\KiemTraManHinhNhung.ps1 -Exe 'D:\duong\dan\QuangLuuStudio.exe'"
    W ""
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 1
}

$fi = Get-Item -LiteralPath $targetExe
W ("File exe   : " + $fi.FullName)
W ("Kich thuoc : " + [math]::Round($fi.Length / 1MB, 0) + " MB")
W ("App dang chay: " + $(if ($proc) { "CO" } else { "KHONG" }))
W ""

# Hai ban cai khac nhau tren cung mot may — shortcut chay ban nay, Program Files
# lai la ban khac. Kiem cai nay truoc moi thu, vi no lam sai het phan con lai.
if ($procExe -and $caiDat -and ($procExe -ne $caiDat)) {
    W "[!] CANH BAO: app dang chay KHONG phai ban trong Program Files."
    W ("    Dang chay      : " + $procExe)
    W ("    Trong Program Files: " + $caiDat)
    W "    Rat co the shortcut tro toi mot ban cai cu. Ket qua duoi day tinh"
    W "    theo ban DANG CHAY."
    W ""
}

# ── 3. Goi cai co kem bo hien thi web khong ──────────────────────────────────
# App dong goi kieu onefile: moi DLL nam BEN TRONG exe, canh exe khong co gi ca.
# Nen phai do ten file trong bang muc luc cua goi, nam dang chu thuong trong exe.
# KHONG dung "QtWebEngineProcess.exe" lam dau hieu — chuoi do co trong CA HAI ban.
# Kiem ca file .pyd: thieu no thi Python khong import duoc, du DLL con nguyen.
W "Dang doc trong exe (mat vai giay)..."
$canTim = @("Qt6WebEngineCore.dll", "QtWebEngineWidgets.pyd", "QtWebEngineCore.pyd")
$thay = @{}
foreach ($t in $canTim) { $thay[$t] = $false }
try {
    $fs = [System.IO.File]::OpenRead($fi.FullName)
    try {
        $buf = New-Object byte[] (4MB)
        $duoi = ""
        while (($n = $fs.Read($buf, 0, $buf.Length)) -gt 0) {
            $doan = $duoi + [Text.Encoding]::ASCII.GetString($buf, 0, $n)
            foreach ($t in $canTim) { if (-not $thay[$t] -and $doan.Contains($t)) { $thay[$t] = $true } }
            $duoi = $doan.Substring([Math]::Max(0, $doan.Length - 32))
        }
    } finally { $fs.Dispose() }
} catch {
    W ("[LOI] Khong doc duoc exe: " + $_.Exception.Message)
}
$coTrongGoi = $thay["Qt6WebEngineCore.dll"]
$thieuPyd   = $coTrongGoi -and (-not $thay["QtWebEngineWidgets.pyd"] -or -not $thay["QtWebEngineCore.pyd"])

# ── 4. Luc chay co bung ra du khong ──────────────────────────────────────────
$meiTrangThai = "khong-biet"     # co-du | thieu-dll | thieu-pyd | khong-biet
$meiNguon = ""
if ($meiDir -and (Test-Path -LiteralPath $meiDir)) {
    $meiNguon = "cua chinh lan chay nay"
} else {
    # Khong bam duoc vao tien trinh -> danh quet %TEMP%. Kem tin cay hon nhieu:
    # thu muc cu khong tu xoa khi app tat dot ngot.
    $meiDir = $null
    foreach ($d in @(Get-ChildItem -Path $env:TEMP -Directory -Filter "_MEI*" -ErrorAction SilentlyContinue |
                     Sort-Object LastWriteTime -Descending)) {
        if (Test-Path -LiteralPath (Join-Path $d.FullName "PySide6")) {
            $meiDir = $d.FullName; $meiNguon = "moi nhat tim thay o %TEMP% (CO THE LA BAN CU)"; break
        }
    }
}
if ($meiDir) {
    $coDll = [bool](Get-ChildItem -Path $meiDir -Filter "Qt6WebEngineCore.dll" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)
    $coPyd = [bool](Get-ChildItem -Path $meiDir -Filter "QtWebEngineWidgets.pyd" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($coDll -and $coPyd) { $meiTrangThai = "co-du" }
    elseif ($coDll)         { $meiTrangThai = "thieu-pyd" }
    else                    { $meiTrangThai = "thieu-dll" }
}

# ── 5. Ket luan ──────────────────────────────────────────────────────────────
W ""
W "-----------------------------------------------"
if (-not $coTrongGoi) {
    W "  KET QUA: ban NHE (Light)"
    W ""
    W "  Bo cai nay khong kem bo hien thi web. O 'Man hinh"
    W "  karaoke nhung' trong Thiet lap mo di la DUNG THIET KE."
    W ""
    W "  Muon dung: cai bo cai co chu 'heavy' trong ten, de len"
    W "  ban dang co. Khong can go truoc, khong mat thiet lap,"
    W "  khong mat danh sach bai, khong phai kich hoat lai."
} elseif ($thieuPyd) {
    W "  KET QUA: GOI CAI DUNG SAI - thieu module Python"
    W ""
    W "  Exe co Qt6WebEngineCore.dll nhung THIEU QtWebEngineWidgets.pyd"
    W "  / QtWebEngineCore.pyd. Python khong import duoc, nen o do van mo"
    W "  du DLL con nguyen. Day la loi luc DONG GOI - bao ky thuat,"
    W "  khach khong tu xu ly duoc."
} elseif ($meiTrangThai -eq "thieu-dll" -or $meiTrangThai -eq "thieu-pyd") {
    W "  KET QUA: ban NANG (Heavy) NHUNG BUNG RA THIEU FILE"
    W ""
    W ("  Thu muc bung ra (" + $meiNguon + "):")
    W ("    " + $meiDir)
    W ("  Thieu: " + $(if ($meiTrangThai -eq "thieu-dll") { "Qt6WebEngineCore.dll" } else { "QtWebEngineWidgets.pyd" }))
    W ""
    W "  Gan nhu chac chan bi phan mem diet virus cach ly."
    W "  Cho CA HAI duong dan sau vao danh sach loai tru roi cai lai:"
    W ("    " + (Split-Path $fi.FullName -Parent))
    W ("    " + $env:TEMP)
} elseif ($meiTrangThai -eq "co-du") {
    W "  KET QUA: goi cai VA file bung ra deu DU"
    W ""
    W ("  Thu muc bung ra (" + $meiNguon + "):")
    W ("    " + $meiDir)
    W ""
    W "  Neu o 'Man hinh karaoke nhung' VAN mo thi khong phai thieu"
    W "  file — app nap QtWebEngine that bai vi ly do khac."
    W ""
    W "  BUOC TIEP THEO (bao ky thuat kem thong tin nay):"
    W "   1. Cai ban 1.7.5 tro len roi mo app mot lan."
    W "   2. Gui dong 'Bien the build:' trong file:"
    W ("      " + (Join-Path $env:APPDATA "QuangLuuStudio\logs\app.log"))
    W "      Dong do ghi thang ly do Python bao loi."
} else {
    W "  KET QUA: ban NANG (Heavy) - chua du du kien"
    W ""
    if ($proc) {
        W "  App dang chay nhung khong doc duoc thu muc bung ra."
        W "  Thu chay lai cong cu nay bang quyen Administrator."
    } else {
        W "  Hay MO app len, de nguyen do, roi chay lai cong cu nay."
        W "  (Phai co app dang chay moi kiem duoc buoc cuoi.)"
    }
}
W "-----------------------------------------------"
W ""
if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
