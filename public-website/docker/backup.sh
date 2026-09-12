#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# RiskIntel Public Website — backup and restore
#
# Covers the two things that cannot be rebuilt from the repository:
#   1. the PostgreSQL database
#   2. the release artefacts on the persistent volume
#
# Everything else — images, configuration, code — is reproducible from git and
# the environment, so it is not backed up here.
#
#   ./backup.sh backup            take a backup of both
#   ./backup.sh restore-db FILE   restore the database from a dump
#   ./backup.sh restore-files TAR restore release artefacts
#   ./backup.sh verify FILE       check a dump is readable and non-trivial
#   ./backup.sh list              show what is stored
#
# A backup nobody has restored is a hypothesis, not a backup. `verify` exists so
# the hypothesis gets tested before it matters.
# ══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RETAIN_DAYS="${RETAIN_DAYS:-14}"

compose() { docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"; }

die() { echo "error: $*" >&2; exit 1; }

# The database credentials are read from the env file rather than passed on the
# command line: an argument is visible in `ps` to every user on the host.
load_env() {
  [ -f "$ENV_FILE" ] || die "missing $ENV_FILE"
  set -a; . "./$ENV_FILE"; set +a
  : "${POSTGRES_USER:?POSTGRES_USER not set}"
  : "${POSTGRES_DB:?POSTGRES_DB not set}"
}

do_backup() {
  load_env
  echo "── database ──"
  # --format=custom supports selective restore and is compressed.
  # PGPASSWORD is passed through the environment, never as an argument.
  compose exec -T \
    -e PGPASSWORD="$POSTGRES_PASSWORD" \
    website-postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner \
    > "db-${STAMP}.dump"

  local size
  size=$(wc -c < "db-${STAMP}.dump")
  [ "$size" -gt 1024 ] || die "dump is implausibly small (${size} bytes) — treating as failed"
  echo "   db-${STAMP}.dump (${size} bytes)"

  echo "── release artefacts ──"
  # Streamed out of a throwaway container that mounts the volume read-only.
  # Nothing writes to the volume during a backup.
  docker run --rm \
    -v riskintel-public_release_files:/data:ro \
    -v "$(pwd)":/backup \
    alpine:3.20 \
    tar czf "/backup/releases-${STAMP}.tar.gz" -C /data .

  echo "   releases-${STAMP}.tar.gz"

  echo "── pruning backups older than ${RETAIN_DAYS} days ──"
  find . -maxdepth 1 -name 'db-*.dump'          -mtime "+${RETAIN_DAYS}" -print -delete || true
  find . -maxdepth 1 -name 'releases-*.tar.gz'  -mtime "+${RETAIN_DAYS}" -print -delete || true

  echo
  echo "Backup complete. Verify it before relying on it:"
  echo "   ./backup.sh verify db-${STAMP}.dump"
}

do_verify() {
  local file="${1:?usage: backup.sh verify FILE}"
  load_env
  [ -f "$file" ] || die "no such file: $file"

  echo "── listing dump contents ──"
  # pg_restore --list parses the archive without touching any database. If the
  # dump is truncated or corrupt this is where it shows.
  compose exec -T website-postgres pg_restore --list < "$file" | head -25
  echo
  local tables
  tables=$(compose exec -T website-postgres pg_restore --list < "$file" | grep -c 'TABLE DATA' || true)
  echo "tables with data in dump: ${tables}"
  [ "$tables" -ge 1 ] || die "dump contains no table data"
  echo "dump is readable."
}

do_restore_db() {
  local file="${1:?usage: backup.sh restore-db FILE}"
  load_env
  [ -f "$file" ] || die "no such file: $file"

  cat <<WARN

  This REPLACES the contents of database '${POSTGRES_DB}'.
  Current data will be dropped. Take a fresh backup first if you have not.

WARN
  read -r -p "Type the database name to confirm: " confirm
  [ "$confirm" = "$POSTGRES_DB" ] || die "confirmation did not match; nothing changed"

  # Stop the API first so nothing writes mid-restore and no request sees a
  # half-restored schema.
  echo "── stopping backend ──"
  compose stop website-backend

  echo "── restoring ──"
  compose exec -T \
    -e PGPASSWORD="$POSTGRES_PASSWORD" \
    website-postgres \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner \
    < "$file"

  echo "── starting backend ──"
  compose start website-backend
  echo "Restore complete. Check /health/ready before announcing recovery."
}

do_restore_files() {
  local file="${1:?usage: backup.sh restore-files TAR}"
  [ -f "$file" ] || die "no such file: $file"

  read -r -p "Replace release artefacts from ${file}? [y/N] " confirm
  [ "$confirm" = "y" ] || die "cancelled"

  docker run --rm \
    -v riskintel-public_release_files:/data \
    -v "$(pwd)":/backup:ro \
    alpine:3.20 \
    sh -c "rm -rf /data/* && tar xzf /backup/$(basename "$file") -C /data"

  echo "Artefacts restored. Their checksums must still match the Release rows;"
  echo "the download endpoint refuses to serve a file whose size disagrees."
}

do_list() {
  echo "── database dumps ──";     ls -lh db-*.dump 2>/dev/null || echo "   none"
  echo "── artefact archives ──";  ls -lh releases-*.tar.gz 2>/dev/null || echo "   none"
}

case "${1:-}" in
  backup)         do_backup ;;
  verify)         do_verify "${2:-}" ;;
  restore-db)     do_restore_db "${2:-}" ;;
  restore-files)  do_restore_files "${2:-}" ;;
  list)           do_list ;;
  *)
    grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -20
    exit 1
    ;;
esac
