#!/bin/bash

# ============================================================
# Shirzad Bot Platform - Production Setup
# Domain: social.msn1.ir
# ============================================================

set -e

echo ""
echo "╔═══════════════════════════════════════════════════╗"
echo "║  Shirzad Bot Platform - Production Setup         ║"
echo "║  Domain: social.msn1.ir                          ║"
echo "╚═══════════════════════════════════════════════════╝"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check current directory
if [ ! -f "app.py" ]; then
    echo -e "${RED}❌ Error: app.py not found!${NC}"
    echo "Please run this script from: /var/www/shirzadBot"
    exit 1
fi

echo -e "${GREEN}✅ In correct directory${NC}"
echo ""

# Check if config.py exists
if [ ! -f "config.py" ]; then
    echo -e "${YELLOW}⚠️  config.py not found!${NC}"
    echo "Creating from template..."
    cp config.example.py config.py
    echo -e "${RED}⚠️  EDIT config.py with your REAL tokens NOW!${NC}"
    echo ""
    read -p "Press Enter after editing config.py..."
    
    # Verify config.py was edited
    if grep -q "YOUR_TELEGRAM_TOKEN_HERE" config.py; then
        echo -e "${RED}❌ Tokens not edited! Please edit config.py first.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ config.py exists${NC}"
fi

echo ""
echo -e "${GREEN}[1/4] Installing system dependencies...${NC}"
sudo apt update -qq && sudo apt upgrade -y > /dev/null 2>&1
sudo apt install -y python3 python3-pip python3-venv nginx supervisor certbot python3-certbot-nginx sqlite3 > /dev/null 2>&1

echo -e "${GREEN}[2/4] Setting up Python environment...${NC}"
python3 -m venv venv 2>/dev/null || python3 -m venv venv --clear
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

mkdir -p uploads logs
chmod 755 uploads logs

echo -e "${GREEN}[3/4] Creating system services...${NC}"

# Systemd service
sudo tee /etc/systemd/system/shirzadbot.service > /dev/null <<EOF
[Unit]
Description=Shirzad Bot Platform
After=network.target

[Service]
Type=simple
User=$(whoami)
Group=$(whoami)
WorkingDirectory=/var/www/shirzadBot
Environment="PATH=/var/www/shirzadBot/venv/bin"
ExecStart=/var/www/shirzadBot/venv/bin/python app.py
Restart=always
RestartSec=10

StandardOutput=append:/var/www/shirzadBot/logs/app.log
StandardError=append:/var/www/shirzadBot/logs/error.log

[Install]
WantedBy=multi-user.target
EOF

# Nginx configuration
sudo tee /etc/nginx/sites-available/shirzadbot > /dev/null <<EOF
server {
    listen 80;
    server_name social.msn1.ir www.social.msn1.ir;

    client_max_body_size 50M;
    proxy_read_timeout 300s;

    location / {
        proxy_pass http://localhost:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t > /dev/null 2>&1
sudo systemctl restart nginx

echo -e "${GREEN}[4/4] Starting services...${NC}"
sudo systemctl daemon-reload
sudo systemctl enable shirzadbot
sudo systemctl start shirzadbot

sleep 3

# Try SSL
echo ""
echo -e "${GREEN}Setting up SSL certificate...${NC}"
sudo certbot --nginx -d social.msn1.ir --non-interactive --agree-tos --register-unsafely-without-email --redirect 2>/dev/null || {
    echo -e "${YELLOW}⚠️  SSL skipped. Run manually: sudo certbot --nginx -d social.msn1.ir${NC}"
}

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""

# Show status
echo "📊 Service Status:"
sudo systemctl status shirzadbot --no-pager | grep "Active:" || true

echo ""
echo "🌐 Access your bot:"
echo -e "${GREEN}  https://social.msn1.ir${NC}"
echo ""

echo "📝 Quick commands:"
echo "  sudo systemctl status shirzadbot"
echo "  sudo systemctl restart shirzadbot"
echo "  tail -f logs/app.log"
echo ""

