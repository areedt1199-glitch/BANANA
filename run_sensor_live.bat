@echo off
chcp 65001 > nul
echo ==============================================================================
echo 🍌 Smart Banana IoT - Live Physical Sensor Bridge (COM4)
echo ==============================================================================
echo.
echo * Sensor Port:    COM4 (CH340 RS485 Modbus RTU 4800 bps)
echo * Metrics:        Soil Moisture, Temp, EC, pH, N, P, K
echo * Microclimate:   Air Temp, Humidity, Light (Lux), Solar Radiation, Wind
echo * Streaming to:   http://localhost:8000
echo.
cd /d "%~dp0"
.\venv\Scripts\python.exe backend\hardware_bridge.py
pause
