# 🚀 راهنمای Deploy در Ubuntu Server

## 📋 پیش‌نیازها

- Ubuntu 20.04+ یا 22.04 (توصیه می‌شود)
- Python 3.8+ نصب شده
- دسترسی sudo
- دامنه یا IP عمومی

---

## ۱️⃣ آماده‌سازی سرور

### نصب Python و ابزارهای پایه

```bash
sudo apt update
sudo apt upgrade -y

# نصب Python و pip
sudo apt install -y python3 python3-pip python3-venv

# نصب Git
sudo apt install -y git

# نصب SQLite (پیش‌فرض نصب است)
sudo apt install -y sqlite3

# نصب Nginx
sudo apt install -y nginx

# نصب Supervisor
sudo apt install -y supervisor
```

---

## ۲️⃣ کلون کردن پروژه

### دریافت کد از Git

```bash
# ایجاد دایرکتوری پروژه
sudo mkdir -p /var/www/shirzadBot
sudo chown $USER:$USER /var/www/shirzadBot

# کلون کردن
cd /var/www/shirzadBot
git clone <YOUR_GIT_REPO_URL> .

# یا اگر قبلاً clone کردید:
# git pull origin main
```

---

## ۳️⃣ تنظیمات محیط

### ایجاد Virtual Environment

```bash
cd /var/www/shirzadBot

# ایجاد venv
python3 -m venv venv

# فعال‌سازی
source venv/bin/activate

# نصب وابستگی‌ها
pip install --upgrade pip
pip install -r requirements.txt
```

### تنظیم متغیرهای محیطی

**⚠️ مهم: توکن‌ها را باید تغییر دهید!**

```bash
# کپی فایل تنظیمات (یا ایجاد کنید)
cp app.py app.py.backup
```

ویرایش `app.py` و تغییر توکن‌ها:

```python
# خط 135-141
TELEGRAM_BOT_TOKEN = "YOUR_ACTUAL_TOKEN"
BALE_BOT_TOKEN = "YOUR_ACTUAL_TOKEN"
ITA_BOT_TOKEN = "YOUR_ACTUAL_TOKEN"

OWNER_ID = YOUR_ACTUAL_ID
BALE_OWNER_ID = YOUR_ACTUAL_ID
ITA_OWNER_ID = "YOUR_ACTUAL_ID"
```

### ایجاد پوشه‌های مورد نیاز

```bash
mkdir -p uploads
mkdir -p logs
chmod 755 uploads logs
```

---

## ۴️⃣ ایجاد Systemd Service

### ایجاد فایل service

```bash
sudo nano /etc/systemd/system/shirzadbot.service
```

محتوای زیر را قرار دهید:

```ini
[Unit]
Description=Shirzad Bot Platform
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/var/www/shirzadBot
Environment="PATH=/var/www/shirzadBot/venv/bin"
ExecStart=/var/www/shirzadBot/venv/bin/python app.py
Restart=always
RestartSec=10

# Logging
StandardOutput=append:/var/www/shirzadBot/logs/app.log
StandardError=append:/var/www/shirzadBot/logs/error.log

[Install]
WantedBy=multi-user.target
```

### راه‌اندازی service

```bash
# Reload systemd
sudo systemctl daemon-reload

# فعال‌سازی خودکار در boot
sudo systemctl enable shirzadbot

# شروع سرویس
sudo systemctl start shirzadbot

# بررسی وضعیت
sudo systemctl status shirzadbot
```

---

## ۵️⃣ تنظیمات Nginx (Reverse Proxy)

### ایجاد configuration

```bash
sudo nano /etc/nginx/sites-available/shirzadbot
```

محتوای زیر را قرار دهید:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN.COM;  # یا IP_آدرس_سرور

    # افزایش timeout برای کارهای طولانی
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;

    # اندازه body برای آپلود
    client_max_body_size 50M;

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_cache_bypass $http_upgrade;
    }

    # لاگ‌ها
    access_log /var/log/nginx/shirzadbot_access.log;
    error_log /var/log/nginx/shirzadbot_error.log;
}
```

### فعال‌سازی سایت

```bash
# ایجاد symlink
sudo ln -s /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/

# تست تنظیمات
sudo nginx -t

# Restart Nginx
sudo systemctl restart nginx
```

---

## ۶️⃣ تنظیم SSL با Let's Encrypt (اختیاری اما توصیه می‌شود)

### نصب Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx

# دریافت SSL
sudo certbot --nginx -d YOUR_DOMAIN.COM

# تست auto-renewal
sudo certbot renew --dry-run
```

---

## ۷️⃣ تنظیمات فایروال

