# ============================================================
#  Quang Luu Studio - Send ALL MIDI Keys
#  Dung winmm.dll (co san tren moi Windows)
#  Khong can Python, khong can cai them gi
# ============================================================

# -- Load Windows MIDI API (winmm.dll) via C# P/Invoke --
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public class WinMidi {
    [DllImport("winmm.dll")]
    public static extern int midiOutGetNumDevs();

    [DllImport("winmm.dll", CharSet = CharSet.Auto)]
    public static extern int midiOutGetDevCaps(int deviceId, ref MIDIOUTCAPS caps, int capsSize);

    [DllImport("winmm.dll")]
    public static extern int midiOutOpen(out IntPtr handle, int deviceId, IntPtr callback, IntPtr instance, int flags);

    [DllImport("winmm.dll")]
    public static extern int midiOutShortMsg(IntPtr handle, int message);

    [DllImport("winmm.dll")]
    public static extern int midiOutClose(IntPtr handle);
}

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
public struct MIDIOUTCAPS {
    public short   wMid;
    public short   wPid;
    public int     vDriverVersion;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
    public string  szPname;
    public short   wTechnology;
    public short   wVoices;
    public short   wNotes;
    public short   wChannelMask;
    public int     dwSupport;
}
"@

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Quang Luu Studio - Send ALL MIDI Keys" -ForegroundColor Cyan
Write-Host "  Port: QuangLuuMIDI" -ForegroundColor Cyan
Write-Host "============================================================`n" -ForegroundColor Cyan

# -- Toan bo CC map tu app_config.json --
$ccMap = [ordered]@{
    "tone_music"    = 10
    "tone_voice"    = 11
    "mix_music"     = 20
    "mix_mic"       = 21
    "mix_reverb"    = 22
    "mix_backing"   = 23
    "mode"          = 30
    "autokey"       = 31
    "score_trigger" = 32
    "key_root"      = 33
    "key_scale"     = 34
    "scale_type"    = 35
    "tune_on_off"   = 36
    "mute_music"    = 50
    "mute_mic"      = 51
    "mute_reverb"   = 52
    "mute_backing"  = 53
    "mix_reverb_ex" = 41
}

# -- Liet ke cac MIDI Out port hien co --
$numDevs = [WinMidi]::midiOutGetNumDevs()
Write-Host "[INFO] Tim thay $numDevs MIDI Out port(s):" -ForegroundColor Gray

$targetDevId = -1
$caps = New-Object MIDIOUTCAPS
$capsSize = [System.Runtime.InteropServices.Marshal]::SizeOf($caps)

for ($i = 0; $i -lt $numDevs; $i++) {
    [WinMidi]::midiOutGetDevCaps($i, [ref]$caps, $capsSize) | Out-Null
    $portName = $caps.szPname
    Write-Host "  [$i] $portName" -ForegroundColor Gray
    if ($portName -like "*QuangLuuMIDI*") {
        $targetDevId = $i
    }
}

Write-Host ""

if ($targetDevId -lt 0) {
    Write-Host "[LOI] Khong tim thay port 'QuangLuuMIDI'!" -ForegroundColor Red
    Write-Host "      Vui long mo loopMIDI va tao port ten 'QuangLuuMIDI' truoc." -ForegroundColor Yellow
    Read-Host "`nNhan Enter de thoat"
    exit 1
}

# -- Mo port --
$handle = [IntPtr]::Zero
$result = [WinMidi]::midiOutOpen([ref]$handle, $targetDevId, [IntPtr]::Zero, [IntPtr]::Zero, 0)

if ($result -ne 0 -or $handle -eq [IntPtr]::Zero) {
    Write-Host "[LOI] Khong the mo MIDI port! Ma loi: $result" -ForegroundColor Red
    Read-Host "`nNhan Enter de thoat"
    exit 1
}

Write-Host "[OK] Da ket noi port [$targetDevId]`n" -ForegroundColor Green

# -- Gui tung CC (64 -> 0 de Studio One learn) --
$success = 0
$fail    = 0
$channel = 0x00  # Channel 1

foreach ($entry in $ccMap.GetEnumerator()) {
    $name = $entry.Key
    $cc   = $entry.Value

    try {
        # CC message: status=0xB0, cc, value
        # Packed as DWORD: value<<16 | cc<<8 | status
        $msgOn  = (64 -shl 16) -bor ($cc -shl 8) -bor (0xB0 -bor $channel)
        $msgOff = ( 0 -shl 16) -bor ($cc -shl 8) -bor (0xB0 -bor $channel)

        [WinMidi]::midiOutShortMsg($handle, $msgOn)  | Out-Null
        Start-Sleep -Milliseconds 150
        [WinMidi]::midiOutShortMsg($handle, $msgOff) | Out-Null
        Start-Sleep -Milliseconds 80

        Write-Host ("  [OK] {0,-16}  CC={1,3}  -> 64, 0" -f $name, $cc) -ForegroundColor Green
        $success++
    } catch {
        Write-Host ("  [!!] {0,-16}  CC={1,3}  -> LOI: {2}" -f $name, $cc, $_) -ForegroundColor Red
        $fail++
    }
}

# -- Dong port va ket qua --
[WinMidi]::midiOutClose($handle) | Out-Null

Write-Host ""
Write-Host "[XONG] Tong: $success thanh cong, $fail loi." -ForegroundColor Cyan
Write-Host ""
Read-Host "Nhan Enter de thoat"
