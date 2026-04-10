#!/usr/bin/env bash
# ============================================================================
# VATéir Web System — Linux VM Deployment Script
# ============================================================================
# Installs and configures all services needed to run the application:
#   - PostgreSQL 17
#   - Redis
#   - Gunicorn (Django WSGI)
#   - Celery Worker
#   - Celery Beat
#   - Discord Bot
#
# Usage:
#   sudo bash deploy/install.sh
#
# Prerequisites:
#   - Ubuntu/Debian-based Linux VM
#   - Root or sudo access
#   - Git repo cloned to the target directory
#   - .env file configured (copy from .env.example)
# ============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override via environment or edit here
# ---------------------------------------------------------------------------
APP_NAME="${APP_NAME:-vateir}"
APP_USER="${APP_USER:-vateir}"
APP_DIR="${APP_DIR:-/opt/vateir}"
VENV_DIR="${APP_DIR}/.venv"
WORKERS="${GUNICORN_WORKERS:-3}"
BIND_ADDR="${BIND_ADDR:-0.0.0.0}"
BIND_PORT="${BIND_PORT:-8002}"
UV_HOME="/opt/uv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error() { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

check_root() {
    [[ $EUID -eq 0 ]] || error "This script must be run as root. Use: sudo DOMAIN=example.com bash $0"
}

# Re-read variables from command-line environment that sudo may have stripped.
# Usage: DOMAIN=ng.vatsim.ie sudo bash ./deploy/install.sh
#    or: sudo DOMAIN=ng.vatsim.ie bash ./deploy/install.sh
parse_env_args() {
    for arg in "$@"; do
        if [[ "${arg}" =~ ^([A-Z_]+)=(.+)$ ]]; then
            export "${BASH_REMATCH[1]}"="${BASH_REMATCH[2]}"
        fi
    done
}

# ---------------------------------------------------------------------------
# 1. System packages
# ---------------------------------------------------------------------------
install_system_packages() {
    info "Installing system packages..."
    apt-get update -qq
    apt-get install -y -qq \
        curl \
        build-essential \
        libpq-dev \
        nodejs \
        npm \
        redis-server \
        postgresql \
        postgresql-contrib

    # Install uv
    if ! command -v uv &>/dev/null; then
        info "Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="${UV_HOME}" sh
    fi
    export PATH="${UV_HOME}:${PATH}"

    # Store uv-managed Python installations in a shared location (not /root)
    export UV_PYTHON_INSTALL_DIR="/opt/uv/python"
    mkdir -p "${UV_PYTHON_INSTALL_DIR}"
}

# ---------------------------------------------------------------------------
# 2. Service user
# ---------------------------------------------------------------------------
create_service_user() {
    if id "${APP_USER}" &>/dev/null; then
        info "User '${APP_USER}' already exists."
    else
        info "Creating service user '${APP_USER}'..."
        useradd --system --shell /usr/sbin/nologin --home-dir "${APP_DIR}" "${APP_USER}"
    fi
}

# ---------------------------------------------------------------------------
# 3. Application directory & virtualenv
# ---------------------------------------------------------------------------
prepare_application() {
    info "Setting up application directory..."

    if [[ ! -d "${APP_DIR}" ]]; then
        mkdir -p "${APP_DIR}"
    fi

    # Copy project files if running from a different directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [[ "${SCRIPT_DIR}" != "${APP_DIR}" ]]; then
        info "Copying project files to ${APP_DIR}..."
        rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='.git' \
            "${SCRIPT_DIR}/" "${APP_DIR}/"
    fi

    # Ensure .env exists
    if [[ ! -f "${APP_DIR}/.env" ]]; then
        if [[ -f "${APP_DIR}/.env.example" ]]; then
            cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
            warn ".env created from .env.example — edit it with real values before starting services!"
        else
            error "No .env or .env.example found in ${APP_DIR}"
        fi
    fi

    info "Installing Python and project dependencies via uv..."
    cd "${APP_DIR}"
    uv sync
    uv pip install gunicorn
}

