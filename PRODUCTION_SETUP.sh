#!/bin/bash

# Shirzad Bot Platform - Production Setup Script
# For domain: social.msn1.ir

set -e

echo "================================================="
echo "Shirzad Bot Platform - Production Setup"
echo "Domain: social.msn1.ir"
echo "================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}Error: Do not run as root. Run as regular user with sudo access.${NC}"
   exit 1
fi

PROJECT_DIR="/var/www/shirzadBot"
DOMAIN="social.msn1.ir"

echo -e "${GREEN}[1/10] Updating system...${NC}"
sudo apt update -y
sudo apt upgrade -y

echo -e "${GREEN}[2/10] Installing dependencies...${NC}"
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 certbot python3-certbot-nginx

echo -e "${GREEN}[3/10] Setting up project directory...${NC}"
sudo mkdir -p $PROJECT_DIR
sudo chown $USER:$USER $PROJECT_DIR

echo -e "${YELLOW}[4/10] Making sure you're in the project directory...${NC}"
if [ ! -f "app.py" ]; then
    echo -e "${RED}Error: app.py not found. Are you in /var/www/shirzadBot?${NC}"
    echo "Run: cd /var/www/shirzadBot"
    exit 1
fi

echo -e "${GREEN}[5/10] Setting up virtual environment...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo -e "${GREEN}[6/10] Creating necessary directories...${NC}"
mkdir -p uploads logs
chmod 755 uploads logs

echo -e "${YELLOW}[7/10] Creating config.py...${NC}"
if [ -f "config.example.py" ] && [ ! -f "config.py" ]; then
    cp config.example.py config.py
    echo -e "${YELLOW}⚠️  IMPORTANT: Edit config.py and add your real tokens!${NC}"
    echo "Run: nano config.py"
    read -p "Press Enter after you've edited config.py..."
else
    echo -e "${GREEN}config.py already exists${NC}"
fi

echo -e "${GREEN}[8/10] Creating systemd service...${NC}"
sudo tee /etc/systemd/system/shirzadbot.service > /dev/null <<EOF
[Unit]
Description=Shirzad Bot Platform
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
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

echo -e "${GREEN}[9/10] Configuring Nginx for $DOMAIN...${NC}"
sudo tee /etc/nginx/sites-available/shirzadbot > /dev/null <<EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;

    location / {
        proxy_pass http://localhost:5010;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
    }

    access_log /var/log/nginx/shirzadbot_access.log;
    error_log /var/log/nginx/shirzadbot_error.log;
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/shirzadbot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test and restart nginx
sudo nginx -t
sudo systemctl restart nginx

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable shirzadbot

echo -e "${GREEN}[10/10] Setting up SSL with Let's Encrypt...${NC}"
echo -e "${YELLOW}This will ask for your email and accept terms...${NC}"
sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos --register-unsafely-without-email || {
    echo -e "${YELLOW}SSL setup skipped or failed. Continue without SSL for now.${NC}"
}

echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}✅ Installation completed!${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo -e "${YELLOW}⚠️  IMPORTANT: Before starting, make sure:${NC}"
echo "1. config.py has your real tokens"
echo "2. DNS for $DOMAIN points to this server"
echo ""
echo -e "${GREEN}Starting service...${NC}"
sudo systemctl start shirzadbot
sleep 3

echo ""
echo -e "${GREEN}Checking status...${NC}"
sudo systemctl status shirzadbot --no-pager -l | head -20

echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}🎉 Setup Complete!${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo "Your bot is available at:"
echo -e "${GREEN}  http://$DOMAIN${NC}"
echo -e "${GREEN}  https://$DOMAIN${NC}"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status shirzadbot"
echo "  sudo systemctl restart shirzadbot"
echo "  sudo systemctl stop shirzadbot"
echo "  tail -f $PROJECT_DIR/logs/app.log"
echo "  bash deploy/update.sh"
echo "  bash deploy/backup.sh"
echo ""
echo "View logs:"
echo "  tail -f logs/app.log"
echo ""