### باز کردن پورت‌های لازم

```bash
# بررسی وضعیت فایروال
sudo ufw status

# باز کردن پورت‌ها (اگر از ufw استفاده می‌کنید)
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS

# فعال‌سازی فایروال
sudo ufw enable
```

---

## ۸️⃣ مدیریت و رصد

### دستورات مفید

```bash
# مشاهده logs
sudo journalctl -u shirzadbot -f

# یا
tail -f /var/www/shirzadBot/logs/app.log

# Restart سرویس
sudo systemctl restart shirzadbot

# Stop سرویس
sudo systemctl stop shirzadbot

# بررسی وضعیت
sudo systemctl status shirzadbot

# بررسی پورت
netstat -tlnp | grep 5000
```

### Backup خودکار

```bash
# ایجاد script backup
nano /var/www/shirzadBot/backup.sh
```

محتوای زیر:

```bash
#!/bin/bash
BACKUP_DIR="/var/backups/shirzadbot"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
cp /var/www/shirzadBot/multi_bot_platform.db $BACKUP_DIR/db_$DATE.db

# حذف backup‌های قدیمی‌تر از 7 روز
find $BACKUP_DIR -name "*.db" -mtime +7 -delete

echo "Backup completed: $DATE"
```

اجرا:

```bash
chmod +x /var/www/shirzadBot/backup.sh

# اضافه به crontab
crontab -e

# اضافه این خط (هر شب ساعت 2)
0 2 * * * /var/www/shirzadBot/backup.sh
```

---

## ۹️⃣ بررسی و تست

### چک لیست

```bash
# ✅ Service در حال اجراست؟
sudo systemctl status shirzadbot

# ✅ پورت 5000 باز است؟
netstat -tlnp | grep 5000

# ✅ Nginx کار می‌کند؟
sudo systemctl status nginx

# ✅ لاگ‌ها نرمال هستند؟
tail -n 50 /var/www/shirzadBot/logs/app.log

# ✅ دسترسی به UI
curl http://localhost:5000
```

### تست در مرورگر

```
http://YOUR_DOMAIN.COM
یا
http://YOUR_SERVER_IP
```

---

## 🔟 Troubleshooting

### مشکل: Service شروع نمی‌شود

```bash
# بررسی logs
sudo journalctl -u shirzadbot -n 50

# بررسی دسترسی‌ها
ls -la /var/www/shirzadBot

# بررسی PATH
which python3
```

### مشکل: 502 Bad Gateway

```bash
# بررسی سرویس
sudo systemctl status shirzadbot

# بررسی پورت
netstat -tlnp | grep 5000

# بررسی firewall
sudo ufw status
```

### مشکل: Database error

```bash
# بررسی دسترسی
ls -la /var/www/shirzadBot/*.db

# بررسی permission
sudo chown www-data:www-data /var/www/shirzadBot/*.db
sudo chmod 644 /var/www/shirzadBot/*.db
```

### مشکل: Upload failed

```bash
# بررسی پوشه uploads
ls -la /var/www/shirzadBot/uploads

# اصلاح permission
sudo chown -R www-data:www-data /var/www/shirzadBot/uploads
sudo chmod -R 755 /var/www/shirzadBot/uploads
```

---

## 📊 مانیتورینگ (اختیاری)

### نصب htop

```bash
sudo apt install -y htop
htop
```

### نصب log viewer

```bash
# برای tail real-time
tail -f /var/www/shirzadBot/logs/app.log /var/www/shirzadBot/logs/error.log

# یا با less
less +F /var/www/shirzadBot/logs/app.log
```

---

## 🎉 تبریک! پروژه شما آماده است!

### دستورات سریع مدیریت

```bash
# Restart کامل
sudo systemctl restart shirzadbot && sudo systemctl restart nginx

# مشاهده logs
tail -f /var/www/shirzadBot/logs/app.log

# بررسی وضعیت
sudo systemctl status shirzadbot

# Backup manual
/var/www/shirzadBot/backup.sh
```

### به‌روزرسانی کد

```bash
cd /var/www/shirzadBot
git pull origin main
sudo systemctl restart shirzadbot
```

---

## 🔐 نکات امنیتی

1. ✅ توکن‌ها را تغییر دهید
2. ✅ از SSL استفاده کنید
3. ✅ فایروال را فعال کنید
4. ✅ فایل‌های حساس را در .gitignore بگذارید
5. ✅ User/group را به www-data تنظیم کنید
6. ✅ Permission‌ها را محدود کنید
7. ✅ backup منظم انجام دهید
8. ✅ لاگ‌ها را چک کنید

---

**موفق باشید! 🚀**

