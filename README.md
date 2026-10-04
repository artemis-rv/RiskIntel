<div align="center">

  # 🛡️ Risk Intel 
  ### Endpoint Risk Analyzer

  <p>
    An intelligent, agent-based platform for evaluating endpoint security posture using CIS benchmarks, ML-assisted risk scoring, and real-time visualization.
  </p>

  <p>
    <a href="#-key-features">Features</a> •
    <a href="#-architecture">Architecture</a> •
    <a href="#-security-posture">Security</a> •
    <a href="#-getting-started">Getting Started</a>
  </p>

</div>

---

## 🌟 Key Features

- **Real-Time Visibility:** Background agents (Python) stream live system configuration data, network states, and OS details directly to the central server.
- **CIS Benchmarking:** Automatically maps endpoint settings against **Center for Internet Security (CIS)** standards to pinpoint misconfigurations and vulnerabilities.
- **ML Risk Assessment:** Built-in Machine Learning models calculate Anomaly Scores and grade the overall organizational security health based on aggregated endpoint telemetry.
- **Secure Architecture:** Complete TLS enforcement. All traffic flows through an Nginx reverse proxy using `HTTPS` and `WSS` (Secure WebSockets), with strict agent-side certificate pinning to prevent Man-in-the-Middle (MITM) attacks.

---

## 💻 Tech Stack

<div align="center">
  <table align="center" style="border: none; background: transparent;">
    <tr>
      <td align="center" width="25%">
        <strong>Frontend</strong><br><br>
        <img src="https://skillicons.dev/icons?i=react,tailwind" alt="React & Tailwind" /><br>
        <sub>React, TailwindCSS, Framer Motion</sub>
      </td>
      <td align="center" width="25%">
        <strong>Backend</strong><br><br>
        <img src="https://skillicons.dev/icons?i=fastapi,python" alt="FastAPI & Python" /><br>
        <sub>FastAPI, WebSockets, Python 3.10+</sub>
      </td>
      <td align="center" width="25%">
        <strong>Database</strong><br><br>
        <img src="https://skillicons.dev/icons?i=mongodb" alt="MongoDB" /><br>
        <sub>MongoDB (Atlas / Local)</sub>
      </td>
      <td align="center" width="25%">
        <strong>Agent / Infra</strong><br><br>
        <img src="https://skillicons.dev/icons?i=windows,nginx" alt="Windows & Nginx" /><br>
        <sub>Python, Psutil, Nginx</sub>
      </td>
    </tr>
  </table>
</div>

---

## 🏗️ Architecture

Risk Intel is built using a modern, decoupled microservices architecture divided into two primary subsystems:

### 1. RiskIntel Core Platform (Internal SOC Posture Analyzer)
- **Agent (`/agent`)**: A lightweight Windows/Linux background sensor. Collects endpoint telemetry (processes, network ports, firewall status, CIS benchmarks via `psutil` and `wmi`), cryptographically registers with the backend, and polls for scan jobs.
- **Backend (`/backend`)**: A high-performance **FastAPI** application on port `8000`. Manages endpoint registration, MongoDB data persistence, machine learning anomaly inference (Isolation Forest & KMeans), CIS benchmark grading, and real-time WebSocket broadcasting.
- **Frontend Dashboard (`/frontend`)**: A modern **React 19 & TailwindCSS** SOC dashboard on port `3000`. Visualizes organizational risk scores, endpoint health cards, CIS audit breakdowns, and live scan triggers.
- **Infrastructure (`/infra`)**: An **Nginx** reverse proxy providing SSL/TLS termination, port routing, and strict agent-side certificate pinning (`dev.crt`).

### 2. RiskIntel Public Portal & Distribution Website
- **Public Backend (`/public-website/backend`)**: A production-grade **FastAPI** service on port `8080`. Backed by **PostgreSQL 17** via asynchronous **SQLAlchemy 2.x** and **Alembic** migrations, handling user authentication (JWT + Argon2id), role-based access control, downloadable signed agent release artifacts, and support feedback.
- **Public Frontend (`/public-website/frontend`)**: A high-speed **React 19 + Vite** single-page application on port `5173`. Provides product showcase, account management, documentation, and agent download workflows.

---

## 🔒 Security Posture

