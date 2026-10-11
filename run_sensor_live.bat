@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Smart Banana IoT - Dual-Sensor Live Streamer (Weather ID 2 + Soil ID 3)
cd /d "%~dp0"
echo ======================================================================
echo  Smart Banana IoT - Live Hardware Streamer (RS485 Modbus RTU Bus)
echo  Sensor 1: SN-3002-GZWS-NO1  (Light + Weather @ Slave ID 2)
echo  Sensor 2: SN-3002-TR-NPK-NO1 (Soil 7-in-1   @ Slave ID 3)
echo ======================================================================
echo.
.\venv\Scripts\python.exe backend\hardware_bridge.py
pause
