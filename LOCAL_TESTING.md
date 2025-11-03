# 🖥️ Local Testing Guide

## Quick Start

### 1. Start the Server

**PowerShell (Windows):**
```powershell
# Navigate to project
cd D:\dev\workspace\shirzadBot

# Activate venv
.\venv\Scripts\activate

# Run the app
python app.py
```

**Bash (Linux/Mac):**
```bash
cd /path/to/shirzadBot
source venv/bin/activate
python app.py
```

**Expected output:**
```
✅ Configuration loaded from config.py
Starting application...
Running on http://127.0.0.1:5010
Press CTRL+C to quit
```

### 2. Test Login

**Open Browser:**
```
http://localhost:5010/login
```

**Login Credentials:**
- Mobile: `09124335080`
- OTP: `11111`

**Expected Result:**
- ✅ Redirect to customer dashboard
- OR redirect to admin dashboard (if admin)

### 3. Access Features

| URL | What You'll See |
|-----|----------------|
| http://localhost:5010/ | Landing page |
| http://localhost:5010/login | Login form |
| http://localhost:5010/customer | Customer dashboard |
| http://localhost:5010/dashboard | Admin dashboard (admin only) |
| http://localhost:5010/admin/users | User management (admin only) |

### 4. Verify Admin

**Check Admin Status:**
```bash
python check_db.py
```

**Expected output:**
```
OK: Admin user exists: 09124335080 (Admin: 1)
```

**Make Another User Admin:**
```bash
python admin_setup.py admin 09123456789
```

**List All Users:**
```bash
python admin_setup.py list
```

## 🔧 Troubleshooting

### Issue: "No module named 'flask'"
**Solution:**
```powershell
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Issue: "Port already in use"
**Solution:**
```powershell
# Find what's using port 5010
netstat -ano | findstr :5010

# Kill the process
taskkill /PID <PID_NUMBER> /F

# Or change port in app.py
```

### Issue: "Database locked"
**Solution:**
```powershell
# Make sure only one app.py is running
# Stop all instances and restart
```

### Issue: "Can't create superadmin"
**Solution:**
```powershell
# First ensure database exists
python check_db.py

# Then create admin
python create_superadmin.py
```

## 📊 Testing Checklist

- [ ] Server starts without errors
- [ ] Landing page loads
- [ ] Login page works
- [ ] Can login with `11111`
- [ ] Redirects to correct dashboard
- [ ] Can access admin panel (if admin)
- [ ] Can view users (if admin)
- [ ] All routes respond

## 🎯 What to Test

### As Regular User
1. ✅ Sign up with mobile
2. ✅ Login
3. ✅ View customer dashboard
4. ✅ Check balance
5. ✅ View profile

### As Admin
1. ✅ Login
2. ✅ Access admin dashboard
3. ✅ View all users
4. ✅ Manage bots
5. ✅ See statistics

## 🚀 Next Steps

After local testing works:
1. Test on production
2. Create admin on production
3. Get first users
4. Start making money! 💰

---

**Everything should work on localhost now!**

