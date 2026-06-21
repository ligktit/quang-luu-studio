@echo off
title Quang Luu Studio - Chan doan dong bo trinh duyet (CDP)

set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%diagnose_cdp.ps1"
