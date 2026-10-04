param(
    [string]$OutPort  = "QuangLuuMIDI",  # cong app GUI vao = MIDI Input cua script trong Cubase
    [string]$BackPort = "QLS_PhanHoi",   # cong Cubase GUI TRA = MIDI Output cua script
    [int]$PingCC      = 49,              # ready_ping trong app_config.json
    [int]$Seconds     = 240,             # theo doi bao lau (Ctrl+C de dung som, van ghi bao cao)
    [int]$PingMs      = 1000,            # nhip gui Ping
    [string]$OutFile,                    # mac dinh: Desktop\QLS_ThamDoCubase_<MAY>_<gio>.txt
    [switch]$NoOpen,                     # khong tu mo Notepad
    [switch]$NoPause,                    # khong cho bam Enter
    [switch]$ChiKhaoSat,                 # chi in phan khao sat tinh (cai dat, prefs, cong), khong theo doi
    [switch]$CaiScript,                  # chep cubase\QuangLuu_QuangLuuMIDI.js vao thu muc MIDI Remote cua Cubase
    [switch]$GoScript                    # xoa script da chep
)
# Tham do Cubase cho Quang Luu Studio - giai doan 0 (xem docs/NGHIEN_CUU_HO_TRO_CUBASE.md).
#
# Tra loi cac cau hoi "[can do may that]":
#   - Cubase cai o dau, exe ten gi, process ten gi, prefs o dau, .cpr gan voi gi.
#   - Mo .cpr tu dong lenh thi vao thang bai hay dung o Steinberg Hub.
#   - Tieu de va class cua so chinh; hop thoai "Save changes?" la class gi (co phai #32770).
#   - Co "Release Driver when Application is in Background" trong prefs khong.
#   - Script MIDI Remote co duoc Cubase nhan, co TRA LOI ping, va bao ten kenh (san sang) luc nao.
#   - Fader 0 dB cua Cubase ung voi gia tri CC nao.
#
# Khong dung Python: goi winmm.dll (MIDI) va user32.dll (cua so) qua C#, chay tren PowerShell 5.1.

$ErrorActionPreference = "Continue"
$startWall = Get-Date
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoScript = Join-Path (Split-Path -Parent (Split-Path -Parent $here)) "cubase\QuangLuu_QuangLuuMIDI.js"
if (-not (Test-Path $repoScript)) { $repoScript = Join-Path $here "QuangLuu_QuangLuuMIDI.js" }  # ban dong goi: nam canh
$docs = [Environment]::GetFolderPath("MyDocuments")
$scriptDir = Join-Path $docs "Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI"
$scriptDst = Join-Path $scriptDir "QuangLuu_QuangLuuMIDI.js"

if (-not $OutFile) {
    $desk = [Environment]::GetFolderPath("Desktop")
    $OutFile = Join-Path $desk ("QLS_ThamDoCubase_" + $env:COMPUTERNAME + "_" + $startWall.ToString("yyyyMMdd_HHmmss") + ".txt")
}
$log = New-Object System.Collections.Generic.List[string]
function W([string]$s) { Write-Host $s; $log.Add($s) }
function T([long]$ms) { return ("{0,7:0.0}s" -f ($ms / 1000.0)) }
function Luu {
    try {
        [IO.File]::WriteAllLines($OutFile, $log, (New-Object System.Text.UTF8Encoding($true)))
        Write-Host ""; Write-Host ("Da luu bao cao: " + $OutFile)
        if (-not $NoOpen) { Start-Process notepad.exe -ArgumentList ('"' + $OutFile + '"') }
    } catch { Write-Host ("[LOI] Khong ghi duoc bao cao: " + $_.Exception.Message) }
}

