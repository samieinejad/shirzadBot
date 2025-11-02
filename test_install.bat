@echo off
chcp 65001 >nul
echo 🧪 تست نصب...

REM بررسی وجود Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python یافت نشد. لطفاً Python را نصب کنید.
    pause
    exit /b 1
)

echo ✅ Python یافت شد
echo.

REM بررسی وجود محیط مجازی
if not exist "venv\Scripts\python.exe" (
    echo ❌ محیط مجازی یافت نشد. ابتدا install_simple.bat را اجرا کنید.
    pause
    exit /b 1
)

echo ✅ محیط مجازی یافت شد
echo.

REM تست import ها
echo 🔍 تست کتابخانه‌ها...
venv\Scripts\python.exe -c "import flask; print('✅ Flask')" 2>nul || echo ❌ Flask
venv\Scripts\python.exe -c "import telegram; print('✅ Telegram')" 2>nul || echo ❌ Telegram
venv\Scripts\python.exe -c "import pandas; print('✅ Pandas')" 2>nul || echo ❌ Pandas
venv\Scripts\python.exe -c "import openpyxl; print('✅ OpenPyXL')" 2>nul || echo ❌ OpenPyXL
venv\Scripts\python.exe -c "import requests; print('✅ Requests')" 2>nul || echo ❌ Requests
venv\Scripts\python.exe -c "import apscheduler; print('✅ APScheduler')" 2>nul || echo ❌ APScheduler
venv\Scripts\python.exe -c "import PIL; print('✅ Pillow')" 2>nul || echo ❌ Pillow
venv\Scripts\python.exe -c "import jdatetime; print('✅ JDateTime')" 2>nul || echo ❌ JDateTime

echo.
echo 🎉 تست تکمیل شد!
echo.
pause
