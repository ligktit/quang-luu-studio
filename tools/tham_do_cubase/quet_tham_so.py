"""Quet CC 0..127 cho tung tham so plugin (CC = 80 + chi so) va in khoang gia tri hien thi. Dung: python quet_tham_so.py 86 87"""
import sys, time, mido, threading, collections
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
outn = [n for n in mido.get_output_names() if 'QuangLuuMIDI' in n][0]
inn  = [n for n in mido.get_input_names() if 'QLS_PhanHoi' in n][0]
ccs = [int(x) for x in sys.argv[1:]]
disp = collections.defaultdict(dict)   # param idx -> {cc value: display}
cur = {}
stop = False
def listener():
    with mido.open_input(inn) as port:
        while not stop:
            for m in port.iter_pending():
                if m.type == 'sysex':
                    d = bytes(m.data)
                    if d[:3] == b'\x7dQL' and d[3] == 4:
                        parts = d[4:].decode('ascii','replace').split('|')
                        idx = int(parts[1]); val = parts[2]
                        if idx in cur: disp[idx][cur[idx]] = val
            time.sleep(0.005)
t = threading.Thread(target=listener, daemon=True); t.start()
with mido.open_output(outn) as out:
    for cc in ccs:
        idx = cc - 80
        for v in range(128):
            cur[idx] = v
            out.send(mido.Message('control_change', channel=0, control=cc, value=v))
            time.sleep(0.06)
        time.sleep(0.5)
stop = True; time.sleep(0.3)
for cc in ccs:
    idx = cc - 80
    print(f'=== CC {cc} (param {idx}) ===')
    runs = []
    for v in range(128):
        val = disp[idx].get(v, '?')
        if runs and runs[-1][2] == val: runs[-1][1] = v
        else: runs.append([v, v, val])
    for a, b, val in runs:
        print(f'  {a:3d}..{b:3d}  {val}')
