"""Nghe cong QLS_PhanHoi N giay, in CC va SysEx cua script Cubase. Dung: python nghe_phan_hoi.py [giay]"""
import sys, time, mido
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 10
name = [n for n in mido.get_input_names() if 'QLS_PhanHoi' in n][0]
t0 = time.time()
with mido.open_input(name) as port:
    while time.time() - t0 < secs:
        for m in port.iter_pending():
            t = time.time() - t0
            if m.type == 'sysex':
                d = bytes(m.data)
                if d[:3] == b'\x7dQL':
                    print(f'{t:6.2f}s SYSEX loai={d[3]} {d[4:].decode("ascii","replace")}')
                else:
                    print(f'{t:6.2f}s SYSEX {d.hex()}')
            elif m.type == 'control_change':
                print(f'{t:6.2f}s CC {m.control} = {m.value}')
            else:
                print(f'{t:6.2f}s {m}')
        time.sleep(0.01)
print('listen done')
