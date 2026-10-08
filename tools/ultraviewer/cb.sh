#!/bin/bash
# cb.sh <lenh...> : chay tools/ultraviewer/cb.py bang Python Windows (.venv) tu WSL.
# Tham so ghi ra file (moi tham so mot dong) de khong vuong cach cmd.exe xu ly dau nhay / Unicode.
# Vi du: tools/ultraviewer/cb.sh quiet 20 ; cb.sh clickt "Windows PowerShell" ; cb.sh deploy cubase/QuangLuu_QuangLuuMIDI.js
ARGF=/mnt/c/Users/GrantTuan/AppData/Local/Temp/qls_cb_args.txt
mkdir -p "$(dirname "$ARGF")"
: > "$ARGF"
for a in "$@"; do printf '%s\n' "$a" >> "$ARGF"; done
set -o pipefail
cmd.exe /c "set PYTHONIOENCODING=utf-8&& set PYTHONUTF8=1&& D:\Projects\quang-luu-studio\.venv\Scripts\python.exe D:\Projects\quang-luu-studio\tools\ultraviewer\cb.py --argfile C:\Users\GrantTuan\AppData\Local\Temp\qls_cb_args.txt" 2>&1 | grep -v '^[[:space:]]*$' || [ ${PIPESTATUS[0]} -eq 0 ]
