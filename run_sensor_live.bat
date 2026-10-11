@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Smart Banana IoT - Live Hardware Bridge (SN-3002GZWS)
echo ==============================================================================
echo 🍌 Smart Banana IoT - Live Sensor Streamer (SN-3002GZWS-NO1-65535)
echo ==============================================================================
echo.
echo * Sensor Model:   SN-3002GZWS-NO1 (Light + Temp + Humidity)
echo * Port / Speed:   Auto-Detect CH340 @ 9600 bps (Slave ID 2)
echo * Streaming to:   http://localhost:8000/api/v1/telemetry/
echo.
echo กำลังดึงข้อมูลสดจากเซนเซอร์ส่งขึ้นหน้าเว็บแบบเรียลไทม์...
echo (กด Ctrl+C หากต้องการหยุด)
echo.
cd /d "%~dp0"
.\venv\Scripts\python.exe backend\hardware_bridge.py
pause
