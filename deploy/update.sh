#!/bin/bash

# Update script for Shirzad Bot Platform
# Run with: bash deploy/update.sh

set -e

echo "================================================="
echo "Shirzad Bot Platform - Update"
echo "================================================="
echo ""

PROJECT_DIR="/var/www/shirzadBot"

# Check if project exists
if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: Project directory not found!"
    exit 1
fi

cd $PROJECT_DIR

echo "[1/4] Pulling latest code..."
git pull origin main

echo "[2/4] Activating virtual environment..."
source venv/bin/activate

echo "[3/4] Updating dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/4] Restarting service..."
sudo systemctl restart shirzadbot

echo ""
echo "✅ Update completed!"
echo ""
echo "Checking status..."
sudo systemctl status shirzadbot --no-pager -l

echo ""
echo "📋 View logs:"
echo "tail -f $PROJECT_DIR/logs/app.log"

