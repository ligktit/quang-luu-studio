param(
    [string]$OutPort  = "QuangLuuMIDI",  # cong app GUI vao = "Receive From" cua Studio One
    [string]$BackPort = "QLS_PhanHoi",   # cong Studio One GUI TRA = "Send To" cua thiet bi
    [int]$PingCC      = 49,              # control "Ping San Sang" trong surface.xml ban tham do
    [int]$Seconds     = 240,             # chay bao lau (Ctrl+C de dung som, van ghi bao cao)
    [int]$PingMs      = 1000,            # nhip gui Ping
    [string]$OutFile,                    # mac dinh: Desktop\QLS_ThamDoSO_<MAY>_<gio>.txt
    [switch]$NoOpen,                     # khong tu mo Notepad
    [switch]$NoPause,                    # khong cho bam Enter
    # ── Kich ban D: trang thai nut (xem HUONG_DAN.md) ──
    [switch]$BatTransmit,                # tam bat "transmit" cho 12 nut trong file thiet bi da cai (co sao luu)
    [switch]$KhoiPhucSurface,            # tra file thiet bi ve ban goc tu ban sao luu
    [switch]$KiemTraNut,                 # gui BAT/TAT tung nut, xem Studio One co bao lai trang thai khong
    [int]$ChoMs       = 1500,            # cho phan hoi sau moi lenh BAT/TAT
    [int]$BamTaySeconds = 30             # thoi gian ky thuat vien tu bam nut TRONG Studio One
)
# Tham do: Studio One nap bai xong luc nao, va co TRA LOI MIDI khong.
#
# Vi sao can: cong loopMIDI mo duoc ca khi Studio One chua chay, nen app khong
# biet luc nao Studio One THAT SU nghe duoc. Cach dang tin duy nhat la hoi-dap:
# gui Ping gia tri N vao QuangLuuMIDI, cho Studio One gui tra dung N qua cong ve.
# Truoc khi code vao app phai biet chac 3 dieu, cong cu nay do ca 3:
#   1. Studio One co gui tra gia tri VUA NHAN tu chinh control do khong
#      (nhieu DAW chan vong nay de khoi doi dap vo tan).
#   2. Luc nap bai Studio One co TU gui gia tri cac control ra khong.
#   3. Tieu de cua so luc dang nap / da nap trong the nao, cach moc tra loi bao lau.
#
# Khong dung Python: goi thang winmm.dll (MIDI) va user32.dll (cua so) qua C#,
# chay duoc tren moi Windows 10/11 co PowerShell 5.1.

$ErrorActionPreference = "Continue"
$startWall = Get-Date

# 12 nut ma giao dien app (va dai "DANG BAT") hien trang thai. Ten = ten control
# trong studio_one/QuangLuuMIDI.surface.xml, CC = midi_cc trong app_config.json.
$NutKiemTra = @(
    @{ name = "modeDanca";     cc = 46; ten = "Mode Dan Ca" },
    @{ name = "modeLofi";      cc = 37; ten = "Mode Lofi" },
    @{ name = "modeRemix";     cc = 38; ten = "Mode Remix" },
    @{ name = "modeDatheloai"; cc = 39; ten = "Mode Da The Loai" },
    @{ name = "toneAuto";      cc = 40; ten = "Auto-Tune" },
    @{ name = "fixMeo";        cc = 45; ten = "Fix Meo" },
    @{ name = "be";            cc = 47; ten = "Be" },
    @{ name = "tatOn";         cc = 48; ten = "Tat On" },
    @{ name = "muteMusic";     cc = 50; ten = "Mute Nhac" },
    @{ name = "muteMic";       cc = 51; ten = "Mute Mic" },
    @{ name = "muteReverb";    cc = 52; ten = "Mute Vang (Tat Vang)" },
    @{ name = "muteBacking";   cc = 53; ten = "Mute Be" }
)