# ── -CaiScript / -GoScript ─────────────────────────────────────────────────────
if ($CaiScript -or $GoScript) {
    if ($GoScript) {
        if (Test-Path $scriptDst) { Remove-Item -LiteralPath $scriptDst -Force; Write-Host ("Da xoa: " + $scriptDst) }
        else { Write-Host ("Khong co gi de xoa: " + $scriptDst) }
    } else {
        if (-not (Test-Path $repoScript)) { Write-Host ("[LOI] Khong thay file script nguon: " + $repoScript); if (-not $NoPause) { Read-Host "Enter de dong" }; exit 2 }
        New-Item -ItemType Directory -Path $scriptDir -Force | Out-Null
        Copy-Item -LiteralPath $repoScript -Destination $scriptDst -Force
        Write-Host ("Da chep script: " + $scriptDst)
        Write-Host "TIEP THEO: trong Cubase mo Lower Zone -> MIDI Remote -> (bieu tuong cai dat) -> Reload Scripts,"
        Write-Host "           hoac mo lai Cubase. Cubase tu nhan khi thay ca hai cong QuangLuuMIDI + QLS_PhanHoi."
    }
    if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
    exit 0
}

# ── Lop C#: MIDI + cua so (giong tools/tham_do_studio_one) ─────────────────────
$csharp = @"
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

public static class QlsProbeCb
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
    [DllImport("user32.dll")] static extern IntPtr GetForegroundWindow();
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    // {x, y, w, h} cua cua so
    public static int[] RectOf(long hwnd) { RECT r; GetWindowRect(new IntPtr(hwnd), out r); return new int[] { r.L, r.T, r.R - r.L, r.B - r.T }; }

    const uint CALLBACK_FUNCTION = 0x00030000;
    const uint MIM_DATA = 0x3C3;

    static readonly Stopwatch Clock = Stopwatch.StartNew();
    static readonly ConcurrentQueue<long[]> Inbox = new ConcurrentQueue<long[]>();
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
        uint n = midiInGetNumDevs(); string[] names = new string[n];
        for (uint i = 0; i < n; i++) { MIDIINCAPS c = new MIDIINCAPS(); names[i] = midiInGetDevCapsW(new UIntPtr(i), ref c, (uint)Marshal.SizeOf(c)) == 0 ? c.szPname : "?"; }
        return names;
    }
    public static string[] OutputNames() {
        uint n = midiOutGetNumDevs(); string[] names = new string[n];
        for (uint i = 0; i < n; i++) { MIDIOUTCAPS c = new MIDIOUTCAPS(); names[i] = midiOutGetDevCapsW(new UIntPtr(i), ref c, (uint)Marshal.SizeOf(c)) == 0 ? c.szPname : "?"; }
        return names;
    }
    public static uint OpenIn(int id, int tag) {
        IntPtr h; uint r = midiInOpen(out h, (uint)id, InProc, new IntPtr(tag), CALLBACK_FUNCTION);
        if (r != 0) return r; InHandles.Add(h); return midiInStart(h);
    }
    public static uint OpenOut(int id) {
        IntPtr h; uint r = midiOutOpen(out h, (uint)id, IntPtr.Zero, IntPtr.Zero, 0);
        if (r == 0) OutHandle = h; return r;
    }
    public static uint SendCC(int channel, int cc, int value) {
        if (OutHandle == IntPtr.Zero) return 999;
        uint msg = (uint)(0xB0 | (channel & 0x0F)) | ((uint)(cc & 0x7F) << 8) | ((uint)(value & 0x7F) << 16);
        return midiOutShortMsg(OutHandle, msg);
    }
    public static long[][] Drain() {
        List<long[]> list = new List<long[]>(); long[] item;
        while (Inbox.TryDequeue(out item)) list.Add(item);
        return list.ToArray();
    }
    public static void CloseAll() {
        foreach (IntPtr h in InHandles) { midiInStop(h); midiInReset(h); midiInClose(h); }
        InHandles.Clear();
        if (OutHandle != IntPtr.Zero) { midiOutClose(OutHandle); OutHandle = IntPtr.Zero; }
    }
    // Cua so top-level cua cac PID: "visible|foreground|class|hwnd|title". Ca cua so KHONG tieu de
    // cung ghi (hop thoai Cubase co the khong co tieu de), nhung chi khi dang hien.
    public static string[] WindowsOf(int[] pids) {
        List<string> found = new List<string>();
        IntPtr fg = GetForegroundWindow();
        EnumWindows(delegate(IntPtr hWnd, IntPtr l) {
            uint pid; GetWindowThreadProcessId(hWnd, out pid);
            if (Array.IndexOf(pids, (int)pid) < 0) return true;
            bool vis = IsWindowVisible(hWnd);
            StringBuilder title = new StringBuilder(512); GetWindowTextW(hWnd, title, title.Capacity);
            if (title.Length == 0 && !vis) return true;
            StringBuilder cls = new StringBuilder(256); GetClassNameW(hWnd, cls, cls.Capacity);
            found.Add(string.Format("{0}|{1}|{2}|{3}|{4}", vis ? 1 : 0, hWnd == fg ? 1 : 0, cls, hWnd.ToInt64(), title));
            return true;
        }, IntPtr.Zero);
        return found.ToArray();
    }
}
"@

