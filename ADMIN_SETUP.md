# Admin Setup Guide

## ✅ What's Been Added

### 1. Admin System
- ✅ `is_admin` column added to `users` table
- ✅ `@require_admin` decorator for admin-only routes
- ✅ Admin panel at `/admin/users` to view all users
- ✅ API endpoints for admin operations

### 2. Public Landing Page
- ✅ Beautiful presentation page at `/` (root)
- ✅ Features showcase with gradient design
- ✅ Call-to-action buttons
- ✅ Responsive design

### 3. Access Control
- `/` → Public landing page (anyone can see)
- `/dashboard` or `/admin` → Admin dashboard (requires admin login)
- `/admin/users` → User management panel (requires admin)
- `/login` → Login/signup page
- `/billing` → User billing page (requires auth)

## 🎯 How to Make Yourself Admin

### Method 1: Using Script (Recommended)

After you've registered through the website:

```bash
# On Ubuntu server
cd /var/www/shirzadBot
python3 make_admin.py YOUR_MOBILE_NUMBER

# Example
python3 make_admin.py 09123456789
```

### Method 2: Direct Database

```bash
cd /var/www/shirzadBot
sqlite3 multi_bot_platform.db

# In SQLite prompt:
UPDATE users SET is_admin = 1 WHERE mobile = '09123456789';
.quit
```

### Method 3: Through Code (First User Auto-Admin)

The first user to register can be automatically made admin. This would need a small code addition.

## 📋 Admin Panel Features

Visit `/admin/users` to see:
- ✅ List of all registered users
- ✅ User mobile numbers
- ✅ Verification status
- ✅ Current balance
- ✅ Total charges
- ✅ Transaction count
- ✅ Registration date
- ✅ Last login time
- ✅ Account status (active/inactive)

## 🔒 Access Levels

### Public Access
- `/` - Landing page
- `/login` - Login page
- `/signup` - Signup page

### Authenticated Users
- `/billing` - Charge account
- `/api/auth/*` - Auth endpoints

### Admin Only
- `/dashboard` - Main bot dashboard
- `/admin` - Main bot dashboard
- `/admin/users` - User management
- All existing bot features

## 🚀 Workflow

1. **User visits**: `https://social.msn1.ir`
2. **Sees**: Beautiful landing page with features
3. **Clicks**: "شروع کنید" (Start)
4. **Redirected**: To `/login`
5. **Registers**: With mobile + OTP
6. **After login**: Redirected to `/` (landing page again!)
7. **Admin visits**: `/dashboard` or `/admin`
8. **Sees**: Full bot dashboard
9. **Regular users**: Cannot access dashboard

## ⚠️ Important Notes

- Users who try to access `/dashboard` without admin will be redirected to dashboard
- Need to create regular user dashboard
- Or show message: "You need admin access"
- Consider adding user dashboard at `/user-dashboard`

## 📝 Next Steps

1. ✅ Make yourself admin using the script
2. ✅ Test admin panel at `/admin/users`
3. ✅ Verify that `/` shows landing page to everyone
4. ⏳ Add regular user dashboard
5. ⏳ Add features to admin panel (edit users, etc.)

## 🎨 Landing Page Sections

1. **Hero Section** - Eye-catching gradient with main CTA
2. **Features Grid** - 6 main features with icons
3. **Call-to-Action** - Another signup prompt
4. **Footer** - Copyright info

All sections are responsive and use Persian RTL layout.

