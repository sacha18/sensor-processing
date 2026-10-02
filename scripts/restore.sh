#!/bin/bash
#
# Sensor Data Processor - Simple restore script
# Usage: ./scripts/restore.sh <backup-file>
#

set -e

if [ -z "$1" ]; then
    echo "❌ Error: Please provide a backup file"
    echo "Usage: ./scripts/restore.sh <backup-file.tar.gz>"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "❌ Error: Backup file not found: ${BACKUP_FILE}"
    exit 1
fi

echo "⚠️  WARNING: This will OVERWRITE existing data!"
echo "📦 Backup file: ${BACKUP_FILE}"
read -p "Continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy]es$ ]]; then
    echo "❌ Restore cancelled"
    exit 1
fi

echo "🛑 Stopping application..."
docker compose down

# Determine if we're restoring to Docker volume or host directory
if [ -d "/data/sensor-data-processor" ]; then
    # Production: restore to host directory
    echo "📦 Restoring to /data/sensor-data-processor..."
    sudo rm -rf /data/sensor-data-processor/*
    sudo tar xzf "${BACKUP_FILE}" -C /
else
    # Development: restore to Docker volume
    echo "📦 Restoring to Docker volume sdp_data..."
    docker volume rm sdp_data 2>/dev/null || true
    docker volume create sdp_data
    docker run --rm \
        -v sdp_data:/data \
        -v "$(pwd):/backup" \
        alpine sh -c "cd /data && tar xzf /backup/${BACKUP_FILE}"
fi

echo "🚀 Restarting application..."
docker compose up -d

echo "✅ Restore completed!"
echo "🌐 Check application at http://localhost:5173"
