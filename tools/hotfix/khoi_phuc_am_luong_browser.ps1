# Khoi phuc am luong trinh duyet trong Windows Volume Mixer ve 100%.
#
# Boi canh: QuangLuuStudio (truoc ban sua trong 1.8.0) luc khoi dong dong bo thanh "Nhac" sang
# trinh duyet. Khi chua co ket noi CDP toi YouTube, app roi xuong nhanh pycaw va
# ha am luong *ung dung* chrome/edge/... trong Volume Mixer xuong bang muc thanh
# truot. Sau do thanh truot chi dieu khien player YouTube (qua CDP) nen muc trong
# Volume Mixer bi ket o muc thap. Script nay dat lai muc do ve 100% (bo mute).
#
# Cach dung (khong can Python, khong can cai gi them):
#   .\khoi_phuc_am_luong_browser.ps1            # sua mot lan roi thoat
#   .\khoi_phuc_am_luong_browser.ps1 -Watch     # canh lien tuc, app ha xuong la keo len lai
#   .\khoi_phuc_am_luong_browser.ps1 -List      # chi liet ke moi session audio, khong sua
#   .\khoi_phuc_am_luong_browser.ps1 -Level 80  # dat ve 80% thay vi 100%
#
# Luu y: Windows chi co session audio cua trinh duyet khi trinh duyet dang chay
# va da tung phat am thanh. Trinh duyet chua mo thi script khong co gi de sua —
# mo trinh duyet, phat 1 video roi chay lai.

