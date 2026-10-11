@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Smart Banana IoT - Soil Sensor Configurator (COM3)
cd /d "%~dp0"
.\venv\Scripts\python.exe tools\config_soil_sensor.py
echo.
pause