setup_django() {
    info "Running Django setup commands..."
    cd "${APP_DIR}"

    info "Building Tailwind CSS..."
    uv run python manage.py tailwind install --no-input
    uv run python manage.py tailwind build

    uv run python manage.py collectstatic --noinput
    uv run python manage.py migrate --noinput

    chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
}

# ---------------------------------------------------------------------------
# 4. PostgreSQL database
# ---------------------------------------------------------------------------
setup_database() {
    info "Configuring PostgreSQL..."
    systemctl enable --now postgresql

    # Source .env to get DATABASE_URL
    local db_url
    db_url=$(grep '^DATABASE_URL=' "${APP_DIR}/.env" | cut -d= -f2-)

    # Parse DATABASE_URL: postgres://user[:password]@host[:port]/dbname
    local db_user db_pass db_name
    db_user=$(echo "${db_url}" | sed -n 's|postgres://\([^:@]*\)[@:].*|\1|p')
    db_pass=$(echo "${db_url}" | sed -n 's|postgres://[^:]*:\([^@]*\)@.*|\1|p')
    db_name=$(echo "${db_url}" | sed -n 's|.*/\([^?]*\).*|\1|p')

    if [[ -z "${db_user}" || -z "${db_name}" ]]; then
        warn "Could not parse DATABASE_URL — skipping database creation."
        warn "Create the database manually: createdb ${APP_NAME}"
        return
    fi

    local create_role
    if [[ -n "${db_pass}" ]]; then
        create_role="CREATE ROLE ${db_user} WITH LOGIN PASSWORD '${db_pass}';"
    else
        create_role="CREATE ROLE ${db_user} WITH LOGIN;"
    fi

    info "Creating database '${db_name}' and user '${db_user}'..."
    sudo -u postgres psql -v ON_ERROR_STOP=0 <<SQL || true
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${db_user}') THEN
        ${create_role}
    END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${db_name} OWNER ${db_user}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db_name}')\gexec
GRANT ALL PRIVILEGES ON DATABASE ${db_name} TO ${db_user};
SQL
}

# ---------------------------------------------------------------------------
# 5. Redis
# ---------------------------------------------------------------------------
setup_redis() {
    info "Enabling Redis..."
    systemctl enable --now redis-server
}

# ---------------------------------------------------------------------------
# 6. Systemd service files
# ---------------------------------------------------------------------------
install_systemd_services() {
    info "Installing systemd service files..."

    local env_file="${APP_DIR}/.env"
    local uv_bin="${UV_HOME}/uv"

    # --- Gunicorn (Django) ---
    cat > /etc/systemd/system/${APP_NAME}-web.service <<EOF
[Unit]
Description=VATéir Gunicorn Web Server
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=notify
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${env_file}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${uv_bin} run gunicorn config.wsgi:application \\
    --bind ${BIND_ADDR}:${BIND_PORT} \\
    --workers ${WORKERS} \\
    --timeout 120 \\
    --access-logfile - \\
    --error-logfile -
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF

    # --- Celery Worker ---
    cat > /etc/systemd/system/${APP_NAME}-celery-worker.service <<EOF
[Unit]
Description=VATéir Celery Worker
After=network.target postgresql.service redis-server.service
Requires=redis-server.service

[Service]
Type=forking
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${env_file}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${uv_bin} run celery -A config multi start worker \\
    --loglevel=info \\
    --concurrency=4 \\
    --pidfile=/run/${APP_NAME}/celery-worker.pid \\
    --logfile=/var/log/${APP_NAME}/celery-worker.log
ExecStop=${uv_bin} run celery -A config multi stopwait worker \\
    --pidfile=/run/${APP_NAME}/celery-worker.pid
ExecReload=${uv_bin} run celery -A config multi restart worker \\
    --loglevel=info \\
    --concurrency=4 \\
    --pidfile=/run/${APP_NAME}/celery-worker.pid \\
    --logfile=/var/log/${APP_NAME}/celery-worker.log
Restart=on-failure
RestartSec=10

RuntimeDirectory=${APP_NAME}
RuntimeDirectoryMode=0755
LogsDirectory=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF

    # --- Celery Beat ---
    cat > /etc/systemd/system/${APP_NAME}-celery-beat.service <<EOF
[Unit]
Description=VATéir Celery Beat Scheduler
After=network.target postgresql.service redis-server.service
Requires=redis-server.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${env_file}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${uv_bin} run celery -A config beat \\
    --loglevel=info \\
    --scheduler django_celery_beat.schedulers:DatabaseScheduler \\
    --pidfile=/run/${APP_NAME}/celery-beat.pid
Restart=on-failure
RestartSec=10

RuntimeDirectory=${APP_NAME}
RuntimeDirectoryMode=0755
LogsDirectory=${APP_NAME}

[Install]
WantedBy=multi-user.target
EOF

    # --- Discord Bot ---
    cat > /etc/systemd/system/${APP_NAME}-discord-bot.service <<EOF
[Unit]
Description=VATéir Discord Bot
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${env_file}
Environment="DJANGO_SETTINGS_MODULE=config.settings.production"
ExecStart=${uv_bin} run python manage.py runbot
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
EOF

    # --- Target to group all services ---
    cat > /etc/systemd/system/${APP_NAME}.target <<EOF
[Unit]
Description=VATéir All Services
Wants=${APP_NAME}-web.service
Wants=${APP_NAME}-celery-worker.service
Wants=${APP_NAME}-celery-beat.service
Wants=${APP_NAME}-discord-bot.service

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
}

