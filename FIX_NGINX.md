# 🔧 Fix Nginx Configuration Issue

## 🔴 **Problem:**

social.msn1.ir is showing another project (Laravel) instead of your bot.

## ✅ **Solution:**

There's another Nginx configuration taking priority. Let's fix it:

---

## 🎯 **Quick Fix Commands:**

Copy and paste these commands in your Ubuntu server:

```bash
# 1. Check all enabled sites
ls -la /etc/nginx/sites-enabled/

# You'll probably see a Laravel site there

# 2. Disable the conflicting site (if any)
sudo rm /etc/nginx/sites-enabled/default
# Or disable Laravel site if it exists:
# sudo rm /etc/nginx/sites-enabled/laravel
# Or whatever the conflict site name is

# 3. Create proper configuration for your bot
sudo tee /etc/nginx/sites-available/shirzadbot > /dev/null <<'EOF'
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
EOF

# 4. Enable your bot site
sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/

# 5. Remove any conflicting sites
sudo rm -f /etc/nginx/sites-enabled/default

# 6. Test configuration
sudo nginx -t

# 7. Reload Nginx
sudo systemctl reload nginx

# 8. Check if bot service is running
sudo systemctl status shirzadbot

# If not running:
sudo systemctl start shirzadbot
```

---

## 🔍 **Check What's Running:**

```bash
# Check all enabled sites
ls /etc/nginx/sites-enabled/

# Check what ports are listening
netstat -tlnp | grep nginx

# Check service status
sudo systemctl status shirzadbot

# Check if port 5000 is running your bot
curl http://localhost:5000
```

---

## 🎯 **Alternative: Use Different Port**

If you want to run both projects:

### Option 1: Use subdomain for Laravel
- Laravel: example.msn1.ir (port 80)
- Your Bot: social.msn1.ir (port 80)

### Option 2: Use different ports
- Laravel: social.msn1.ir (port 80)
- Your Bot: social.msn1.ir:5000 or bot.msn1.ir

---

## ✅ **Verify Fix:**

```bash
# After fixing, test:
curl http://localhost:5000
# Should return your bot's HTML

curl http://social.msn1.ir
# Should return your bot's HTML (not Laravel)
```

---

**The issue is Nginx priority. Disable the conflicting site and your bot will work!**

