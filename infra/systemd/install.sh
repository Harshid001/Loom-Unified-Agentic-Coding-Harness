#!/usr/bin/env bash
# Loom native deployment — systemd + Postgres + Redis + Nginx (no Docker).
# Run as root on a Debian/Ubuntu host:
#   sudo bash infra/systemd/install.sh /opt/loom
set -euo pipefail

LOOM_DIR="${1:-/opt/loom}"
LOOM_USER="loom"
LOOM_ENV_FILE="/etc/loom/loom.env"
DASHBOARD_ENV_FILE="/etc/loom/dashboard.env"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

log() { echo -e "\n\033[1;32m[loom]\033[0m $*"; }
warn() { echo -e "\n\033[1;33m[loom]\033[0m WARNING: $*"; }

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash $0" >&2
    exit 1
fi

log "Installing system packages (python3, postgresql, redis, nginx, nodejs)..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    nodejs npm \
    git curl openssl ca-certificates >/dev/null

log "Creating system user '${LOOM_USER}'..."
if ! id -u "$LOOM_USER" >/dev/null 2>&1; then
    useradd --create-home --shell /bin/bash "$LOOM_USER"
fi

log "Deploying application code to ${LOOM_DIR}..."
install -d -o "$LOOM_USER" -g "$LOOM_USER" "$LOOM_DIR"
cp -a "$REPO_ROOT"/. "$LOOM_DIR"/
chown -R "$LOOM_USER:$LOOM_USER" "$LOOM_DIR"

log "Creating shared directories..."
install -d -o "$LOOM_USER" -g "$LOOM_USER" /var/repos /var/lib/loom
install -d -o "$LOOM_USER" -g "$LOOM_USER" /home/"$LOOM_USER"/.loom

log "Creating Python virtualenv and installing Loom..."
sudo -u "$LOOM_USER" python3 -m venv "$LOOM_DIR/venv"
sudo -u "$LOOM_USER" "$LOOM_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$LOOM_USER" "$LOOM_DIR/venv/bin/pip" install --quiet "$LOOM_DIR"

log "Configuring PostgreSQL..."
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$LOOM_USER'" | grep -q 1; then
    DB_PASSWORD="$(openssl rand -hex 16)"
    sudo -u postgres psql -qc "CREATE ROLE $LOOM_USER LOGIN PASSWORD '$DB_PASSWORD'"
    sudo -u postgres psql -qc "CREATE DATABASE loom OWNER $LOOM_USER"
    warn "PostgreSQL password for user 'loom' generated: $DB_PASSWORD"
    warn "Set DATABASE_URL=postgresql://loom:$DB_PASSWORD@127.0.0.1:5432/loom in $LOOM_ENV_FILE"
else
    warn "PostgreSQL role '$LOOM_USER' already exists; skipping creation."
fi

log "Enabling and starting PostgreSQL and Redis..."
systemctl enable --now postgresql >/dev/null 2>&1 || true
systemctl enable --now redis-server >/dev/null 2>&1 || true

log "Applying database migrations..."
DATABASE_URL="${DATABASE_URL:-postgresql://loom:@127.0.0.1:5432/loom}"
sudo -u "$LOOM_USER" "$LOOM_DIR/venv/bin/python" \
    "$LOOM_DIR/scripts/postgres_migrate.py" --database-url "$DATABASE_URL" || warn "Migration failed; run it manually after setting DATABASE_URL."

log "Installing environment files..."
install -d -o root -g root /etc/loom
if [[ ! -f "$LOOM_ENV_FILE" ]]; then
    install -o root -g root -m 600 "$SCRIPT_DIR/loom.env.example" "$LOOM_ENV_FILE"
    warn "Created $LOOM_ENV_FILE — edit it with real secrets before starting the API."
fi
if [[ ! -f "$DASHBOARD_ENV_FILE" ]]; then
    install -o root -g root -m 600 "$SCRIPT_DIR/dashboard.env.example" "$DASHBOARD_ENV_FILE"
    warn "Created $DASHBOARD_ENV_FILE — set DASHBOARD_AUTH_TOKEN and API_KEY."
fi

log "Building Next.js dashboard (standalone output)..."
cd "$LOOM_DIR/web"
sudo -u "$LOOM_USER" npm ci --legacy-peer-deps --no-audit --no-fund >/dev/null 2>&1 || \
    sudo -u "$LOOM_USER" npm install --legacy-peer-deps --no-audit --no-fund
sudo -u "$LOOM_USER" env NODE_ENV=production LOOM_API_URL=http://127.0.0.1:8000 \
    npm run build >/dev/null
install -d -o "$LOOM_USER" -g "$LOOM_USER" "$LOOM_DIR/web/.next/standalone/.next/static"
cp -a "$LOOM_DIR/web/.next/static/." "$LOOM_DIR/web/.next/standalone/.next/static/" 2>/dev/null || true
if [[ -d "$LOOM_DIR/web/public" ]]; then
    install -d -o "$LOOM_USER" -g "$LOOM_USER" "$LOOM_DIR/web/.next/standalone/public"
    cp -a "$LOOM_DIR/web/public/." "$LOOM_DIR/web/.next/standalone/public/" 2>/dev/null || true
fi
chown -R "$LOOM_USER:$LOOM_USER" "$LOOM_DIR/web"

log "Installing systemd units..."
for unit in loom-api loom-worker loom-backup loom-dashboard; do
    install -o root -g root -m 644 "$SCRIPT_DIR/$unit.service" "/etc/systemd/system/$unit.service"
done

log "Installing nginx (TLS reverse proxy)..."
install -d -o root -g root /etc/nginx/certs
if [[ ! -f /etc/nginx/certs/tls.crt ]]; then
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/nginx/certs/tls.key \
        -out /etc/nginx/certs/tls.crt \
        -subj "/C=US/ST=State/L=City/O=Loom/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
    warn "Self-signed TLS cert generated. Replace /etc/nginx/certs with a real domain certificate (e.g. Let's Encrypt)."
fi
install -o root -g root -m 644 "$SCRIPT_DIR/nginx.conf" /etc/nginx/nginx.conf
nginx -t

log "Starting Loom services..."
systemctl daemon-reload
systemctl enable --now loom-api loom-worker loom-backup loom-dashboard >/dev/null 2>&1 || true

log "Done. Service status:"
systemctl --no-pager --no-legend status loom-api loom-worker loom-backup loom-dashboard --lines=0 || true
echo
log "Dashboard: https://<this-host>/   (self-signed TLS until you swap in real certs)"
log "API docs:  http://127.0.0.1:8000/docs"
log
warn "Before going live:"
warn "  1. Edit $LOOM_ENV_FILE (secrets, DATABASE_URL, provider keys)"
warn "  2. Edit $DASHBOARD_ENV_FILE (DASHBOARD_AUTH_TOKEN)"
warn "  3. Restart: systemctl restart loom-api loom-dashboard"
warn "  4. Tier B/C (Firecracker) requires a KVM host; Tier A (worktree) works everywhere."