# RiskIntel Public Website — Python Backend

Production-grade FastAPI backend for the RiskIntel public website.

## Technology Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.115 |
| Language | Python 3.12+ |
| Database | PostgreSQL 17 |
| ORM | SQLAlchemy 2.x (async) |
| Migrations | Alembic |
| Auth | JWT (HS256) + Argon2id |
| Validation | Pydantic v2 |
| Rate Limiting | slowapi (Redis-backed) |
| Caching | Redis 7 |
| Logging | structlog (JSON) |
| Container | Docker (multi-stage) |

---

## Folder Structure

```
backend/
├── app/
│   ├── api/v1/          ← Route handlers (thin, no business logic)
│   │   ├── admin/       ← ADMIN+ protected routes
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── releases.py
│   │   ├── downloads.py
│   │   ├── feedback.py
│   │   ├── contact.py
│   │   └── health.py
│   ├── core/            ← Config, security, logging, dependencies
│   ├── db/              ← Engine, session, base
│   ├── models/          ← SQLAlchemy ORM models
│   ├── schemas/         ← Pydantic v2 I/O schemas
│   ├── repositories/    ← Data access layer (all SQL here)
│   ├── services/        ← Business logic layer
│   ├── middleware/      ← Request ID, security headers, rate limit
│   ├── utils/           ← Email, audit logging, pagination
│   ├── tests/           ← pytest test suite
│   └── main.py          ← FastAPI app factory
├── alembic/             ← Database migrations
├── alembic.ini
├── Dockerfile
├── pyproject.toml       ← pytest config
├── requirements.txt
└── .env.example
```

---

---

## Quick Start (Local Development)

To run the backend smoothly, start required services in this exact order:

### 1. What to Start FIRST: Database & Caching Services

Before launching the Python backend, ensure your data services are running:

1. **PostgreSQL 17 (Required - Port `5432`):**
   - Start your local PostgreSQL server:
     ```powershell
     net start postgresql-x64-17   # On Windows
     # Or via Docker:
     docker run -d --name local-postgres -p 5432:5432 -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=riskintel_public postgres:17
     ```
2. **Redis 7 (Optional - Port `6379`):**
   - Used for distributed rate limiting and token management.
   - *If you have Redis/Docker:*
     ```powershell
     docker run -d --name local-redis -p 6379:6379 redis:7
     ```
   - *If you do NOT want to run Redis locally:* No problem! Simply set `REDIS_URL=memory://` in your `.env` (see step 4 below).

---

### 2. Create and Activate Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows PowerShell / CMD
# source venv/bin/activate   # Linux/macOS
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment (`.env`)

```bash
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/macOS
```

Key configuration options in `.env`:
```env
DATABASE_URL=postgresql+asyncpg://postgres:your_password@localhost:5432/riskintel_public
JWT_SECRET_KEY=dev-secret-key-change-in-production-min-32-chars

# 💡 REDIS & RATE LIMITING CONFIGURATION:
# Option A (Recommended for local dev): Use in-memory rate limiting (avoids Redis timeout & warning)
REDIS_URL=memory://

# Option B: Use local Redis server if running on port 6379
# REDIS_URL=redis://localhost:6379/0
```

> [!NOTE]
> ### 💡 Understanding the `rate_limit_storage_fallback` Warning
> If you see:
> ```text
> [warning ] rate_limit_storage_fallback detail=Redis unreachable; rate limits will be enforced per process. reason=TimeoutError
> ```
> **This is a non-fatal warning, NOT a crash.** The application probes Redis on startup; if Redis is unreachable, it automatically and safely degrades to in-memory rate limiting (`memory://`).
> - **To eliminate this warning completely:** Set `REDIS_URL=memory://` in your `.env` file.
> - **Or start Redis:** Run `docker run -d -p 6379:6379 redis:7`.

### 5. Run Database Migrations

Apply the SQLAlchemy/Alembic schema migrations:

