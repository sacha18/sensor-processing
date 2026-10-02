#!/bin/bash
#
# Sensor Data Processor - Simple backup script
# Usage: ./scripts/backup.sh [backup-destination]
#

set -e

BACKUP_DIR="${1:-./backups}"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="sensor-data-processor-backup-${DATE}.tar.gz"

echo "🔄 Starting backup..."
echo "📅 Date: ${DATE}"

# Create backup directory if it doesn't exist
mkdir -p "${BACKUP_DIR}"

# Determine if we're backing up Docker volume or host directory
if [ -d "/data/sensor-data-processor" ]; then
    # Production: backup from host directory
    echo "📦 Backing up from /data/sensor-data-processor..."
    sudo tar czf "${BACKUP_DIR}/${BACKUP_FILE}" /data/sensor-data-processor
else
    # Development: backup from Docker volume
    echo "📦 Backing up from Docker volume sdp_data..."
    docker run --rm \
        -v sdp_data:/data:ro \
        -v "$(pwd)/${BACKUP_DIR}:/backup" \
        alpine tar czf "/backup/${BACKUP_FILE}" -C /data .
fi

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/${BACKUP_FILE}" | cut -f1)
echo "✅ Backup completed: ${BACKUP_FILE} (${BACKUP_SIZE})"
echo "📍 Location: ${BACKUP_DIR}/${BACKUP_FILE}"

# Optional: cleanup old backups (keep last 5)
echo "🧹 Cleaning old backups (keeping last 5)..."
ls -t "${BACKUP_DIR}"/sensor-data-processor-backup-*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm
echo "✨ Done!"
