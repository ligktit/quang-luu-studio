#!/bin/bash

echo "========================================"
echo "Building LiveStudio EXE"
echo "========================================"
echo ""

# Kiểm tra xem file spec có hiddenimports chưa
if ! grep -q "rtmidi" main.spec; then
    echo "[ERROR] File main.spec chưa có hiddenimports cho rtmidi!"
    echo "Vui lòng kiểm tra lại file main.spec"
    exit 1
fi

echo "[INFO] File main.spec đã có hiddenimports"
echo "[INFO] Đang build EXE từ file spec..."
echo ""

# Build từ file spec
pyinstaller main.spec

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================"
    echo "Build thành công!"
    echo "File EXE: dist/main.exe"
    echo "========================================"
else
    echo ""
    echo "========================================"
    echo "Build thất bại!"
    echo "========================================"
    exit 1
fi