# ── -BatTransmit / -KhoiPhucSurface: sua file thiet bi DA CAI (khong phai file trong repo) ──
# Studio One chi gui nguoc gia tri cua control co "transmit". Ban phat hanh chi bat cho
# readyPing, nen muon biet Studio One co bao trang thai nut khong thi phai tam bat cho
# 12 nut tren. Sao luu ban goc canh file (duoi .thamdo_goc) de tra lai bang -KhoiPhucSurface.
if ($BatTransmit -or $KhoiPhucSurface) {
    $files = @(Get-ChildItem -Path (Join-Path $env:APPDATA "PreSonus") -Filter "QuangLuuMIDI.surface.xml" -Recurse -ErrorAction SilentlyContinue |
               Where-Object { $_.FullName -like "*User Devices*" })
    if ($files.Count -eq 0) {
        Write-Host "[LOI] Khong tim thay QuangLuuMIDI.surface.xml trong %APPDATA%\PreSonus\...\User Devices."
        Write-Host "      Chay setup_all.bat trong thu muc cai dat truoc."
        if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
        exit 2
    }
    foreach ($f in $files) {
        $bak = $f.FullName + ".thamdo_goc"
        if ($KhoiPhucSurface) {
            if (Test-Path $bak) {
                Copy-Item -Path $bak -Destination $f.FullName -Force
                Remove-Item -Path $bak -Force
                Write-Host ("Da tra ve ban goc: " + $f.FullName)
            } else {
                Write-Host ("Khong co ban sao luu (chua tung -BatTransmit?): " + $f.FullName)
            }
            continue
        }
        $bytes = [IO.File]::ReadAllBytes($f.FullName)
        $hasBom = ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)
        $text = [Text.Encoding]::UTF8.GetString($bytes)
        if ($hasBom) { $text = $text.Substring(1) }
        $doi = 0
        foreach ($n in $NutKiemTra) {
            $pat = '(<Control\s+name="' + $n.name + '"[^>]*\soptions=")(?![^"]*transmit)([^"]*)"'
            $moi = [Regex]::Replace($text, $pat, '${1}transmit ${2}"')
            if ($moi -ne $text) { $doi++; $text = $moi }
        }
        if ($doi -eq 0) {
            Write-Host ("Khong co gi de doi (da bat san?): " + $f.FullName)
            continue
        }
        if (-not (Test-Path $bak)) { Copy-Item -Path $f.FullName -Destination $bak }
        [IO.File]::WriteAllText($f.FullName, $text, (New-Object System.Text.UTF8Encoding($hasBom)))
        Write-Host ("Da bat transmit cho " + $doi + " nut: " + $f.FullName)
        Write-Host ("  Sao luu ban goc : " + $bak)
    }
    if ($BatTransmit) {
        Write-Host ""
        Write-Host "TIEP THEO: dong Studio One roi mo lai (de nap file thiet bi moi), mo bai mau,"
        Write-Host "           roi chay:  ThamDoStudioOne.bat -KiemTraNut"
        Write-Host "XONG VIEC: ThamDoStudioOne.bat -KhoiPhucSurface  (roi mo lai Studio One)"
    }
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 0
}
if (-not $OutFile) {
    $desk = [Environment]::GetFolderPath("Desktop")
    $OutFile = Join-Path $desk ("QLS_ThamDoSO_" + $env:COMPUTERNAME + "_" + $startWall.ToString("yyyyMMdd_HHmmss") + ".txt")
}

$log = New-Object System.Collections.Generic.List[string]
function W([string]$s) { Write-Host $s; $log.Add($s) }
function T([long]$ms) { return ("{0,7:0.0}s" -f ($ms / 1000.0)) }

