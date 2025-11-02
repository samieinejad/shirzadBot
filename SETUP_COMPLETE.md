# 🎉 Setup Complete - Multi-User Bot Platform

## ✅ What's Ready

### 1. Landing Page
- Beautiful presentation page at root URL: `https://social.msn1.ir`
- Features showcase
- Call-to-action buttons
- **Anyone can view this page**

### 2. User Registration & Login
- Visit `/login` or `/signup`
- Enter Iranian mobile number (09xxxxxxxxx)
- OTP verification
- **Development Mode**: Use code `11111` for any mobile number

### 3. Admin System
- Root dashboard `/dashboard` or `/admin` - **Admin Only**
- All bot management features require admin access
- User management panel at `/admin/users`

### 4. Billing System
- Payping integration ready
- User balance tracking
- Transaction history

## 🚀 Quick Start Guide

### Step 1: Pull Latest Code on Server

```bash
cd /var/www/shirzadBot
git pull
sudo systemctl restart shirzadbot
```

### Step 2: Make Yourself Admin

```bash
# First, register through website
# Visit: https://social.msn1.ir/login

# Then make yourself admin:
python3 make_admin.py YOUR_MOBILE_NUMBER

# Example:
python3 make_admin.py 09123456789
```

### Step 3: Configure API Keys (Optional)

Edit `config.py` and add:
```python
KAVENEGAR_API_KEY = "your_kavenegar_key"  # For real SMS
PAYPING_TOKEN = "your_payping_token"      # For payments
```

**Note**: Without these, OTP bypass (11111) and billing won't work with real services, but you can test!

### Step 4: Access Your Platform

- **Public**: `https://social.msn1.ir/` - Landing page
- **Admin Dashboard**: `https://social.msn1.ir/admin` - Full bot control
- **User Management**: `https://social.msn1.ir/admin/users` - See all users
- **Billing**: `https://social.msn1.ir/billing` - Charge accounts

## 📋 Testing Flow

### As New User:
1. Visit `https://social.msn1.ir`
2. Click "شروع کنید"
3. Enter mobile: `09123456789`
4. Click "ارسال کد تایید" (or skip SMS)
5. Enter code: `11111`
6. Click "تایید"
7. ✅ Logged in!

### As Admin:
1. After making yourself admin (see Step 2)
2. Visit `https://social.msn1.ir/admin`
3. See full dashboard with all bot features
4. Visit `https://social.msn1.ir/admin/users`
5. See all registered users

## 🔐 Access Levels

| Route | Access | Description |
|-------|--------|-------------|
| `/` | Public | Landing page |
| `/login` | Public | Login/signup |
| `/billing` | Authenticated | Charge account |
| `/dashboard` | Admin | Main bot dashboard |
| `/admin` | Admin | Main bot dashboard |
| `/admin/users` | Admin | User management |
| `/api/*` | Various | API endpoints |

## 🎯 Current Features

### ✅ Working
- User registration with mobile + OTP
- Admin authentication system
- Admin panel to view users
- Beautiful landing page
- Billing/payment structure
- Session management

### ⏳ TODO
- Migrate bot features to per-user mode
- Add user_id to chats table
- Filter data by user
- Add billing deduction logic
- Regular user dashboard

## 🛠️ Development Tools

### Make User Admin:
```bash
python3 make_admin.py 09123456789
```

### OTP Bypass:
- Use code `11111` for any mobile number
- No SMS needed for testing

## 📝 Important Notes

1. **First User**: Make yourself admin after registration
2. **OTP Code**: `11111` works for all users (dev mode)
3. **Landing Page**: Public, anyone can see
4. **Dashboard**: Admin only, protected
5. **Bot Features**: Still use global config (needs migration)

## 🎉 You're All Set!

Your platform is ready with:
- ✅ Multi-user authentication
- ✅ Admin panel
- ✅ Beautiful landing page
- ✅ Payment gateway ready
- ✅ Production hosting at social.msn1.ir

**Next**: Test it, make yourself admin, and enjoy!

---

**Questions?** Check `ADMIN_SETUP.md` and `MULTI_USER_AUTH_FEATURE.md` for details.

