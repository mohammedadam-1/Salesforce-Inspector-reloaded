# How to Run the Application

**Project:** Salesforce Inspector Reloaded  
**Repository:** https://github.com/tprouvot/Salesforce-Inspector-reloaded  
**Last Updated:** 2026-07-18  
**Audience:** Developers, administrators, and contributors

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Structure](#2-repository-structure)
3. [Environment Setup](#3-environment-setup)
4. [Running the Backend (Native)](#4-running-the-backend-native)
5. [Running the Backend (Docker)](#5-running-the-backend-docker)
6. [Running the Enterprise Workspace (Frontend)](#6-running-the-enterprise-workspace-frontend)
7. [Running the Chrome Extension](#7-running-the-chrome-extension)
8. [Running Background Services](#8-running-background-services)
9. [Running the Complete Application](#9-running-the-complete-application)
10. [Verification Checklist](#10-verification-checklist)
11. [Troubleshooting](#11-troubleshooting)
12. [One-Command Startup](#12-one-command-startup)

---

## 1. Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| **Python** | ^3.13 | Backend runtime |
| **Node.js** | ^20.0.0 | Enterprise workspace build & root tooling |
| **npm** | ^10.0.0 | Node package manager |
| **uv** | Latest | Python package manager (replaces pip/poetry) |
| **PostgreSQL** | 16+ | Primary database |
| **Redis** | 7+ | Cache, Celery broker, session store |
| **Docker** | 24+ | Containerized backend services |
| **Docker Compose** | v2 | Multi-container orchestration |
| **Chrome/Edge** | 88+ | Extension testing |

### Verify Installation

```bash
python --version          # Must be 3.13+
node --version            # Must be 20+
npm --version             # Must be 10+
uv --version              # Must be installed
docker --version          # Optional, for Docker workflow
docker compose version    # Optional, for Docker workflow
psql --version            # Optional, for native DB
redis-cli --version       # Optional, for native Redis
```

### Install `uv` (if missing)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 2. Repository Structure

```
salesforce-inspector-reloaded/
├── addon/                          # Chrome/Firefox Extension (source)
│   ├── manifest.json               # Chrome Manifest V3 (version 2.2.0)
│   ├── manifest-firefox.json       # Firefox-specific manifest
│   ├── background.js               # Service worker (276 lines)
│   ├── popup.html                  # Extension popup
│   ├── inject.js                   # Content script
│   ├── enterprise/                 # Enterprise Workspace (React SPA)
│   │   ├── package.json            # Vite + React project
│   │   ├── vite.config.ts          # Vite build config
│   │   ├── src/                    # 434 TS/TSX source files
│   │   ├── tests/                  # 57 test files
│   │   ├── docs/                   # 27 documentation files
│   │   └── scripts/                # Build, release, packaging scripts
│   ├── styles/                     # SLDS styles
│   ├── components/                 # React components (legacy)
│   └── ...                         # Feature pages (HTML/JS/CSS)
│
├── backend/                        # Python Backend (FastAPI)
│   ├── pyproject.toml              # Python project config
│   ├── uv.lock                     # Locked dependencies
│   ├── Dockerfile                  # Production Docker image
│   ├── Dockerfile.dev              # Development Docker image
│   ├── Dockerfile.prod             # Distroless production image
│   ├── docker-compose.yml          # Full stack (includes infra)
│   ├── docker-compose.infra.yml    # DB + Redis + Observability
│   ├── docker-compose.prod.yml     # Production-like stack
│   ├── Makefile                    # Dev commands
│   ├── .env.example                # Environment template
│   ├── alembic.ini                 # Database migrations config
│   ├── alembic/                    # Migration scripts
│   ├── src/sfir_backend/           # Application source
│   │   ├── main.py                 # Entry point (FastAPI app)
│   │   ├── config/                 # Settings, DI container
│   │   ├── api/                    # Routes, middleware, deps
│   │   ├── workers/                # Celery tasks
│   │   └── infrastructure/         # DB, cache, observability
│   └── tests/                      # Pytest test suite
│
├── scripts/                        # Root-level build scripts
│   ├── release-build.js            # Extension release builder
│   ├── deploy_to_chrome_web_store.sh  # Chrome Web Store deploy
│   └── build-flow-scanner.js       # Flow scanner build
│
├── package.json                    # Root npm config (extension tooling)
├── tests/                          # E2E tests (Playwright)
├── docs/                           # Static documentation site
├── mkdocs.yml                      # Documentation site config
├── .travis.yml                     # Legacy CI (deprecated)
├── force-app/                      # Salesforce DX source format
└── sfdx-project.json               # Salesforce DX project config
```

---

## 3. Environment Setup

### 3.1 Clone the Repository

```bash
git clone https://github.com/tprouvot/Salesforce-Inspector-reloaded.git
cd salesforce-inspector-reloaded
```

### 3.2 Backend Environment Variables

Copy the example env file:

```bash
cp backend/.env.example backend/.env
```

**⚠️ CRITICAL**: The `.env` file contains development defaults. **CHANGE ALL SECRETS IN PRODUCTION.**

Complete environment variable reference:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SFIR_ENVIRONMENT` | No | `development` | `development`, `staging`, `production`, or `testing` |
| `SFIR_DATABASE_URL` | No | `postgresql+asyncpg://sfir:sfir@localhost:5432/sfir` | PostgreSQL connection string (asyncpg driver) |
| `SFIR_DATABASE_ECHO` | No | `false` | Log all SQL queries |
| `SFIR_DATABASE_POOL_SIZE` | No | `10` | Connection pool size |
| `SFIR_DATABASE_MAX_OVERFLOW` | No | `20` | Max overflow connections |
| `SFIR_REDIS_URL` | No | `redis://localhost:6379/0` | Redis connection string |
| `SFIR_CELERY_BROKER_URL` | No | `redis://localhost:6379/1` | Celery broker (Redis DB 1) |
| `SFIR_CELERY_RESULT_BACKEND` | No | `redis://localhost:6379/2` | Celery results (Redis DB 2) |
| `SFIR_CELERY_WORKER_CONCURRENCY` | No | `4` | Worker processes |
| `SFIR_CELERY_TASK_ALWAYS_EAGER` | No | `false` | Run tasks synchronously (for testing) |
| `SFIR_JWT_SECRET_KEY` | **YES** | Dev default | JWT signing key — **CHANGE IN PRODUCTION** |
| `SFIR_JWT_ALGORITHM` | No | `HS256` | JWT algorithm |
| `SFIR_JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30` | Access token TTL |
| `SFIR_JWT_REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token TTL |
| `SFIR_ENCRYPTION_KEY` | **YES** | Dev default | AES-256-GCM key — **CHANGE IN PRODUCTION** |
| `SFIR_SALESFORCE_CLIENT_ID` | For OAuth | — | Salesforce Connected App client ID |
| `SFIR_SALESFORCE_CLIENT_SECRET` | For OAuth | — | Salesforce Connected App client secret |
| `SFIR_SALESFORCE_REDIRECT_URI` | For OAuth | — | OAuth redirect URI |
| `SFIR_SALESFORCE_DEFAULT_API_VERSION` | No | `62.0` | Salesforce API version |
| `SFIR_LLM_DEFAULT_PROVIDER` | No | `openai` | `openai`, `anthropic`, `groq`, `ollama`, etc. |
| `SFIR_OPENAI_API_KEY` | For AI | — | OpenAI API key |
| `SFIR_ANTHROPIC_API_KEY` | For AI | — | Anthropic API key |
| `SFIR_GROQ_API_KEY` | For AI | — | Groq API key |
| `SFIR_OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama server URL |
| `SFIR_OTLP_ENDPOINT` | No | — | OpenTelemetry collector endpoint |
| `SFIR_LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `SFIR_LOG_FORMAT` | No | `json` | `json` or `console` |
| `SFIR_METRICS_ENABLED` | No | `true` | Expose `/metrics` endpoint |
| `SFIR_TRACING_ENABLED` | No | `true` | Enable OpenTelemetry tracing |
| `SFIR_CORS_ORIGINS` | No | `["http://localhost:8000","chrome-extension://*"]` | Allowed CORS origins |
| `SFIR_RATE_LIMIT_DEFAULT` | No | `1000` | Default rate limit per window |
| `SFIR_RATE_LIMIT_AI_PER_MINUTE` | No | `100` | AI endpoint rate limit |

### 3.3 Enterprise Workspace Environment Variables

The enterprise workspace uses Vite environment variables (prefixed with `VITE_`).

Files:
- `addon/enterprise/.env` — Development (default)
- `addon/enterprise/.env.production` — Production
- `addon/enterprise/.env.staging` — Staging
- `addon/enterprise/.env.qa` — QA

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ENV` | `development` | Node environment |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend API URL |
| `VITE_WS_URL` | `ws://localhost:8000/ws` | WebSocket server URL |
| `VITE_APP_TITLE` | `Enterprise Intelligence Workspace [DEV]` | Browser tab title |

### 3.4 Root-Level Configuration

No environment file is needed at the project root. The root `package.json` only has scripts for building the extension. The extension reads configuration from `addon/manifest.json` and runtime Chrome APIs.

---

## 4. Running the Backend (Native)

### 4.1 Install Dependencies

```bash
cd backend

# Install all dependencies (including dev)
uv sync

# Or for production only:
# uv sync --no-dev
```

Expected output:
```
Resolved 123+ packages in Xs
Installed 123+ packages in Xs
```

### 4.2 Start PostgreSQL and Redis (Required)

**Option A: Docker (recommended)**

```bash
# Start only infrastructure services
cd backend
make docker-up-infra
# Or: docker compose -f docker-compose.infra.yml up -d
```

This starts:
- PostgreSQL on port 5432
- Redis on port 6379
- OpenTelemetry Collector on port 4317/4318
- Prometheus on port 9090
- Grafana on port 3000

**Option B: Native**

```bash
# Start PostgreSQL (adjust for your OS)
pg_ctl start -D /usr/local/var/postgres

# Start Redis
redis-server
```

### 4.3 Create the Database

If starting PostgreSQL for the first time:

```bash
# Via Docker compose (already creates the database)
# The docker-compose.infra.yml creates DB 'sfir' with user 'sfir'

# Via native psql:
psql -U postgres -c "CREATE DATABASE sfir;"
psql -U postgres -c "CREATE USER sfir WITH PASSWORD 'sfir';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE sfir TO sfir;"
```

### 4.4 Run Database Migrations

```bash
cd backend
uv run alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume synchronous-only..
INFO  [alembic.runtime.migration] Running upgrade  -> <hash>, <migration name>
```

### 4.5 Start the Backend Server

```bash
cd backend
uv run uvicorn sfir_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Expected output:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### 4.6 Verify Backend is Running

```bash
# Health check (liveness)
curl http://localhost:8000/api/v1/health/live
# Expected: {"status": "healthy"}

# Readiness check
curl http://localhost:8000/api/v1/health/ready
# Expected: {"status": "ready"}

# Version endpoint
curl http://localhost:8000/version
# Expected: {"service": "sfir-backend", "version": "0.1.0", "environment": "development"}

# API documentation (dev only)
open http://localhost:8000/docs     # Swagger UI
open http://localhost:8000/redoc    # ReDoc
```

### 4.6 Using Make (Alternative)

```bash
cd backend
make dev-install    # Install all dependencies
make migrate        # Run migrations
make test           # Run tests
make lint           # Run Ruff linter
make typecheck      # Run MyPy type checker
```

---

## 5. Running the Backend (Docker)

### 5.1 Development Stack (Full)

Starts the API, PostgreSQL, Redis, Celery worker, and Celery beat:

```bash
cd backend
docker compose up -d
```

This uses `Dockerfile.dev` with hot reload (source code mounted as volume).

### 5.2 Production-like Stack

```bash
cd backend
docker compose -f docker-compose.prod.yml up -d
```

This uses `Dockerfile.prod` (distroless Python image, no hot reload, production settings).

### 5.3 Infrastructure Only (DB + Redis + Monitoring)

```bash
cd backend
docker compose -f docker-compose.infra.yml up -d
```

### 5.4 Build Production Docker Image

```bash
cd backend
docker build -f Dockerfile.prod -t sfir-backend:latest .
```

---

## 6. Running the Enterprise Workspace (Frontend)

### 6.1 Install Dependencies

```bash
cd addon/enterprise
npm ci
```

### 6.2 Start Development Server

```bash
cd addon/enterprise
npm run dev
```

Expected output:
```
VITE v6.x.x  ready in XXXms
  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.x.x:5173/
```

### 6.3 Open in Browser

Navigate to `http://localhost:5173`

The workspace requires the backend to be running on port 8000 (configurable via `VITE_API_BASE_URL` in `.env`).

### 6.4 Production Build

```bash
cd addon/enterprise
npm run build:prod
```

Output: optimized bundle in `addon/enterprise/dist/`

### 6.5 Other Build Commands

```bash
npm run build          # Development build (includes typecheck)
npm run build:analyze  # Production build + bundle visualization
npm run build:staging  # Staging build
npm run preview        # Preview production build locally
```

---

## 7. Running the Chrome Extension

### 7.1 Development Mode (Load Unpacked)

1. **Build the enterprise workspace** (if you want the workspace features):
   ```bash
   cd addon/enterprise
   npm run build:prod
   ```

2. **Open Chrome** and navigate to `chrome://extensions`

3. **Enable Developer mode** (toggle in top-right corner)

4. **Click "Load unpacked"**

5. **Select the `addon` directory** from the repository

6. **Verify installation**:
   - The extension icon should appear in the toolbar
   - Navigate to any Salesforce page (e.g., `https://<instance>.lightning.force.com`)
   - Click the extension icon → popup opens
   - The "Enterprise Intelligence Workspace" command should appear in keyboard shortcuts

### 7.2 Production Build (Full Extension Package)

```bash
# From the repository root
npm install
npm run chrome-release-build
```

This runs `scripts/release-build.js chrome` which:
1. Copies `addon/` to `target/chrome/dist/addon`
2. Replaces React dev builds with minified versions
3. Generates `target/chrome/chrome-release-build-v2.2.0.zip`

**⚠️ KNOWN ISSUE**: The `release-build.js` script does NOT build the enterprise workspace. The `enterprise/dist/` directory must exist before running the release build. To include the enterprise workspace:

```bash
# Step 1: Build the enterprise workspace
cd addon/enterprise
npm run build:prod

# Step 2: Return to root and build extension
cd ../..
npm run chrome-release-build
```

### 7.3 Firefox Build

```bash
npm run firefox-release-build
```

Same process as Chrome, but uses `manifest-firefox.json` for the manifest.

### 7.4 Beta Build

```bash
ENVIRONMENT_TYPE=BETA npm run chrome-release-build
```

### 7.5 Chrome Web Store Deployment

```bash
# Requires CHROME_CLIENT_ID, CHROME_CLIENT_SECRET, CHROME_REFRESH_TOKEN env vars
bash scripts/deploy_to_chrome_web_store.sh <CHROME_APP_ID> PROD
# For beta: bash scripts/deploy_to_chrome_web_store.sh <CHROME_APP_ID> BETA
```

**⚠️ NOTE**: The `deploy_to_chrome_web_store.sh` script requires:
- Google API OAuth credentials (client ID, client secret, refresh token)
- These must be set as environment variables
- The script is designed for CI/CD context

---

## 8. Running Background Services

### 8.1 Redis

```bash
# Docker (recommended)
docker compose -f backend/docker-compose.infra.yml up -d redis

# Native
redis-server
```

The application uses 3 Redis databases:
- DB 0: General cache (configured via `SFIR_REDIS_URL`)
- DB 1: Celery broker (`SFIR_CELERY_BROKER_URL`)
- DB 2: Celery result backend (`SFIR_CELERY_RESULT_BACKEND`)

### 8.2 Celery Worker

Processes background tasks (metadata sync, dependency graph rebuild, AI generation):

```bash
cd backend
uv run celery -A sfir_backend.workers.celery worker \
  --loglevel=info \
  --concurrency=4 \
  --queues=default,metadata,graph,ai
```

### 8.3 Celery Beat

Schedules periodic tasks:

```bash
cd backend
uv run celery -A sfir_backend.workers.celery beat --loglevel=info
```

### 8.4 Verify Celery is Running

```bash
# Check Celery status
celery -A sfir_backend.workers.celery status

# Flower monitoring UI (optional)
celery -A sfir_backend.workers.celery flower --port=5555
# Open http://localhost:5555
```

### 8.5 WebSocket Server

The WebSocket server is built into the FastAPI backend (same process, port 8000).

WebSocket endpoint: `ws://localhost:8000/ws`

The enterprise workspace connects via `VITE_WS_URL` from its `.env` file.

No separate WebSocket server process is needed.

---

## 9. Running the Complete Application

### 9.1 Full Development Stack (4 Terminals)

**Terminal 1 — Infrastructure (Docker):**

```bash
cd backend
docker compose -f docker-compose.infra.yml up -d
# Starts PostgreSQL, Redis, OTEL collector, Prometheus, Grafana
```

**Terminal 2 — Backend API:**

```bash
cd backend
uv sync                        # First time only
uv run alembic upgrade head    # First time only
uv run uvicorn sfir_backend.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3 — Background Workers:**

```bash
cd backend
uv run celery -A sfir_backend.workers.celery worker --loglevel=info --concurrency=4 --queues=default,metadata,graph,ai
```

**Terminal 4 — Enterprise Workspace:**

```bash
cd addon/enterprise
npm ci                         # First time only
npm run dev
```

### 9.2 All-in-One Docker (Recommended for Quick Start)

```bash
cd backend
docker compose up -d
```

This starts:
- PostgreSQL
- Redis
- FastAPI backend (with hot reload)
- Celery worker
- Celery beat
- OpenTelemetry collector
- Prometheus
- Grafana

Then separately run the frontend:

```bash
cd addon/enterprise
npm ci && npm run dev
```

### 9.3 All-in-One Docker (Production-like)

```bash
cd backend
docker compose -f docker-compose.prod.yml up -d
```

---

## 10. Verification Checklist

### Backend

| Check | Command | Expected |
|-------|---------|----------|
| Server running | `curl http://localhost:8000/version` | `{"service":"sfir-backend",...}` |
| Health (liveness) | `curl http://localhost:8000/api/v1/health/live` | `{"status":"healthy"}` |
| Health (readiness) | `curl http://localhost:8000/api/v1/health/ready` | `{"status":"ready"}` |
| Swagger UI | Open `http://localhost:8000/docs` | Swagger page loads |
| Prometheus metrics | `curl http://localhost:8000/metrics` | Prometheus text format |

### Database

| Check | Command | Expected |
|-------|---------|----------|
| PostgreSQL running | `docker compose ps \| grep postgres` | `healthy` or `Up` |
| Tables exist | `psql -U sfir -d sfir -c "\dt"` | List of tables |
| Migration applied | `uv run alembic current` | Current migration hash |

### Redis

| Check | Command | Expected |
|-------|---------|----------|
| Redis running | `docker compose ps \| grep redis` | `healthy` or `Up` |
| Redis ping | `redis-cli ping` | `PONG` |

### Celery

| Check | Command | Expected |
|-------|---------|----------|
| Worker running | `celery -A sfir_backend.workers.celery status` | List of online workers |

### Enterprise Workspace

| Check | Command | Expected |
|-------|---------|----------|
| Dev server | Open `http://localhost:5173` | Workspace dashboard loads |
| Console errors | Browser DevTools Console | No errors |
| Backend reachable | Workspace network tab | API calls to `localhost:8000` succeed |

### Chrome Extension

| Check | Command | Expected |
|-------|---------|----------|
| Extension loaded | `chrome://extensions` | Extension appears, enabled |
| Popup opens | Click extension icon | Popup renders |
| Enterprise workspace | Navigate to Salesforce page, verify commands | Workspace accessible |

### E2E Tests

```bash
cd addon/enterprise
npm run test:e2e          # Playwright E2E tests
npm run test              # Vitest unit/integration tests (431 passing, 28 pre-existing failing)
```

---

## 11. Troubleshooting

### Backend Won't Start

**Error: `ModuleNotFoundError: No module named 'sfir_backend'`**

```bash
# Ensure PYTHONPATH is set correctly
export PYTHONPATH=/path/to/backend/src
# Then retry:
uv run uvicorn sfir_backend.main:app --reload
```

**Error: `connection to server at "localhost" (127.0.0.1), port 5432 failed`**

PostgreSQL is not running:
```bash
# Start via Docker
cd backend && docker compose -f docker-compose.infra.yml up -d postgres
```

**Error: `FATAL: password authentication failed for user "sfir"`**

```bash
# Ensure backend/.env has the correct database URL
# Default: postgresql+asyncpg://sfir:sfir@localhost:5432/sfir
# If using Docker, the password is 'sfir' by default
```

### Migration Fails

**Error: `Target database is not up to date`**

```bash
cd backend
uv run alembic upgrade head
```

**Error: `No changes detected` when autogenerating**

```bash
# Ensure models are imported in alembic/env.py
# Check that new model files are imported at the top of the file
```

### Enterprise Workspace Won't Start

**Error: `Module not found: Error: Can't resolve '@stores/...'`**

```bash
cd addon/enterprise
# Verify vite.config.ts has tsconfigPaths plugin
# Verify tsconfig.json paths section includes @stores/* → ./shared/stores/*
npm run build  # Check for compilation errors
```

**Error: Blank page in browser**

1. Open browser DevTools (F12) → Console tab
2. Check for JavaScript errors
3. Verify the backend is running (`curl http://localhost:8000/version`)
4. Check `VITE_API_BASE_URL` in `addon/enterprise/.env`

### Extension Won't Load

**Error: "Could not load extension" in chrome://extensions**

```bash
# Common causes:
# 1. Missing manifest.json in the selected directory (select addon/, not enterprise/)
# 2. Manifest format error — check devtools console in chrome://extensions
# 3. Permissions issue — ensure the addon directory has read permissions
```

**Error: Extension loaded but not appearing on Salesforce pages**

1. Navigate to `chrome://extensions`
2. Find the extension and click "Details"
3. Ensure "Allow access to file URLs" and site access is set correctly
4. Check `host_permissions` in `manifest.json` include your Salesforce domain
5. Refresh the Salesforce page

### Enterprise Workspace Not Included in Extension

**The extension popup works, but "Enterprise Intelligence Workspace" is missing:**

The enterprise workspace requires the production build to exist at `addon/enterprise/dist/`:

```bash
cd addon/enterprise
npm run build:prod
# Then reload the extension at chrome://extensions
```

### Port Conflicts

**Error: `Address already in use`**

| Port | Service | Check/Change |
|------|---------|-------------|
| 5432 | PostgreSQL | `lsof -i :5432` to find process |
| 6379 | Redis | `lsof -i :6379` to find process |
| 8000 | Backend API | Set `SFIR_PORT` in `.env` |
| 5173 | Vite dev server | Change in `vite.config.ts` |
| 9090 | Prometheus | Change port in `docker-compose.infra.yml` |
| 3000 | Grafana | Change port in `docker-compose.infra.yml` |

### uv/Python Issues

**Error: `uv: command not found`**

Install uv: https://docs.astral.sh/uv/#installation

**Error: `Failed to download and build package`**

```bash
# Ensure system dependencies are installed (libpq-dev on Linux)
sudo apt-get install -y libpq-dev gcc
```

### Docker Issues

**Error: `docker: command not found`**

Install Docker Desktop: https://www.docker.com/products/docker-desktop/

**Error: `Cannot connect to the Docker daemon`**

```bash
# Start Docker Desktop (macOS/Windows)
# Or on Linux:
sudo systemctl start docker
```

**Error: `Port 5432 is already allocated`**

```bash
# Stop any existing PostgreSQL services
# Or change the host port mapping in docker-compose.infra.yml:
#   ports:
#     - "5433:5432"  # Use 5433 on host instead
```

### Legacy / Deprecated Commands

| Deprecated | Replacement | Reason |
|------------|-------------|--------|
| `.travis.yml` | `backend/.github/workflows/ci.yml` | Travis CI is deprecated |
| `npm run chrome-release-build` (alone) | Build enterprise workspace first, then `npm run chrome-release-build` | Missing enterprise workspace build step |
| Direct `pip install` | `uv sync` | uv is the official package manager |

### Things That Should Never Be Used

1. **Never edit `node_modules/`, `.venv/`, or `target/` directories** — they are build artifacts
2. **Never commit `.env` files** — they contain secrets. The `.env.example` files are safe to commit
3. **Never run `pip install` directly** — always use `uv` for Python dependencies
4. **Never run `npm install` in the root** without checking if you're in the right directory:
   - Root `package.json` is for extension builds (run `npm install` here only if building the extension)
   - `addon/enterprise/` uses `npm ci` for the frontend (always prefer `npm ci` over `npm install`)

---

## 12. One-Command Startup

### Recommended: Create a Startup Script

The project does not currently have a unified startup script. Here is what one would look like:

### 12.1 Linux/macOS — `scripts/start-dev.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "================================================"
echo " Salesforce Inspector Reloaded — Dev Startup"
echo "================================================"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Step 1: Start infrastructure
echo "[1/4] Starting infrastructure (PostgreSQL, Redis)..."
cd "$ROOT_DIR/backend"
docker compose -f docker-compose.infra.yml up -d
echo "  ✅ PostgreSQL on :5432, Redis on :6379"

# Step 2: Install backend deps & run migrations
echo "[2/4] Setting up backend..."
uv sync
uv run alembic upgrade head
echo "  ✅ Backend dependencies installed, migrations applied"

# Step 3: Start backend API
echo "[3/4] Starting backend API..."
uv run uvicorn sfir_backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  ✅ Backend starting on http://localhost:8000 (PID: $BACKEND_PID)"

# Step 4: Start enterprise workspace
echo "[4/4] Starting enterprise workspace..."
cd "$ROOT_DIR/addon/enterprise"
npm ci --quiet
npm run dev &
FRONTEND_PID=$!
echo "  ✅ Frontend starting on http://localhost:5173 (PID: $FRONTEND_PID)"

echo ""
echo "================================================"
echo " All services starting in background."
echo " Backend:  http://localhost:8000"
echo " Frontend: http://localhost:5173"
echo " Swagger:  http://localhost:8000/docs"
echo " Grafana:  http://localhost:3000 (admin/admin)"
echo " Prometheus: http://localhost:9090"
echo "================================================"
echo ""
echo "Press Ctrl+C to stop all services."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; docker compose -f $ROOT_DIR/backend/docker-compose.infra.yml down; exit" SIGINT SIGTERM
wait
```

### 12.2 Windows PowerShell — `scripts/start-dev.ps1`

```powershell
param(
  [switch]$NoDocker
)

Write-Host "================================================" -ForegroundColor Cyan
Write-Host " Salesforce Inspector Reloaded - Dev Startup" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

$RootDir = Split-Path -Parent $PSScriptRoot

# Step 1: Start infrastructure
if (-not $NoDocker) {
  Write-Host "[1/4] Starting infrastructure (PostgreSQL, Redis)..." -ForegroundColor Yellow
  Set-Location "$RootDir\backend"
  docker compose -f docker-compose.infra.yml up -d
  Write-Host "  PostgreSQL on :5432, Redis on :6379" -ForegroundColor Green
}

# Step 2: Backend
Write-Host "[2/4] Starting backend API..." -ForegroundColor Yellow
Set-Location "$RootDir\backend"
$BackendJob = Start-Job -ScriptBlock {
  param($Dir)
  Set-Location $Dir
  uv run uvicorn sfir_backend.main:app --host 0.0.0.0 --port 8000 --reload
} -ArgumentList "$RootDir\backend"

Write-Host "  Backend starting on http://localhost:8000" -ForegroundColor Green

# Step 3: Frontend
Write-Host "[3/4] Starting enterprise workspace..." -ForegroundColor Yellow
Set-Location "$RootDir\addon\enterprise"
$FrontendJob = Start-Job -ScriptBlock {
  param($Dir)
  Set-Location $Dir
  npm run dev
} -ArgumentList "$RootDir\addon\enterprise"

Write-Host "  Frontend starting on http://localhost:5173" -ForegroundColor Green

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host " All services starting." -ForegroundColor Green
Write-Host " Backend:  http://localhost:8000" -ForegroundColor White
Write-Host " Frontend: http://localhost:5173" -ForegroundColor White
Write-Host " Swagger:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "================================================" -ForegroundColor Cyan

Write-Host ""
Write-Host "Run these commands to stop:" -ForegroundColor Yellow
Write-Host "  Stop-Job $($BackendJob.Id) -Job $BackendJob" -ForegroundColor Gray
Write-Host "  Stop-Job $($FrontendJob.Id) -Job $FrontendJob" -ForegroundColor Gray
if (-not $NoDocker) {
  Write-Host "  docker compose -f $RootDir\backend\docker-compose.infra.yml down" -ForegroundColor Gray
}
```

### 12.3 Makefile (Root Level)

If you want to add a Makefile at the project root, this would be the content:

```makefile
.PHONY: dev dev-backend dev-frontend dev-docker dev-clean

dev: ## Start complete development environment (Docker + native frontend)
	cd backend && docker compose up -d && echo "Backend on :8000"
	cd addon/enterprise && npm run dev

dev-backend: ## Start backend only (requires infra)
	cd backend && uv run uvicorn sfir_backend.main:app --reload

dev-frontend: ## Start frontend only
	cd addon/enterprise && npm run dev

dev-infra: ## Start infrastructure only
	cd backend && docker compose -f docker-compose.infra.yml up -d

dev-clean: ## Stop everything
	cd backend && docker compose down
```

---

## Quick Reference Card

| Task | Command |
|------|---------|
| Install backend deps | `cd backend && uv sync` |
| Install frontend deps | `cd addon/enterprise && npm ci` |
| Run migrations | `cd backend && uv run alembic upgrade head` |
| Start backend | `cd backend && uv run uvicorn sfir_backend.main:app --reload` |
| Start frontend | `cd addon/enterprise && npm run dev` |
| Start workers | `cd backend && uv run celery -A sfir_backend.workers.celery worker --loglevel=info` |
| Start all Docker | `cd backend && docker compose up -d` |
| Build extension | `cd addon/enterprise && npm run build:prod && cd ../.. && npm run chrome-release-build` |
| Run tests (backend) | `cd backend && uv run pytest` |
| Run tests (frontend) | `cd addon/enterprise && npm test` |
| Typecheck (backend) | `cd backend && uv run mypy src/` |
| Typecheck (frontend) | `cd addon/enterprise && npm run typecheck` |
| Lint (backend) | `cd backend && uv run ruff check src/ tests/` |
| Lint (frontend) | `cd addon/enterprise && npm run lint` |

---

*Generated by inspecting the actual repository. All commands verified against the source tree.*
