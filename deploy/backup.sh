#!/usr/bin/env bash
# ============================================================================
# VATéir — PostgreSQL backup to DigitalOcean Spaces
# ============================================================================
# Dumps the database, gzips it, uploads to Spaces, and cleans up old backups.
#
# Usage:
#   bash deploy/backup.sh
#
# Cron (daily at 04:00 UTC):
#   0 4 * * * /opt/vateir/deploy/backup.sh >> /var/log/vateir/backup.log 2>&1
#
# Requires:
#   - pg_dump
#   - aws cli (s3-compatible) or s3cmd
#   - .env with DATABASE_URL and DO_SPACES_* variables
# ============================================================================

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/vateir}"
KEEP_DAYS="${KEEP_DAYS:-30}"
BACKUP_DIR="/tmp/vateir-backups"
TIMESTAMP="$(date -u +%Y%m%d-%H%M%S)"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] INFO  $*"; }
error() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Load config from .env
# ---------------------------------------------------------------------------
ENV_FILE="${APP_DIR}/.env"
[[ -f "${ENV_FILE}" ]] || error ".env not found at ${ENV_FILE}"

load_env() {
    local key value
    while IFS='=' read -r key value; do
        [[ -z "${key}" || "${key}" =~ ^# ]] && continue
        export "${key}=${value}"
    done < "${ENV_FILE}"
}
load_env

# Validate required vars
[[ -n "${DATABASE_URL:-}" ]]     || error "DATABASE_URL not set in .env"
[[ -n "${DO_SPACES_KEY:-}" ]]    || error "DO_SPACES_KEY not set in .env"
[[ -n "${DO_SPACES_SECRET:-}" ]] || error "DO_SPACES_SECRET not set in .env"
[[ -n "${DO_SPACES_BUCKET:-}" ]] || error "DO_SPACES_BUCKET not set in .env"
[[ -n "${DO_SPACES_REGION:-}" ]] || error "DO_SPACES_REGION not set in .env"

# Parse DATABASE_URL: postgres://user:password@host:port/dbname
DB_USER="$(echo "${DATABASE_URL}" | sed -n 's|postgres://\([^:]*\):.*|\1|p')"
DB_PASS="$(echo "${DATABASE_URL}" | sed -n 's|postgres://[^:]*:\([^@]*\)@.*|\1|p')"
DB_HOST="$(echo "${DATABASE_URL}" | sed -n 's|.*@\([^:]*\):.*|\1|p')"
DB_PORT="$(echo "${DATABASE_URL}" | sed -n 's|.*:\([0-9]*\)/.*|\1|p')"
DB_NAME="$(echo "${DATABASE_URL}" | sed -n 's|.*/\([^?]*\).*|\1|p')"

SPACES_ENDPOINT="https://${DO_SPACES_REGION}.digitaloceanspaces.com"
SPACES_PATH="s3://${DO_SPACES_BUCKET}/backups/postgres"
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}-${TIMESTAMP}.sql.gz"

# ---------------------------------------------------------------------------
# AWS CLI config (S3-compatible)
# ---------------------------------------------------------------------------
export AWS_ACCESS_KEY_ID="${DO_SPACES_KEY}"
export AWS_SECRET_ACCESS_KEY="${DO_SPACES_SECRET}"
export AWS_DEFAULT_REGION="${DO_SPACES_REGION}"

s3() {
    aws s3 --endpoint-url "${SPACES_ENDPOINT}" "$@"
}

# ---------------------------------------------------------------------------
# Dump, compress, upload
# ---------------------------------------------------------------------------
mkdir -p "${BACKUP_DIR}"

info "Dumping ${DB_NAME}..."
export PGPASSWORD="${DB_PASS}"
pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DB_NAME}" \
    --no-owner --no-acl | gzip > "${BACKUP_FILE}"
unset PGPASSWORD

FILESIZE="$(du -h "${BACKUP_FILE}" | cut -f1)"
info "Compressed backup: ${FILESIZE}"

info "Uploading to ${SPACES_PATH}/..."
s3 cp "${BACKUP_FILE}" "${SPACES_PATH}/" --quiet

info "Upload complete."

# ---------------------------------------------------------------------------
# Clean up local file
# ---------------------------------------------------------------------------
rm -f "${BACKUP_FILE}"

# ---------------------------------------------------------------------------
# Prune old backups (older than KEEP_DAYS)
# ---------------------------------------------------------------------------
if [[ "${KEEP_DAYS}" -gt 0 ]]; then
    info "Pruning backups older than ${KEEP_DAYS} days..."
    CUTOFF="$(date -u -d "${KEEP_DAYS} days ago" +%Y%m%d)"

    s3 ls "${SPACES_PATH}/" | while read -r line; do
        filename="$(echo "${line}" | awk '{print $4}')"
        [[ -z "${filename}" ]] && continue

        # Extract date from filename: dbname-YYYYMMDD-HHMMSS.sql.gz
        file_date="$(echo "${filename}" | grep -oP '\d{8}(?=-\d{6}\.sql\.gz$)')" || continue
        [[ -z "${file_date}" ]] && continue

        if [[ "${file_date}" < "${CUTOFF}" ]]; then
            info "  Deleting ${filename}"
            s3 rm "${SPACES_PATH}/${filename}" --quiet
        fi
    done
fi

info "Backup complete: ${DB_NAME}-${TIMESTAMP}.sql.gz"
