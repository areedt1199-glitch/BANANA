@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Smart Banana IoT - Triple-Sensor Live Streamer (RS485 Bus)
cd /d "%~dp0"
echo ======================================================================
echo  Smart Banana IoT - Triple Hardware Streamer (RS485 Modbus RTU Bus)
echo  Sensor 1: ZTS-3002-TR-ECTHNPKPH (Soil 7-in-1: Moist/Temp/EC/pH @ ID 1)
echo  Sensor 2: SN-3002-GZWS-NO1      (Light 0-65535 Lux + Weather  @ ID 2)
echo  Sensor 3: SN-3002-TR-NPK-NO1    (Soil NPK Nutrients           @ ID 3)
echo ======================================================================
echo.
.\venv\Scripts\python.exe backend\hardware_bridge.py
pause
