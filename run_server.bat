@echo off
chcp 65001 > nul
echo ==============================================================================
echo 🍌 Starting Smart Banana IoT & AI Platform (กล้วยหอมทอง)
echo ==============================================================================
echo.
echo * Backend API:   http://localhost:8000
echo * Web Console:   http://localhost:8000
echo * Swagger Docs:  http://localhost:8000/docs
echo.
cd /d "%~dp0backend"
..\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
