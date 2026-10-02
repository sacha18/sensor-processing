# Sensor Data Processor - Simplified Deployment Guide

## 📋 Prerequisites

### Server
- **OS**: Ubuntu 22.04 LTS / Debian 12
- **CPU**: 2-4 cores
- **RAM**: 4-8 GB
- **Disk**: 50-100 GB SSD
- **Network**: Fixed local IP (e.g., 192.168.1.100)

### Software
- Docker & Docker Compose v2
- Git

---

## 🚀 Quick Installation

### 1. Prepare Server

```bash
# Connect to server
ssh user@192.168.1.100

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose v2
sudo apt install docker-compose-plugin -y

# Restart session to apply permissions
exit
# Reconnect
```

### 2. Clone Project

```bash
# Create directory
sudo mkdir -p /opt/sensor-data-processor
sudo chown $USER:$USER /opt/sensor-data-processor

# Clone
cd /opt/sensor-data-processor
git clone <your-repo> .
```

### 3. Create Data Directories

```bash
# Create persistent storage directory
sudo mkdir -p /data/sensor-data-processor
sudo chown -R 1000:1000 /data/sensor-data-processor
```

### 4. Configuration

```bash
# Copy configuration file
cp .env.example .env

# Edit configuration
nano .env
```

**Modify only if needed**:
```bash
# Session retention duration (days)
SDP_STORE_TTL_DAYS=30

# Frontend API URL (replace with your server IP)
FRONTEND_API_URL=http://192.168.1.100:8000
```

### 5. Start Application

```bash
# Development mode (with hot-reload)
docker compose up -d --build

# OR production mode (optimized)
docker compose -f docker-compose.prod.yml up -d --build
```

### 6. Verify Everything Works

```bash
# View logs
docker compose logs -f

# Check services
docker compose ps

# Test API
curl http://localhost:8000/health
```

---

## 🌐 Application Access

### Development Mode
- **Frontend**: http://192.168.1.100:5173
- **API**: http://192.168.1.100:8000
- **API Docs**: http://192.168.1.100:8000/docs

### Production Mode
- **Application**: http://192.168.1.100
- **API Docs**: http://192.168.1.100/docs

**Production mode includes nginx reverse proxy**:
- Nginx container serves static React build on port 80
- Automatically proxies `/api` requests to FastAPI backend
- Automatically proxies `/docs` to API documentation
- Configured in `frontend/nginx.conf` (used by Docker)
- Handles large uploads (500 MB) and long-running jobs (300s timeout)

---

## 📝 Useful Commands

### View Logs
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api
docker compose logs -f worker

# Last 50 lines
docker compose logs --tail=50 api
```

### Restart Application
```bash
# Restart everything
docker compose restart

# Specific service
docker compose restart api
docker compose restart worker
```

### Update Application
```bash
cd /opt/sensor-data-processor
git pull
docker compose down
docker compose up -d --build
```

### Clean Old Images
```bash
docker system prune -a
```

---

## 💾 Backups

### Simple Manual Backup
```bash
# Create backup
cd /data
tar czf sensor-data-processor-backup-$(date +%Y%m%d).tar.gz sensor-data-processor/

# Copy to another disk/NAS
cp sensor-data-processor-backup-*.tar.gz /mnt/backup/
```

### Restore Backup
```bash
# Stop application
docker compose down

# Restore
cd /data
tar xzf sensor-data-processor-backup-YYYYMMDD.tar.gz

# Restart
docker compose up -d
```

### Automated Monthly Backup (Optional)
```bash
# Create script
sudo nano /usr/local/bin/backup-sensor-data.sh
```

Content:
```bash
#!/bin/bash
tar czf /mnt/backup/sensor-data-$(date +%Y%m%d).tar.gz /data/sensor-data-processor/
find /mnt/backup -name "sensor-data-*.tar.gz" -mtime +90 -delete
```

```bash
# Make executable
sudo chmod +x /usr/local/bin/backup-sensor-data.sh

# Add to cron (1st of month at 2am)
sudo crontab -e
# Add: 0 2 1 * * /usr/local/bin/backup-sensor-data.sh
```

### Use Included Backup Scripts
```bash
# Backup
./scripts/backup.sh

