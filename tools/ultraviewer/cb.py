# -*- coding: utf-8 -*-
"""Dieu khien may khach qua cua so UltraViewer tren may dev - KHONG can doc anh chup.

Chay bang Python Windows (.venv) tu WSL qua cb.sh. Toa do truyen vao la toa do MAN HINH KHACH
(1920x1080); OFF = goc man hinh khach tren man hinh dev (UltraViewer phong to, man dev 2560x1440).

Lenh chinh (xem docs/QUY_TRINH_UV_CUBASE.md):
  focus                      dua cua so UltraViewer len truoc
  calib                      tu do goc + ty le anh may khach trong cua so UltraViewer (chay dau phien, hoac khi doi man hinh)
  who                        in ten may khach (tieu de cua so UltraViewer)
  quiet [giay]               chup 2 lan cach nhau, in % o thay doi + vung thay doi -> co nguoi dang dung?
  shot [x y w h] [file]      chup man hinh khach (toan bo hoac vung)
  ocr [x y w h]              doc chu tren man hinh khach: moi dong "x,y,w,h<TAB>chu"
  find CHU [x y w h]         tim dong chu (khong phan biet hoa/thuong/dau), in "x y" tam dong; exit 1 neu khong thay
  clickt CHU [--dx N --dy N --right --exact --near MOC] [x y w h]   tim chu roi bam (lech dx,dy so voi tam dong; --near: lay dong gan chu MOC)
  click|dbl|rclick|move X Y  drag X1 Y1 X2 Y2  key K...  hotkey K...  type CHU
  clip set FILE | clip get   clipboard may dev (UltraViewer dong bo sang may khach va nguoc lai)
  agent                      dat lenh khoi dong agent PowerShell vao clipboard (dan vao console may khach)
  rpc "CODE" | rpc @FILE     gui code PowerShell cho agent qua clipboard, in ket qua (#QLSOUT)
  deploy FILE                ghi FILE thanh script MIDI Remote tren may khach (backup .bak), qua agent
  midi CC VAL [KENH]         gui CC thang vao cong QuangLuuMIDI tren may khach (bo qua app) de thu script Cubase
  midis CC V1 V2 [STEP] [KENH]  quet dai gia tri (250 ms/lan) de do bang gia tri roi rac, doc disp[] tren console
  activate TIEU_DE           dua cua so len truoc theo tieu de (qua agent, khong can chuot)
  wins                       liet ke tieu de cac cua so dang hien tren may khach (qua agent)
  win TIEU_DE max|restore|min|front   phong to / tra lai / thu nho / dua len truoc cua so may khach (qua agent)
  info                       thong tin may khach: app/exe/config CC/loopMIDI/script/Cubase/log
"""
import sys, time, subprocess, os, re, asyncio, unicodedata
import pyautogui, pygetwindow
from PIL import Image, ImageChops

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05
SIZE = (1920, 1080)          # man hinh khach (toa do logic ma moi lenh dung)
TMP = os.path.join(os.environ.get('LOCALAPPDATA', r'C:\Users\Public'), 'Temp', 'qls_cb')
os.makedirs(TMP, exist_ok=True)
CALIB = os.path.join(TMP, 'calib.txt')     # "offx offy scale" do lenh calib ghi
OFF, SCALE = (294, 192), 1.0
if os.path.exists(CALIB):
    try:
        _ox, _oy, _sc = open(CALIB).read().split()
        OFF, SCALE = (int(_ox), int(_oy)), float(_sc)
    except Exception:
        pass
OFF = (int(os.environ.get('QLS_OFFX', OFF[0])), int(os.environ.get('QLS_OFFY', OFF[1])))
SCALE = float(os.environ.get('QLS_SCALE', SCALE))
OUT = os.path.join(TMP, 'shot.png')
SCRIPT_REL = r"\Steinberg\Cubase\MIDI Remote\Driver Scripts\Local\QuangLuu\QuangLuuMIDI"
SCRIPT_NAME = 'QuangLuu_QuangLuuMIDI.js'

