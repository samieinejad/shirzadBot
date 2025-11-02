#!/bin/bash
# Fix Nginx configuration for social.msn1.ir

set -e

echo "🔧 Fixing Nginx Configuration..."
echo ""

# Check current enabled sites
echo "Current enabled sites:"
ls -la /etc/nginx/sites-enabled/
echo ""

# Create proper configuration
echo "Creating Nginx configuration..."
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

# Enable bot site
sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/

# Remove default
sudo rm -f /etc/nginx/sites-enabled/default

# Test
echo "Testing Nginx configuration..."
sudo nginx -t

echo "Reloading Nginx..."
sudo systemctl reload nginx

echo ""
echo "✅ Nginx fixed!"
echo ""
echo "Check service:"
sudo systemctl status shirzadbot --no-pager | head -5
echo ""

echo "Test locally:"
curl -s http://localhost:5000 | head -5
echo ""

