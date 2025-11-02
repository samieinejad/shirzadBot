# 🚨 فوری: توکن‌های شما محافظت نمی‌شوند!

## ❌ **مشکل فعلی:**

توکن‌های واقعی شما در `app.py` خطوط 150-155 هستند و در Git History موجودند!

```python
TELEGRAM_BOT_TOKEN = "YOUR_TOKEN_HERE"  # ❌ واقعی!
BALE_BOT_TOKEN = "YOUR_TOKEN_HERE"  # ❌ واقعی!
ITA_BOT_TOKEN = "YOUR_TOKEN_HERE"        # ❌ واقعی!
```

---

## ✅ **Fix Now (3 دقیقه)**

### **مرحله ۱: توکن‌های فعلی را Secure کنید**

فایل `config.py` را ویرایش کنید:

```bash
nano config.py
```

توکن‌های فعلی را وارد کنید:
```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_TOKEN_HERE"
BALE_BOT_TOKEN = "YOUR_BALE_TOKEN_HERE"
ITA_BOT_TOKEN = "YOUR_ITA_TOKEN_HERE"

OWNER_ID = YOUR_OWNER_ID
BALE_OWNER_ID = YOUR_BALE_OWNER_ID
ITA_OWNER_ID = "YOUR_ITA_OWNER_ID"
```

### **مرحله ۲: از app.py حذف کنید**

```bash
nano app.py
```

خطوط 150-155 را تغییر دهید به:

```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_TOKEN_HERE"
BALE_BOT_TOKEN = "YOUR_BALE_TOKEN_HERE"
ITA_BOT_TOKEN = "YOUR_ITA_TOKEN_HERE"

OWNER_ID = 0
BALE_OWNER_ID = 0
ITA_OWNER_ID = "0"
```

### **مرحله ۳: تست کنید**

```bash
python app.py
```

باید ببینید:
```
✅ Configuration loaded from config.py
```

---

## 🔐 **اگر Repository Public است**

### **آپشن ۱: Private کنید (فوری)**

```
1. GitHub → Repo Settings → Change visibility → Make private
```

### **آپشن ۲: توکن‌ها را Revoke کنید**

```
Telegram: @BotFather → /revoke
Bale: Dashboard → Revoke token  
Ita: Admin panel → Revoke token
```

---

## 📋 **بررسی امنیت**

```bash
# چک که config.py در Git نیست
git status
# نباید config.py را ببیند!

# چک .gitignore
cat .gitignore | grep config.py
# باید ببیند: config.py
```

---

**این کار را همین الان انجام دهید! ⏰**