Risk Intel is engineered with a **"Secure-by-Default"** philosophy:
- **Strict Certificate Pinning**: The agent explicitly verifies the server's pinned TLS certificate (`verify=CERT_PATH`), immediately dropping any spoofed or MITM connections.
- **HMAC Job Signatures**: Server-issued scan jobs are cryptographically signed using HMAC-SHA256, ensuring agents only execute verified instructions.
- **Enrollment Token Authentication**: Agents must supply a shared cryptographically secure enrollment token (`ENROLLMENT_TOKEN`) during initial onboarding to receive an API session key.
- **Argon2id & JWT Auth**: Public portal users are secured using industry-standard Argon2id hashing and HS256 signed access tokens with strict CORS and security headers.

---

## 🚀 Execution & Setup Guide (Step-by-Step)

To run the complete system correctly, services **must be started in a specific chronological order**. Below is the execution matrix followed by detailed explanations and commands.

### 📋 Execution Order Matrix

| Order | Component / Task | Port | Directory | Why This Step Must Come First |
|:---:|---|:---:|---|---|
| **Step 1** | **Databases** (MongoDB & PostgreSQL) | `27017`<br>`5432` | System / Docker | Both FastAPI backends check DB connectivity immediately at boot. If databases are offline, the backends crash instantly. |
| **Step 2** | **Environment Configuration** (`.env`) | N/A | Multiple | Both backends and the agent need their environment variables. Crucially, the Backend and Agent **must share the same `ENROLLMENT_TOKEN`**. |
| **Step 3** | **DB Migrations & Seed Data** | N/A | `public-website/backend` | PostgreSQL tables must be created before the public API starts, and test accounts/releases must exist so features work without external SMTP. |
| **Step 4** | **Backend Services** (Core & Public) | `8000`<br>`8080` | `Main/EndpointRiskAnalyzer`<br>`public-website/backend` | Frontends and agents are clients that connect to these backends. Starting clients before servers causes immediate network drop errors. |
| **Step 5** | **Frontend Applications** (Dashboard & Portal) | `3000`<br>`5173` | `frontend`<br>`public-website/frontend` | Once the APIs and WebSockets are live, the browser interfaces can load, authenticate, and display live data seamlessly. |
| **Step 6** | **Endpoint Monitoring Agent** | Client | `agent` | The agent immediately performs a registration handshake with the Core Backend on launch. It requires the backend, DB, and token to be ready. |
| **Step 7** | *(Optional)* **Nginx TLS Reverse Proxy** | `80`, `443` | `infra` | Required when testing strict production HTTPS certificate pinning or unified domain routing. |

---

### 🗄️ Step 1: Start the Databases (MongoDB & PostgreSQL + optional Redis)

#### What are we doing?
We are starting the data engines that power Risk Intel:
- **MongoDB** (Port `27017`): Stores endpoint telemetry, raw JSON scans, ML feature vectors, and CIS benchmark audit results.
- **PostgreSQL** (Port `5432`): Stores user accounts, permissions, downloadable agent releases, and feedback for the public portal.
- **Redis** (Port `6379`, *Optional*): Used by the public website backend for distributed rate-limiting. If you do not want to run Redis, you can simply set `REDIS_URL=memory://` in your `.env` to use fast local in-memory limiting without any warnings.

#### Why do this first?
When the Core Backend (`backend/db/main.py`) boots, it immediately executes `client.admin.command("ping")`. If MongoDB is not running, Python raises `RuntimeError: MongoDB connection failed` and halts. Similarly, the public backend checks PostgreSQL readiness at `/health/ready`. **The databases must be active before any backend code can run.**

#### Proper Commands:

**Option A — Native Local Services (Windows):**
```powershell
# Start MongoDB service (if installed as a service)
net start MongoDB
# Or if running mongod manually:
mongod

# Ensure PostgreSQL service is running (Port 5432)
net start postgresql-x64-17   # or your installed Postgres version name
```

**Option B — Fast Track via Docker (Recommended):**
From the repository root `Main/EndpointRiskAnalyzer`:
```powershell
# Spin up both MongoDB and PostgreSQL containers in the background
docker compose up -d mongodb postgres

# (Optional) If you want Redis running locally to avoid rate-limiter fallback warnings:
docker run -d --name local-redis -p 6379:6379 redis:7
```

