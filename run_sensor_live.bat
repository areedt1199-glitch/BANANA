@echo off
chcp 65001 > nul
echo ==============================================================================
echo 🍌 Smart Banana IoT - ตัวอ่านเซนเซอร์จริง SN-3002GZWS-NO1-65535
echo ==============================================================================
echo.
echo * Sensor Model:   SN-3002GZWS-NO1-65535 (Light + Temp + Humidity)
echo * Port:           COM4 (CH340 USB-to-RS485 @ 4800 bps)
echo * Live Metrics:   ค่าแสง (0 - 65,535 Lux), อุณหภูมิอากาศ (°C), ความชื้นอากาศ (%%RH)
echo * Streaming to:   http://localhost:8000
echo.
echo กำลังเริ่มดึงข้อมูลจากเซนเซอร์...
echo (กด Ctrl+C หากต้องการหยุด)
echo.
cd /d "%~dp0"
.\venv\Scripts\python.exe backend\hardware_bridge.py
pause