# ── Lop C#: MIDI + cua so ────────────────────────────────────────────────────
# Callback MIDI chay tren thread cua winmm, khong co runspace PowerShell nen phai
# la code C# thuan: chi day tin vao hang doi, vong chinh ben duoi moi doc ra.
$csharp = @"
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class QlsProbe
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
    public delegate void MidiInProc(IntPtr h, uint msg, IntPtr inst, IntPtr p1, IntPtr p2);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("winmm.dll")] static extern uint midiInGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern uint midiInGetDevCapsW(UIntPtr id, ref MIDIINCAPS caps, uint cb);
    [DllImport("winmm.dll")] static extern uint midiOutGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] static extern uint midiOutGetDevCapsW(UIntPtr id, ref MIDIOUTCAPS caps, uint cb);
    [DllImport("winmm.dll")] static extern uint midiInOpen(out IntPtr h, uint id, MidiInProc cb, IntPtr inst, uint flags);
    [DllImport("winmm.dll")] static extern uint midiInStart(IntPtr h);
    [DllImport("winmm.dll")] static extern uint midiInStop(IntPtr h);
    [DllImport("winmm.dll")] static extern uint midiInReset(IntPtr h);
    [DllImport("winmm.dll")] static extern uint midiInClose(IntPtr h);
    [DllImport("winmm.dll")] static extern uint midiOutOpen(out IntPtr h, uint id, IntPtr cb, IntPtr inst, uint flags);
    [DllImport("winmm.dll")] static extern uint midiOutShortMsg(IntPtr h, uint msg);
    [DllImport("winmm.dll")] static extern uint midiOutClose(IntPtr h);

    [DllImport("user32.dll")] static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowTextW(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassNameW(IntPtr hWnd, StringBuilder sb, int max);

    const uint CALLBACK_FUNCTION = 0x00030000;
    const uint MIM_DATA = 0x3C3;

    static readonly Stopwatch Clock = Stopwatch.StartNew();
    // Moi tin: { ms, tag cong (1 = cong chinh, 2 = cong ve), status, data1, data2 }
    static readonly ConcurrentQueue<long[]> Inbox = new ConcurrentQueue<long[]>();
    // Giu delegate trong truong static: de GC thu hoi thi winmm goi vao dia chi chet.
    static readonly MidiInProc InProc = OnMidiIn;
    static readonly List<IntPtr> InHandles = new List<IntPtr>();
    static IntPtr OutHandle = IntPtr.Zero;

    public static long NowMs() { return Clock.ElapsedMilliseconds; }

    static void OnMidiIn(IntPtr h, uint msg, IntPtr inst, IntPtr p1, IntPtr p2) {
        if (msg != MIM_DATA) return;
        long m = p1.ToInt64();
        Inbox.Enqueue(new long[] { Clock.ElapsedMilliseconds, inst.ToInt64(), m & 0xFF, (m >> 8) & 0x7F, (m >> 16) & 0x7F });
    }

    public static string[] InputNames() {
        uint n = midiInGetNumDevs();
        string[] names = new string[n];
        for (uint i = 0; i < n; i++) {
            MIDIINCAPS c = new MIDIINCAPS();
            names[i] = midiInGetDevCapsW(new UIntPtr(i), ref c, (uint)Marshal.SizeOf(c)) == 0 ? c.szPname : "?";
        }
        return names;
    }

    public static string[] OutputNames() {
        uint n = midiOutGetNumDevs();
        string[] names = new string[n];
        for (uint i = 0; i < n; i++) {
            MIDIOUTCAPS c = new MIDIOUTCAPS();
            names[i] = midiOutGetDevCapsW(new UIntPtr(i), ref c, (uint)Marshal.SizeOf(c)) == 0 ? c.szPname : "?";
        }
        return names;
    }

    public static uint OpenIn(int id, int tag) {
        IntPtr h;
        uint r = midiInOpen(out h, (uint)id, InProc, new IntPtr(tag), CALLBACK_FUNCTION);
        if (r != 0) return r;
        InHandles.Add(h);
        return midiInStart(h);
    }

    public static uint OpenOut(int id) {
        IntPtr h;
        uint r = midiOutOpen(out h, (uint)id, IntPtr.Zero, IntPtr.Zero, 0);
        if (r == 0) OutHandle = h;
        return r;
    }

    public static uint SendCC(int channel, int cc, int value) {
        if (OutHandle == IntPtr.Zero) return 999;
        uint msg = (uint)(0xB0 | (channel & 0x0F)) | ((uint)(cc & 0x7F) << 8) | ((uint)(value & 0x7F) << 16);
        return midiOutShortMsg(OutHandle, msg);
    }

    public static long[][] Drain() {
        List<long[]> list = new List<long[]>();
        long[] item;
        while (Inbox.TryDequeue(out item)) list.Add(item);
        return list.ToArray();
    }

    public static void CloseAll() {
        foreach (IntPtr h in InHandles) { midiInStop(h); midiInReset(h); midiInClose(h); }
        InHandles.Clear();
        if (OutHandle != IntPtr.Zero) { midiOutClose(OutHandle); OutHandle = IntPtr.Zero; }
    }

    // Cua so top-level co tieu de cua cac PID, dang "visible|class|title".
    public static string[] WindowsOf(int[] pids) {
        List<string> found = new List<string>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr l) {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (Array.IndexOf(pids, (int)pid) < 0) return true;
            StringBuilder title = new StringBuilder(512);
            GetWindowTextW(hWnd, title, title.Capacity);
            if (title.Length == 0) return true;
            StringBuilder cls = new StringBuilder(256);
            GetClassNameW(hWnd, cls, cls.Capacity);
            found.Add(string.Format("{0}|{1}|{2}", IsWindowVisible(hWnd) ? 1 : 0, cls, title));
            return true;
        }, IntPtr.Zero);
        return found.ToArray();
    }
}
"@

W ""
W "==============================================="
W "  Quang Luu Studio - tham do Studio One / MIDI"
W "==============================================="
W ("Bat dau    : " + $startWall.ToString("yyyy-MM-dd HH:mm:ss") + "   May: " + $env:COMPUTERNAME)
W ("Tham so    : OutPort='" + $OutPort + "' BackPort='" + $BackPort + "' PingCC=" + $PingCC + " Seconds=" + $Seconds + " PingMs=" + $PingMs)
W ""

try {
    Add-Type -TypeDefinition $csharp -Language CSharp -ErrorAction Stop
} catch {
    W ("[LOI] Khong bien dich duoc phan goi MIDI: " + $_.Exception.Message)
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 2
}

