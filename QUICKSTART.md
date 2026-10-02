# Sensor Data Processor - Quick Start

Sensor data cleaning and homogenization platform (TMS pipeline).

## 🚀 2-Minute Setup

### Local Development

```bash
# 1. Clone the project
git clone <repo>
cd sensor-data-processor

# 2. Copy config
cp .env.example .env

# 3. Start
docker compose up -d --build

# 4. Access
# Frontend: http://localhost:5173
# API Docs: http://localhost:8000/docs
```

### Production (Local Server)

```bash
# 1. Create data directory
sudo mkdir -p /data/sensor-data-processor
sudo chown -R 1000:1000 /data/sensor-data-processor

# 2. Configure server IP
nano .env
# Set: FRONTEND_API_URL=http://192.168.1.100:8000

# 3. Start
docker compose -f docker-compose.prod.yml up -d --build

# 4. Access from any network device
# http://192.168.1.100
```

## 📚 Documentation

- **Full deployment guide**: [DEPLOY.md](./DEPLOY.md)
- **Architecture documentation**: [CLAUDE.md](./CLAUDE.md)

## 🔧 Useful Commands

```bash
# View logs
docker compose logs -f

# Restart
docker compose restart

# Stop
docker compose down

# Update
git pull && docker compose up -d --build
```

## 📊 Services

| Service | Dev | Prod | Description |
|---------|-----|------|-------------|
| Frontend | :5173 | :80 | React UI (+ nginx in prod) |
| API | :8000 | :8000 | FastAPI Backend |
| Redis | :6379 | - | Job queue |
| Worker | - | - | Async processing |

**Production mode** includes nginx reverse proxy that:
- Serves static React build on port 80
- Proxies `/api` → FastAPI backend
- Proxies `/docs` → API documentation
- Handles large file uploads (500 MB max)
- Manages timeouts for long-running jobs

## 💾 Persistent Data

- **Dev**: Docker volume `sdp_data`
- **Prod**: `/data/sensor-data-processor` on server

## 🎯 Optimized for 5 Users

- ✅ 1 RQ worker (enough for small teams)
- ✅ No complex monitoring
- ✅ Lightweight Redis (20 MB)
- ✅ Minimal configuration

## 🚨 Troubleshooting

```bash
# Check logs
docker compose logs api
docker compose logs worker

# Full rebuild
docker compose down
docker compose up -d --build
```

See [DEPLOY.md](./DEPLOY.md) for details.
