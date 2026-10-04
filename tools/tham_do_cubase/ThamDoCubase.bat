@echo off
rem Tham do Cubase cho Quang Luu Studio. Tham so truyen thang cho ThamDoCubase.ps1,
rem vd:  ThamDoCubase.bat -CaiScript      ThamDoCubase.bat -ChiKhaoSat      ThamDoCubase.bat -Seconds 60
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ThamDoCubase.ps1" %*
