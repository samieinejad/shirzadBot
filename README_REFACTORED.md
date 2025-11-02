# 🎉 Shirzad Bot Platform - Refactored Structure

## 📁 New Directory Structure

```
shirzadBot/
├── app/                          # Main application package
│   ├── __init__.py              # Flask factory
│   ├── settings.py              # Configuration
│   ├── models/                  # Database models
│   ├── services/                # Business logic
│   ├── routes/                  # Route handlers
│   │   ├── auth.py             # Authentication routes
│   │   ├── admin.py            # Admin routes
│   │   └── api.py              # API routes
│   ├── decorators/              # Custom decorators
│   ├── utils/                   # Utilities
│   │   └── database.py         # Database helpers
│   └── bots/                    # Bot implementations
├── templates/                    # HTML templates
├── static/                       # Static files (CSS, JS)
├── logs/                         # Log files
├── docs/                         # Documentation
├── app.py                        # Legacy (still works!)
├── run.py                        # New entry point
├── config.py                     # Configuration (gitignored)
└── requirements.txt              # Dependencies
```

## ✨ Features

### 🎯 Multi-User Platform
- ✅ Iranian mobile authentication (OTP)
- ✅ User registration and login
- ✅ Admin panel for user management
- ✅ Per-user token management
- ✅ Session-based authentication

### 💳 Payment System
- ✅ Payping integration
- ✅ Account balance management
- ✅ Transaction history

### 🤖 Bot Management
- ✅ Telegram Bot integration
- ✅ Bale Bot integration
- ✅ Ita Bot integration
- ✅ Unified dashboard

### 📊 Features
- ✅ Group broadcasting
- ✅ Scheduled messages
- ✅ Tag management
- ✅ Admin operations (promote, demote, pin, etc.)
- ✅ Comprehensive reporting
- ✅ Excel exports

## 🚀 Quick Start

### Installation

```bash
# Clone repository
git clone https://github.com/samieinejad/shirzadBot.git
cd shirzadBot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Configure
cp config.example.py config.py
# Edit config.py with your tokens

# Run
python app.py
```

### Production Deployment

```bash
cd /var/www/shirzadBot
git pull
sudo systemctl restart shirzadbot
```

## 📝 Configuration

Edit `config.py`:

```python
# Bot Tokens
TELEGRAM_BOT_TOKEN = "your_token"
BALE_BOT_TOKEN = "your_token"
ITA_BOT_TOKEN = "your_token"

# Owner IDs
OWNER_ID = 123456789

# SMS API
KAVENEGAR_API_KEY = "your_key"

# Payment
PAYPING_TOKEN = "your_token"
```

## 🎯 Access Levels

| Route | Access | Description |
|-------|--------|-------------|
| `/` | Public | Landing page |
| `/login` | Public | Login/signup |
| `/dashboard` | Admin | Bot dashboard |
| `/admin/users` | Admin | User management |
| `/billing` | User | Account charging |

## 🔑 Admin Setup

```bash
# Register via website first, then:
python3 make_admin.py YOUR_MOBILE_NUMBER
```

## 🧪 Development

```bash
# Test OTP code: 11111 (for any mobile)
# Run locally: python app.py
# Run new structure: python run.py (when ready)
```

## 📖 Documentation

- `README.md` - This file
- `SETUP_COMPLETE.md` - Setup guide
- `ADMIN_SETUP.md` - Admin configuration
- `MULTI_USER_AUTH_FEATURE.md` - Authentication details
- `REFACTORING_PLAN.md` - Code structure plan
- `MIGRATION_GUIDE.md` - Migration guide

## 🏗️ Architecture

### SOLID Principles
- ✅ Single Responsibility
- ✅ Open/Closed
- ✅ Liskov Substitution
- ✅ Interface Segregation
- ✅ Dependency Inversion

### Best Practices
- ✅ Separation of concerns
- ✅ Modular design
- ✅ Clean architecture
- ✅ Industry standards

## 📞 Support

For issues or questions, check the documentation files.

---

**Version**: 2.0 (Refactored)  
**Status**: Production Ready  
**License**: MIT

