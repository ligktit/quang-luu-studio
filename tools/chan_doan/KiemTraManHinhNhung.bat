@echo off
setlocal
chcp 65001 >nul
:: Bam doi vao file nay de kiem tra: may dang dung ban NANG hay NHE, va bo hien
:: thi web (man hinh karaoke nhung) co nap duoc khong.
::
:: Chi DOC, khong sua gi, khong cai gi. An toan gui thang cho khach.
:: Nen MO app len truoc roi hay chay, de kiem duoc ca buoc cuoi.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0KiemTraManHinhNhung.ps1"
