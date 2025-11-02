# ⚠️ IMPORTANT: قبل از Push به Git

## 🔴 ۱. توکن‌ها را حذف/تغییر دهید!

قبل از Push به Git، **حتماً** توکن‌های واقعی را از `app.py` حذف کنید:

### فایل: `app.py` - خطوط 135-141

**قبل از Push:**
```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_TOKEN"  # توکن خود را اینجا وارد کنید
BALE_BOT_TOKEN = "YOUR_BALE_TOKEN"          # توکن خود را اینجا وارد کنید
ITA_BOT_TOKEN = "YOUR_ITA_TOKEN"            # توکن خود را اینجا وارد کنید

OWNER_ID = YOUR_TELEGRAM_ID          # آیدی عددی ادمین تلگرام
BALE_OWNER_ID = YOUR_BALE_ID         # آیدی عددی ادمین بله
ITA_OWNER_ID = "YOUR_ITA_ID"         # آیدی ادمین ایتا
```

**یا از Environment Variables استفاده کنید** (بهتر است)

---

## 🔴 ۲. فایل‌های حساس Push نکنید!

فایل‌های زیر با `.gitignore` محافظت می‌شوند:
- ✅ `*.db` (دیتابیس‌ها)
- ✅ `*.log` (لاگ‌ها)
- ✅ `uploads/` (فایل‌های آپلود شده)
- ✅ `venv/` (محیط مجازی)
- ✅ `*.bat` (فایل‌های Windows)

---

## ✅ ۳. قبل از Deploy

### روی Local (Windows):
```bash
# Check .gitignore
git status

# Commit
git add .
git commit -m "Initial commit with full UI and deployment scripts"

# Push
git push origin main
```

### روی Server (Ubuntu):
```bash
# Clone
git clone <YOUR_REPO_URL>

# Install
bash deploy/install.sh

# Configure tokens
nano app.py  # Edit tokens

# Start
sudo systemctl start shirzadbot
```

---

## 🔐 Security Best Practices

1. ✅ **هرگز توکن‌های واقعی را Push نکنید**
2. ✅ **از Environment Variables استفاده کنید**
3. ✅ **.gitignore را چک کنید**
4. ✅ **Backup به صورت منظم**
5. ✅ **لاگ‌ها را بررسی کنید**
6. ✅ **SSL تنظیم کنید**
7. ✅ **فایروال فعال کنید**

---

## 📝 Quick Deploy Commands

### On Ubuntu Server:
```bash
# 1. Install
bash deploy/install.sh

# 2. Configure
nano app.py

# 3. Start
sudo systemctl start shirzadbot

# 4. Status
sudo systemctl status shirzadbot

# 5. Logs
tail -f logs/app.log
```

---

**⚠️ حتماً توکن‌ها را قبل از Push تغییر دهید!**