AGENT = ("$h=(Get-Date).AddHours(4);$l='';'QLS agent chay den '+$h.ToString('HH:mm');"
         "while((Get-Date) -lt $h){Start-Sleep -m 500;$c=[string](Get-Clipboard -Raw);"
         "if($c -ne $l -and $c.StartsWith('#QLSCMD')){$l=$c;"
         "try{$o=(Invoke-Expression $c.Substring(8) 2>&1|Out-String)}catch{$o='ERR '+$_};"
         "Set-Clipboard ('#QLSOUT'+[char]10+$o);'cmd ok '+(Get-Date).ToString('HH:mm:ss')}}")

INFO_PS = r"""$o=@();$o+='PC '+$env:COMPUTERNAME+' '+$env:USERNAME
$p=Get-Process -Name 'QuangLuu*' -EA 0|select -First 1
if($p){$o+='EXE '+$p.Path;$cf=Join-Path (Split-Path $p.Path) 'app_config.json'
 if(Test-Path $cf){$o+='CFG '+((Select-String -Path $cf -Pattern 'tone_music|tone_voice|"be"|key_root|scale_type' | % {$_.Line.Trim()}) -join ' ')}}else{$o+='NO APP'}
$lm=Get-Process -Name 'loopMIDI*' -EA 0;$o+='LOOPMIDI '+$(if($lm){'running'}else{'NOT running'})
$k=Get-Item 'HKCU:\Software\Tobias Erichsen\loopMIDI\Ports' -EA 0;if($k){$o+='PORTS '+(($k.GetValueNames()) -join ', ')}else{$o+='PORTS key missing'}
$d=[Environment]::GetFolderPath('MyDocuments')+'SCRIPT_REL\SCRIPT_NAME'
$o+='SCRIPT '+$d+' '+$(if(Test-Path $d){(Get-Item $d).Length.ToString()+' bytes '+(Get-Item $d).LastWriteTime}else{'MISSING'})
$cb=Get-Process -Name 'Cubase*' -EA 0|select -First 1;if($cb){$o+='CUBASE '+$cb.Path}
$lg=Join-Path $env:APPDATA 'QuangLuuStudio\logs\app.log'
if(Test-Path $lg){$o+='LOG '+$lg;$o+=(Get-Content $lg -Tail 300 | Select-String 'MIDI|KEY\]|Cubase' | select -Last 12 | % {$_.Line})}
$o -join "`n"
""".replace('SCRIPT_REL', SCRIPT_REL).replace('SCRIPT_NAME', SCRIPT_NAME)


WIN_PS = r"""
if(-not ('W2' -as [type])){Add-Type @"
using System;using System.Text;using System.Runtime.InteropServices;using System.Collections.Generic;
public class W2{public delegate bool EnumProc(IntPtr h,IntPtr l);
[DllImport("user32.dll")]public static extern bool EnumWindows(EnumProc p,IntPtr l);
[DllImport("user32.dll")]public static extern int GetWindowText(IntPtr h,StringBuilder s,int n);
[DllImport("user32.dll")]public static extern bool IsWindowVisible(IntPtr h);
[DllImport("user32.dll")]public static extern bool ShowWindow(IntPtr h,int n);
[DllImport("user32.dll")]public static extern bool SetForegroundWindow(IntPtr h);
public static List<string> L=new List<string>();public static List<IntPtr> H=new List<IntPtr>();
public static void Scan(){L.Clear();H.Clear();EnumWindows((h,l)=>{if(IsWindowVisible(h)){var sb=new StringBuilder(512);GetWindowText(h,sb,512);if(sb.Length>0){L.Add(sb.ToString());H.Add(h);}}return true;},IntPtr.Zero);}}
"@}
[W2]::Scan()
if(__SW__ -eq 0){ $i=0; [W2]::L | % { $_ } }
else { $k=-1; for($i=0;$i -lt [W2]::L.Count;$i++){ if([W2]::L[$i] -like '*__TITLE__*'){$k=$i;break} }
  if($k -lt 0){'KHONG THAY cua so'} else { [W2]::ShowWindow([W2]::H[$k],__SW__)|Out-Null; [W2]::SetForegroundWindow([W2]::H[$k])|Out-Null; 'OK '+[W2]::L[$k] } }
"""


