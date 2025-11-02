@echo off
chcp 65001 >nul
echo 🚀 شروع برنامه...

REM بررسی وجود محیط مجازی
if not exist "venv\Scripts\python.exe" (
    echo ❌ محیط مجازی یافت نشد. ابتدا install_simple.bat را اجرا کنید.
    pause
    exit /b 1
)

echo ✅ محیط مجازی یافت شد
echo.

REM بررسی وجود فایل‌های مورد نیاز
if not exist "app.py" (
    echo ❌ فایل app.py یافت نشد
    pause
    exit /b 1
)

if not exist "index.html" (
    echo ❌ فایل index.html یافت نشد
    pause
    exit /b 1
)

echo ✅ فایل‌های مورد نیاز یافت شدند
echo.

REM تست سریع Flask
echo 🔍 تست Flask...
venv\Scripts\python.exe -c "import flask; print('✅ Flask آماده است')" 2>nul
if errorlevel 1 (
    echo ❌ Flask نصب نشده است. ابتدا install_simple.bat را اجرا کنید.
    pause
    exit /b 1
)

echo 🔄 شروع برنامه...
echo.

REM اجرای برنامه
venv\Scripts\python.exe app.py

echo.
echo 📝 برنامه متوقف شد
pause
