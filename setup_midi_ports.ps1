param(
    [string[]]$Ports = @("QuangLuuMIDI", "QLS_PhanHoi"),
    [switch]$NoPause,      # khong cho bam Enter (chay tu dong / CI)
    [int]$WaitSeconds = 20 # cho bao lau de cong hien ra sau khi khoi dong loopMIDI
)
# Tao cac cong MIDI ao can cho Quang Luu Studio, roi KIEM CHUNG lai.
#
#   QuangLuuMIDI - app GUI lenh vao, Studio One "Receive From" cong nay.
#   QLS_PhanHoi  - Studio One GUI TRA ve ("Send To"), app nghe o day de biet
#                  Studio One da nap bai xong chua.
#
# Vi sao khong tin vao moi buoc ghi registry: cach them cong bang registry
# KHONG phai duong chinh thuc cua loopMIDI, ban loopMIDI moi co the doi cho
# luu. Nen sau khi ghi, script DEM LAI danh sach cong MIDI that su co tren may
# (goi thang winmm.dll). Khong thay du cong thi mo loopMIDI len va chi cach
# them tay - khong bao gio bao "xong" khi chua thuc su xong.
#
# Ten cong phan hoi co y KHONG chua chu "QuangLuuMIDI": app tim cong gui theo
# kieu "ten co chua QuangLuuMIDI" (core/midi.py), de trung thi app mo nham.

$ErrorActionPreference = "Continue"

function W($s) { Write-Host $s }

$csharp = @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class QlsMidiPorts
{
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct MIDIINCAPS {
        public ushort wMid; public ushort wPid; public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public uint dwSupport;
    }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct MIDIOUTCAPS {
        public ushort wMid; public ushort wPid; public uint vDriverVersion;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string szPname;
        public ushort wTechnology; public ushort wVoices; public ushort wNotes; public ushort wChannelMask;
        public uint dwSupport;
    }
    [DllImport("winmm.dll")] static extern uint midiInGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern uint midiInGetDevCapsW(UIntPtr id, ref MIDIINCAPS caps, uint cb);
    [DllImport("winmm.dll")] static extern uint midiOutGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern uint midiOutGetDevCapsW(UIntPtr id, ref MIDIOUTCAPS caps, uint cb);

    public static string[] Inputs() {
        uint n = midiInGetNumDevs();
        string[] r = new string[n];
        for (uint i = 0; i < n; i++) {
            MIDIINCAPS c = new MIDIINCAPS();
            r[i] = midiInGetDevCapsW(new UIntPtr(i), ref c, (uint)Marshal.SizeOf(c)) == 0 ? c.szPname : "?";
        }
        return r;
    }

    public static string[] Outputs() {
        uint n = midiOutGetNumDevs();
        string[] r = new string[n];
        for (uint i = 0; i < n; i++) {
            MIDIOUTCAPS c = new MIDIOUTCAPS();
            r[i] = midiOutGetDevCapsW(new UIntPtr(i), ref c, (uint)Marshal.SizeOf(c)) == 0 ? c.szPname : "?";
        }
        return r;
    }
}
"@

try {
    Add-Type -TypeDefinition $csharp -Language CSharp -ErrorAction Stop
} catch {
    W ("[LOI] Khong goi duoc winmm.dll de kiem tra cong MIDI: " + $_.Exception.Message)
    exit 2
}

function Get-LoopMidiExe {
    foreach ($p in @(
        "$env:ProgramFiles\Tobias Erichsen\loopMIDI\loopMIDI.exe",
        "${env:ProgramFiles(x86)}\Tobias Erichsen\loopMIDI\loopMIDI.exe",
        "$env:LOCALAPPDATA\Programs\Tobias Erichsen\loopMIDI\loopMIDI.exe")) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    return $null
}

# Cong chi ton tai khi loopMIDI DANG CHAY - phai co ca o danh sach gui lan nhan.
function Get-MissingPorts([string[]]$want) {
    $outs = [QlsMidiPorts]::Outputs()
    $ins  = [QlsMidiPorts]::Inputs()
    $missing = @()
    foreach ($p in $want) {
        $hasOut = @($outs | Where-Object { $_ -eq $p }).Count -gt 0
        $hasIn  = @($ins  | Where-Object { $_ -eq $p }).Count -gt 0
        if (-not ($hasOut -and $hasIn)) { $missing += $p }
    }
    return $missing
}

function Wait-ForPorts([string[]]$want, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ($true) {
        $missing = Get-MissingPorts $want
        if ($missing.Count -eq 0) { return @() }
        if ((Get-Date) -ge $deadline) { return $missing }
        Start-Sleep -Milliseconds 1500
    }
}

