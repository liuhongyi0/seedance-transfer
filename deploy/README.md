# Seedance Studio — Deploy Guide

## Quick Start (Docker Compose)

```bash
# 1. Configure environment
cp Seedance/backend/.env.example Seedance/backend/.env
# Edit .env — fill in EVOLINK_API_KEY, VOLC_API_KEY, JWT_SECRET

# 2. (First time only) Get SSL certificate
chmod +x deploy/certbot-init.sh
sudo ./deploy/certbot-init.sh see4dance.com admin@see4dance.com

# 3. Start all services
docker compose up -d

# 4. Verify
curl http://localhost/health
curl -I https://see4dance.com
```

Services:
- **nginx** :80/:443 — reverse proxy + SSL termination + static files
- **backend** :8000 — FastAPI (internal only)
- **db** :5432 — PostgreSQL 16 (internal only)
- **certbot** — Let's Encrypt auto-renewal (every 12h)
- **backup** — Daily PostgreSQL dump at 3:00 AM (keeps 7 days)

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `EVOLINK_API_KEY` | Yes | EvoLink AI API (image/music/video draft) |
| `VOLC_API_KEY` | Yes | Volcano Engine API (vision model + final video) |
| `JWT_SECRET` | Yes | JWT signing key (`openssl rand -hex 32`) |
| `DB_PASSWORD` | Yes | PostgreSQL password (defaults to `seedance_dev`) |
| `BASE_URL` | Yes | Public URL (`https://see4dance.com`) |
| `SENTRY_DSN` | No | Sentry error tracking |
| `ADMIN_KEY` | No | Admin API authentication |
| `IMGBB_API_KEY` | No | imgbb upload (fallback image hosting) |
| `GOOGLE_CLIENT_ID` | No | Google OAuth |
| `GITHUB_CLIENT_ID` | No | GitHub OAuth client ID |
| `GITHUB_CLIENT_SECRET` | No | GitHub OAuth secret |
| `STRIPE_SECRET_KEY` | No | Stripe payment (intl only) |

## Endpoints

| Path | Description |
|---|---|
| `/` | Portal landing page |
| `/studio` | AI video creation workbench |
| `/health` | Health check (DB + EvoLink + Volcengine) |
| `/docs` | Swagger API docs |
| `/share/{id}` | Shared video page |
| `/api/auth/*` | Auth (register/login/me/OAuth) |
| `/api/session/*` | Session CRUD |
| `/api/image/*` | Image generation |
| `/api/video-draft/*` | Video draft generation |
| `/api/final-video/*` | Final video rendering |
| `/api/music/*` | Music generation |
| `/api/payment/*` | Pricing + Stripe checkout |

## SSL Setup

```bash
# Staging test (no rate limits)
./deploy/certbot-init.sh see4dance.com admin@see4dance.com 1

# Production
./deploy/certbot-init.sh see4dance.com admin@see4dance.com

# Auto-renewal: certbot service runs every 12h in docker compose
```

## Backup & Restore

```bash
# Manual dump
./deploy/backup.sh

# Manual dump + S3 upload
./deploy/backup.sh --s3 s3://my-bucket/seedance-backups/

# Restore from backup
./deploy/backup.sh --restore backups/seedance_20260101.sql.gz

# Automated: backup container runs pg_dump daily at 3:00 AM
# Keeps last 7 days (configurable via BACKUP_KEEP_DAYS env)
```

## Updating

```bash
./deploy/update.sh              # Full update (pull + rebuild + restart)
./deploy/update.sh --backend    # Backend only
./deploy/update.sh --nginx      # Nginx config only
```

## Health Check

```bash
curl http://localhost/health
# {"status":"ok","db":"connected","dependencies":{"evolink":"ok","volcengine":"ok"},"service":"seedance-studio-api","version":"1.0.0"}
```

## CI/CD

GitHub Actions runs on push to main:
- **bandit** — Python security lint
- **semgrep** — SAST (Python + Secrets + OWASP + CWE Top 25)
- **ruff** — Python linter

See `.github/workflows/ci.yml`.