W ""
W "==============================================="
W "  Quang Luu Studio - tham do Cubase / MIDI Remote"
W "==============================================="
W ("Bat dau    : " + $startWall.ToString("yyyy-MM-dd HH:mm:ss") + "   May: " + $env:COMPUTERNAME + "   " + (Get-CimInstance Win32_OperatingSystem).Caption)
W ("Tham so    : OutPort='" + $OutPort + "' BackPort='" + $BackPort + "' PingCC=" + $PingCC + " Seconds=" + $Seconds + " PingMs=" + $PingMs)
W ""

try { Add-Type -TypeDefinition $csharp -Language CSharp -ErrorAction Stop }
catch { W ("[LOI] Khong bien dich duoc phan goi MIDI: " + $_.Exception.Message); Luu; if (-not $NoPause) { Read-Host "Enter de dong" }; exit 2 }

# ── A. Khao sat tinh ───────────────────────────────────────────────────────────
W "A. CAI DAT CUBASE / STEINBERG"
$cubaseExes = @()
foreach ($root in @("$env:ProgramFiles\Steinberg", "${env:ProgramFiles(x86)}\Steinberg")) {
    if (-not (Test-Path $root)) { continue }
    foreach ($d in Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue) {
        $exes = @(Get-ChildItem -LiteralPath $d.FullName -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -Expand Name)
        W ("  " + $d.FullName + "   exe: " + $(if ($exes.Count) { $exes -join ", " } else { "(khong co)" }))
        if ($d.Name -like "Cubase*") { $cubaseExes += @($exes | ForEach-Object { Join-Path $d.FullName $_ }) }
    }
}
if (-not (Test-Path "$env:ProgramFiles\Steinberg") -and -not (Test-Path "${env:ProgramFiles(x86)}\Steinberg")) {
    W "  [CHUA CAI] Khong co thu muc Steinberg trong Program Files."
    W "  -> Cai Steinberg Download Assistant (da tai ve Downloads) -> dang nhap MySteinberg -> Cubase Pro (trial 60 ngay)."
}
W ""
W "A2. LIEN KET FILE .cpr"
try {
    $prog = (Get-ItemProperty -Path "Registry::HKEY_CLASSES_ROOT\.cpr" -ErrorAction Stop).'(default)'
    W ("  .cpr -> " + $prog)
    $cmd = (Get-ItemProperty -Path ("Registry::HKEY_CLASSES_ROOT\" + $prog + "\shell\open\command") -ErrorAction Stop).'(default)'
    W ("  lenh mo: " + $cmd)
} catch { W "  [CHUA CO] .cpr chua gan voi chuong trinh nao (Cubase chua cai hoac chua mo lan dau)." }
W ""
W "A3. PREFS CUBASE (%APPDATA%\Steinberg\Cubase*)"
$prefDirs = @(Get-ChildItem -LiteralPath (Join-Path $env:APPDATA "Steinberg") -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Cubase*" })
if ($prefDirs.Count -eq 0) { W "  (chua co - Cubase chua chay lan nao)" }
foreach ($pd in $prefDirs) {
    W ("  " + $pd.FullName)
    # "Release Driver when Application is in Background": tim moi dong co chu Release trong XML prefs.
    $hits = @(Get-ChildItem -LiteralPath $pd.FullName -Filter "*.xml" -ErrorAction SilentlyContinue |
              Select-String -Pattern "release" -SimpleMatch -CaseSensitive:$false -ErrorAction SilentlyContinue)
    if ($hits.Count -eq 0) { W "     (khong thay chu 'release' trong *.xml - co the prefs chua ghi, hay nam file khac)" }
    foreach ($h in $hits | Select-Object -First 12) { W ("     " + $h.Filename + ":" + $h.LineNumber + "  " + $h.Line.Trim()) }
    $tpl = Join-Path $pd.FullName "Project Templates"
    if (Test-Path $tpl) { W ("     Templates: " + ((Get-ChildItem -LiteralPath $tpl -ErrorAction SilentlyContinue | Select-Object -Expand Name) -join ", ")) }
}
W ""
W "A4. SCRIPT MIDI REMOTE"
W ("  Nguon (repo) : " + $repoScript + $(if (Test-Path $repoScript) { "" } else { "   [KHONG THAY]" }))
W ("  Dich (Cubase): " + $scriptDst)
if (Test-Path $scriptDst) {
    $h1 = (Get-FileHash -LiteralPath $scriptDst -Algorithm SHA256).Hash
    $h2 = if (Test-Path $repoScript) { (Get-FileHash -LiteralPath $repoScript -Algorithm SHA256).Hash } else { "" }
    W ("  Da chep: " + $(if ($h1 -eq $h2) { "GIONG ban trong repo" } else { "KHAC ban trong repo -> chay -CaiScript de cap nhat" }))
} else { W "  [CHUA CHEP] Chay: ThamDoCubase.bat -CaiScript" }
$mrRoot = Join-Path $docs "Steinberg\Cubase\MIDI Remote"
if (Test-Path $mrRoot) {
    $others = @(Get-ChildItem -LiteralPath (Join-Path $mrRoot "Driver Scripts\Local") -Directory -ErrorAction SilentlyContinue | Select-Object -Expand Name)
    W ("  Local vendors khac: " + $(if ($others.Count) { $others -join ", " } else { "(khong)" }))
    $us = Join-Path $mrRoot "User Settings"
    if (Test-Path $us) { W ("  User Settings: " + ((Get-ChildItem -LiteralPath $us -ErrorAction SilentlyContinue | Select-Object -Expand Name) -join ", ")) }
}
W ""
W "A5. CONG MIDI"
$ins  = [QlsProbeCb]::InputNames()
$outs = [QlsProbeCb]::OutputNames()
for ($i = 0; $i -lt $outs.Length; $i++) { W ("  (gui)  [" + $i + "] " + $outs[$i]) }
for ($i = 0; $i -lt $ins.Length; $i++)  { W ("  (nhan) [" + $i + "] " + $ins[$i]) }
W ""
W "A6. TIEN TRINH DANG CHAY LIEN QUAN"
$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "cubase|steinberg|activation|loopMIDI|QuangLuuStudio|Studio One" })
if ($running.Count -eq 0) { W "  (khong co)" }
foreach ($p in $running) { W ("  PID " + $p.Id + "  " + $p.ProcessName + "  " + $(try { $p.Path } catch { "" })) }
W ""

if ($ChiKhaoSat) { Luu; if (-not $NoPause) { Read-Host "Nhan Enter de dong" }; exit 0 }

# ── B. Mo cong MIDI ────────────────────────────────────────────────────────────
function Find-Port([string[]]$names, [string]$want, [string]$exclude) {
    for ($i = 0; $i -lt $names.Length; $i++) { if ($names[$i] -eq $want) { return $i } }
    for ($i = 0; $i -lt $names.Length; $i++) {
        $n = $names[$i]
        if ($n.IndexOf($want, [StringComparison]::OrdinalIgnoreCase) -lt 0) { continue }
        if ($exclude -and $n.IndexOf($exclude, [StringComparison]::OrdinalIgnoreCase) -ge 0) { continue }
        return $i
    }
    return -1
}
if (Get-Process -Name "QuangLuuStudio" -ErrorAction SilentlyContinue) { W "[!] App Quang Luu Studio DANG CHAY - dong app de ket qua sach."; W "" }
$outIdx  = Find-Port $outs $OutPort $BackPort
$mainIn  = Find-Port $ins  $OutPort $BackPort
$backIdx = Find-Port $ins  $BackPort ""
if ($outIdx -lt 0) { W ("[LOI] Khong co cong ra '" + $OutPort + "'. Chay setup_midi_ports.ps1."); Luu; if (-not $NoPause) { Read-Host "Enter de dong" }; exit 2 }
$r = [QlsProbeCb]::OpenOut($outIdx)
if ($r -ne 0) { W ("[LOI] Khong mo duoc cong ra (winmm " + $r + ")."); Luu; if (-not $NoPause) { Read-Host "Enter de dong" }; exit 2 }
W ("Gui Ping vao   : [" + $outIdx + "] " + $outs[$outIdx])
if ($backIdx -ge 0) {
    $r = [QlsProbeCb]::OpenIn($backIdx, 2)
    if ($r -eq 0) { W ("Nghe cong ve   : [" + $backIdx + "] " + $ins[$backIdx]) } else { W ("[!] Khong mo duoc cong ve (winmm " + $r + ")."); $backIdx = -1 }
} else { W ("[!] Khong co cong ve '" + $BackPort + "' -> chi do duoc cua so.") }
if ($mainIn -ge 0) { if ([QlsProbeCb]::OpenIn($mainIn, 1) -eq 0) { W ("Nghe cong chinh: [" + $mainIn + "] " + $ins[$mainIn] + " (kiem tu vong)") } else { $mainIn = -1 } }
W ""
W "Dang theo doi. Neu Cubase CHUA mo: bam dup file .cpr bai mau NGAY BAY GIO."
W "Khi bai da nap: (1) keo fader kenh Mic ve dung 0 dB, (2) bam Mute kenh Nhac roi bo,"
W "(3) sua gi do roi DONG Cubase de hien hop thoai Save -> script ghi lai class/tieu de."
W "Nhan Ctrl+C de dung som - bao cao van duoc ghi."
W ""
W "  thoi gian  su kien"
W "  ---------  ------------------------------------------------------------"

# ── C. Vong theo doi ───────────────────────────────────────────────────────────
$sent = New-Object System.Collections.Generic.List[object]
$lat  = New-Object System.Collections.Generic.List[long]
$k = 0; $nextPing = 0; $endMs = [long]$Seconds * 1000
$procFirst = $null; $winFirst = $null; $mainWinFirst = $null; $firstBack = $null; $firstEcho = $null
$tenKenhFirst = $null; $tenKenh = @{}; $faderVe = @{}; $muteVe = @{}; $pluginParams = $null
$mismatch = 0; $backOther = @{}; $backLines = 0; $mainSelf = 0; $mainOther = 0
$lastPidSig = ""; $lastWinSig = ""; $lastStatus = -100000
$seenWin = @{}   # "class|title" -> lan dau thay (ms)
$dialogs  = New-Object System.Collections.Generic.List[string]

try {
    while ([QlsProbeCb]::NowMs() -lt $endMs) {
        $now = [QlsProbeCb]::NowMs()
        if ($now -ge $nextPing) {
            $val = 10 + (($k * 37) % 100)
            [void][QlsProbeCb]::SendCC(0, $PingCC, $val)
            $sent.Add(@{ ms = $now; val = $val; hit = $false }); $k++; $nextPing = $now + $PingMs
        }
        foreach ($m in [QlsProbeCb]::Drain()) {
            $ms = $m[0]; $tag = $m[1]; $st = [int]$m[2]; $d1 = [int]$m[3]; $d2 = [int]$m[4]
            $isCC = (($st -band 0xF0) -eq 0xB0)
            if ($tag -eq 1) {
                if ($isCC -and $d1 -eq $PingCC) { $mainSelf++ } else { $mainOther++; if ($mainOther -le 10) { W ((T $ms) + ("  [CHINH] Tin la tren cong chinh: status=0x{0:X2} d1={1} d2={2}" -f $st, $d1, $d2)) } }
                continue
            }
            if ($null -eq $firstBack) { $firstBack = $ms; W ((T $ms) + ("  [VE] Lan dau Cubase gui ve: status=0x{0:X2} d1={1} d2={2}" -f $st, $d1, $d2)) }
            if (-not $isCC) { $backLines++; if ($backLines -le 40) { W ((T $ms) + ("  [VE] status=0x{0:X2} d1={1} d2={2}" -f $st, $d1, $d2)) }; continue }

            if ($d1 -eq $PingCC) {
                $match = $null; $lo = [Math]::Max(0, $sent.Count - 6)
                for ($i = $sent.Count - 1; $i -ge $lo; $i--) { $e = $sent[$i]; if (-not $e.hit -and [Math]::Abs($e.val - $d2) -le 2) { $match = $e; break } }
                if ($match) {
                    $match.hit = $true; $l = $ms - $match.ms; $lat.Add($l)
                    if ($null -eq $firstEcho) { $firstEcho = $ms; W ((T $ms) + "  [PING] Cubase TRA LOI PING lan dau: gui " + $match.val + " -> nhan " + $d2 + " (tre " + $l + " ms)") }
                } else { $mismatch++; if ($mismatch -le 10) { W ((T $ms) + "  [PING] CC " + $PingCC + "=" + $d2 + " khong khop ping vua gui") } }
            } elseif ($d1 -ge 60 -and $d1 -le 67) {
                $idx = $d1 - 60
                if ($null -eq $tenKenhFirst) { $tenKenhFirst = $ms; W ((T $ms) + "  [KENH] Lan dau Cubase bao ten kenh (bai da nap toi mixer): kenh " + $idx + " do dai ten " + $d2) }
                elseif (-not $tenKenh.ContainsKey($idx)) { W ((T $ms) + "  [KENH] kenh " + $idx + " do dai ten " + $d2) }
                $tenKenh[$idx] = $d2
            } elseif ($d1 -ge 20 -and $d1 -le 23) {
                $faderVe[$d1] = $d2; W ((T $ms) + "  [FADER] CC " + $d1 + " = " + $d2 + "  (keo tay ve 0 dB roi doc gia tri nay; Studio One = 76)")
            } elseif ($d1 -ge 50 -and $d1 -le 53) {
                $muteVe[$d1] = $d2; W ((T $ms) + "  [MUTE] CC " + $d1 + " = " + $d2)
            } elseif ($d1 -eq 70) {
                $pluginParams = $d2; W ((T $ms) + "  [PLUGIN] insert slot kenh Mic doi, so tham so = " + $d2 + " (chi tiet tag/ten xem Script Console trong Cubase)")
            } else {
                $key = ("CC " + $d1); if ($backOther.ContainsKey($key)) { $backOther[$key]++ } else { $backOther[$key] = 1 }
                $backLines++; if ($backLines -le 40) { W ((T $ms) + "  [VE] CC " + $d1 + " = " + $d2) }
            }
        }

        if ($now - $lastStatus -ge 500) {
            $lastStatus = $now
            $procs = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match "cubase" })
            $pids = @($procs | ForEach-Object { [int]$_.Id })
            $pidSig = (@($pids | Sort-Object) -join ",")
            if ($pidSig -ne $lastPidSig) {
                $names = (@($procs | ForEach-Object { $_.ProcessName + ".exe" } | Sort-Object -Unique) -join ", ")
                W ((T $now) + "  [CB] Tien trinh: " + $(if ($pidSig) { "PID " + $pidSig + " (" + $names + ")" } else { "KHONG CHAY" }))
                $lastPidSig = $pidSig
                if ($pidSig -and $null -eq $procFirst) { $procFirst = $now }
            }
            if ($pids.Count -gt 0) {
                $lines = @()
                foreach ($w in [QlsProbeCb]::WindowsOf([int[]]$pids)) {
                    $p = $w.Split([char]'|', 5)
                    $vis = $p[0]; $fg = $p[1]; $cls = $p[2]; $title = $p[4]
                    if ($vis -ne "1" -and $title.Length -eq 0) { continue }
                    $lines += ("hien=" + $vis + " fg=" + $fg + " class=" + $cls + " tieu_de=" + $title)
                    $key = $cls + "|" + $title
                    if (-not $seenWin.ContainsKey($key)) {
                        $seenWin[$key] = $now
                        if ($null -eq $winFirst) { $winFirst = $now; W ((T $now) + "  [CB] Cua so dau tien: class=" + $cls + " tieu_de=" + $title) }
                        $tl = $title.ToLower()
                        if ($null -eq $mainWinFirst -and $tl.Contains("cubase") -and ($tl.Contains("project") -or $tl.Contains(".cpr"))) {
                            $mainWinFirst = $now; W ((T $now) + "  [CB] Cua so PROJECT dau tien (moc 'co cua so chinh'): " + $title)
                        }
                        if ($tl.Contains("hub")) { W ((T $now) + "  [CB] THAY STEINBERG HUB: " + $title + " (mo .cpr ma van hien Hub = can xu ly)") }
                        # Hop thoai Cubase: cung class SteinbergWindowClass*, tieu de chi "Cubase Pro", kich thuoc nho (do 2026-10-04: 295x126)
                        $isSmall = $false
                        if ($p.Length -ge 5) { try { $rc = [QlsProbeCb]::RectOf([long]$p[3]); $isSmall = ($rc[2] -lt 700 -and $rc[3] -lt 400) } catch { } }
                        if ($vis -eq "1" -and ($cls -eq "#32770" -or $tl.Contains("save") -or $tl.Contains("luu") -or ($isSmall -and -not $tl.Contains("project")))) {
                            $dialogs.Add($cls + " | " + $title); W ((T $now) + "  [HOP THOAI] class=" + $cls + " tieu_de=" + $title)
                        }
                    }
                }
                $sig = (@($lines | Sort-Object) -join "`n")
                if ($sig -ne $lastWinSig) {
                    W ((T $now) + "  [CB] Cua so doi (" + $lines.Count + "):")
                    foreach ($l in @($lines | Sort-Object)) { W ("              " + $l) }
                    $lastWinSig = $sig
                }
            }
        }
        Start-Sleep -Milliseconds 50
    }
} finally {
    [QlsProbeCb]::CloseAll()
    $endReal = [QlsProbeCb]::NowMs()
    W ""
    W "-----------------------------------------------"
    W "  TOM TAT"
    W "-----------------------------------------------"
    W ("  Da chay                           : " + (T $endReal))
    W ("  Tien trinh Cubase xuat hien       : " + $(if ($null -ne $procFirst) { T $procFirst } else { "khong thay" }))
    W ("  Cua so dau tien                   : " + $(if ($null -ne $winFirst) { T $winFirst } else { "khong thay" }))
    W ("  Cua so PROJECT dau tien           : " + $(if ($null -ne $mainWinFirst) { T $mainWinFirst } else { "khong thay" }))
    W ("  Cubase bao ten kenh (san sang)    : " + $(if ($null -ne $tenKenhFirst) { T $tenKenhFirst } else { "khong co" }))
    W ("  Ping duoc tra loi dau tien        : " + $(if ($null -ne $firstEcho) { T $firstEcho } else { "khong co" }))
    if ($null -ne $mainWinFirst) {
        if ($null -ne $tenKenhFirst) { W ("  -> ten kenh cach cua so project    : " + ("{0:0.0}s" -f (($tenKenhFirst - $mainWinFirst) / 1000.0))) }
        if ($null -ne $firstEcho)    { W ("  -> ping cach cua so project        : " + ("{0:0.0}s" -f (($firstEcho - $mainWinFirst) / 1000.0))) }
    }
    W ("  Ping gui / tra dung               : " + $sent.Count + " / " + $lat.Count)
    if ($lat.Count -gt 0) { $s = 0; $mx = 0; foreach ($x in $lat) { $s += $x; if ($x -gt $mx) { $mx = $x } }; W ("  Do tre (tb / lon nhat)            : " + [Math]::Round($s / $lat.Count) + " ms / " + $mx + " ms") }
    W ("  Ten kenh da bao (kenh: do dai)    : " + $(if ($tenKenh.Count) { (($tenKenh.GetEnumerator() | Sort-Object Name | ForEach-Object { "" + $_.Name + ":" + $_.Value }) -join ", ") } else { "(khong)" }))
    W ("  Fader ve lan cuoi (CC: gia tri)   : " + $(if ($faderVe.Count) { (($faderVe.GetEnumerator() | Sort-Object Name | ForEach-Object { "" + $_.Name + "=" + $_.Value }) -join ", ") } else { "(khong)" }))
    W ("  Mute ve lan cuoi                  : " + $(if ($muteVe.Count) { (($muteVe.GetEnumerator() | Sort-Object Name | ForEach-Object { "" + $_.Name + "=" + $_.Value }) -join ", ") } else { "(khong)" }))
    W ("  Plugin insert Mic: so tham so     : " + $(if ($null -ne $pluginParams) { $pluginParams } else { "(chua bao)" }))
    W ("  Hop thoai da thay                 : " + $(if ($dialogs.Count) { ($dialogs | Sort-Object -Unique) -join " ; " } else { "(khong)" }))
    W ("  Tu vong cong chinh / tin la       : " + $mainSelf + " / " + $mainOther)
    if ($backOther.Count -gt 0) { W "  CC khac Cubase gui ve             :"; foreach ($kv in ($backOther.GetEnumerator() | Sort-Object Name)) { W ("      " + $kv.Name + "  x" + $kv.Value) } }
    W ""
    W "  MOI CUA SO DA THAY (class | tieu de | lan dau):"
    foreach ($kv in ($seenWin.GetEnumerator() | Sort-Object Value)) { $p = $kv.Name.Split([char]'|', 2); W ("    " + (T $kv.Value) + "  " + $p[0] + " | " + $p[1]) }
    W ""
    W "  KET LUAN:"
    if ($lat.Count -gt 0 -and $null -ne $tenKenhFirst) { W "   Script MIDI Remote CHAY DUNG: Cubase tra loi ping va bao ten kenh. Dung mOnTitleChange lam moc 'san sang'." }
    elseif ($lat.Count -gt 0) { W "   Cubase tra loi ping nhung KHONG bao ten kenh: bai chua nap, hoac mixer bank zone khong co kenh (xem Script Console)." }
    elseif ($backIdx -lt 0) { W "   Chua do duoc hoi-dap: khong co cong ve. Chay setup_midi_ports.ps1." }
    elseif ($null -ne $procFirst) { W "   Cubase chay nhung KHONG gui gi ve. Kiem: -CaiScript da chep? Reload Scripts? MIDI Remote Manager co thay 'QuangLuu QuangLuuMIDI' khong? Cong co bi 'All MIDI Inputs' chiem?" }
    else { W "   Khong thay Cubase chay trong luc theo doi." }
    W "-----------------------------------------------"
    Luu
}
if (-not $NoPause) { Read-Host "Nhan Enter de dong" }
