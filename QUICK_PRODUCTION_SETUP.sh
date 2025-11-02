#!/bin/bash
# Quick Production Setup for social.msn1.ir

set -e

echo "🚀 Starting Production Setup..."
echo ""

PROJECT_DIR="/var/www/shirzadBot"
DOMAIN="social.msn1.ir"

# Check we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: Not in project directory!"
    echo "Run: cd /var/www/shirzadBot && bash QUICK_PRODUCTION_SETUP.sh"
    exit 1
fi

echo "[1/6] Installing dependencies..."
sudo apt update -qq
sudo apt install -y python3 python3-pip python3-venv nginx supervisor certbot python3-certbot-nginx > /dev/null 2>&1

echo "[2/6] Setting up Python environment..."
python3 -m venv venv --clear
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "[3/6] Creating directories..."
mkdir -p uploads logs
chmod 755 uploads logs

echo "[4/6] Creating config.py..."
if [ ! -f "config.py" ]; then
    cp config.example.py config.py
    echo "⚠️  EDIT config.py NOW with your tokens!"
    echo "Press Enter after editing..."
    read
fi

echo "[5/6] Creating systemd service..."
sudo tee /etc/systemd/system/shirzadbot.service > /dev/null <<EOF
[Unit]
Description=Shirzad Bot Platform
After=network.target

[Service]
Type=simple
User=$(whoami)
Group=$(whoami)
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python app.py
Restart=always
RestartSec=10
StandardOutput=append:$PROJECT_DIR/logs/app.log
StandardError=append:$PROJECT_DIR/logs/error.log

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/nginx/sites-available/shirzadbot > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    client_max_body_size 50M;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t > /dev/null
sudo systemctl restart nginx

echo "[6/6] Starting service..."
sudo systemctl daemon-reload
sudo systemctl enable shirzadbot
sudo systemctl start shirzadbot

# Try SSL
echo "Setting up SSL..."
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos --register-unsafely-without-email --redirect 2>/dev/null || echo "⚠️  SSL skipped (setup manually later)"

sleep 2

echo ""
echo "✅ Setup Complete!"
echo ""
echo "Check status: sudo systemctl status shirzadbot"
echo "View logs: tail -f logs/app.log"
echo "Access: https://$DOMAIN"
echo ""