MIDI_PS = r"""
if(-not ('Mm3' -as [type])){Add-Type @"
using System;using System.Runtime.InteropServices;
public class Mm3{[DllImport("winmm.dll")]public static extern int midiOutGetNumDevs();
[StructLayout(LayoutKind.Sequential,CharSet=CharSet.Unicode)]public struct CAPS{public ushort wMid;public ushort wPid;public uint v;[MarshalAs(UnmanagedType.ByValTStr,SizeConst=32)]public string szPname;public ushort t;public ushort vo;public ushort no;public ushort ch;public uint su;}
[DllImport("winmm.dll",CharSet=CharSet.Unicode)]public static extern int midiOutGetDevCaps(IntPtr id,out CAPS caps,int size);
[DllImport("winmm.dll")]public static extern int midiOutOpen(out IntPtr h,int id,IntPtr cb,IntPtr inst,int flags);
[DllImport("winmm.dll")]public static extern int midiOutShortMsg(IntPtr h,int msg);
[DllImport("winmm.dll")]public static extern int midiOutClose(IntPtr h);
public static string Send(string name,int cc,int val,int ch){int n=midiOutGetNumDevs();for(int i=0;i<n;i++){CAPS c;midiOutGetDevCaps((IntPtr)i,out c,Marshal.SizeOf(typeof(CAPS)));if(c.szPname.StartsWith(name)){IntPtr h;int r=midiOutOpen(out h,i,IntPtr.Zero,IntPtr.Zero,0);if(r!=0)return "open loi "+r;midiOutShortMsg(h,(0xB0|ch)|(cc<<8)|(val<<16));System.Threading.Thread.Sleep(50);midiOutClose(h);return "sent "+c.szPname+" ch"+(ch+1)+" cc"+cc+"="+val;}}return "khong thay cong "+name;}}
"@}
[Mm3]::Send('QuangLuuMIDI',__CC__,__VAL__,__CH__)
"""
MIDIS_PS = MIDI_PS.replace("[Mm3]::Send('QuangLuuMIDI',__CC__,__VAL__,__CH__)",
    "$o=@();for($v=__V1__;$v -le __V2__;$v+=__STEP__){$o+=[Mm3]::Send('QuangLuuMIDI',__CC__,$v,__CH__);Start-Sleep -Milliseconds 250};$o.Count.ToString()+' lan: '+$o[0]+' .. '+$o[-1]")


def log(*a):
    print(*a, flush=True)


def focus():
    for w in pygetwindow.getAllWindows():
        if 'UltraViewer' in w.title and ' - UltraViewer' in w.title:
            try:
                w.activate()
            except Exception:
                pass
            time.sleep(0.4)
            return w.title
    return None


def sc(x, y):
    return OFF[0] + int(round(int(x) * SCALE)), OFF[1] + int(round(int(y) * SCALE))


def grab(x=0, y=0, w=None, h=None):
    """Chup vung (toa do khach) va tra ve anh o kich thuoc toa do khach (1 px = 1 px khach)."""
    w = SIZE[0] - x if w is None else w
    h = SIZE[1] - y if h is None else h
    img = pyautogui.screenshot(region=(OFF[0] + int(round(x * SCALE)), OFF[1] + int(round(y * SCALE)),
                                       int(round(w * SCALE)), int(round(h * SCALE))))
    if abs(SCALE - 1.0) > 0.01:
        img = img.resize((int(w), int(h)), Image.LANCZOS)
    return img


