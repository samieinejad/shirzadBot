# ✅ Deployment Checklist

## 🎯 قبل از Push به Git

### چک‌لیست فایل‌ها:

- [ ] `.gitignore` اضافه شده
- [ ] توکن‌ها و ID‌ها از `app.py` حذف/تغییر شده
- [ ] `requirements.txt` به‌روز است
- [ ] Documentation کامل است
- [ ] `.bat` فایل‌ها حذف شده یا در `.gitignore` هستند
- [ ] دیتابیس‌ها در `.gitignore` هستند
- [ ] لاگ‌ها در `.gitignore` هستند

---

## 🚀 Push به Git

```bash
# Add files
git add .
git commit -m "Complete UI with all features + deployment scripts"

# Push
git push origin main
```

---

## 📦 در Ubuntu Server

### گام ۱: آماده‌سازی سرور

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install required packages
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3
```

### گام ۲: کلون کردن

```bash
# Create directory
sudo mkdir -p /var/www/shirzadBot
sudo chown $USER:$USER /var/www/shirzadBot

# Clone project
cd /var/www/shirzadBot
git clone <YOUR_GIT_REPO_URL> .

# یا اگر git remote setup نکردید:
# 1. دانلود ZIP از Git
# 2. Extract به /var/www/shirzadBot
```

### گام ۳: نصب خودکار

```bash
cd /var/www/shirzadBot
bash deploy/install.sh
```

### گام ۴: تنظیم توکن‌ها

```bash
nano app.py
# خطوط 135-141 را ویرایش کنید
```

```python
TELEGRAM_BOT_TOKEN = "YOUR_ACTUAL_TOKEN_HERE"
BALE_BOT_TOKEN = "YOUR_ACTUAL_TOKEN_HERE"
ITA_BOT_TOKEN = "YOUR_ACTUAL_TOKEN_HERE"

OWNER_ID = YOUR_ACTUAL_ID
BALE_OWNER_ID = YOUR_ACTUAL_ID
ITA_OWNER_ID = "YOUR_ACTUAL_ID"
```

### گام ۵: شروع سرویس

```bash
# Start
sudo systemctl start shirzadbot

# Check status
sudo systemctl status shirzadbot

# View logs
tail -f logs/app.log
```

### گام ۶: تست

```bash
# Check port
netstat -tlnp | grep 5000

# Test locally
curl http://localhost:5000

# Test from browser
http://YOUR_SERVER_IP
```

---

## 🔐 SSL Setup (اختیاری اما مهم)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

---

## 🔄 Backup Setup

```bash
# Setup auto-backup
crontab -e

# Add this line (daily at 2 AM)
0 2 * * * /var/www/shirzadBot/deploy/backup.sh >> /var/www/shirzadBot/logs/backup.log 2>&1
```

---

## 📊 مانیتورینگ

```bash
# Status
sudo systemctl status shirzadbot

# Logs
tail -f logs/app.log
tail -f logs/error.log

# Nginx
sudo tail -f /var/log/nginx/shirzadbot_access.log
sudo tail -f /var/log/nginx/shirzadbot_error.log

# Resources
htop
```

---

## 🔄 به‌روزرسانی

```bash
cd /var/www/shirzadBot
bash deploy/update.sh
```

---

## 📋 چک‌لیست نهایی

- [ ] Service در حال اجراست (`systemctl status shirzadbot`)
- [ ] پورت 5000 باز است (`netstat -tlnp | grep 5000`)
- [ ] Nginx کار می‌کند (`systemctl status nginx`)
- [ ] UI در دسترس است (`curl localhost:5000`)
- [ ] لاگ‌ها نرمال هستند
- [ ] SSL تنظیم شده (اختیاری)
- [ ] Backup خودکار فعال است
- [ ] فایروال تنظیم شده

---

## 🆘 در صورت مشکل

### 1. Service شروع نمی‌شود:
```bash
sudo journalctl -u shirzadbot -n 50
# بررسی خطاها
```

### 2. 502 Bad Gateway:
```bash
sudo systemctl status shirzadbot
sudo systemctl restart shirzadbot
```

### 3. Permission errors:
```bash
sudo chown -R www-data:www-data /var/www/shirzadBot
sudo chmod -R 755 /var/www/shirzadBot
```

### 4. Database issues:
```bash
ls -la *.db
sudo chown www-data:www-data *.db
```

### 5. Logs را ببینید:
```bash
tail -f logs/app.log logs/error.log
sudo journalctl -u shirzadbot -f
```

---

## 📞 دستورات مفید

```bash
# Restart همه چیز
sudo systemctl restart shirzadbot && sudo systemctl restart nginx

# Manual backup
bash deploy/backup.sh

# Update code
bash deploy/update.sh

# View all logs
tail -f logs/app.log logs/error.log /var/log/nginx/*.log

# Check ports
netstat -tlnp | grep -E '5000|80|443'

# Disk usage
df -h
du -sh /var/www/shirzadBot/*

# Process info
ps aux | grep app.py
```

---

**حالا پروژه شما در production آماده است! 🎉**

