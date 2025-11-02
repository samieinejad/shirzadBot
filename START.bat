@echo off
chcp 65001 >nul
echo.
echo ========================================
echo   Shirzad Bot Platform - Starting...
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found!
    echo Please run: python -m venv venv
    echo Then: venv\Scripts\activate
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Check if index.html exists
if not exist "index.html" (
    echo [ERROR] index.html not found!
    pause
    exit /b 1
)

REM Activate virtual environment and run
echo [INFO] Activating virtual environment...
call venv\Scripts\activate.bat

echo [INFO] Starting Flask web server and bots...
echo.
echo ========================================
echo   Bot Panel: http://localhost:5000
echo ========================================
echo.
echo Press Ctrl+C to stop the server
echo.

python app.py

pause

