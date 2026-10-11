@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Smart Banana IoT - RS485 Multi-Sensor Bus Configurator
cd /d "%~dp0"
echo ======================================================================
echo  Smart Banana IoT - RS485 Modbus Bus Configurator & Monitor
echo  Support: SN-3002-TR-NPK-NO1 (Soil 7-in-1) & SN-3002-GZWS (Weather)
echo ======================================================================
echo.
.\venv\Scripts\python.exe tools\config_soil_sensor.py
echo.
pause
