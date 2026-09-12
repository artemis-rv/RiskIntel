# RiskIntel Public Website — Deployment

How the public website is built, deployed, operated and recovered.

Two surfaces exist in this repository and they stay separate:

| Surface | Location | Stack | Audience |
| --- | --- | --- | --- |
| **Public website** | `public-website/` | React SPA on Vercel → FastAPI on Render → PostgreSQL | anyone; accounts; downloads |
| **Internal console** | repo root (`frontend/`, `backend/`, `infra/`) | React → FastAPI → MongoDB | operators, on their own network |

This document covers the public website. The internal console has its own
`docker-compose.yml` at the repository root and is not touched by anything here.

---

## Contents

- [Status](#status)
- [Architecture](#architecture)
- [Platform choice](#platform-choice)
- [What the split origin costs](#what-the-split-origin-costs)
- [Release artefact storage](#release-artefact-storage)
- [Deploying the frontend to Vercel](#deploying-the-frontend-to-vercel)
- [Deploying the backend to Render](#deploying-the-backend-to-render)
- [Migrations](#migrations)
- [Publishing a release](#publishing-a-release)
- [Backups and restore](#backups-and-restore)
- [Local production stack](#local-production-stack)
- [Security posture](#security-posture)
- [Verification](#verification)
- [Load testing](#load-testing)
- [Future scaling](#future-scaling)

---

## Status

**Configured and verified locally; not yet deployed.** Every artefact needed to
deploy is in this repository and has been exercised as far as it can be without
a live environment:

| | State |
| --- | --- |
| Frontend build + SPA routing + CSP/env guards | verified locally |
| Backend image, config, migrations | verified locally; 136 backend tests pass |
| `render.yaml` blueprint | written, **not applied** |
| Vercel project | **not created** — applied from the dashboard by the account owner |
| Production E2E against the live system | **not run** (no deployment exists) |
| Load testing (Phase 8) | **not run** (same reason); harness ready, see below |

The two things blocking deployment are account-level, not technical:

1. **Vercel** — the CLI in the working environment is logged out and cannot run
   an interactive login. The frontend is therefore applied through the Vercel
   dashboard by the account owner, using the steps below.
2. **Render** — the blueprint requires paid plans (Starter is the cheapest plan
   a persistent disk can attach to, plus a `basic-256mb` database), so applying
   it is a spending decision for the account owner.

Nothing below has been tested against a live deployment. Where a step has not
been run, it says so rather than implying it has.

---

## Architecture

```
   Browser
      │
      ├── HTTPS ──► Vercel  ── static SPA, CDN, security headers, SPA fallback
      │                          (public-website/frontend/vercel.json)
      │
      └── HTTPS ──► Render  ── FastAPI
                     │            authn → authz → email verified →
                     │            release valid → record → stream
                     │
        ┌────────────┼───────────────┬──────────────────┐
        │            │               │                  │
   PostgreSQL     Key Value      Persistent disk    (SMTP, outbound)
   managed,       rate limits,   /data/releases
   no public      refresh        mounted read-only
   ingress        tokens         to the API
                                       │
                                   agent.exe
```

The SPA and the API are **different origins**. The browser talks to each
directly; Vercel does not proxy the API. That is a deliberate change from the
previous same-origin nginx arrangement and it has consequences — see below.

---

## Platform choice

The deciding requirement is **persistent storage for release artefacts**. The
artefact must survive container replacement and must never be a static asset.

| | Docker | Postgres | Persistent disk | HTTPS | Secrets | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **Vercel** | no backend | external only | **no** — functions get ephemeral `/tmp` | yes | yes | **Frontend only.** |
| **Railway** | yes | managed | volumes | yes | yes | Close second. Backups less turnkey. |
| **Render** | yes | managed, daily backups + PITR | **disks** | yes | yes | **Chosen for the API.** |

Vercel serves the SPA because the build output is plain static files and a CDN
serves them faster and cheaper than an nginx instance. It cannot host the API,
because a function's filesystem does not survive the request.

Cost note: a persistent disk requires the Starter plan for the API service. The
Vercel project is on the free tier and Render's key-value store is on its free
tier.

---

## What the split origin costs

The previous design put the SPA and the API on one origin behind nginx, which
removed CORS entirely. Splitting them re-introduces four things that must now be
kept in agreement, and every one of them fails **silently** — the deploy
succeeds and the site looks fine until a user tries something.

| Setting | Where | Must equal |
| --- | --- | --- |
| `VITE_API_BASE_URL` | Vercel env | the Render API origin |
| `connect-src` | `frontend/vercel.json` | the same origin, or the browser blocks every call |
| `CORS_ORIGINS` | Render env | the Vercel site origin, exactly, as a JSON array |
| `VITE_SITE_URL` | Vercel env | the Vercel site origin (canonical URLs, `og:url`, sitemap) |

Three of these are now enforced at build time by
`frontend/scripts/check-deploy-env.mjs`, which runs before every Vercel build and
**fails the build** if `VITE_API_BASE_URL` is absent from the CSP, is not https,
or if `VITE_SITE_URL` is missing from a deployed build. The fourth,
`CORS_ORIGINS`, lives on the other platform and cannot be checked from here; it
is the first thing to suspect if the site loads but nothing works.

The API takes no cookies — it authenticates with a bearer token the client
attaches deliberately — so the cross-origin move does not introduce a CSRF
surface. `allow_credentials` remains true only because the origin list is an
explicit allowlist; the code refuses to combine it with a wildcard
(`app/main.py`).

**Preview deployments are not allowed through CORS.** Vercel gives every commit
its own origin, and adding a wildcard for them would let any preview — including
one built from an unreviewed branch — hold real credentials. Previews render,
but their API calls are refused. That is the intended behaviour.

---

## Release artefact storage

The rules, and how each is enforced:

| Rule | Enforcement |
| --- | --- |
| Not in the frontend bundle or on the CDN | the artefact is never in `frontend/public`; Vercel only ever receives `dist/`, which is built from source that does not contain it |
| Not in ephemeral container storage | a Render disk mounted at `/data/releases`; `.dockerignore` excludes `storage/` so it can never be baked into an image |
| Not a public static URL | the only route to it is `GET /api/v1/downloads/{release_id}/file`, which authenticates, authorises, checks email verification and release status, applies the hourly limit, records the download, then streams |
| No path traversal | `app/services/storage.py` resolves every path and rejects anything landing outside the storage root, including via symlink |
| No filesystem-path disclosure | `ReleasePublicResponse` has no `file_path`; `Content-Disposition` is built from the release version, never the stored path |
| The API cannot modify it | the disk is mounted read-only to the API; publishing uses a separate one-shot process with write access |

On Render the mounted disk is already writable by the service user, so the
one-time `chown` needed for a fresh Docker volume does not apply.

---

## Deploying the frontend to Vercel

Applied from the dashboard. `public-website/frontend/vercel.json` describes the
build, the SPA fallback, the cache policy and every security header, so the only
dashboard input is the project root and the environment variables.

1. Vercel → **Add New… → Project** → import `artemis-rv/EndpointRiskAnalyzer`.
2. Set **Root Directory** to `public-website/frontend`. Leave framework
   detection on Vite; `vercel.json` supplies the build and output settings.
3. Add environment variables (Production, and Preview if you want previews to
   build):

   | Key | Value |
   | --- | --- |
   | `VITE_API_BASE_URL` | `https://<api-service>.onrender.com` — no trailing slash, no `/api/v1` |
   | `VITE_SITE_URL` | the site's own origin, e.g. `https://riskintel.vercel.app` |
   | `VITE_API_TIMEOUT_MS` | `15000` |
   | `VITE_SUPPORT_EMAIL` | the public support address |

   No secret may be set here. Everything prefixed `VITE_` is inlined into the
   JavaScript bundle and is readable by anyone who opens devtools.

4. **Before the first deploy**, set `connect-src` in `vercel.json` to the same
   API origin as `VITE_API_BASE_URL` and commit it. If they disagree the build
   fails with a message naming both — by design.
5. Deploy. Then confirm, on the deployed site:
   - a deep link (`/docs/security`) survives a hard refresh — SPA fallback,
   - `/robots.txt` and `/sitemap.xml` contain **absolute** URLs on the real
     domain — both are generated at build time from `VITE_SITE_URL`,
   - `view-source:` shows `og:image`, `og:url` and a canonical in the static
     head — link scrapers never run JavaScript, so runtime tags are invisible to
     them,
   - the response headers include the CSP and HSTS from `vercel.json`.

### What is generated rather than checked in

`robots.txt` and `sitemap.xml` are emitted during the build by the `seoAssets`
plugin in `vite.config.ts`, not stored in `public/`. Both require absolute URLs
— the sitemap protocol rejects a relative `<loc>`, and crawlers ignore a
relative `Sitemap:` line — and the origin is not known until deploy. The sitemap
is derived from the route table and the docs slugs, so a new article cannot be
added and then forgotten.

---

## Deploying the backend to Render

1. Push the repository to GitHub (Render builds from it).
2. Render → **Blueprints** → **New Blueprint Instance** → select the repo.
   `public-website/render.yaml` describes the API, the database and the
   key-value store.
3. Fill in the values marked `sync: false`:
   - `CORS_ORIGINS` — the Vercel site origin, **as a JSON array**:
     `["https://riskintel.vercel.app"]`. A bare URL fails at startup rather than
     being silently split.
   - `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM_ADDRESS`.
     Leaving them blank is supported — empty values are treated as unset — but
     registration then cannot deliver a verification email, and accounts must be
     verified with `manage_account.py`.
4. Apply migrations (below). They do not run automatically.
5. Create the first admin (below).
6. Publish a release (below).
7. Set `VITE_API_BASE_URL` and `connect-src` on the Vercel side to this
   service's real URL, and redeploy the frontend.

`JWT_SECRET_KEY` is generated by Render and never appears in the repository.
Rotating it invalidates every existing session, which is the intended effect.

### Settings that are load-bearing, and why

| Setting | Value | Why it is not something else |
| --- | --- | --- |
| `DATABASE_URL` | wired from the database | Render supplies `postgresql://…`, sometimes with `?sslmode=require`. SQLAlchemy reads the scheme as the driver and would select psycopg2, which is not installed. `app/core/config.py` rewrites it to `postgresql+asyncpg://` and translates `sslmode`, so the platform's string is pasted unedited. |
| `FORWARDED_ALLOW_IPS` | `10.0.0.0/8` | **Never `*`.** With `*`, uvicorn trusts the whole forwarded chain and takes its **leftmost** entry — which is whatever the client sent. Anyone could then choose the address the rate limiter counts against. A CIDR makes it walk the chain right-to-left and stop at the first address that is not Render's. |
| `TRUSTED_PROXIES` | `["10.0.0.0/8"]` | The application repeats the same derivation for its own rate-limit key and for the address written into the download audit trail. |
| `REDIS_URL` | wired from the key-value service | Shared state across workers: rate-limit counters **and** the set of issued refresh tokens. |
| `WEB_CONCURRENCY` | `2` | More than one worker is only correct **because** the store above is shared. With per-process storage, a refresh that lands on the other worker is answered "revoked" and the user is signed out at random. |

---

## Migrations

**Prisma owns this schema.** Both Prisma migrations are applied to the live
database and `alembic_version` does not exist. Alembic is retained only as a
mirror for environments that provision with it, and is **never** run on deploy —
two tools naming the same enum types differently is what produced the
`type "releasestatus" does not exist` failure fixed in Phase 6.12.

Migrations are applied deliberately, not on every deploy, because a rollback of
code does not roll back a schema.

```bash
# 1. Back up first. Always.
cd public-website/docker && ./backup.sh backup && ./backup.sh verify db-<stamp>.dump

# 2. Apply, using the pinned migration image.
docker build -t riskintel-migrate public-website/prisma
docker run --rm -e DB_URL="postgresql://user:pass@host:5432/db" riskintel-migrate
```

The schema declares `env("DB_URL")`, **not** `DATABASE_URL`. Both names are set
in the deployment: `DATABASE_URL` is what SQLAlchemy reads, `DB_URL` is the form
Prisma accepts. Using the wrong one fails with Prisma error `P1012`.

The migration image has the tool and the schema baked in, so it needs no
internet access and no npm registry availability at deploy time.

---

## Publishing a release

`agent.exe` reaches storage through the deployment channel, not over HTTP. There
is no upload endpoint, and there should not be: an internet-reachable path that
writes attacker-influenced bytes into the directory the download endpoint serves
from is the single most valuable target in the system.

On Render, run the script from the service's shell — that is where the disk is
mounted:

```bash
python scripts/publish_release.py \
  --file /data/releases/incoming/EndpointAgent.exe \
  --version 1.2.0 \
  --title "RiskIntel Endpoint Agent 1.2.0" \
  --notes-file /data/releases/incoming/RELEASE_NOTES.md \
  --publisher admin@example.com \
  --publish --latest
```

Locally, the same script runs in a one-shot container with the volume mounted
read-write:

```bash
cd public-website/docker
docker compose -f docker-compose.prod.yml -f docker-compose.admin.yml \
  --env-file .env run --rm website-publish \
  python scripts/publish_release.py --file /artefacts/EndpointAgent.exe ...
```

The script copies the file, then computes the checksum **from the copy**, so the
published checksum describes the bytes users will actually receive. It refuses
to write outside the storage root and refuses to attribute a release to a
non-admin.

### First admin

Roles are only grantable by an admin, so a fresh database cannot produce one.

```bash
python scripts/manage_account.py --email you@example.com --create --role ADMIN --verified
```

It prompts for the password rather than taking it as an argument, where it would
be visible in shell history and to `ps`. The same script can mark an address
verified when SMTP is unavailable.

---

## Backups and restore

Two things cannot be rebuilt from the repository: the database and the release
artefacts. Everything else is reproducible from git and the environment.

```bash
cd public-website/docker
./backup.sh backup                    # database dump + artefact archive
./backup.sh verify db-<stamp>.dump    # parse the dump; confirm it has table data
./backup.sh list
./backup.sh restore-db db-<stamp>.dump
./backup.sh restore-files releases-<stamp>.tar.gz
```

`verify` exists because a backup nobody has restored is a hypothesis. Run it as
part of taking the backup, not as part of the incident.

On Render, the managed database also takes daily backups with point-in-time
recovery. That covers the database; **it does not cover the disk**, so artefact
archives still matter.

Retention defaults to 14 days (`RETAIN_DAYS`).

---

## Local production stack

The Compose stack still exists and is still the way to exercise the real images
before promoting them. It runs the same backend image Render builds, with nginx
serving the SPA same-origin — so it verifies the API, the database, the
migration job and the download path, but **not** the cross-origin CORS
arrangement that only exists in the deployed topology.

```bash
cd public-website/docker
cp .env.example .env          # then fill it in — see the notes inside
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Two formats catch people out, because both settings are typed `List[str]` and
are JSON-decoded straight from the environment:

```bash
CORS_ORIGINS=["https://riskintel.example.com"]     # correct
CORS_ORIGINS=https://riskintel.example.com         # fails at startup
TRUSTED_PROXIES=["172.16.0.0/12"]
```

Generate every secret with real entropy, once, per environment:
`openssl rand -hex 32`.

---

## Security posture

| OWASP | Handling |
| --- | --- |
| **A01 Access control** | Every admin route is guarded by `require_admin` server-side. Frontend route guards are UX only. |
| **A02 Cryptographic failures** | Argon2id password hashing. Secrets only via environment; none in images, git or the bundle. TLS terminated at both edges; HSTS set on both. |
| **A03 Injection** | Parameterised queries throughout; admin search escapes LIKE metacharacters. CSP has no `unsafe-inline`/`unsafe-eval` in `script-src`. No HTML from any source is ever rendered. |
| **A04 Insecure design** | Publishing is a shell operation, not an endpoint. The API mounts storage read-only. Migrations are deliberate. |
| **A05 Misconfiguration** | Non-root container, `no-new-privileges`, read-only rootfs locally, FastAPI docs disabled in production, no source maps, resource limits. Build-time guards on the env/CSP agreement. |
| **A06 Vulnerable components** | Four runtime frontend dependencies; pinned base images; lockfile-driven builds; migration tool version pinned. |
| **A07 Authentication** | Rotating refresh tokens with single-use enforcement, short-lived access tokens, uniform failure messages, anti-enumeration on reset and resend. |
| **A08 Integrity** | Published SHA-256 per release, verified against the delivered bytes at request time. Migration tool baked in rather than fetched at deploy. |
| **A09 Logging** | No secret, token or password is logged anywhere. Download events are recorded with a spoofing-resistant client address. |
| **A10 SSRF** | No user input reaches a request destination. |
| **Path traversal** | Enforced in `storage.py` and covered by tests. |
| **Rate limiting** | Application-level, keyed on a client address derived from trusted-proxy rules, shared across workers through Redis. The edge nginx layer exists only in the self-hosted stack; on Render the application limiter is the only layer. |

### CSRF

The API takes no cookies (`credentials: 'omit'`) and authenticates purely with a
bearer token the client attaches deliberately. A cross-site form submission
carries no such header, so the classic CSRF path does not apply. If the
authentication scheme ever moves to cookies, CSRF protection becomes mandatory
at the same moment.

### Cookie consent

The site sets **no cookies**. The only persisted item is the refresh token in
`sessionStorage`, which is strictly necessary to keep a signed-in session and is
disclosed in the privacy policy. There is no analytics, advertising or
third-party tracking, so a consent banner is not required. Adding any analytics
tag changes that answer, and would also need a CSP amendment — `script-src` is
`'self'` only.

### Known limitations

- **`style-src 'unsafe-inline'`** — Tailwind emits inline styles. Removing it
  requires a nonce or hash pipeline in the build.
- **Google Fonts** — `index.html` loads Inter and JetBrains Mono from Google,
  which sends visitor IPs to a third party and adds two render-blocking
  round-trips. Self-hosting the two families would remove both concerns.
- **No analytics** — the site launches with no visibility into traffic,
  download-conversion or 404 rates. A deliberate trade for a zero-tracking
  posture, but it is a trade.
- **Soft 404s** — a static SPA returns HTTP 200 for unknown URLs. The 404 page
  is correct for humans; only the status code is wrong.

---

## Verification

### Local (run, passing)

- Backend: 136 tests, including 13 covering the deployment-specific behaviour
  (connection-string translation, refresh-token rotation and single use,
  forwarded-address derivation).
- Frontend: 87 tests; production build clean; CSP/env guard exercised in both
  its passing and failing directions.
- `deploy_verify.sh` runs 66 checks against the containerized stack through the
  nginx edge. Re-running it immediately will fail: the download endpoint allows
  five per release per hour per account, and the edge allows ten auth requests
  per minute. Both are the limits doing their job — allow ~70 seconds.

### Production (not run)

The end-to-end sequence below requires a live deployment and has **not** been
executed. It is the checklist to work through once the platforms are applied:

health → register → verify email → login → protected routes → admin routes →
releases → authenticated `agent.exe` download → checksum comparison against the
original binary → download history → feedback → contact → rate limiting →
authorization (403/401 for the wrong role) → security headers on both origins →
CORS (allowed origin succeeds, other origins refused) → path traversal → generic
error bodies → persistence across a restart and a redeploy.

Two of these deserve particular attention on first deploy, because they are the
ones the local stack cannot exercise:

- **CORS**, because the origins only differ in the deployed topology.
- **Disk persistence**, because a redeploy replaces the container: publish a
  release, redeploy, and confirm the artefact still downloads with the same
  checksum.

---

## Load testing

Harness: `public-website/scripts/loadtest.py` (Python + httpx, no external
tooling). It reports achieved RPS, success/error/timeout counts by status,
p50/p95/p99 latency, throughput, and — for download runs — whether each transfer
completed and matched the published checksum.

```bash
python scripts/loadtest.py --base-url https://<api>.onrender.com \
  --scenario health --levels 100,500,1000 --requests-per-level 2000 \
  --out loadtest-results/api-health.json
```

**Not yet run.** Points to settle before it is, so the numbers mean something:

- **The limits will be hit, and that is the point.** `RATE_LIMIT_DEFAULT` is
  100/minute per client address and auth is 10/minute. A load test from one
  address measures the rate limiter, not the application. Either test from many
  addresses, or raise the limit for a controlled window and say so in the
  results.
- **Downloads cannot be tested at high concurrency without a bandwidth budget.**
  The artefact is 19.5 MB; 10,000 downloads is 195 GB. The harness caps this
  (`--max-total-bytes`) and the application independently caps five downloads
  per release per hour per account, so a realistic download test needs many test
  accounts and a stated byte budget.
- **Expected first bottleneck: password hashing.** Argon2id at 64 MiB is
  intentionally expensive and runs synchronously inside the request handler, so
  it occupies the event loop. On a 0.5-CPU Starter instance, login throughput
  will be the first thing to fall over. The fix, if measurement confirms it, is
  to move hashing to a worker thread — not to weaken the parameters.
- **Database connections.** The pool is 10 + 20 overflow per worker; at
  `WEB_CONCURRENCY=2` that is up to 60 connections against a `basic-256mb`
  instance. Worth watching before raising either number.

Optimise only what measurement shows. Kubernetes, object storage and a CDN for
the artefact are all deliberately absent until there is evidence for them.

---

## Future scaling

What keeps the door open:

- **Storage.** `RELEASE_FILES_BASE_PATH` is read in exactly one module,
  `app/services/storage.py`. Moving to S3/R2 means reimplementing two functions
  behind the same signatures — no route, schema or frontend change. Downloads
  would become a redirect to a short-lived signed URL, which also removes the
  memory cost of streaming through the API.
- **Backend replicas.** The refresh-token store and the rate-limit counters are
  both in Redis, so the API is now horizontally scalable without signing people
  out. That was the prerequisite, and it is done.
- **CDN for the SPA.** Already the case — Vercel is a CDN, assets are
  content-hashed and cache headers are set.
- **Database.** Managed Postgres scales vertically first; read replicas only
  after measurement.

Measure before any of it. None are needed at current load, and each adds a
component that can fail on its own.
