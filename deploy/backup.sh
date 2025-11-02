#!/bin/bash

# Backup script for Shirzad Bot Platform
# Run with: bash deploy/backup.sh

set -e

BACKUP_DIR="/var/backups/shirzadbot"
PROJECT_DIR="/var/www/shirzadBot"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

echo "Starting backup..."
echo "Date: $DATE"
echo ""

# Backup database
if [ -f "$PROJECT_DIR/multi_bot_platform.db" ]; then
    cp "$PROJECT_DIR/multi_bot_platform.db" "$BACKUP_DIR/db_$DATE.db"
    echo "✅ Database backed up: db_$DATE.db"
fi

# Backup bot database
if [ -f "$PROJECT_DIR/bot_database.db" ]; then
    cp "$PROJECT_DIR/bot_database.db" "$BACKUP_DIR/bot_db_$DATE.db"
    echo "✅ Bot database backed up: bot_db_$DATE.db"
fi

# Backup logs (last 7 days)
if [ -d "$PROJECT_DIR/logs" ]; then
    tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" "$PROJECT_DIR/logs/" 2>/dev/null || true
    echo "✅ Logs backed up: logs_$DATE.tar.gz"
fi

# Backup uploaded files
if [ -d "$PROJECT_DIR/uploads" ]; then
    tar -czf "$BACKUP_DIR/uploads_$DATE.tar.gz" "$PROJECT_DIR/uploads/" 2>/dev/null || true
    echo "✅ Uploads backed up: uploads_$DATE.tar.gz"
fi

echo ""
echo "Deleting backups older than 7 days..."
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo ""
echo "✅ Backup completed successfully!"
echo "Backup location: $BACKUP_DIR"
echo ""

# List backups
echo "Current backups:"
ls -lh $BACKUP_DIR | tail -n +2