def calib():
    """Tim goc anh may khach (1920x1080, hien 1:1) trong cua so UltraViewer da phong to.
    Ngang: anh can giua vung client cua cua so -> tinh tu hinh hoc. Doc: hang cuoi cung co diem sang trong
    dai ngang do (taskbar may khach luon sang) = mep duoi anh. Ghi 'offx offy 1.0' vao calib.txt."""
    ws = [w for w in pygetwindow.getAllWindows() if ' - UltraViewer' in w.title]
    if not ws:
        log('KHONG CO phien UltraViewer'); return 1
    w = ws[0]
    try:
        w.activate(); time.sleep(0.4)
        if w.left >= 0 or w.top >= 0:          # chua phong to -> phong to de hinh hoc on dinh (vien am 8/11 px)
            w.maximize(); time.sleep(1.2)
            w = [x for x in pygetwindow.getAllWindows() if ' - UltraViewer' in x.title][0]
            log(f'da phong to cua so UltraViewer: ({w.left},{w.top},{w.width}x{w.height})')
    except Exception as e:
        log('khong phong to duoc:', e)
    sw, sh = pyautogui.size()
    b = max(-w.left, 0)                       # vien an cua cua so phong to (8 o 100%, 11 o 4K)
    cw = w.width - 2 * b
    if cw < SIZE[0]:
        log(f'CANH BAO: vung xem rong {cw} < 1920 -> UltraViewer dang thu nho anh, cb.py chua ho tro ty le'); return 1
    offx = w.left + b + (cw - SIZE[0]) // 2
    top = max(w.top, 0) + 90
    bottom = min(w.top + w.height - b, sh)
    img = pyautogui.screenshot(region=(offx, top, SIZE[0], bottom - top)).convert('L')
    bg = img.getpixel((2, img.height - 3))
    data = img.tobytes()
    last = None
    for y in range(img.height - 1, -1, -1):
        row = data[y * img.width:(y + 1) * img.width]
        if sum(1 for v in row if abs(v - bg) > 18) > 100:
            last = y; break
    if last is None:
        log('khong thay hang sang nao - man hinh khach toi den?'); return 1
    offy = top + last - (SIZE[1] - 1)
    log(f'man_dev={sw}x{sh} cua_so=({w.left},{w.top},{w.width}x{w.height}) -> OFF=({offx},{offy}) scale=1.0')
    if offy < top - 5:
        log('CANH BAO: offy tinh ra nam tren toolbar - kiem tra lai bang shot')
    open(CALIB, 'w').write(f'{offx} {offy} 1.0')
    log('da ghi', CALIB)
    return 0


def shot(args):
    x, y, w, h = 0, 0, SIZE[0], SIZE[1]
    path = OUT
    nums = [a for a in args if re.fullmatch(r'-?\d+', a)]
    files = [a for a in args if not re.fullmatch(r'-?\d+', a)]
    if len(nums) >= 4:
        x, y, w, h = map(int, nums[:4])
    if files:
        path = files[0]
    img = grab(x, y, w, h)
    img.save(path)
    log('shot', path, img.size)