#### ✅ Verification:
Confirm ports are listening:
```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 27017  # MongoDB -> Should return True
Test-NetConnection -ComputerName 127.0.0.1 -Port 5432   # PostgreSQL -> Should return True
```

---

### ⚙️ Step 2: Configure Environment Files & Shared Secrets

#### What are we doing?
Copying the template `.env.example` files to `.env` and setting the necessary parameters.

#### Why do this first?
Services cannot read their database URIs, CORS rules, or secret keys without these files. Most importantly:
> [!IMPORTANT]
> **The Core Backend and the Endpoint Agent MUST share the EXACT SAME `ENROLLMENT_TOKEN`**.
> During agent registration (`POST /api/agent/register`), the backend compares the agent's `X-Enrollment-Token` header against its own `ENROLLMENT_TOKEN`. If they do not match, the agent is rejected with `401 Unauthorized`.

#### Proper Commands:

1. **Configure Core Backend `.env`:**
   ```powershell
   cd "backend"
   Copy-Item .env.example .env
   ```
   *Edit `backend/.env` to ensure:*
   - `MONGO_URI=mongodb://localhost:27017/`
   - `DB_NAME=org_security_posture_dev`
   - `ENFORCE_HTTPS=false` *(for local HTTP development without Nginx)*
   - `ENROLLMENT_TOKEN=CHANGE_ME_ENROLLMENT_TOKEN` *(set to a secure string of your choice)*

