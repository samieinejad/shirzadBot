# 🎯 Complete Production Setup Instructions

## For: msn@localhost:/var/www/shirzadBot

---

## 🚀 **Quick Method (Recommended)**

Copy and paste these commands one by one:

```bash
# 1. Make scripts executable
chmod +x QUICK_PRODUCTION_SETUP.sh PRODUCTION_SETUP.sh deploy/*.sh

# 2. Run the quick setup
bash QUICK_PRODUCTION_SETUP.sh
```

When prompted, edit config.py and add your tokens.

Done! Your bot will be running at **https://social.msn1.ir**

---

## 📝 **Step-by-Step Method**

### **1. Install System Dependencies:**

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 certbot python3-certbot-nginx
```

### **2. Setup Python Environment:**

```bash
cd /var/www/shirzadBot

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### **3. Configure Tokens:**

```bash
# Copy example file
cp config.example.py config.py

# Edit with your tokens
nano config.py
```

In `config.py`, add your real tokens:
```python
TELEGRAM_BOT_TOKEN = "7963827943:AAHsvRqbwqTjTtiZK_Iv7Rer5Lra0VmwW0s"
BALE_BOT_TOKEN = "1982745502:dgLeJruWoNcoUOe21hAvQ1mjqiBfZCfV1SytWAQY"
ITA_BOT_TOKEN = "bot195541:69b9f7fd-c523-4a2f-a22a-5501cf076a07"

OWNER_ID = 6483380759
BALE_OWNER_ID = 205469326
ITA_OWNER_ID = "6483380759"
```

Save: `Ctrl+X`, `Y`, `Enter`

### **4. Create Directories:**

```bash
mkdir -p uploads logs
chmod 755 uploads logs
```

### **5. Create Systemd Service:**

```bash
sudo nano /etc/systemd/system/shirzadbot.service
```

Paste this:
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

Save and exit: `Ctrl+X`, `Y`, `Enter`

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable shirzadbot
sudo systemctl start shirzadbot
```

### **6. Configure Nginx:**

```bash
sudo nano /etc/nginx/sites-available/shirzadbot
```

Paste this:
```nginx
server {
    listen 80;
    server_name social.msn1.ir www.social.msn1.ir;

    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    access_log /var/log/nginx/shirzadbot_access.log;
    error_log /var/log/nginx/shirzadbot_error.log;
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

### **7. Setup SSL Certificate:**

```bash
sudo certbot --nginx -d social.msn1.ir -d www.social.msn1.ir
```

Follow the prompts (enter your email, agree to terms).

---

## ✅ **Verify Everything Works:**

```bash
# Check service
sudo systemctl status shirzadbot

# Should show: "active (running)"

# Check port
netstat -tlnp | grep 5000

# Check logs
tail -f logs/app.log

# Test locally
curl http://localhost:5000

# Should return HTML content
```

---

## 🌐 **Access Your Bot:**

Open your browser:
```
https://social.msn1.ir
```

You should see the beautiful dashboard!

---

## 🔧 **Useful Commands:**

```bash
# Service management
sudo systemctl restart shirzadbot    # Restart
sudo systemctl stop shirzadbot       # Stop
sudo systemctl start shirzadbot      # Start
sudo systemctl status shirzadbot     # Status

# View logs
tail -f logs/app.log                 # App logs
tail -f logs/error.log               # Error logs
sudo journalctl -u shirzadbot -f     # System logs

# Update code
bash deploy/update.sh

# Backup
bash deploy/backup.sh
```

---

## 🔥 **Troubleshooting:**

### Service won't start:
```bash
sudo journalctl -u shirzadbot -n 50
# Look for errors
```

### Can't access domain:
```bash
# Check DNS
curl http://social.msn1.ir
nslookup social.msn1.ir

# Check Nginx
sudo systemctl status nginx
sudo nginx -t

# Check firewall
sudo ufw status
```

### 502 Bad Gateway:
```bash
# Service might not be running
sudo systemctl start shirzadbot

# Check port
netstat -tlnp | grep 5000
```

### SSL certificate issues:
```bash
sudo certbot renew
sudo systemctl reload nginx
```

---

## 📋 **Quick Checklist:**

- [ ] All dependencies installed
- [ ] Virtual environment created
- [ ] Packages installed
- [ ] config.py with real tokens
- [ ] Systemd service created and running
- [ ] Nginx configured
- [ ] SSL certificate installed
- [ ] Service status: active
- [ ] Accessible at https://social.msn1.ir

---

**🎉 You're all set! Your bot is running in production!**

