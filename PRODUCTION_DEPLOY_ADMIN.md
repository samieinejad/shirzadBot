# 🚀 Deploy Admin to Production

## ⚠️ Problem

You're seeing "کد تایید نامعتبر یا منقضی شده" on production.

**Cause**: Your local database has the admin, but production doesn't!

## ✅ Solution

### Step 1: Pull Latest Code

```bash
# SSH to production
ssh msn@your-server

# Go to project
cd /var/www/shirzadBot

# Pull latest code
git pull origin main

# Stop service temporarily
sudo systemctl stop shirzadbot
```

### Step 2: Create Superadmin on Production

```bash
# Activate venv
source venv/bin/activate

# Run superadmin script
python3 create_superadmin.py
```

**Expected output**:
```
SUCCESS: Superadmin created with mobile: 09124335080

To login:
1. Go to https://social.msn1.ir/login
2. Enter mobile: 09124335080
3. Use OTP code: 11111
4. You'll be redirected to admin dashboard
```

### Step 3: Start Service

```bash
# Start service
sudo systemctl start shirzadbot

# Check status
sudo systemctl status shirzadbot

# Check logs if needed
tail -f logs/app.log
```

### Step 4: Test Login

1. Go to https://social.msn1.ir/login
2. Mobile: `09124335080`
3. OTP: `11111`
4. Should redirect to `/customer` or `/dashboard`

## 🔍 If Still Not Working

### Check Logs

```bash
# Check app logs
tail -100 logs/app.log

# Check error logs  
tail -100 logs/error.log

# Check systemctl
sudo journalctl -u shirzadbot -n 50 --no-pager
```

### Verify Database

```bash
python3 check_db.py
```

### Verify User

```bash
python3 -c "import sqlite3; conn = sqlite3.connect('multi_bot_platform.db'); cursor = conn.cursor(); cursor.execute('SELECT mobile, is_admin FROM users'); print(cursor.fetchall()); conn.close()"
```

### Re-run Setup

```bash
python3 create_superadmin.py
```

## 📊 Verification Checklist

Before you finish, verify:

- [ ] Code pulled successfully
- [ ] Admin script ran without errors
- [ ] Service restarted
- [ ] Login works
- [ ] Can access admin dashboard
- [ ] Can see `/admin/users` page

## 🚨 Common Issues

### Issue 1: Permission Denied
```bash
# Fix permissions
sudo chown -R msn:msn /var/www/shirzadBot
```

### Issue 2: Database Locked
```bash
# Stop service first
sudo systemctl stop shirzadbot

# Then run script
python3 create_superadmin.py

# Start service
sudo systemctl start shirzadbot
```

### Issue 3: Import Errors
```bash
# Reinstall dependencies
source venv/bin/activate
pip install -r requirements.txt
```

## 🎯 After Successful Deployment

Once working:
1. ✅ Test login with 09124335080
2. ✅ Access admin dashboard
3. ✅ View users page
4. ✅ Everything works!

---

**Run these commands on your production server NOW!**