2. **Configure Endpoint Agent `.env`:**
   ```powershell
   cd "..\agent\agent_config"
   Copy-Item .env.example .env
   ```
   *Edit `agent/agent_config/.env` to ensure:*
   - `BACKEND_URL=http://localhost:8000` *(or `https://localhost` if using Nginx)*
   - `ENROLLMENT_TOKEN=CHANGE_ME_ENROLLMENT_TOKEN` *(MUST match the backend's token exactly!)*

3. **Configure Public Website Backend `.env`:**
   ```powershell
   cd "..\..\public-website\backend"
   Copy-Item .env.example .env
   ```
   *Edit `public-website/backend/.env` to verify:*
   - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/riskintel_public` *(update user/pass if needed)*
   - `JWT_SECRET_KEY=dev-secret-key-change-in-production-min-32-chars`
   - `REDIS_URL=memory://` *(Recommended for local dev: disables Redis probing and eliminates the `rate_limit_storage_fallback` timeout warning)*

---

### 📦 Step 3: Run Database Migrations & Seed Development Data

#### What are we doing?
Applying Alembic database schema migrations to PostgreSQL and seeding default test accounts and agent releases.

#### Why do this first?
The public website backend cannot query or save user accounts if the relational tables do not exist. Furthermore, local development does not send real confirmation emails; running `seed_dev.py` automatically creates verified test accounts (Admin, User, Unverified) and creates a downloadable placeholder agent artifact (`riskintel-1.0.0.tar.gz`).

#### Proper Commands:
From `Main/EndpointRiskAnalyzer/public-website/backend`:
```powershell
cd "public-website\backend"

# 1. Activate the Python virtual environment
.\venv\Scripts\activate
# (On macOS/Linux: source venv/bin/activate)

# 2. Run database migrations:
# If database is fresh/empty:
alembic upgrade head
# ⚠️ If tables already exist (e.g. relation "User" already exists from Prisma):
alembic stamp head

# 3. Seed development accounts and download artifact
python scripts/seed_dev.py
```

#### 🔑 Development Test Credentials:
| Role | Email | Password | Permissions |
|---|---|---|---|
| **Admin** | `admin@riskintel.io` | `Admin-Riskintel-2026!` | Full Admin Portal, Release Management, Logs |
| **Verified User** | `user@riskintel.io` | `User-Riskintel-2026!` | Release Downloads, Account Management |
| **Unverified User** | `unverified@riskintel.io` | `Unverified-Riskintel-2026!` | Limited access (pending verification state) |

---

### 🖥️ Step 4: Launch the Backend Services

#### What are we doing?
Starting the two FastAPI web servers:
1. **Core Posture Backend** on port `8000`
2. **Public Website Backend** on port `8080`

#### Why do this first?
All frontends (React dashboards) and background agents are clients. If you open a frontend before the backend is running, the dashboard displays network errors and WebSocket disconnection banners. If you start an agent before the backend is running, registration fails immediately.

#### Proper Commands:

#### ⚡ Terminal 1: Core Posture Backend (Port 8000)
> [!IMPORTANT]
> **Working Directory Notice:** Run this command from the `Main/EndpointRiskAnalyzer` root folder so Python can resolve all module packages (`backend.db.mongo`, `backend.routes`, `analysis`). If you run from inside `backend/` without adjusting `PYTHONPATH`, Python will throw `ModuleNotFoundError: No module named 'backend'`.

```powershell
# Navigate to the Main/EndpointRiskAnalyzer folder
cd "Main\EndpointRiskAnalyzer"

# Activate the Core Backend virtual environment
.\backend\venv\Scripts\activate

# Launch the FastAPI Core Backend
python -m uvicorn backend.db.main:app --reload --port 8000
```
- **API Documentation:** http://localhost:8000/docs
- **Health Check:** http://localhost:8000/health

#### ⚡ Terminal 2: Public Website Backend (Port 8080)
Open a new terminal window:
```powershell
# Navigate to the public-website/backend folder
cd "Main\EndpointRiskAnalyzer\public-website\backend"

# Activate the virtual environment
.\venv\Scripts\activate

# Launch the Public Website Backend
uvicorn app.main:app --reload --port 8080
```
- **API Documentation:** http://localhost:8080/docs
- **Liveness Probe:** http://localhost:8080/health/live
- **Readiness Probe:** http://localhost:8080/health/ready

---

### 🌐 Step 5: Launch the Frontend Applications

#### What are we doing?
Starting the web dashboards so administrators can inspect security posture and public users can interact with the product.

#### Why do this next?
Now that the backends are actively listening on ports `8000` and `8080`, the React client applications can connect to REST endpoints and establish live WebSocket channels without connection drops.

#### Proper Commands:

#### ⚡ Terminal 3: Core SOC Dashboard (Port 3000)
Open a new terminal window:
```powershell
cd "Main\EndpointRiskAnalyzer\frontend"

# Install node dependencies (first time only)
npm install

# Start the React dashboard
npm start
```
- **SOC Dashboard URL:** http://localhost:3000

#### ⚡ Terminal 4: Public Website Portal (Port 5173)
Open a new terminal window:
```powershell
cd "Main\EndpointRiskAnalyzer\public-website\frontend"

# Install node dependencies (first time only)
npm install

# Start the Vite development server
npm run dev
```
- **Public Portal URL:** http://localhost:5173

---

### 🛡️ Step 6: Run the Endpoint Monitoring Agent

#### What are we doing?
Running the Python monitoring agent on the endpoint (your workstation). The agent:
1. Generates or loads a persistent endpoint UUID (`.endpoint_id`).
2. Sends a cryptographic onboarding registration request with `X-Enrollment-Token` to the Core Backend (`POST /api/agent/register`).
3. Saves the received API key (`.api_key`).
4. Enters a background heartbeat and polling loop, awaiting scan commands.
5. When a scan is triggered from the React dashboard (or via schedule), the agent executes CIS checks, network exposure audits, and system posture diagnostics, sending the encrypted results to the backend.

#### Why do this last?
The agent is the consumer and data producer. It requires:
1. MongoDB to be active to store scan records.
2. The Core Backend to be listening on port `8000`.
3. The shared `ENROLLMENT_TOKEN` to match.
4. The React dashboard to be open so you can see the agent appear live and trigger scans!

#### Proper Commands:

#### ⚡ Terminal 5: Endpoint Agent
Open a new terminal window:
```powershell
cd "Main\EndpointRiskAnalyzer\agent"

# Activate the Agent virtual environment
.\venv\Scripts\activate

# Run the agent
python agent.py
```

#### ✅ Expected Agent Console Output:
```text
[*] Target Backend: http://localhost:8000
[+] Agent registered with backend
[+] Agent started for endpoint: YOUR-WORKSTATION-NAME
```

Now, navigate to your SOC Dashboard at **http://localhost:3000**:
- Your machine will appear in the **Active Endpoints** table!
- Click **"Run Scan"** or **"Scan All"** from the dashboard.
- The agent console will immediately log:
  ```text
  [+] Received RUN_SCAN job. Signature verified.
  [+] Scan successfully sent to backend
  ```
- The dashboard will dynamically refresh with live CIS compliance scores, ML anomaly ratings, and vulnerability breakdowns.

---

### 🔒 Step 7: (Optional) Start Nginx Reverse Proxy with TLS Pinning

#### What are we doing?
For production-grade simulations or strict TLS certificate pinning tests, traffic routes through Nginx on port `443` (HTTPS) and `wss://` (Secure WebSockets).

#### How to configure:
1. Generate or verify certificates in `infra/certs/dev.crt` and `infra/certs/dev.key`.
2. Update `backend/.env`:
   ```env
   ENFORCE_HTTPS=true
   ```
3. Update `agent/agent_config/.env`:
   ```env
   BACKEND_URL=https://localhost
   ```
4. Update `frontend/.env`:
   ```env
   REACT_APP_API_URL=https://localhost
   REACT_APP_WS_URL=wss://localhost/wss/dashboard
   ```
5. Start Nginx:
   ```bash
   # In WSL / Linux
   sudo cp infra/nginx/riskintel.dev.conf /etc/nginx/sites-available/
   sudo ln -s /etc/nginx/sites-available/riskintel.dev.conf /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo service nginx restart
   ```

---

## 🛠️ Common Troubleshooting & Gotchas

### 1. `ModuleNotFoundError: No module named 'backend'`
- **Cause:** You ran `uvicorn backend.db.main:app` from inside the `backend/` subdirectory.
- **Fix:** Either run from `Main/EndpointRiskAnalyzer`:
  ```powershell
  cd "Main\EndpointRiskAnalyzer"
  python -m uvicorn backend.db.main:app --reload --port 8000
  ```
  Or set `PYTHONPATH` to the parent folder before running:
  ```powershell
  $env:PYTHONPATH=".."
  python -m uvicorn backend.db.main:app --reload --port 8000
  ```

### 2. Agent Registration Fails (`401 Unauthorized` / `Enrollment token not set`)
- **Cause:** `ENROLLMENT_TOKEN` is missing or mismatched between `backend/.env` and `agent/agent_config/.env`.
- **Fix:** Open both files, set `ENROLLMENT_TOKEN` to the exact same string in both, delete `agent/.api_key` and `agent/.endpoint_id` if re-registering, and restart the agent.

### 3. `RuntimeError: MongoDB connection failed`
- **Cause:** MongoDB is not running on `localhost:27017`.
- **Fix:** Start MongoDB via `net start MongoDB` or `docker compose up -d mongodb`.

### 4. Public Website "Database Unreachable" (`503 Service Unavailable`)
- **Cause:** PostgreSQL is not running on port `5432` or migrations were not run.
- **Fix:** Verify PostgreSQL is running (`net start postgresql-x64-17` or `docker compose up -d postgres`) and execute `alembic upgrade head` from `public-website/backend`.

### 5. `rate_limit_storage_fallback: detail=Redis unreachable (TimeoutError)`
- **Log message:**
  ```text
  [warning ] rate_limit_storage_fallback detail=Redis unreachable; rate limits will be enforced per process. reason=TimeoutError
  ```
- **What it means:** **This is a non-fatal warning, NOT a fatal crash.** The public backend probes for a Redis server on startup. When Redis is not running, it gracefully falls back to local in-memory rate limiting (`memory://`).
- **How to fix/eliminate the warning:**
  - **Option A (Instant Fix, No Redis needed):** In `public-website/backend/.env`, set:
    ```env
    REDIS_URL=memory://
    ```
    This skips the 1-second Redis timeout probe completely and runs cleanly without any warning.
  - **Option B (If you want Redis):** Start Redis before launching the backend:
    ```powershell
    docker run -d --name local-redis -p 6379:6379 redis:7
    ```

### 6. `DuplicateTableError: relation "User" already exists`
- **Cause:** PostgreSQL already contains the application tables (e.g. from Prisma), but Alembic's `alembic_version` tracking table was not initialized.
- **Fix:** Tell Alembic that the schema is already at head without trying to re-execute `CREATE TABLE`:
  ```powershell
  alembic stamp head
  ```

---

## 📄 License & Terms

This project is source-available software intended for educational, research, and non-commercial purposes.
Commercial usage, resale, managed hosting, or redistribution is prohibited without explicit permission.
See `LICENSE` and `TERMS.md` for details.

