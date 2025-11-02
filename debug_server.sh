#!/bin/bash

echo "=== Checking service status ==="
sudo systemctl status shirzadbot -l | tail -30

echo ""
echo "=== Checking logs ==="
tail -50 /var/www/shirzadBot/logs/app.log 2>/dev/null || echo "No app.log"
tail -50 /var/www/shirzadBot/logs/error.log 2>/dev/null || echo "No error.log"

echo ""
echo "=== Checking if code was updated ==="
cd /var/www/shirzadBot
git log --oneline -5

echo ""
echo "=== Checking app.py port ==="
grep -n "app.run" app.py | head -5

echo ""
echo "=== Testing venv ==="
source venv/bin/activate
python --version
which python

echo ""
echo "=== Checking if port is listening ==="
netstat -tlnp | grep 5010 || echo "Port 5010 not listening"

