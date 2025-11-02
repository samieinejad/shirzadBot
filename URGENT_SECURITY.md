# 🚨 URGENT: توکن‌های شما ممکن است لو رفته باشند!

## 🔴 **وضعیت اضطراری**

توکن‌های واقعی شما در Git History موجود هستند و **در صورت Public بودن Repository، در معرض دید همگان!**

---

## ⚡ **اقدام فوری (Do NOW!)**

### ۱. فوراً Revoke کنید:

#### Telegram:
```
1. باز کردن: @BotFather در تلگرام
2. ارسال دستور: /revoke
3. انتخاب ربات خود
4. تأیید Revoke
5. توکن جدید دریافت کنید
```

#### Bale:
```
1. پنل توسعه‌دهنده Bale را باز کنید
2. ربات خود را انتخاب کنید
3. Revoke توکن
4. توکن جدید ایجاد کنید
```

#### Ita:
```
1. پنل ادمین Ita را باز کنید
2. Revoke توکن
3. توکن جدید ایجاد کنید
```

### ۲. توکن‌های جدید را Secure کنید:

```bash
# کپی example
copy config.example.py config.py

# ویرایش config.py
nano config.py
```

توکن‌های جدید را وارد کنید:
```python
TELEGRAM_BOT_TOKEN = "TOKEN_NEW_1"
BALE_BOT_TOKEN = "TOKEN_NEW_2"
ITA_BOT_TOKEN = "TOKEN_NEW_3"
```

### ۳. از app.py حذف کنید:

```bash
# ویرایش app.py
nano app.py
```

مطمئن شوید خطوط fallback دارای مقادیر placeholder هستند:
```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_TOKEN"
BALE_BOT_TOKEN = "YOUR_BALE_TOKEN"
ITA_BOT_TOKEN = "YOUR_ITA_TOKEN"
```

---

## 🔐 **ایمن‌سازی Git History**

### **مشکل:** توکن‌ها در Git History هستند

### **راه حل:**

#### گزینه ۱: Repository جدید (راحت‌تر)

```bash
# 1. Create new repo on GitHub (private!)
# 2. Remove old repo
# 3. Clone locally
# 4. Copy your files (except .git)
# 5. Initialize new git
git init
git remote add origin <NEW_REPO_URL>
git add .
git commit -m "Clean history - no tokens"
git push origin main
```

#### گزینه ۲: پاک کردن History (پیچیده‌تر)

```bash
# ⚠️ احتیاط: این History را از بین می‌برد!
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch app.py" \
  --prune-empty --tag-name-filter cat -- --all

# Force push
git push origin --force --all
```

---

## ✅ **اقدامات امنیتی**

### ۱. Repository را Private کنید:

```
1. GitHub → Settings → Change visibility → Make private
```

### ۲. .gitignore را چک کنید:

```bash
cat .gitignore | grep config.py
```

باید ببیند: `config.py`

### ۳. بررسی که config.py Push نشده:

```bash
git ls-files | grep config.py
```

نباید چیزی نشان دهد!

### ۴. تست کنید:

```bash
# اجرا
python app.py

# باید ببیند:
# ✅ Configuration loaded from config.py
```

---

## 📋 **چک‌لیست امنیتی**

- [ ] توکن‌های قدیمی Revoke شدند
- [ ] توکن‌های جدید دریافت شدند
- [ ] توکن‌های جدید در config.py قرار گرفتند
- [ ] config.py در .gitignore است
- [ ] app.py دارای placeholder است
- [ ] Repository Private شد
- [ ] تست انجام شد و کار می‌کند
- [ ] Git History پاک شد یا Repository جدید ایجاد شد

---

## 🔄 **بعد از Fix کردن**

### روی Production Server:

```bash
# 1. Pull latest code
git pull origin main

# 2. Create config.py
cp config.example.py config.py

# 3. Edit with NEW tokens
nano config.py

# 4. Restart
sudo systemctl restart shirzadbot

# 5. Check
sudo systemctl status shirzadbot
```

---

## 🆘 **اگر کسی از توکن‌ها استفاده کرد**

### چک کردن سوء استفاده:

```bash
# Check logs
tail -f logs/app.log

# Check last activity
# در پلتفرم‌ها چک کنید:
- تلگرام: @BotFather → ربات خود → آمار
- بله: Dashboard → Analytics
- ایتا: Dashboard → Activity logs
```

### اگر سوء استفاده مشاهده شد:

1. ✅ تمام توکن‌ها را Revoke کنید
2. ✅ توکن‌های کاملاً جدید بگیرید
3. ✅ Repository را Private کنید
4. ✅ لاگ‌ها را بررسی کنید
5. ✅ تمام عملیات مشکوک را Cancel کنید

---

## 📞 **Help**

اگر نیاز به کمک دارید:
1. تمام لاگ‌ها را Save کنید
2. تمام پیام‌های خطا را کپی کنید
3. وضعیت فعلی را بررسی کنید

---

**⚠️ حتماً همین الان Revoke کنید! دیر نشود! 🚨**