def quiet(seconds=20):
    a = grab()
    time.sleep(float(seconds))
    b = grab()
    diff = ImageChops.difference(a.convert('L'), b.convert('L')).point(lambda v: 255 if v > 24 else 0)
    bbox = diff.getbbox()
    px = sum(1 for v in diff.tobytes() if v)
    pct = 100.0 * px / (SIZE[0] * SIZE[1])
    # luoi 40x40: dem o co thay doi de biet thay doi rai rac (nguoi dung) hay gom mot vung (visualizer app)
    cells = set()
    if bbox:
        small = diff.resize((SIZE[0] // 40, SIZE[1] // 40), Image.BOX)
        for i, v in enumerate(small.tobytes()):
            if v > 8:
                cells.add((i % small.width, i // small.width))
    # gom o thay doi thanh cum (8 lang gieng) va in bbox tung cum: visualizer app = mot dai ngang rong ~1000x100,
    # dong ho taskbar = o nho goc duoi phai; con lai moi dang nghi la nguoi dang thao tac
    cums = []
    con_lai = set(cells)
    while con_lai:
        seed = con_lai.pop(); q = [seed]; cum = {seed}
        while q:
            cx, cy = q.pop()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    n = (cx + dx, cy + dy)
                    if n in con_lai:
                        con_lai.discard(n); cum.add(n); q.append(n)
        xs = [c[0] for c in cum]; ys = [c[1] for c in cum]
        cums.append((len(cum), min(xs) * 40, min(ys) * 40, (max(xs) + 1) * 40, (max(ys) + 1) * 40))
    cums.sort(reverse=True)
    log(f'thay_doi={pct:.2f}% o_luoi={len(cells)} bbox={bbox} (OFF={OFF} SCALE={SCALE})')
    for n, x0, y0, x1, y1 in cums[:6]:
        tag = ''
        if x1 - x0 >= 600 and y1 - y0 <= 200: tag = '  <- dang dai ngang: visualizer app?'
        if x0 >= 1700 and y0 >= 1000: tag = '  <- dong ho taskbar'
        log(f'  cum {n:3d} o: ({x0},{y0})-({x1},{y1}){tag}')
    dai = [c for c in cums if c[3] - c[1] >= 600 and c[4] - c[2] <= 200]      # dai visualizer
    def lanh(c):
        if c in dai or (c[1] >= 1700 and c[2] >= 1000) or c[0] < 2:
            return True
        return any(c[2] >= d[2] - 40 and c[4] <= d[4] + 40 for d in dai)   # manh roi cung hang voi dai visualizer
    la = [c for c in cums if not lanh(c)]
    log('KET LUAN:', 'yen (chi visualizer/dong ho)' if not la else f'CO {len(la)} cum thay doi la - co the co nguoi dang dung')


def _ocr_lines(img):
    import winrt.windows.media.ocr as ocr
    import winrt.windows.graphics.imaging as imaging
    import winrt.windows.storage.streams as streams
    scale = 2
    g = img.convert('L').resize((img.width * scale, img.height * scale), Image.LANCZOS)
    writer = streams.DataWriter()
    writer.write_bytes(g.tobytes())
    bmp = imaging.SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), imaging.BitmapPixelFormat.GRAY8, g.width, g.height)
    eng = ocr.OcrEngine.try_create_from_user_profile_languages()

    async def run():
        return await eng.recognize_async(bmp)
    res = asyncio.run(run())
    out = []
    for line in res.lines:
        xs, ys, xe, ye = 1e9, 1e9, 0, 0
        words = []
        for wd in line.words:
            r = wd.bounding_rect
            xs, ys = min(xs, r.x), min(ys, r.y)
            xe, ye = max(xe, r.x + r.width), max(ye, r.y + r.height)
            words.append((int(r.x / scale), int(r.y / scale), int(r.width / scale), int(r.height / scale), wd.text))
        out.append((int(xs / scale), int(ys / scale), int((xe - xs) / scale), int((ye - ys) / scale), line.text, words))
    return out


def ocr(x=0, y=0, w=None, h=None):
    lines = _ocr_lines(grab(x, y, w, h))
    return [(lx + x, ly + y, lw, lh, t, [(wx + x, wy + y, ww, wh, wt) for wx, wy, ww, wh, wt in words])
            for lx, ly, lw, lh, t, words in lines]


def fold(s):
    """Chuan hoa de so khop: bo dau, thuong hoa, gop cac ky tu OCR hay nham (I/l/1 -> i, O/0 -> o)."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = re.sub(r'\s+', ' ', s.replace('đ', 'd').replace('Đ', 'D')).strip().lower()
    return s.translate(str.maketrans({'l': 'i', '1': 'i', '|': 'i', '0': 'o'}))


def giong(a, b):
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()


def find(text, region=None, exact=False, near=None):
    """Tim dong chu. near = chu moc: trong cac dong khop, lay dong gan moc nhat (vd menu "Studio" gan tieu de Cubase,
    khong phai chu "Studio" cua icon desktop)."""
    reg = region or (0, 0, None, None)
    lines = ocr(*reg)
    want = fold(text)
    anchor = None
    if near:
        wn = fold(near)
        for lx, ly, lw, lh, t, _w in lines:
            if wn in fold(t) or giong(fold(t), wn) >= 0.88:
                anchor = (lx + lw // 2, ly + lh // 2); break
        if anchor is None:
            log('KHONG THAY moc:', near); return None
    # Ung vien: (1) chuoi TU lien tiep khop dung want (menu bar bi OCR gop thanh mot dong) -> tam cum tu;
    #           (2) dong co chua want (khong exact) -> tam dong.
    cands = []
    nw = len(want.split())
    for lx, ly, lw, lh, t, words in lines:
        for i in range(len(words)):
            seg = words[i:i + nw]
            if len(seg) < nw:
                break
            g = giong(fold(' '.join(w[4] for w in seg)), want)
            if g >= 0.75:   # 0 = khop tot (>=0.88), 0.5 = khop mo (chu nho cua app: "Tone Miac" ~ "Tone Nhac")
                x0 = min(w[0] for w in seg); x1 = max(w[0] + w[2] for w in seg)
                y0 = min(w[1] for w in seg); y1 = max(w[1] + w[3] for w in seg)
                cands.append((0 if g >= 0.88 else 0.5, (x0 + x1) // 2, (y0 + y1) // 2, ' '.join(w[4] for w in seg)))
        ft = fold(t)
        if not exact and want in ft and ft != want:
            cands.append((len(ft) - len(want), lx + lw // 2, ly + lh // 2, t))
        elif not exact and len(ft) >= len(want) and giong(ft, want) >= 0.88:
            cands.append((1, lx + lw // 2, ly + lh // 2, t))
    if not cands:
        return None
    for muc in (0, 0.5):                        # uu tien cum tu khop tot, roi cum tu khop mo, cuoi cung moi la "dong chua chu"
        if any(c[0] == muc for c in cands):
            cands = [c for c in cands if c[0] == muc]
            break
    if anchor:
        cands = [(((cx - anchor[0]) ** 2 + (cy - anchor[1]) ** 2) ** 0.5, cx, cy, t) for _, cx, cy, t in cands]
    return min(cands, key=lambda c: c[0])


def parse_region(args):
    nums = [a for a in args if re.fullmatch(r'-?\d+', a)]
    if len(nums) >= 4:
        return tuple(int(n) for n in nums[:4])
    return None


def clipboard_get():
    r = subprocess.run(['powershell', '-NoP', '-C', '[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw'],
                       capture_output=True)
    return r.stdout.decode('utf-8', 'replace').replace('\r\n', '\n')


def clipboard_set(text):
    # Set-Clipboard qua stdin de khong gioi han do dai dong lenh.
    p = subprocess.run(['powershell', '-NoP', '-C',
                        '$t=[Console]::In.ReadToEnd(); Set-Clipboard -Value $t'],
                       input=text.encode('utf-8'), capture_output=True)
    return p.returncode == 0


def rpc(code, timeout=60):
    clipboard_set('#QLSCMD\n' + code)
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(1.0)
        c = clipboard_get()
        if c.startswith('#QLSOUT'):
            return c[len('#QLSOUT'):].lstrip('\n')
    return None


def deploy(path):
    src = open(path, encoding='utf-8').read().replace('\r\n', '\n')
    assert "'@" not in src, "script chua chuoi '@ - pha here-string"
    code = ("$dir=[Environment]::GetFolderPath('MyDocuments')+'" + SCRIPT_REL + "';"
            "New-Item -ItemType Directory -Force $dir|Out-Null;$f=Join-Path $dir '" + SCRIPT_NAME + "';"
            "if(Test-Path $f){Copy-Item $f ($f+'.bak') -Force};"
            "$c=@'\n" + src + "\n'@;"
            "[IO.File]::WriteAllText($f,$c.Replace([string][char]13,'')+[string][char]10,[Text.Encoding]::ASCII);"
            "'DA GHI '+(Get-Item $f).Length+' byte -> '+$f")
    return rpc(code, timeout=90)


def main(args):
    if not args:
        log(__doc__)
        return 0
    cmd, rest = args[0], args[1:]
    if cmd in ('shot', 'ocr', 'find', 'clickt', 'click', 'dbl', 'rclick', 'move', 'drag', 'key', 'hotkey', 'type', 'pixel'):
        focus()   # cua so UltraViewer phai o tren cung: terminal may dev de len la click/OCR rot vao terminal
    if cmd == 'focus':
        log(focus())
    elif cmd == 'calib':
        return calib()
    elif cmd == 'who':
        ds = [w for w in pygetwindow.getAllWindows() if ' - UltraViewer' in w.title]
        if not ds:
            log('KHONG CO phien UltraViewer nao dang mo tren may dev'); return 1
        for w in ds:
            log(f'{w.title}  cua_so=({w.left},{w.top},{w.width}x{w.height})'
                + ('' if (w.left, w.top) == (-8, -8) else '  <- CHUA phong to: OFF (294,192) co the sai'))
    elif cmd == 'quiet':
        focus(); quiet(rest[0] if rest else 20)
    elif cmd == 'shot':
        shot(rest)
    elif cmd == 'ocrfile':   # go loi: OCR mot file anh co san
        for lx, ly, lw, lh, t, _w in _ocr_lines(Image.open(rest[0])):
            log(f'{lx},{ly},{lw},{lh}\t{t}')
    elif cmd == 'ocr':
        reg = parse_region(rest) or (0, 0, None, None)
        for lx, ly, lw, lh, t, _w in ocr(*reg):
            log(f'{lx},{ly},{lw},{lh}\t{t}')
    elif cmd in ('find', 'clickt'):
        opts = {'dx': 0, 'dy': 0, 'right': False, 'exact': False, 'near': None}
        text, i, nums = None, 0, []
        while i < len(rest):
            a = rest[i]
            if a == '--near': opts['near'] = rest[i + 1]; i += 2; continue
            if a == '--dx': opts['dx'] = int(rest[i + 1]); i += 2; continue
            if a == '--dy': opts['dy'] = int(rest[i + 1]); i += 2; continue
            if a == '--right': opts['right'] = True; i += 1; continue
            if a == '--exact': opts['exact'] = True; i += 1; continue
            if text is None: text = a
            else: nums.append(a)
            i += 1
        region = parse_region(nums)
        best = find(text, region, opts['exact'], opts['near'])
        if not best:
            log('KHONG THAY:', text); return 1
        _, cx, cy, t = best
        log(f'thay "{t}" tai {cx} {cy}')
        if cmd == 'clickt':
            x, y = sc(cx + opts['dx'], cy + opts['dy'])
            pyautogui.moveTo(x, y, duration=0.15)
            pyautogui.rightClick() if opts['right'] else pyautogui.click()
            time.sleep(0.3)
    elif cmd in ('click', 'dbl', 'rclick', 'move'):
        x, y = sc(rest[0], rest[1])
        pyautogui.moveTo(x, y, duration=0.15)
        if cmd == 'click': pyautogui.click()
        elif cmd == 'dbl': pyautogui.doubleClick()
        elif cmd == 'rclick': pyautogui.rightClick()
        time.sleep(0.3)
    elif cmd == 'drag':
        x1, y1 = sc(rest[0], rest[1]); x2, y2 = sc(rest[2], rest[3])
        pyautogui.moveTo(x1, y1, duration=0.15); pyautogui.mouseDown(); time.sleep(0.15)
        pyautogui.moveTo(x2, y2, duration=0.6); time.sleep(0.15); pyautogui.mouseUp()
    elif cmd == 'key':
        for k in rest:
            pyautogui.press(k); time.sleep(0.15)
    elif cmd == 'hotkey':
        pyautogui.hotkey(*rest); time.sleep(0.3)
    elif cmd == 'type':
        pyautogui.typewrite(' '.join(rest), interval=0.06)
    elif cmd == 'pixel':      # pixel X Y [r] : mau trung binh vung (2r+1)^2 quanh diem (toa do khach) - de biet nut sang/toi
        x, y = int(rest[0]), int(rest[1]); r = int(rest[2]) if len(rest) > 2 else 3
        img = grab(x - r, y - r, 2 * r + 1, 2 * r + 1).convert('RGB')
        px = list(img.getdata()); n = len(px)
        log('rgb=(%d,%d,%d)' % tuple(sum(c[i] for c in px) // n for i in range(3)))
    elif cmd == 'sleep':
        time.sleep(float(rest[0]))
    elif cmd == 'clip':
        if rest[0] == 'get':
            log(clipboard_get())
        else:
            clipboard_set(open(rest[1], encoding='utf-8').read()); log('clip set')
    elif cmd == 'agent':
        clipboard_set(AGENT); log('clipboard = lenh agent; dan vao PowerShell may khach (chuot phai) roi Enter')
    elif cmd == 'rpc':
        code = ' '.join(rest)
        if code.startswith('@'):
            code = open(code[1:], encoding='utf-8').read()
        out = rpc(code)
        if out is None:
            log('RPC TIMEOUT - agent chua chay?'); return 2
        log(out)
    elif cmd == 'deploy':
        out = deploy(rest[0])
        log(out if out else 'DEPLOY TIMEOUT - agent chua chay?')
        return 0 if out and out.startswith('DA GHI') else 2
    elif cmd in ('win', 'wins'):   # wins: liet ke cua so hien thi; win "<phan tieu de>" max|restore|min|front (qua agent, user32)
        act = rest[-1] if cmd == 'win' else 'list'
        title = (' '.join(rest[:-1]) if cmd == 'win' else '').replace("'", "''")
        sw = {'max': 3, 'restore': 9, 'min': 6, 'front': 5, 'list': 0}[act]
        ps = WIN_PS.replace('__TITLE__', title).replace('__SW__', str(sw))
        out = rpc(ps)
        log(out if out else 'RPC TIMEOUT'); time.sleep(0.8)
    elif cmd == 'midi':       # midi CC VAL : gui Control Change (kenh 1) vao cong loopMIDI QuangLuuMIDI tu may khach (qua agent, winmm)
        ch = int(rest[2]) - 1 if len(rest) > 2 else 0     # kenh MIDI 1..16 (mac dinh 1); script: tham so i>=48 -> kenh 2 + (i-48)//100, cc (i-48)%100
        out = rpc(MIDI_PS.replace('__CC__', str(int(rest[0]))).replace('__VAL__', str(int(rest[1]))).replace('__CH__', str(ch)))
        log(out if out else 'RPC TIMEOUT')
    elif cmd == 'midis':      # midis CC V1 V2 [STEP] [KENH] : quet mot dai gia tri (de do bang gia tri roi rac cua tham so, doc disp[] tren console)
        step = int(rest[3]) if len(rest) > 3 else 1
        ch = int(rest[4]) - 1 if len(rest) > 4 else 0
        out = rpc(MIDIS_PS.replace('__CC__', str(int(rest[0]))).replace('__V1__', str(int(rest[1]))).replace('__V2__', str(int(rest[2])))
                  .replace('__STEP__', str(step)).replace('__CH__', str(ch)), timeout=120)
        log(out if out else 'RPC TIMEOUT')
    elif cmd == 'activate':   # dua cua so may khach len truoc theo (mot phan) tieu de, qua agent
        out = rpc("(New-Object -ComObject WScript.Shell).AppActivate('" + ' '.join(rest).replace("'", "''") + "')")
        log(out if out else 'RPC TIMEOUT'); time.sleep(0.8)
    elif cmd == 'info':
        out = rpc(INFO_PS)
        log(out if out else 'RPC TIMEOUT - agent chua chay?')
    elif cmd == 'seq':   # cac lenh cach nhau boi ';'
        for part in ' '.join(rest).split(';'):
            p = part.strip().split()
            if p:
                rc = main(p)
                if rc:
                    return rc
    else:
        log('lenh la', cmd); return 1
    return 0


if __name__ == '__main__':
    argv = sys.argv[1:]
    if len(argv) == 2 and argv[0] == '--argfile':
        with open(argv[1], encoding='utf-8') as f:
            argv = [l.rstrip('\n') for l in f if l.rstrip('\n') != '']
    sys.exit(main(argv) or 0)
