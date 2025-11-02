#!/bin/bash
# Final fix with port 5010

echo "🔧 Fixing Nginx with port 5010..."
echo ""

cd /var/www/shirzadBot || exit 1

# Stop bot service
sudo systemctl stop shirzadbot 2>/dev/null

# Create proper Nginx config
echo "Creating Nginx configuration..."
sudo tee /etc/nginx/sites-available/shirzadbot > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name social.msn1.ir www.social.msn1.ir;

    client_max_body_size 50M;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://localhost:5010;
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

# Enable site
sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/

# Remove default
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx
echo "Testing Nginx configuration..."
sudo nginx -t

echo "Reloading Nginx..."
sudo systemctl reload nginx

# Start bot
echo "Starting bot service..."
sudo systemctl start shirzadbot
sudo systemctl enable shirzadbot

sleep 3

echo ""
echo "✅ Fix complete!"
echo ""
echo "Checking status:"
sudo systemctl status shirzadbot --no-pager | head -8
echo ""

echo "Testing port 5010:"
curl -s http://localhost:5010 | head -10
echo ""

echo "🌐 Your bot should now work at:"
echo "   https://social.msn1.ir"
echo ""

