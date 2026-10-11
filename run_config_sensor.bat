@echo off
chcp 65001 > nul
title 🍌 Smart Banana IoT - 7-in-1 Soil Sensor Configurator (COM3)
cls
echo ==============================================================================
echo 🍌 Smart Banana IoT - โปรแกรมตั้งค่าเซนเซอร์ดิน RS485 Modbus 7-in-1
echo ==============================================================================
echo.
echo * ค่าเริ่มต้นพอร์ต:    COM3 (USB-SERIAL CH340)
echo * ความสามารถ:         Auto-Detect, เปลี่ยน Slave ID (0x0100), เปลี่ยน Baudrate (0x0101)
echo * การตรวจสอบ:        คำนวณ CRC16 อัตโนมัติ และทดสอบอ่านค่าดิน 7 ค่าเพื่อยืนยัน 100%%
echo.
cd /d "%~dp0"
.\venv\Scripts\python.exe tools\config_soil_sensor.py
echo.
pause
