@echo off
setlocal
chcp 65001 >nul
:: Tham do: Studio One nap bai xong luc nao, va co TRA LOI MIDI khong.
::
:: Mac dinh chi DOC va gui tin hieu Ping (CC 49) vao cong QuangLuuMIDI, khong sua file nao.
:: Kich ban D (-BatTransmit / -KiemTraNut / -KhoiPhucSurface) THI CO: tam sua file thiet bi
:: Studio One (co sao luu) va bat/tat that 12 nut trong bai - xem HUONG_DAN.md.
:: Truoc khi chay: DONG app Quang Luu Studio, lam xong phan cai dat trong
:: HUONG_DAN.md (cong loopMIDI thu 2, file surface.xml ban tham do, gan Ping).
::
:: Mac dinh chay 4 phut. Doi thoi gian: ThamDoStudioOne.bat -Seconds 60
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ThamDoStudioOne.ps1" %*