# ---------------------------------------------------------------------------
# 7. Enable & start services
# ---------------------------------------------------------------------------
enable_services() {
    info "Enabling and starting services..."

    systemctl enable ${APP_NAME}.target
    systemctl enable ${APP_NAME}-web.service
    systemctl enable ${APP_NAME}-celery-worker.service
    systemctl enable ${APP_NAME}-celery-beat.service
    systemctl enable ${APP_NAME}-discord-bot.service

    systemctl start ${APP_NAME}-web.service
    systemctl start ${APP_NAME}-celery-worker.service
    systemctl start ${APP_NAME}-celery-beat.service
    systemctl start ${APP_NAME}-discord-bot.service
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    parse_env_args "$@"
    check_root

    # Re-apply defaults after parsing args (so CLI overrides take effect)
    APP_NAME="${APP_NAME:-vateir}"
    APP_USER="${APP_USER:-vateir}"
    APP_DIR="${APP_DIR:-/opt/vateir}"
    VENV_DIR="${APP_DIR}/.venv"
    WORKERS="${GUNICORN_WORKERS:-3}"
    BIND_ADDR="${BIND_ADDR:-0.0.0.0}"
    BIND_PORT="${BIND_PORT:-8002}"
    UV_HOME="${UV_HOME:-/opt/uv}"

    info "=== VATéir Deployment Starting ==="
    echo ""
    info "App name:    ${APP_NAME}"
    info "App user:    ${APP_USER}"
    info "App dir:     ${APP_DIR}"
    info "Bind:        ${BIND_ADDR}:${BIND_PORT}"
    echo ""

    install_system_packages
    create_service_user
    prepare_application
    setup_database
    setup_redis
    setup_django
    install_systemd_services
    enable_services

    echo ""
    info "=== Deployment Complete ==="
    echo ""
    info "Services installed:"
    info "  ${APP_NAME}-web.service            — Gunicorn (Django)"
    info "  ${APP_NAME}-celery-worker.service   — Celery task worker"
    info "  ${APP_NAME}-celery-beat.service     — Celery beat scheduler"
    info "  ${APP_NAME}-discord-bot.service     — Discord bot"
    info "  ${APP_NAME}.target                  — Group target for all services"
    echo ""
    info "Useful commands:"
    info "  systemctl status ${APP_NAME}-web"
    info "  systemctl restart ${APP_NAME}.target          # restart everything"
    info "  journalctl -u ${APP_NAME}-celery-worker -f    # tail worker logs"
    info "  journalctl -u ${APP_NAME}-web -f              # tail web logs"
    info "  Gunicorn listening on ${BIND_ADDR}:${BIND_PORT}"
}

main "$@"
