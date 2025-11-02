# 🚀 Deployment Scripts

این پوشه شامل اسکریپت‌های خودکار برای Deploy در Ubuntu Server است.

## 📋 فایل‌ها

### 1️⃣ `install.sh` - نصب کامل
اجرای تمام مراحل نصب به صورت خودکار:
- نصب Python و وابستگی‌ها
- تنظیم Virtual Environment
- ایجاد Systemd Service
- تنظیم Nginx
- آماده برای راه‌اندازی

**استفاده:**
```bash
bash deploy/install.sh
```

---

### 2️⃣ `update.sh` - به‌روزرسانی
به‌روزرسانی کد از Git و Restart سرویس

**استفاده:**
```bash
bash deploy/update.sh
```

---

### 3️⃣ `backup.sh` - Backup خودکار
Backup تمام دیتابیس‌ها و فایل‌های مهم

**استفاده:**
```bash
bash deploy/backup.sh
```

**برای Backup خودکار روزانه:**
```bash
# اضافه به crontab
crontab -e

# این خط را اضافه کنید (هر شب ساعت 2)
0 2 * * * /var/www/shirzadBot/deploy/backup.sh >> /var/www/shirzadBot/logs/backup.log 2>&1
```

---

## 🎯 روش استفاده

### نصب اولیه:

```bash
# 1. کلون کردن پروژه
cd /var/www
sudo git clone <YOUR_REPO_URL> shirzadBot
sudo chown -R $USER:$USER shirzadBot
cd shirzadBot

# 2. اجرای نصب
bash deploy/install.sh

# 3. تنظیم توکن‌ها
nano app.py
# خطوط 135-141 را ویرایش کنید

# 4. شروع سرویس
sudo systemctl start shirzadbot
sudo systemctl status shirzadbot

# 5. بررسی لاگ‌ها
tail -f logs/app.log
```

### به‌روزرسانی:

```bash
cd /var/www/shirzadBot
bash deploy/update.sh
```

### Backup:

```bash
cd /var/www/shirzadBot
bash deploy/backup.sh
```

---

## 🔧 تنظیمات اضافی

### SSL (Let's Encrypt):

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

### مانیتورینگ:

```bash
# مشاهده وضعیت
sudo systemctl status shirzadbot

# مشاهده لاگ‌ها
tail -f logs/app.log
tail -f logs/error.log

# مشاهده استفاده از منابع
htop
```

---

## ⚠️ نکات مهم

1. ✅ قبل از اجرای `install.sh`، Git repository را کلون کنید
2. ✅ حتماً توکن‌ها را در `app.py` تغییر دهید
3. ✅ بعد از نصب، SSL را تنظیم کنید
4. ✅ Backup خودکار را برای cron setup کنید
5. ✅ لاگ‌ها را منظم چک کنید

---

## 📞 عیب‌یابی

### Service شروع نمی‌شود:
```bash
sudo journalctl -u shirzadbot -n 50
ls -la /var/www/shirzadBot/
```

### Error در Nginx:
```bash
sudo nginx -t
sudo systemctl restart nginx
```

### Permission errors:
```bash
sudo chown -R www-data:www-data /var/www/shirzadBot
```

---

**موفق باشید! 🎉**

