@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
title Smart Banana IoT - Test SN-3002GZWS Light Sensor
cd /d "%~dp0"
.\venv\Scripts\python.exe tools\test_sn3002_live.py
echo.
pause
