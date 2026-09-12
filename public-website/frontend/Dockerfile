# ══════════════════════════════════════════════════════════════════════════════
# RiskIntel Public Website Frontend — production image
#
# Multi-stage: Node builds the bundle, nginx serves it. The Node toolchain,
# node_modules and source never reach the runtime image, which is why the
# result is ~50 MB rather than ~1 GB and has almost no attack surface.
# ══════════════════════════════════════════════════════════════════════════════

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /build

# Lockfile first so dependency installation is cached independently of source.
COPY package.json package-lock.json ./

# `npm ci` installs exactly what the lockfile pins — a build cannot silently
# pick up a different version of a dependency than the one that was reviewed.
RUN npm ci

COPY . .

# Build-time configuration.
#
# These are Vite variables, which means they are INLINED INTO THE BUNDLE and are
# public. Only values that are safe to publish may be passed here. A real secret
# given as a build arg would be readable in the image layers and in the shipped
# JavaScript, so nothing secret is ever accepted at this boundary.
#
# VITE_API_BASE_URL is normally left empty: the frontend then calls the current
# origin and nginx proxies /api to the backend, which removes the CORS surface
# entirely.
ARG VITE_API_BASE_URL=""
ARG VITE_SITE_URL=""
ARG VITE_API_TIMEOUT_MS="15000"
ARG VITE_SUPPORT_EMAIL=""

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL \
    VITE_SITE_URL=$VITE_SITE_URL \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS \
    VITE_SUPPORT_EMAIL=$VITE_SUPPORT_EMAIL

# `npm run build` runs tsc first, so a type error fails the image build rather
# than shipping.
RUN npm run build


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# The nginx image ships a default site that would otherwise be served if our
# config failed to load. Removing it means a broken config fails loudly.
RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
# Included by every location block — see the note in the file itself.
COPY nginx/security-headers.conf /etc/nginx/security-headers.conf

# ── Run unprivileged ─────────────────────────────────────────────────────────
# The stock image runs its master process as root. Here nginx runs wholly as
# uid 101, which needs its pid file and temp paths moved somewhere that user can
# write, and the listen port raised above 1024 since unprivileged processes
# cannot bind low ports.
RUN mkdir -p /var/cache/nginx /var/run/nginx /etc/nginx/templates \
    && chown -R nginx:nginx /var/cache/nginx /var/run/nginx /usr/share/nginx/html /etc/nginx

USER nginx

# 8080, not 80: an unprivileged process cannot bind a privileged port.
EXPOSE 8080

# `wget` ships with alpine; no extra package is installed just to health-check.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

# The base image's entrypoint expands /etc/nginx/templates/*.template with the
# environment, which is how BACKEND_ORIGIN reaches the proxy_pass directive
# without baking a hostname into the image.
ENV BACKEND_ORIGIN="http://website-backend:8080"
