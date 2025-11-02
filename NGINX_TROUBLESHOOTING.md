# 🔧 Nginx Troubleshooting

## 🔴 Problem: social.msn1.ir shows Laravel instead of your bot

---

## ✅ Quick Fix:

Run on your server:

```bash
cd /var/www/shirzadBot
chmod +x fix_nginx.sh
bash fix_nginx.sh
```

---

## 🔍 Diagnosis:

### Check enabled sites:

```bash
ls -la /etc/nginx/sites-enabled/
```

You might see:
- `default` (catch-all, showing Laravel)
- `laravel` or another site

### Check Nginx configuration priority:

```bash
# See all configurations
sudo cat /etc/nginx/sites-enabled/*

# Check which one handles social.msn1.ir
sudo nginx -T | grep -A 5 "server_name"
```

---

## 🎯 Solutions:

### Solution 1: Fix Priority (Recommended)

The issue is that another site is catching your domain first.

```bash
# 1. Create your bot config with specific domain
sudo nano /etc/nginx/sites-available/shirzadbot
```

Paste:
```nginx
server {
    listen 80;
    listen [::]:80;
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
}
```

```bash
# 2. Enable
sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/

# 3. Fix default to NOT catch all domains
sudo nano /etc/nginx/sites-available/default
```

Change from:
```nginx
server_name _;
```

To:
```nginx
server_name your-laravel-domain.com;
```

Or disable completely:
```bash
sudo rm /etc/nginx/sites-enabled/default
```

```bash
# 4. Test and reload
sudo nginx -t
sudo systemctl reload nginx

# 5. Start bot
sudo systemctl start shirzadbot
sudo systemctl status shirzadbot
```

---

### Solution 2: Use Different Domain

If Laravel is on social.msn1.ir, use a different subdomain for your bot:

```bash
# Configure for bot.msn1.ir instead
sudo nano /etc/nginx/sites-available/shirzadbot
```

Change:
```nginx
server_name bot.msn1.ir www.bot.msn1.ir;
```

Then update DNS in Cloudflare.

---

### Solution 3: Check Service is Running

Your bot might not be running:

```bash
# Check status
sudo systemctl status shirzadbot

# Start if not running
sudo systemctl start shirzadbot

# Check logs
tail -f /var/www/shirzadBot/logs/app.log

# Check port
netstat -tlnp | grep 5000
# Should show: python listening on port 5000
```

---

## 🔍 Debug Steps:

```bash
# 1. Is your bot running?
sudo systemctl status shirzadbot

# 2. Is port 5000 listening?
netstat -tlnp | grep 5000

# 3. Can curl reach it?
curl http://localhost:5000
# Should return your bot's HTML

# 4. Check Nginx is proxying
curl http://social.msn1.ir
# Should return same HTML

# 5. Check Nginx config
sudo nginx -T | grep -A 10 "server_name social.msn1.ir"

# 6. Check error logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/www/shirzadBot/logs/error.log
```

---

## 🎯 Most Likely Fix:

Your server probably has this in `/etc/nginx/sites-enabled/default`:

```nginx
server {
    listen 80 default_server;
    server_name _;
    ...
}
```

The `default_server` means it catches ALL unhandled domains.

**Fix:**

```bash
# Option A: Disable default
sudo rm /etc/nginx/sites-enabled/default

# Option B: Make sure your bot config has higher priority
# Rename your bot config to start with 'a' for alphabetical priority:
sudo mv /etc/nginx/sites-enabled/shirzadbot /etc/nginx/sites-enabled/00-shirzadbot

# Then reload
sudo systemctl reload nginx
```

---

## ✅ After Fix:

```bash
# Restart bot
sudo systemctl restart shirzadbot

# Check status
sudo systemctl status shirzadbot

# Test
curl http://localhost:5000
curl http://social.msn1.ir

# View browser
# Open: https://social.msn1.ir
```

---

**Run `fix_nginx.sh` and your bot should work!**