# Restore
./scripts/restore.sh backups/sensor-data-processor-backup-YYYYMMDD_HHMMSS.tar.gz
```

---

## 🔧 Maintenance

### Check Disk Space
```bash
# Total space
df -h

# Data details
du -sh /data/sensor-data-processor/*
```

### Check Resource Usage
```bash
# Container CPU/RAM
docker stats

# System processes
htop
```

### Clean Old Sessions (if needed)
```bash
# Sessions older than SDP_STORE_TTL_DAYS are automatically purged on startup
# To force cleanup:
docker compose restart api
```

---

## 🚨 Troubleshooting

### Application Won't Start
```bash
# Check logs
docker compose logs api
docker compose logs worker

# Check if ports are already in use
sudo netstat -tlnp | grep -E ':(80|8000|5173|6379)'

# Full rebuild
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Worker Not Processing Jobs
```bash
# Check worker is running
docker compose ps worker

# View worker logs
docker compose logs -f worker

# Restart worker
docker compose restart worker
```

### Permission Issues
```bash
# Fix data permissions
sudo chown -R 1000:1000 /data/sensor-data-processor
```

### Disk Full
```bash
# Clean old Docker images
docker system prune -a

# Manually remove old sessions
# (Caution: data loss!)
rm -rf /data/sensor-data-processor/store/sessions/old-session-id
```

---

## 📊 Simplified Monitoring (for 5 users)

No need for Prometheus/Grafana. Just:

1. **Check logs when there's a problem**
   ```bash
   docker compose logs -f
   ```

2. **Check disk space once a month**
   ```bash
   df -h
   ```

3. **Users will tell you if something's broken** 😊

---

## 🌐 Nginx on Host Server (Optional - Advanced)

**Note**: By default, nginx is already included in `docker-compose.prod.yml`. This section is only needed if you want nginx running on the host server instead (e.g., if you already have nginx managing multiple sites).

**When to use this**:
- You already have nginx on the server with other sites
- You want centralized SSL certificate management
- You need more control over nginx configuration

**For most users**: Skip this section and use the default Docker setup.

---

If you want to use nginx on the host server instead of the Docker setup:

### Install Nginx on Host
```bash
sudo apt install nginx -y
```

### Configure Nginx
```bash
# Copy the provided config
sudo cp nginx-host.conf /etc/nginx/sites-available/sensor-data-processor

# Create symbolic link
sudo ln -s /etc/nginx/sites-available/sensor-data-processor /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload nginx
sudo systemctl reload nginx
```

### Adjust Docker Ports
If using host nginx, remove port mappings from docker-compose:

```yaml
# Don't expose frontend port in docker-compose.yml
# frontend:
#   ports:
#     - "80:80"  # Remove this line
```

Then access via:
- **Application**: http://192.168.1.100 (nginx proxies to Docker)
- **API**: http://192.168.1.100/api

---

## 🔐 Security (optional for local network)

### Firewall (if exposed to internet)
```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw enable
```

### SSL/HTTPS (if exposed to internet)

**For Docker nginx** (recommended):
```bash
# Generate self-signed certificate for local network
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ./frontend/ssl/nginx.key \
  -out ./frontend/ssl/nginx.crt

# Update frontend/nginx.conf to add HTTPS server block
# Then rebuild: docker compose -f docker-compose.prod.yml up -d --build
```

**For host nginx** (if using `nginx-host.conf`):
```bash
# Install certbot
sudo apt install certbot

# Get certificate (requires domain name)
sudo certbot certonly --standalone -d yourdomain.com

# Uncomment HTTPS section in nginx-host.conf and reload
sudo nano /etc/nginx/sites-available/sensor-data-processor
sudo nginx -t && sudo systemctl reload nginx
```

The `nginx-host.conf` file includes a commented HTTPS template ready to use.

---

## 📌 Important Notes

- **Redis + RQ kept**: already implemented, lightweight, useful for async
- **1 worker only**: enough for 5 users
- **No RQ Dashboard**: logs sufficient for debugging
- **Default 30-day TTL**: adjust based on your needs
- **Manual backups OK**: once a month sufficient for 5 users

---

## 💡 Need Help?

1. Check logs: `docker compose logs -f`
2. Check API docs: http://your-ip/docs
3. Check this file: [DEPLOY.md](./DEPLOY.md)

---
