#!/bin/bash

# Shirzad Bot Platform - Ubuntu Installation Script
# Run with: bash deploy/install.sh

set -e  # Exit on error

echo "================================================="
echo "Shirzad Bot Platform - Ubuntu Installation"
echo "================================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}Error: Do not run as root. Run as regular user with sudo access.${NC}"
   exit 1
fi

# Check if running on Ubuntu
if ! grep -q "Ubuntu" /etc/os-release; then
    echo -e "${YELLOW}Warning: This script is designed for Ubuntu. Proceeding anyway...${NC}"
fi

echo -e "${GREEN}[1/8] Updating system packages...${NC}"
sudo apt update -y
sudo apt upgrade -y

echo -e "${GREEN}[2/8] Installing required packages...${NC}"
sudo apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3

echo -e "${GREEN}[3/8] Creating project directory...${NC}"
PROJECT_DIR="/var/www/shirzadBot"
sudo mkdir -p $PROJECT_DIR
sudo chown $USER:$USER $PROJECT_DIR

echo -e "${GREEN}[4/8] Setting up virtual environment...${NC}"
cd $PROJECT_DIR
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip

echo -e "${GREEN}[5/8] Installing Python dependencies...${NC}"
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo -e "${YELLOW}Warning: requirements.txt not found. Installing manually...${NC}"
    pip install Flask python-telegram-bot pandas openpyxl requests APScheduler Pillow jdatetime pytz
fi

echo -e "${GREEN}[6/8] Creating necessary directories...${NC}"
mkdir -p uploads logs
chmod 755 uploads logs

echo -e "${GREEN}[7/8] Setting up systemd service...${NC}"
sudo tee /etc/systemd/system/shirzadbot.service > /dev/null <<EOF
[Unit]
Description=Shirzad Bot Platform
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python app.py
Restart=always
RestartSec=10

# Logging
StandardOutput=append:$PROJECT_DIR/logs/app.log
StandardError=append:$PROJECT_DIR/logs/error.log

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}[8/8] Configuring Nginx...${NC}"
sudo tee /etc/nginx/sites-available/shirzadbot > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;

    location / {
        proxy_pass http://localhost:5000;
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

echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}Installation completed successfully!${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo "⚠️  IMPORTANT: Before starting the service:"
echo "1. Edit $PROJECT_DIR/app.py and update your bot tokens (lines 135-141)"
echo "2. Set your OWNER_IDs"
echo "3. Then run: sudo systemctl start shirzadbot"
echo ""
echo "Useful commands:"
echo "  sudo systemctl start shirzadbot    # Start service"
echo "  sudo systemctl stop shirzadbot     # Stop service"
echo "  sudo systemctl status shirzadbot   # Check status"
echo "  tail -f $PROJECT_DIR/logs/app.log  # View logs"
echo ""
echo "Your bot will be available at: http://YOUR_SERVER_IP"
echo ""

