# 🚀 Production Setup Guide - social.msn1.ir

## 🎯 Quick Start (5 minutes)

You've already cloned to: `/var/www/shirzadBot`

---

## 📝 Step-by-Step Commands

### **1. Run the Setup Script:**

```bash
cd /var/www/shirzadBot

# Make script executable
chmod +x PRODUCTION_SETUP.sh

# Run setup
bash PRODUCTION_SETUP.sh
```

The script will:
- ✅ Install all dependencies
- ✅ Create virtual environment
- ✅ Install Python packages
- ✅ Create systemd service
- ✅ Configure Nginx for social.msn1.ir
- ✅ Setup SSL certificate
- ✅ Start the service

### **2. Configure Tokens:**

The script will ask you to edit config.py:

```bash
nano config.py
```

Add your tokens:
```python
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_TOKEN"
BALE_BOT_TOKEN = "YOUR_BALE_TOKEN"
ITA_BOT_TOKEN = "YOUR_ITA_TOKEN"

OWNER_ID = YOUR_OWNER_ID
BALE_OWNER_ID = YOUR_BALE_OWNER_ID
ITA_OWNER_ID = "YOUR_ITA_OWNER_ID"
```

Save and exit: `Ctrl+X`, `Y`, `Enter`

### **3. Start Service:**

```bash
sudo systemctl start shirzadbot
sudo systemctl status shirzadbot
```

---

## 🌐 Access Your Bot

```
https://social.msn1.ir
```

---

## 🔧 Manual Setup (If Script Fails)

### **1. Install Dependencies:**

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 certbot python3-certbot-nginx
```

### **2. Setup Virtual Environment:**

```bash
cd /var/www/shirzadBot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### **3. Create config.py:**

```bash
cp config.example.py config.py
nano config.py  # Add your tokens
```

### **4. Create Systemd Service:**

```bash
sudo nano /etc/systemd/system/shirzadbot.service
```

Paste:
```ini
[Unit]
Description=Shirzad Bot Platform
After=network.target

[Service]
Type=simple
User=msn
Group=msn
WorkingDirectory=/var/www/shirzadBot
Environment="PATH=/var/www/shirzadBot/venv/bin"
ExecStart=/var/www/shirzadBot/venv/bin/python app.py
Restart=always
RestartSec=10

StandardOutput=append:/var/www/shirzadBot/logs/app.log
StandardError=append:/var/www/shirzadBot/logs/error.log

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable shirzadbot
sudo systemctl start shirzadbot
```

### **5. Configure Nginx:**

```bash
sudo nano /etc/nginx/sites-available/shirzadbot
```

Paste:
```nginx
server {
    listen 80;
    server_name social.msn1.ir www.social.msn1.ir;

    client_max_body_size 50M;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    access_log /var/log/nginx/shirzadbot_access.log;
    error_log /var/log/nginx/shirzadbot_error.log;
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### **6. Setup SSL:**

```bash
sudo certbot --nginx -d social.msn1.ir -d www.social.msn1.ir
```

---

## ✅ Verify Installation

```bash
# Check service
sudo systemctl status shirzadbot

# Check port
netstat -tlnp | grep 5000

# Check Nginx
sudo systemctl status nginx

# Check logs
tail -f logs/app.log

# Test from browser
curl http://localhost:5000
```

---

## 🔄 Useful Commands

```bash
# Service management
sudo systemctl start shirzadbot
sudo systemctl stop shirzadbot
sudo systemctl restart shirzadbot
sudo systemctl status shirzadbot

# View logs
tail -f logs/app.log
tail -f logs/error.log
sudo journalctl -u shirzadbot -f

# Update code
bash deploy/update.sh

# Backup
bash deploy/backup.sh
```

---

## 🔒 Firewall (if needed)

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 🎉 Done!

Your bot is now running at:
**https://social.msn1.ir**

