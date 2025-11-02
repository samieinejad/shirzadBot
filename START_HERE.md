# 🚀 START HERE - Quick Guide

## 🎯 مرحله ۱: روی Local Machine (Windows)

### ۱.۱ آماده‌سازی:

```bash
# Clone from Git
git clone <YOUR_REPO_URL>
cd shirzadBot

# Check Python
python --version

# Install dependencies
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Edit tokens in app.py
nano app.py  # Lines 135-141

# Run
python app.py
# Or: RUN_BOT.bat

# Open browser
# http://localhost:5000
```

---

## 🌐 مرحله ۲: روی Production Server (Ubuntu)

### ۲.۱ نصب سریع:

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install packages
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor

# 3. Clone project
sudo mkdir -p /var/www/shirzadBot
sudo chown $USER:$USER /var/www/shirzadBot
cd /var/www/shirzadBot
git clone <YOUR_REPO_URL> .

# 4. Auto-install (easiest way!)
bash deploy/install.sh

# 5. Configure tokens
nano app.py  # Edit lines 135-141

# 6. Start service
sudo systemctl start shirzadbot
sudo systemctl status shirzadbot

# 7. Check logs
tail -f logs/app.log

# 8. Access UI
# http://YOUR_SERVER_IP
```

---

## 📚 Documentation Files

### برای شروع:
1. **IMPORTANT.md** ⚠️ - هشدارهای مهم (حتماً بخوانید!)
2. **USER_GUIDE.md** 📖 - راهنمای کامل کاربری
3. **WHAT_CAN_YOU_DO.md** 🎯 - چه کارهایی می‌توانید انجام دهید
4. **QUICK_REFERENCE.md** ⚡ - مرجع سریع

### برای Deploy:
1. **DEPLOY_UBUNTU.md** 🚀 - راهنمای کامل Deploy
2. **DEPLOYMENT_CHECKLIST.md** ✅ - چک‌لیست
3. **deploy/README.md** 🔧 - راهنمای Scripts
4. **PRODUCTION_READY.md** 🎉 - خلاصه

---

## ⚡ Quick Commands

### Windows:
```batch
RUN_BOT.bat              # اجرای برنامه
```

### Ubuntu:
```bash
bash deploy/install.sh   # نصب
bash deploy/update.sh    # به‌روزرسانی
bash deploy/backup.sh    # Backup
sudo systemctl restart shirzadbot  # Restart
```

---

## 🔐 Security First!

**قبل از Push به Git:**
1. ✅ توکن‌ها را از `app.py` حذف کنید (خط 135-141)
2. ✅ `.gitignore` را چک کنید
3. ✅ Database و log files Push نشوند

---

## 📋 Deployment Checklist

- [ ] Git repository created
- [ ] Code pushed to Git
- [ ] Ubuntu server ready
- [ ] Tokens configured
- [ ] Service running
- [ ] Nginx configured
- [ ] SSL certificate installed (optional)
- [ ] Backup automated
- [ ] Monitoring setup
- [ ] Documentation read

---

## 🆘 Need Help?

### Common Issues:

**❌ Python not found**
→ `QUICK_START.md` یا `INSTALL_PYTHON.md`

**❌ Service won't start**
→ Check: `sudo journalctl -u shirzadbot -n 50`

**❌ Can't access UI**
→ Check: `sudo systemctl status shirzadbot`
→ Check: `netstat -tlnp | grep 5000`

**❌ Deployment errors**
→ `DEPLOY_UBUNTU.md` section "Troubleshooting"

---

## 🎉 Ready!

**محلی:** دابل‌کلیک `RUN_BOT.bat`  
**سرور:** `bash deploy/install.sh` سپس `sudo systemctl start shirzadbot`

**موفق باشید! 🚀**