```bash
# For a fresh/empty database:
alembic upgrade head

# ⚠️ If tables already exist (e.g. error: relation "User" already exists):
# Tell Alembic the schema is already at head without re-running CREATE TABLE:
alembic stamp head
```

### 6. Seed Development Data & Test Accounts

Seed development accounts (admin, user, unverified) and publish a placeholder release artifact so you can test downloads immediately:

```bash
python scripts/seed_dev.py
```

*Pre-seeded credentials:*
- **Admin:** `admin@riskintel.io` / `Admin-Riskintel-2026!`
- **Verified User:** `user@riskintel.io` / `User-Riskintel-2026!`

### 7. Start the Development Server

```bash
uvicorn app.main:app --reload --port 8080
```

- **Interactive API Documentation:** http://localhost:8080/docs
- **Liveness Probe:** http://localhost:8080/health/live
- **Readiness Probe:** http://localhost:8080/health/ready

---

## Docker Deployment

To launch PostgreSQL, Redis, database migrations, and the FastAPI backend together in Docker:

```bash
# Navigate to public-website/docker/
cd public-website/docker

# Copy environment template
copy .env.example .env       # Windows
# cp .env.example .env       # Linux/macOS

# Spin up all services
docker compose up -d
```

The `website-migrate` service runs `alembic upgrade head` before the backend container starts.

---

## Running Tests

```bash
# Install test dependencies (already in requirements.txt)
pytest

# With coverage
pytest --cov=app --cov-report=term-missing
```

---

## API Endpoints

### Authentication (`/api/v1/auth/`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/register` | Register new user |
| POST | `/login` | Login, receive JWT tokens |
| POST | `/refresh` | Rotate refresh token |
| POST | `/logout` | Revoke refresh token |
| POST | `/verify-email` | Verify email address |
| POST | `/request-password-reset` | Request reset email |
| POST | `/reset-password` | Complete password reset |

### Users (`/api/v1/users/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/me` | Any | Get own profile |
| PATCH | `/me` | Any | Update own profile |

### Releases (`/api/v1/releases/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `/` | None | List published releases |
| GET | `/latest` | None | Get latest release |
| GET | `/{id}` | None | Get release by ID |

### Downloads (`/api/v1/downloads/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | Verified | Record download |
| GET | `/me` | Verified | My download history |

### Feedback (`/api/v1/feedback/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | Any | Submit feedback |
| GET | `/me` | Any | My feedback |

### Contact (`/api/v1/contact/`)

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/` | Any | Submit contact request |
| GET | `/me` | Any | My contact requests |

### Admin

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET/POST | `/api/v1/admin/releases` | ADMIN+ | Manage releases |
| PATCH/DELETE | `/api/v1/admin/releases/{id}` | ADMIN+ | Update/delete release |
| GET/PATCH | `/api/v1/admin/feedback` | ADMIN+ | Manage feedback |
| GET/PATCH | `/api/v1/admin/contact` | ADMIN+ | Manage contacts |

### Health

| Endpoint | Description |
|---|---|
| `GET /health/live` | Process alive check |
| `GET /health/ready` | DB connectivity check |

---

## Security

- **Passwords**: Argon2id (64 MiB, time_cost=3)
- **JWT**: HS256, 15-minute access tokens, 7-day refresh tokens
- **Refresh rotation**: Single-use tokens, hashed storage
- **Rate limiting**: 10 req/min for auth, 100 req/min default
- **Headers**: HSTS, CSP, X-Frame-Options, X-Content-Type-Options
- **CORS**: Strict allowlist from `CORS_ORIGINS` env var
- **Request size**: 1 MB limit
- **Audit logging**: All auth events and admin actions logged as structured JSON

---

## Environment Variables

See [`.env.example`](.env.example) for full reference.

Critical variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:port/db` |
| `JWT_SECRET_KEY` | Random 64+ char hex string |
| `REDIS_URL` | Redis connection string |
| `CORS_ORIGINS` | Comma-separated allowed origins |