W ""
W "----------------------------------------"
W " Tao cong MIDI ao: $($Ports -join ', ')"
W "----------------------------------------"

# ── 1. loopMIDI da cai chua ──────────────────────────────────────────────────
$exe = Get-LoopMidiExe
if (-not $exe) {
    W "[CHUA CAI] Khong thay loopMIDI. Dang thu cai tu dong bang winget..."
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install --id TobiasErichsen.loopMIDI --exact --silent --accept-package-agreements --accept-source-agreements
        $exe = Get-LoopMidiExe
    } else {
        W "[INFO] May nay khong co winget."
    }
}
if (-not $exe) {
    W "[INFO] Dang mo trang tai loopMIDI..."
    Start-Process "https://www.tobias-erichsen.de/software/loopmidi.html"
    if (-not $NoPause) {
        Read-Host "Cai xong loopMIDI thi nhan Enter de chay tiep"
        $exe = Get-LoopMidiExe
    }
}
if (-not $exe) {
    W "[LOI] Van chua co loopMIDI. Cai loopMIDI roi chay lai file nay."
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 1
}
W ("[OK] loopMIDI: " + $exe)

# ── 2. Ghi cau hinh cong + bat loopMIDI ──────────────────────────────────────
$regPath = "HKCU:\Software\Tobias Erichsen\loopMIDI\Ports"
$added = $false
try {
    if (-not (Test-Path $regPath)) { New-Item -Path $regPath -Force | Out-Null }
    foreach ($p in $Ports) {
        $cur = Get-ItemProperty -Path $regPath -Name $p -ErrorAction SilentlyContinue
        if ($null -eq $cur) {
            New-ItemProperty -Path $regPath -Name $p -Value $p -PropertyType String -Force | Out-Null
            W ("[OK] Da ghi cau hinh cong: " + $p)
            $added = $true
        } else {
            W ("[OK] Cau hinh cong da co: " + $p)
        }
    }
} catch {
    W ("[CANH BAO] Khong ghi duoc cau hinh cong vao registry: " + $_.Exception.Message)
}

$running = [bool](Get-Process -Name "loopMIDI" -ErrorAction SilentlyContinue)
if ($added -and $running) {
    W "[INFO] Khoi dong lai loopMIDI de nap cong moi..."
    try { Stop-Process -Name "loopMIDI" -Force -ErrorAction Stop } catch { }
    Start-Sleep -Seconds 2
    $running = $false
}
if (-not $running) {
    W "[INFO] Dang bat loopMIDI..."
    Start-Process -FilePath $exe
}

# Cho loopMIDI chay khi dang nhap - khong co no thi cong bien mat, app mat MIDI.
try {
    New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
        -Name "loopMIDI" -Value ('"' + $exe + '" /autostart') -PropertyType String -Force | Out-Null
    W "[OK] Da dat loopMIDI tu chay khi khoi dong Windows"
} catch {
    W ("[CANH BAO] Khong dat duoc tu khoi dong: " + $_.Exception.Message)
}

# ── 3. Kiem chung: cong co THAT SU hien ra khong ─────────────────────────────
W ""
W "[INFO] Dang kiem tra danh sach cong MIDI that su co tren may..."
$missing = Wait-ForPorts $Ports $WaitSeconds

$round = 0
while ($missing.Count -gt 0 -and -not $NoPause -and $round -lt 3) {
    $round++
    W ""
    W ("[CHUA DU] Chua thay cong: " + ($missing -join ", "))
    W "  Cach them tay (30 giay):"
    W "   1. Mo loopMIDI (bieu tuong o khay he thong, canh dong ho)"
    W "   2. Go ten cong vao o 'New port-name' o duoi cung"
    W "   3. Bam nut  +  ben trai de tao"
    W "   4. Lam lan luot cho TUNG ten con thieu o tren"
    try { Start-Process -FilePath $exe } catch { }
    Read-Host "   Tao xong thi nhan Enter de kiem lai"
    $missing = Wait-ForPorts $Ports 5
}

W ""
W "Danh sach cong MIDI hien co:"
foreach ($n in [QlsMidiPorts]::Outputs()) { W ("   (gui)  " + $n) }
foreach ($n in [QlsMidiPorts]::Inputs())  { W ("   (nhan) " + $n) }
W ""

if ($missing.Count -eq 0) {
    W "[OK] Da co du cong MIDI: $($Ports -join ', ')"
    exit 0
}

W ("[CANH BAO] Con thieu cong: " + ($missing -join ", "))
W "  - Thieu QuangLuuMIDI : app khong dieu khien duoc Studio One."
W "  - Thieu QLS_PhanHoi  : app van chay, chi khong biet chac Studio One da"
W "                         nap bai xong chua (quay ve cach hen gio nhu cu)."
exit 1
