# ══════════════════════════════════════════════════════════════════════════════
# Schema migration image
#
# Prisma owns this schema (see docker-compose.prod.yml). This image exists so
# migrations can run without the migration container needing internet access.
#
# WHY BAKE THE TOOL IN
# The first attempt fetched Prisma with `npx` at container start. That failed,
# and the failure was the design telling us something: the migration container
# sits on an `internal: true` network with no route off the host, because the
# thing that talks to the database should not also be able to reach the
# internet. Granting it egress to fix the download would have widened the blast
# radius of a compromised migration step to satisfy a build-time convenience.
#
# It is also a supply-chain question (OWASP A08). Fetching a tool at deploy time
# means the deploy depends on a third-party registry being up and serving the
# same bytes it served yesterday. Pinning the version into an image makes the
# tool an artefact that is built once, scanned, and promoted like any other.
# ══════════════════════════════════════════════════════════════════════════════

FROM node:22-alpine

# Pinned to the version in package-lock.json. A floating migration tool can
# change behaviour between two deploys of otherwise identical code.
ARG PRISMA_VERSION=6.19.3

WORKDIR /work

# `--no-save` keeps the install to exactly this package; nothing writes a
# manifest that a later build could drift from.
RUN npm install --global --no-fund --no-audit "prisma@${PRISMA_VERSION}" \
    && npm cache clean --force

# The schema and its committed migrations. Nothing else from the repository is
# needed, and nothing else is copied.
COPY schema.prisma ./prisma/schema.prisma
COPY migrations ./prisma/migrations

# Warm the query-engine download at build time so the container needs no
# network at all when it runs.
RUN prisma version --schema=./prisma/schema.prisma || true

# ── Run unprivileged ─────────────────────────────────────────────────────────
# This container holds credentials for a database containing real accounts. It
# has no reason to be root, and the node image ships a suitable user already.
RUN chown -R node:node /work
USER node

# `migrate deploy` applies committed migrations only. It never generates a
# migration and never resets — the two operations that must not be possible
# against a database holding real accounts.
#
# DB_URL is supplied by the orchestrator at run time and is never baked in.
# The schema declares env("DB_URL"), not DATABASE_URL; using the wrong name
# fails with Prisma error P1012.
CMD ["prisma", "migrate", "deploy", "--schema=/work/prisma/schema.prisma"]