[CmdletBinding()]
param(
    [switch]$Watch,
    [switch]$List,
    [ValidateRange(0, 100)][int]$Level = 100,
    [int]$IntervalSec = 2,
    [string[]]$Names = @("chrome", "msedge", "opera", "firefox", "brave", "vivaldi", "chromium")
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

if (-not ("QLS.AudioSessionFix" -as [type])) {
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;

namespace QLS {
    [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
    class MMDeviceEnumeratorComObject { }

    [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceEnumerator {
        int EnumAudioEndpoints(int dataFlow, int stateMask, out IMMDeviceCollection devices);
        int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice device);
        int GetDevice(string id, out IMMDevice device);
        int RegisterEndpointNotificationCallback(IntPtr client);
        int UnregisterEndpointNotificationCallback(IntPtr client);
    }

    [Guid("0BD7A1BE-7A1A-44DB-8397-CC5392387B5E"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDeviceCollection {
        int GetCount(out int count);
        int Item(int index, out IMMDevice device);
    }

    [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IMMDevice {
        int Activate(ref Guid iid, int clsCtx, IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object iface);
        int OpenPropertyStore(int access, out IntPtr store);
        int GetId([MarshalAs(UnmanagedType.LPWStr)] out string id);
        int GetState(out int state);
    }

    [Guid("77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionManager2 {
        int GetAudioSessionControl(IntPtr sessionId, int streamFlags, out IAudioSessionControl ctl);
        int GetSimpleAudioVolume(IntPtr sessionId, int streamFlags, out ISimpleAudioVolume vol);
        int GetSessionEnumerator(out IAudioSessionEnumerator enumerator);
        int RegisterSessionNotification(IntPtr n);
        int UnregisterSessionNotification(IntPtr n);
        int RegisterDuckNotification(string sessionId, IntPtr n);
        int UnregisterDuckNotification(IntPtr n);
    }

    [Guid("E2F5BB11-0570-40CA-ACDD-3AA01277DEE8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionEnumerator {
        int GetCount(out int count);
        int GetSession(int index, out IAudioSessionControl session);
    }

    [Guid("F4B1A599-7266-4319-A8CA-E70ACB11E8CD"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionControl {
        int GetState(out int state);
        int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string value, IntPtr eventContext);
        int GetIconPath([MarshalAs(UnmanagedType.LPWStr)] out string path);
        int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string value, IntPtr eventContext);
        int GetGroupingParam(out Guid param);
        int SetGroupingParam(ref Guid param, IntPtr eventContext);
        int RegisterAudioSessionNotification(IntPtr client);
        int UnregisterAudioSessionNotification(IntPtr client);
    }

    [Guid("BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IAudioSessionControl2 {
        // IAudioSessionControl (phai khai bao lai de giu dung thu tu vtable)
        int GetState(out int state);
        int GetDisplayName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        int SetDisplayName([MarshalAs(UnmanagedType.LPWStr)] string value, IntPtr eventContext);
        int GetIconPath([MarshalAs(UnmanagedType.LPWStr)] out string path);
        int SetIconPath([MarshalAs(UnmanagedType.LPWStr)] string value, IntPtr eventContext);
        int GetGroupingParam(out Guid param);
        int SetGroupingParam(ref Guid param, IntPtr eventContext);
        int RegisterAudioSessionNotification(IntPtr client);
        int UnregisterAudioSessionNotification(IntPtr client);
        // IAudioSessionControl2
        int GetSessionIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string id);
        int GetSessionInstanceIdentifier([MarshalAs(UnmanagedType.LPWStr)] out string id);
        int GetProcessId(out uint pid);
        int IsSystemSoundsSession();
        int SetDuckingPreference(bool optOut);
    }

    [Guid("87CE5498-68D6-44E5-9215-6DA47EF883D8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface ISimpleAudioVolume {
        int SetMasterVolume(float level, IntPtr eventContext);
        int GetMasterVolume(out float level);
        int SetMute(bool mute, IntPtr eventContext);
        int GetMute(out bool mute);
    }

    public class SessionInfo {
        public string Device;
        public uint Pid;
        public string Process;
        public float Before;
        public bool MutedBefore;
        public float After;
        public bool Changed;
    }

    public static class AudioSessionFix {
        const int eRender = 0;
        const int DEVICE_STATE_ACTIVE = 1;
        const int CLSCTX_ALL = 23;

        static string ProcName(uint pid) {
            if (pid == 0) return "(system)";
            try { return Process.GetProcessById((int)pid).ProcessName.ToLowerInvariant(); }
            catch { return "(pid " + pid + ")"; }
        }

        // names: ten process (khong .exe, chu thuong); null = moi session.
        // level: 0..1; doSet=false chi doc.
        public static List<SessionInfo> Apply(string[] names, float level, bool doSet) {
            var result = new List<SessionInfo>();
            var en = (IMMDeviceEnumerator)new MMDeviceEnumeratorComObject();
            IMMDeviceCollection coll;
            Marshal.ThrowExceptionForHR(en.EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, out coll));
            int nDev; coll.GetCount(out nDev);
            for (int d = 0; d < nDev; d++) {
                IMMDevice dev; coll.Item(d, out dev);
                string devId; dev.GetId(out devId);
                object o; Guid iid = typeof(IAudioSessionManager2).GUID;
                if (dev.Activate(ref iid, CLSCTX_ALL, IntPtr.Zero, out o) != 0) continue;
                var mgr = (IAudioSessionManager2)o;
                IAudioSessionEnumerator se;
                if (mgr.GetSessionEnumerator(out se) != 0) continue;
                int nSes; se.GetCount(out nSes);
                for (int i = 0; i < nSes; i++) {
                    IAudioSessionControl ctl;
                    if (se.GetSession(i, out ctl) != 0) continue;
                    var ctl2 = (IAudioSessionControl2)ctl;
                    uint pid; ctl2.GetProcessId(out pid);
                    string pname = ProcName(pid);
                    if (names != null && Array.IndexOf(names, pname) < 0) continue;
                    var vol = (ISimpleAudioVolume)ctl;
                    var info = new SessionInfo { Device = devId, Pid = pid, Process = pname };
                    vol.GetMasterVolume(out info.Before);
                    vol.GetMute(out info.MutedBefore);
                    info.After = info.Before;
                    if (doSet) {
                        bool needVol = Math.Abs(info.Before - level) > 0.005f;
                        if (needVol) vol.SetMasterVolume(level, IntPtr.Zero);
                        if (info.MutedBefore) vol.SetMute(false, IntPtr.Zero);
                        vol.GetMasterVolume(out info.After);
                        info.Changed = needVol || info.MutedBefore;
                    }
                    result.Add(info);
                }
            }
            return result;
        }
    }
}
"@
}

$target = [float]($Level / 100.0)
$nameList = $Names | ForEach-Object { $_.ToLowerInvariant() -replace '\.exe$', '' }

function Show-Sessions($items) {
    foreach ($s in $items) {
        $mute = if ($s.MutedBefore) { " [MUTE]" } else { "" }
        $tag  = if ($s.Changed) { "  -> {0,3}%" -f [int][math]::Round($s.After * 100) } else { "" }
        "{0,-14} pid {1,-6} {2,3}%{3}{4}" -f $s.Process, $s.Pid, [int][math]::Round($s.Before * 100), $mute, $tag
    }
}

if ($List) {
    $all = [QLS.AudioSessionFix]::Apply($null, $target, $false)
    if ($all.Count -eq 0) { "Khong co session audio nao dang mo." } else { Show-Sessions $all }
    exit 0
}

if ($Watch) {
    "Dang canh am luong trinh duyet ($($nameList -join ', ')) moi $IntervalSec giay. Ctrl+C de dung."
    while ($true) {
        try {
            $r = [QLS.AudioSessionFix]::Apply($nameList, $target, $true)
            $changed = @($r | Where-Object { $_.Changed })
            if ($changed.Count -gt 0) {
                "[{0}] Keo len {1}%:" -f (Get-Date -Format "HH:mm:ss"), $Level
                Show-Sessions $changed
            }
        } catch { "Loi: $($_.Exception.Message)" }
        Start-Sleep -Seconds $IntervalSec
    }
}

$r = [QLS.AudioSessionFix]::Apply($nameList, $target, $true)
if ($r.Count -eq 0) {
    "Khong thay session audio cua trinh duyet nao ($($nameList -join ', '))."
    "Mo trinh duyet, phat mot video roi chay lai script nay."
    exit 2
}
Show-Sessions $r
$n = @($r | Where-Object { $_.Changed }).Count
if ($n -gt 0) { "Da dat lai $n session ve $Level%." } else { "Tat ca da o $Level%, khong can sua." }
