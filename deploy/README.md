# Seedance Studio — Deploy Guide

## Quick Start (Docker Compose)

```bash
# 1. Configure environment
cp Seedance/backend/.env.example Seedance/backend/.env
# Edit .env — fill in EVOLINK_API_KEY, VOLC_API_KEY, DATABASE_URL, JWT_SECRET

# 2. Start all services
docker compose up -d

# 3. Verify
curl http://localhost/health
open http://localhost          # Portal
open http://localhost/studio   # Studio workbench
```

Services:
- **nginx** :80 — reverse proxy + static files
- **backend** :8000 — FastAPI (not exposed externally)
- **db** :5432 — PostgreSQL 16 (not exposed externally)

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `EVOLINK_API_KEY` | Yes | EvoLink AI API (image/music/video draft) |
| `VOLC_API_KEY` | Yes | Volcano Engine API (vision model + final video) |
| `JWT_SECRET` | Yes | JWT signing key (random 64-char hex) |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `ADMIN_KEY` | No | Admin API authentication key |
| `IMGBB_API_KEY` | No | imgbb upload (fallback image hosting) |

## Endpoints

| Path | Description |
|---|---|
| `/` | Portal landing page |
| `/studio` | AI video creation workbench |
| `/health` | Health check (DB + service status) |
| `/docs` | Swagger API docs |
| `/share/{id}` | Shared video page |
| `/api/auth/*` | Auth (register/login/me) |
| `/api/session/*` | Session CRUD |
| `/api/image/*` | Image generation |
| `/api/video-draft/*` | Video draft generation |
| `/api/final-video/*` | Final video rendering |
| `/api/music/*` | Music generation |
| `/api/payment/*` | Pricing + Stripe checkout |

## Health Check

```bash
curl http://localhost/health
# {"status":"ok","db":"connected","service":"seedance-studio-api","version":"1.0.0"}
```

## Manual Deployment (without Docker)

```bash
# Python 3.11+ required
cd Seedance/backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## CI/CD

GitHub Actions runs on push to main:
- **bandit** — Python security lint
- **semgrep** — SAST (Python + Secrets + OWASP + CWE Top 25)
- **ruff** — Python linter

See `.github/workflows/ci.yml`.
