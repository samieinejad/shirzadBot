@echo off
chcp 65001 >nul
echo 🚀 نصب ساده وابستگی‌ها...

REM بررسی وجود Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python یافت نشد. لطفاً Python را نصب کنید.
    pause
    exit /b 1
)

echo ✅ Python یافت شد
echo.

REM حذف محیط مجازی قدیمی (اگر وجود دارد)
if exist "venv" (
    echo 🗑️ حذف محیط مجازی قدیمی...
    rmdir /s /q venv
)

REM ایجاد محیط مجازی جدید
echo 🔧 ایجاد محیط مجازی جدید...
python -m venv venv
if errorlevel 1 (
    echo ❌ خطا در ایجاد محیط مجازی
    pause
    exit /b 1
)

echo ✅ محیط مجازی ایجاد شد
echo.

REM فعال‌سازی محیط مجازی و نصب وابستگی‌ها
echo 📦 نصب وابستگی‌ها...
echo 🔄 به‌روزرسانی pip...
venv\Scripts\python.exe -m pip install --upgrade pip

echo 🔄 نصب Flask...
venv\Scripts\python.exe -m pip install Flask

echo 🔄 نصب Telegram Bot...
venv\Scripts\python.exe -m pip install python-telegram-bot

echo 🔄 نصب Pandas...
venv\Scripts\python.exe -m pip install pandas

echo 🔄 نصب OpenPyXL...
venv\Scripts\python.exe -m pip install openpyxl

echo 🔄 نصب Requests...
venv\Scripts\python.exe -m pip install requests

echo 🔄 نصب APScheduler...
venv\Scripts\python.exe -m pip install APScheduler

echo 🔄 نصب Pillow...
venv\Scripts\python.exe -m pip install Pillow

echo 🔄 نصب JDateTime...
venv\Scripts\python.exe -m pip install jdatetime

echo 🔄 نصب PyTZ...
venv\Scripts\python.exe -m pip install pytz

echo.
echo 🧪 تست نصب...
venv\Scripts\python.exe -c "import flask; print('✅ Flask نصب شد')"
venv\Scripts\python.exe -c "import telegram; print('✅ Telegram Bot نصب شد')"
venv\Scripts\python.exe -c "import pandas; print('✅ Pandas نصب شد')"
venv\Scripts\python.exe -c "import openpyxl; print('✅ OpenPyXL نصب شد')"
venv\Scripts\python.exe -c "import requests; print('✅ Requests نصب شد')"
venv\Scripts\python.exe -c "import apscheduler; print('✅ APScheduler نصب شد')"
venv\Scripts\python.exe -c "import PIL; print('✅ Pillow نصب شد')"
venv\Scripts\python.exe -c "import jdatetime; print('✅ JDateTime نصب شد')"

echo.
echo 🎉 نصب با موفقیت تکمیل شد!
echo.
echo 📝 برای اجرای برنامه:
echo    venv\Scripts\python.exe app.py
echo.
pause
