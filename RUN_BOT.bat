@echo off
chcp 65001 >nul
title Shirzad Bot Platform
color 0A

echo.
echo ╔══════════════════════════════════════════════╗
echo ║    Shirzad Bot Platform - Starting...       ║
echo ╚══════════════════════════════════════════════╝
echo.

REM Activate venv
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
) else (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please run first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo ────────────────────────────────────────────────
echo   Opening browser at: http://localhost:5000
echo   Press Ctrl+C to stop the server
echo ────────────────────────────────────────────────
echo.

REM Wait a bit then open browser
start /b timeout /t 3 /nobreak >nul 2>&1 & start http://localhost:5000

REM Run the app
python app.py

pause

