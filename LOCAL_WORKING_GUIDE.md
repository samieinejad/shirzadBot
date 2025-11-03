# 💻 Local Development Guide

## ✅ What You Have Locally

### 1. Admin Created ✅
- **Mobile**: `09124335080`
- **OTP**: `11111` (dev bypass)
- **Status**: Super Admin

### 2. Available Endpoints

#### Public
- `http://localhost:5010/` - Landing page
- `http://localhost:5010/login` - Login/signup

#### Customer (after login)
- `http://localhost:5010/customer` - Customer dashboard
- `http://localhost:5010/profile` - Profile page
- `http://localhost:5010/billing` - Charge account

#### Admin (after login as admin)
- `http://localhost:5010/dashboard` - Admin dashboard
- `http://localhost:5010/admin` - Admin dashboard (alias)
- `http://localhost:5010/admin/users` - View all users

### 3. Running Locally

```bash
# Activate venv
venv\Scripts\activate

# Run app
python app.py

# Or use batch file
run_simple.bat
```

Then open: http://localhost:5010

## 🧪 Testing

### Test Login
1. Go to http://localhost:5010/login
2. Mobile: `09124335080`
3. OTP: `11111`
4. Should redirect to `/customer` or `/dashboard`

### Test Admin Panel
1. Login as admin
2. Click "مدیریت کاربران" in sidebar
3. See all users

### Test Customer Features
1. Register a new user
2. Login
3. Access customer dashboard
4. Manage profile
5. Charge account

## 📁 Key Files

### Main App
- `app.py` - Main application (18k lines)
- `index.html` - Admin dashboard UI
- `config.py` - Configuration

### Database
- `multi_bot_platform.db` - SQLite database
- `app/utils/db_schema.py` - Schema definitions
- `app/utils/database.py` - DB helpers

### Auth
- `app/services/auth_service.py` - Auth logic
- `create_superadmin.py` - Create admin
- `admin_setup.py` - User management

### Structure
- `app/` - New modular structure
  - `services/` - Business logic
  - `routes/` - Flask routes
  - `utils/` - Utilities
  - `models/` - Data models
  - `decorators/` - Decorators
  - `bots/` - Bot code

## 🎯 What You Can Work On

### Immediate Tasks
1. ✅ Test all features locally
2. ✅ Verify admin panel
3. ✅ Test customer flow
4. ✅ Check billing integration

### Next Steps
1. Deploy to production
2. Get more users
3. Add features
4. Grow business

## 🔧 Useful Commands

```bash
# Check database
python check_db.py
python admin_setup.py list

# Create admin
python create_superadmin.py

# Make user admin
python admin_setup.py admin 09XXXXXXXXX

# Run app
python app.py

# Run in background
python app.py &
```

## 📊 Current Status

✅ **Local**: Everything working
✅ **Admin**: Created and working
✅ **Auth**: OTP bypass working
✅ **Dashboard**: Customer + Admin ready
✅ **Database**: Configured

⏳ **Production**: Needs admin setup

---

**You're all set for local development!** 🎉

Focus on building features or deploy to production!