# App dang chay thi no cung gui CC vao QuangLuuMIDI, lan vao ket qua.
if (Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue) {
    W "[!] App Quang Luu Studio DANG CHAY. Nen dong app roi chay lai de ket qua sach."
    W ""
}

function Find-Port([string[]]$names, [string]$want, [string]$exclude) {
    for ($i = 0; $i -lt $names.Length; $i++) {
        if ($names[$i] -eq $want) { return $i }
    }
    for ($i = 0; $i -lt $names.Length; $i++) {
        $n = $names[$i]
        if ($n.IndexOf($want, [StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
        if ($exclude -and $n.IndexOf($exclude, [StringComparison]::OrdinalIgnoreCase) -ge 0) { continue }
        return $i
    }
    return -1
}

$ins  = [QlsProbe]::InputNames()
$outs = [QlsProbe]::OutputNames()
W "Cong MIDI VAO (doc duoc):"
for ($i = 0; $i -lt $ins.Length; $i++) { W ("  [" + $i + "] " + $ins[$i]) }
W "Cong MIDI RA (gui duoc):"
for ($i = 0; $i -lt $outs.Length; $i++) { W ("  [" + $i + "] " + $outs[$i]) }
W ""

# App tim cong gui theo kieu "ten CO CHUA QuangLuuMIDI" (core/midi.py). Cong ve
# ma cung chua chu do thi app co the mo nham no de gui -> Studio One khong nghe.
if ($BackPort.IndexOf($OutPort, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
    W ("[!] Ten cong ve '" + $BackPort + "' co chua chu '" + $OutPort + "'. App se bat nham cong nay.")
    W "    Doi ten cong ve trong loopMIDI (vd: QLS_PhanHoi) roi chay lai."
    W ""
}

$outIdx  = Find-Port $outs $OutPort $BackPort
$mainIn  = Find-Port $ins  $OutPort $BackPort
$backIdx = Find-Port $ins  $BackPort ""

if ($outIdx -lt 0) {
    W ("[LOI] Khong co cong ra '" + $OutPort + "'. loopMIDI chua chay hoac chua tao cong.")
    [IO.File]::WriteAllLines($OutFile, $log, (New-Object System.Text.UTF8Encoding($true)))
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 2
}
$r = [QlsProbe]::OpenOut($outIdx)
if ($r -ne 0) {
    W ("[LOI] Khong mo duoc cong ra '" + $outs[$outIdx] + "' (ma loi winmm " + $r + ").")
    [IO.File]::WriteAllLines($OutFile, $log, (New-Object System.Text.UTF8Encoding($true)))
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 2
}
W ("Gui Ping vao   : [" + $outIdx + "] " + $outs[$outIdx])

if ($backIdx -ge 0) {
    $r = [QlsProbe]::OpenIn($backIdx, 2)
    if ($r -eq 0) { W ("Nghe cong ve   : [" + $backIdx + "] " + $ins[$backIdx]) }
    else { W ("[!] Khong mo duoc cong ve (ma loi winmm " + $r + ")."); $backIdx = -1 }
} else {
    W ("[!] Khong co cong ve '" + $BackPort + "' -> chi do duoc cua so, chua do duoc hoi-dap.")
}
# Nghe ca cong chinh: xac nhan loopMIDI tra lai chinh tin minh gui (ly do app
# KHONG duoc nghe phan hoi tren cong nay) va bat ai khac dang gui vao do.
if ($mainIn -ge 0) {
    $r = [QlsProbe]::OpenIn($mainIn, 1)
    if ($r -eq 0) { W ("Nghe cong chinh: [" + $mainIn + "] " + $ins[$mainIn] + " (kiem tu vong)") }
    else { $mainIn = -1 }
}
W ""

# ── Kich ban D: Studio One co bao lai TRANG THAI NUT khong ──────────────────────
# App hien nut/dai "DANG BAT" theo lenh NO DA GUI, khong theo trang thai that trong
# Studio One. Muon hien dung thi Studio One phai gui tra gia tri cua tung nut qua
# cong ve. Do hai dieu:
#   1. App gui BAT/TAT -> Studio One co gui tra dung CC do khong (xac nhan lenh).
#   2. Bam nut TRONG Studio One -> Studio One co tu bao ra khong (dong bo nguoc).
if ($KiemTraNut) {
    if ($backIdx -lt 0) {
        W "[LOI] Khong co cong ve '$BackPort' -> khong do duoc. Xem HUONG_DAN.md buoc 1."
        [QlsProbe]::CloseAll()
        [IO.File]::WriteAllLines($OutFile, $log, (New-Object System.Text.UTF8Encoding($true)))
        if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
        exit 2
    }
    $theoCC = @{}
    foreach ($n in $NutKiemTra) { $theoCC[[int]$n.cc] = $n }
    $ketQua = @{}
    foreach ($n in $NutKiemTra) { $ketQua[[int]$n.cc] = @{ on = $null; off = $null; tay = 0 } }
    $tuVong = 0
    $tinKhac = 0

    # Gom tin ve trong $ms mili giay; tra ve danh sach {ms, cc, val} tren cong ve.
    function Gom-Tin([int]$ms) {
        $den = [QlsProbe]::NowMs() + $ms
        $ra = New-Object System.Collections.Generic.List[object]
        while ([QlsProbe]::NowMs() -lt $den) {
            foreach ($m in [QlsProbe]::Drain()) {
                if ($m[1] -eq 1) { $script:tuVong++; continue }
                if (([int]$m[2] -band 0xF0) -ne 0xB0) { $script:tinKhac++; continue }
                $ra.Add(@{ ms = $m[0]; cc = [int]$m[3]; val = [int]$m[4] })
            }
            Start-Sleep -Milliseconds 20
        }
        return $ra
    }

    W "KICH BAN D - kiem tra Studio One co bao lai trang thai nut."
    W "Studio One phai DANG MO bai mau, va da chay -BatTransmit + mo lai Studio One."
    W "Script se BAT roi TAT lan luot 12 nut. Xong viec mo lai app de app dong bo lai."
    W ""
    [void](Gom-Tin 1000)   # bo tin ton dong truoc khi do

    foreach ($n in $NutKiemTra) {
        foreach ($buoc in @(@{ k = "on"; v = 127 }, @{ k = "off"; v = 0 })) {
            $t0 = [QlsProbe]::NowMs()
            [void][QlsProbe]::SendCC(0, [int]$n.cc, [int]$buoc.v)
            $ve = Gom-Tin $ChoMs
            $trung = @($ve | Where-Object { $_.cc -eq [int]$n.cc })
            if ($trung.Count -gt 0) {
                $ketQua[[int]$n.cc][$buoc.k] = @{ val = $trung[-1].val; tre = ($trung[0].ms - $t0); so = $trung.Count }
            }
            foreach ($x in @($ve | Where-Object { $_.cc -ne [int]$n.cc })) {
                $ten = if ($theoCC.ContainsKey($x.cc)) { $theoCC[$x.cc].ten } else { "CC " + $x.cc }
                W ((T $x.ms) + "  [VE] tin kem theo: " + $ten + " = " + $x.val)
            }
        }
        $r = $ketQua[[int]$n.cc]
        $moTa = { param($x, $gui) if ($null -eq $x) { "gui $gui -> KHONG tra" } else { "gui $gui -> tra " + $x.val + " (tre " + $x.tre + " ms, " + $x.so + " tin)" } }
        W (("  {0,-22} CC {1,-3}  " -f $n.ten, $n.cc) + (& $moTa $r.on 127) + " | " + (& $moTa $r.off 0))
    }

    W ""
    W ("BAM TAY: trong " + $BamTaySeconds + " giay toi, dung CHUOT bam bat/tat vai nut TRONG Studio One")
    W "         (vd tham so da gan Lofi, Remix, Mute Vang). Moi tin Studio One tu bao se hien duoi day."
    $ve = Gom-Tin ($BamTaySeconds * 1000)
    foreach ($x in $ve) {
        $ten = if ($theoCC.ContainsKey($x.cc)) { $theoCC[$x.cc].ten } else { "CC " + $x.cc }
        W ((T $x.ms) + "  [TAY] " + $ten + " = " + $x.val)
        if ($theoCC.ContainsKey($x.cc)) { $ketQua[$x.cc].tay++ }
    }
    # Tra 12 nut ve TAT de Studio One khong bi bo o trang thai lung chung.
    foreach ($n in $NutKiemTra) { [void][QlsProbe]::SendCC(0, [int]$n.cc, 0) }
    Start-Sleep -Milliseconds 300
    [QlsProbe]::CloseAll()

    $coTra = @($NutKiemTra | Where-Object { $null -ne $ketQua[[int]$_.cc].on -and $null -ne $ketQua[[int]$_.cc].off })
    $khongTra = @($NutKiemTra | Where-Object { $null -eq $ketQua[[int]$_.cc].on -and $null -eq $ketQua[[int]$_.cc].off })
    $saiGiaTri = @($coTra | Where-Object { $ketQua[[int]$_.cc].on.val -lt 64 -or $ketQua[[int]$_.cc].off.val -ge 64 })
    $coTay = @($NutKiemTra | Where-Object { $ketQua[[int]$_.cc].tay -gt 0 })

    W ""
    W "-----------------------------------------------"
    W "  TOM TAT KICH BAN D"
    W "-----------------------------------------------"
    W ("  Nut tra lai ca BAT lan TAT        : " + $coTra.Count + " / " + $NutKiemTra.Count)
    W ("  Nut KHONG tra gi                  : " + $khongTra.Count + $(if ($khongTra.Count) { "  (" + (($khongTra | ForEach-Object { $_.ten }) -join ", ") + ")" } else { "" }))
    W ("  Nut tra SAI gia tri (bat<64/tat>=64): " + $saiGiaTri.Count)
    W ("  Nut Studio One tu bao khi bam tay : " + $coTay.Count + $(if ($coTay.Count) { "  (" + (($coTay | ForEach-Object { $_.ten }) -join ", ") + ")" } else { "" }))
    W ("  Tu vong tren cong chinh (bo qua)  : " + $tuVong)
    W ""
    W "  KET LUAN:"
    if ($coTra.Count -eq $NutKiemTra.Count -and $saiGiaTri.Count -eq 0) {
        W "   XAC NHAN TRANG THAI DUNG DUOC: Studio One tra lai dung tung lenh."
        W "   App co the chi coi nut la BAT khi nhan duoc phan hoi tu Studio One."
    } elseif ($coTra.Count -gt 0) {
        W "   Chi MOT PHAN nut tra lai. Nut KHONG tra thuong la nut chua gan (Control Link)"
        W "   vao tham so nao trong bai - kiem lai bai mau roi chay lai."
    } elseif ($coTay.Count -gt 0) {
        W "   Studio One KHONG tra lai lenh cua app, nhung CO bao khi bam trong Studio One."
        W "   -> Dung duoc de dong bo nguoc (Studio One -> app), KHONG xac nhan duoc lenh."
    } else {
        W "   Khong nhan duoc gi. Kiem tra: da -BatTransmit va MO LAI Studio One chua,"
        W ("   Send To = " + $BackPort + ", va cac nut da gan vao tham so trong bai chua.")
    }
    W "-----------------------------------------------"
    try {
        [IO.File]::WriteAllLines($OutFile, $log, (New-Object System.Text.UTF8Encoding($true)))
        Write-Host ""
        Write-Host ("Da luu bao cao: " + $OutFile)
        Write-Host "Gui file nay cho ky thuat. Nho chay -KhoiPhucSurface khi xong."
        if (-not $NoOpen) { Start-Process notepad.exe -ArgumentList ('"' + $OutFile + '"') }
    } catch {
        Write-Host ("[LOI] Khong ghi duoc bao cao: " + $_.Exception.Message)
    }
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 0
}

W "Dang tham do. Neu Studio One CHUA mo: mo Studio One + bai mau NGAY BAY GIO."
W "Khi bai da nap xong: KEO TAY tham so da gan Ping mot lan (xem HUONG_DAN.md)."
W "Nhan Ctrl+C de dung som - bao cao van duoc ghi."
W ""
W "  thoi gian  su kien"
W "  ---------  ------------------------------------------------------------"

$sent       = New-Object System.Collections.Generic.List[object]
$latencies  = New-Object System.Collections.Generic.List[long]
$k          = 0
$nextPing   = 0
$endMs      = [long]$Seconds * 1000
$soFirst    = $null
$winFirst   = $null
$firstBack  = $null
$firstEcho  = $null
$lastEcho   = $null
$mismatch   = 0
$backOther  = @{}
$backLines  = 0
$mainSelf   = 0
$mainOther  = 0
$lastPidSig = ""
$lastWinSig = ""
$lastStatus = -100000
$lastCpuLog = -100000
$cpuPrev    = $null
$cpuPrevMs  = 0

try {
    while ([QlsProbe]::NowMs() -lt $endMs) {
        $now = [QlsProbe]::NowMs()

        # ── Gui Ping ──
        if ($now -ge $nextPing) {
            # 10..109, hai lan lien tiep luon khac nhau -> biet chinh xac ping nao duoc tra.
            $val = 10 + (($k * 37) % 100)
            [void][QlsProbe]::SendCC(0, $PingCC, $val)
            $sent.Add(@{ ms = $now; val = $val; hit = $false })
            $k++
            $nextPing = $now + $PingMs
        }

        # ── Doc tin nhan ve ──
        foreach ($m in [QlsProbe]::Drain()) {
            $ms = $m[0]; $tag = $m[1]; $st = [int]$m[2]; $d1 = [int]$m[3]; $d2 = [int]$m[4]
            $isCC = (($st -band 0xF0) -eq 0xB0)

            if ($tag -eq 1) {
                if ($isCC -and $d1 -eq $PingCC) { $mainSelf++ }
                else {
                    $mainOther++
                    if ($mainOther -le 10) {
                        W ((T $ms) + ("  [CHINH] Co tin la tren cong chinh: status=0x{0:X2} d1={1} d2={2}" -f $st, $d1, $d2))
                    }
                }
                continue
            }

            if ($null -eq $firstBack) {
                $firstBack = $ms
                W ((T $ms) + ("  [VE] Lan dau Studio One gui ve: status=0x{0:X2} d1={1} d2={2}" -f $st, $d1, $d2))
            }

            if ($isCC -and $d1 -eq $PingCC) {
                $match = $null
                $lo = [Math]::Max(0, $sent.Count - 6)
                for ($i = $sent.Count - 1; $i -ge $lo; $i--) {
                    $e = $sent[$i]
                    if (-not $e.hit -and [Math]::Abs($e.val - $d2) -le 2) { $match = $e; break }
                }
                if ($match) {
                    $match.hit = $true
                    $lat = $ms - $match.ms
                    $latencies.Add($lat)
                    if ($null -eq $firstEcho) {
                        $firstEcho = $ms
                        W ((T $ms) + "  [PING] Studio One TRA LOI PING lan dau: gui " + $match.val + " -> nhan " + $d2 + " (tre " + $lat + " ms)")
                    }
                    $lastEcho = $ms
                } else {
                    $mismatch++
                    if ($mismatch -le 10) {
                        W ((T $ms) + "  [PING] Nhan CC " + $PingCC + "=" + $d2 + " KHONG khop ping vua gui (keo tay hoac Studio One tu gui)")
                    }
                }
            } else {
                $key = ("status=0x{0:X2} d1={1}" -f $st, $d1)
                if ($backOther.ContainsKey($key)) { $backOther[$key]++ } else { $backOther[$key] = 1 }
                $backLines++
                if ($backLines -le 40) {
                    W ((T $ms) + ("  [VE] status=0x{0:X2} d1={1} d2={2}" -f $st, $d1, $d2))
                }
            }
        }

        # ── Trang thai Studio One, moi giay ──
        if ($now - $lastStatus -ge 1000) {
            $lastStatus = $now
            $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -like "*studio one*" })
            $pids = @($procs | ForEach-Object { [int]$_.Id })
            $pidSig = (@($pids | Sort-Object) -join ",")
            if ($pidSig -ne $lastPidSig) {
                W ((T $now) + "  [SO] Tien trinh: " + $(if ($pidSig) { "PID " + $pidSig } else { "KHONG CHAY" }))
                $lastPidSig = $pidSig
                if ($pidSig -and $null -eq $soFirst) { $soFirst = $now }
                $cpuPrev = $null
            }

            if ($pids.Count -gt 0) {
                # Chi ghi cua so DANG HIEN hoac co chu "studio one" - con lai la cua so an vo nghia.
                $lines = @()
                foreach ($w in [QlsProbe]::WindowsOf([int[]]$pids)) {
                    $p = $w.Split([char]'|', 3)
                    $isMain = $p[2].ToLower().Contains("studio one")
                    if ($p[0] -eq "1" -or $isMain) {
                        $lines += ("hien=" + $p[0] + " class=" + $p[1] + " tieu_de=" + $p[2])
                    }
                    if ($isMain -and $null -eq $winFirst) {
                        $winFirst = $now
                        W ((T $now) + "  [SO] Lan dau thay cua so co chu 'Studio One' (moc app dang dung): " + $p[2])
                    }
                }
                $sig = (@($lines | Sort-Object) -join "`n")
                if ($sig -ne $lastWinSig) {
                    W ((T $now) + "  [SO] Cua so doi (" + $lines.Count + "):")
                    foreach ($l in @($lines | Sort-Object)) { W ("              " + $l) }
                    $lastWinSig = $sig
                }

                # CPU: luc nap bai thuong cao, xong thi ha - de doi chieu voi moc tra loi ping.
                $cpu = 0.0
                foreach ($pp in $procs) { try { $cpu += $pp.TotalProcessorTime.TotalMilliseconds } catch { } }
                if ($null -ne $cpuPrev -and $now -gt $cpuPrevMs -and ($now - $lastCpuLog) -ge 5000) {
                    $pct = ($cpu - $cpuPrev) / ($now - $cpuPrevMs) * 100.0 / [Environment]::ProcessorCount
                    W ((T $now) + ("  [CPU] Studio One {0:0}%" -f $pct))
                    $lastCpuLog = $now
                    $cpuPrev = $cpu; $cpuPrevMs = $now
                } elseif ($null -eq $cpuPrev) {
                    $cpuPrev = $cpu; $cpuPrevMs = $now
                }
            }
        }

        Start-Sleep -Milliseconds 50
    }
} finally {
    [QlsProbe]::CloseAll()

    $endMsReal = [QlsProbe]::NowMs()
    W ""
    W "-----------------------------------------------"
    W "  TOM TAT"
    W "-----------------------------------------------"
    W ("  Da chay                          : " + (T $endMsReal))
    W ("  Tien trinh Studio One xuat hien  : " + $(if ($null -ne $soFirst) { T $soFirst } else { "khong thay" }))
    W ("  Cua so 'Studio One' dau tien     : " + $(if ($null -ne $winFirst) { T $winFirst } else { "khong thay" }))
    W ("  Tin dau tien Studio One gui ve   : " + $(if ($null -ne $firstBack) { T $firstBack } else { "khong co" }))
    W ("  Ping duoc tra loi dau tien       : " + $(if ($null -ne $firstEcho) { T $firstEcho } else { "khong co" }))
    if ($null -ne $firstEcho -and $null -ne $winFirst) {
        W ("  -> cach moc cua so               : " + ("{0:0.0}s" -f (($firstEcho - $winFirst) / 1000.0)))
    }
    $hits = $latencies.Count
    W ("  Ping da gui / duoc tra dung      : " + $sent.Count + " / " + $hits)
    if ($hits -gt 0) {
        $sum = 0; $max = 0
        foreach ($x in $latencies) { $sum += $x; if ($x -gt $max) { $max = $x } }
        W ("  Do tre tra loi (tb / lon nhat)   : " + [Math]::Round($sum / $hits) + " ms / " + $max + " ms")
        if ($null -ne $lastEcho) {
            $pingAfter = 0
            foreach ($e in $sent) { if ($e.ms -ge $firstEcho) { $pingAfter++ } }
            W ("  Ty le tra loi sau lan dau        : " + $hits + " / " + $pingAfter)
        }
    }
    W ("  CC " + $PingCC + " ve KHONG khop ping         : " + $mismatch)
    if ($backOther.Count -gt 0) {
        W "  Tin khac Studio One gui ve       :"
        foreach ($kv in ($backOther.GetEnumerator() | Sort-Object Name)) { W ("      " + $kv.Name + "  x" + $kv.Value) }
    }
    W ("  Tu vong tren cong chinh (ping)   : " + $mainSelf + $(if ($mainIn -lt 0) { " (khong nghe duoc cong chinh)" } else { "" }))
    W ("  Tin la tren cong chinh           : " + $mainOther)
    W ""
    W "  KET LUAN:"
    if ($hits -gt 0) {
        W "   HOI-DAP MIDI DUNG DUOC. Studio One tra loi ping tu moc da ghi o tren -"
        W "   do chinh la luc bai da nap va Studio One nhan duoc MIDI."
    } elseif ($backIdx -lt 0) {
        W "   CHUA DO DUOC hoi-dap: khong co cong ve. Tao cong trong loopMIDI (HUONG_DAN.md buoc 1)."
    } elseif ($null -ne $firstBack) {
        W "   Studio One CO gui ve nhung KHONG tra loi ping. Hai kha nang:"
        W "    (a) Ping chua duoc gan (Control Link) vao tham so trong bai."
        W ("    (b) Studio One KHONG gui lai gia tri vua nhan. Neu luc keo tay tham so co")
        W ("        dong 'Nhan CC " + $PingCC + "=... KHONG khop' o tren thi chinh la (b).")
    } else {
        W "   Khong nhan duoc gi tu Studio One. Kiem tra theo HUONG_DAN.md:"
        W ("    - Thiet bi QuangLuuMIDI: Send To = " + $BackPort)
        W "    - Da chep surface.xml ban tham do + KHOI DONG LAI Studio One"
        W "    - Control 'Ping San Sang' da gan vao tham so trong bai"
    }
    if ($mainOther -gt 0) {
        W "   [!] Co tin la tren cong chinh: app dang chay, hoac Send To dang tro nham ve QuangLuuMIDI."
    }
    W "-----------------------------------------------"

    try {
        [IO.File]::WriteAllLines($OutFile, $log, (New-Object System.Text.UTF8Encoding($true)))
        Write-Host ""
        Write-Host ("Da luu bao cao: " + $OutFile)
        Write-Host "Gui file nay cho ky thuat."
        if (-not $NoOpen) { Start-Process notepad.exe -ArgumentList ('"' + $OutFile + '"') }
    } catch {
        Write-Host ("[LOI] Khong ghi duoc bao cao: " + $_.Exception.Message)
    }
}

if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
