#!/bin/bash
set -e

cd /home/frappe/frappe-bench

# ── Env defaults ──────────────────────────────────────────────────────────────
SITE_NAME="${SITE_NAME:-impactos.localhost}"
DB_HOST="${MYSQLHOST:-${MYSQLDATABASE_HOST:-${DB_HOST:-localhost}}}"
DB_PORT="${MYSQLPORT:-${MYSQLDATABASE_PORT:-3306}}"
DB_ROOT_PASSWORD="${MYSQLPASSWORD:-${MYSQL_ROOT_PASSWORD:-frappe}}"
REDIS_HOST="${REDISHOST:-${REDIS_HOST:-localhost}}"
REDIS_PORT="${REDISPORT:-${REDIS_PORT:-6379}}"

echo "==> Config: DB=$DB_HOST:$DB_PORT REDIS=$REDIS_HOST:$REDIS_PORT SITE=$SITE_NAME"

# ── Build Redis base URL ───────────────────────────────────────────────────────
# Railway provides REDIS_URL (full URL with auth) — use it directly if available.
# Strip any trailing /N db-number so we can append /0, /1, /2 ourselves.
if [ -n "${REDIS_URL:-}" ]; then
    REDIS_BASE=$(echo "$REDIS_URL" | sed 's|/[0-9]*$||')
    echo "==> Using REDIS_URL (auth included)"
else
    # Fall back to building from individual vars; try several Railway password var names
    REDIS_PASS="${REDISPASSWORD:-${REDIS_PASSWORD:-}}"
    if [ -n "$REDIS_PASS" ]; then
        REDIS_BASE="redis://:${REDIS_PASS}@${REDIS_HOST}:${REDIS_PORT}"
        echo "==> Using REDIS_PASS from env"
    else
        REDIS_BASE="redis://${REDIS_HOST}:${REDIS_PORT}"
        echo "==> WARNING: no Redis password found — connecting without auth"
    fi
fi

# ── Wait for MariaDB ──────────────────────────────────────────────────────────
echo "==> Waiting for MariaDB at $DB_HOST:$DB_PORT..."
until nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; do
    echo "    not ready, retrying in 3s..."
    sleep 3
done
echo "==> MariaDB port open!"

# ── Wait for Redis ────────────────────────────────────────────────────────────
echo "==> Waiting for Redis at $REDIS_HOST:$REDIS_PORT..."
until nc -z "$REDIS_HOST" "$REDIS_PORT" 2>/dev/null; do
    echo "    not ready, retrying in 3s..."
    sleep 3
done
echo "==> Redis port open!"

# ── Write common_site_config.json ─────────────────────────────────────────────
# NOTE: do NOT include rq_username/rq_password — those break workers against
# managed Redis (Railway) where we can't use Redis ACL namespaces.
cat > sites/common_site_config.json << EOF
{
    "db_host": "$DB_HOST",
    "db_port": $DB_PORT,
    "redis_cache": "${REDIS_BASE}/0",
    "redis_queue": "${REDIS_BASE}/1",
    "redis_socketio": "${REDIS_BASE}/2",
    "socketio_port": 9000,
    "developer_mode": 1,
    "default_site": "$SITE_NAME"
}
EOF

# ── First-time site creation ──────────────────────────────────────────────────
if [ ! -f "sites/$SITE_NAME/site_config.json" ]; then
    echo "==> Creating site '$SITE_NAME' (first run — takes ~15 mins)..."

    bench new-site "$SITE_NAME" \
        --db-host "$DB_HOST" \
        --db-port "$DB_PORT" \
        --db-root-password "$DB_ROOT_PASSWORD" \
        --admin-password "${ADMIN_PASSWORD:-admin123}" \
        --mariadb-user-host-login-scope='%'

    echo "==> Installing impact_os_ai..."
    bench --site "$SITE_NAME" install-app impact_os_ai

    bench --site "$SITE_NAME" set-config openai_api_key  "${OPENAI_API_KEY:-}"
    bench --site "$SITE_NAME" set-config jwt_secret       "${JWT_SECRET:-impactos-change-this}"
    bench --site "$SITE_NAME" set-config developer_mode  1

    echo "==> Site created!"
else
    echo "==> Site exists — running migrations..."
    bench --site "$SITE_NAME" migrate || true

    # Ensure impact_os_ai is installed even if it was missing on first run
    bench --site "$SITE_NAME" list-apps 2>/dev/null | grep -q "impact_os_ai" || \
        bench --site "$SITE_NAME" install-app impact_os_ai || true
fi

# ── Set default site ──────────────────────────────────────────────────────────
bench use "$SITE_NAME"

# ── Start background worker ───────────────────────────────────────────────────
echo "==> Starting background worker..."
bench worker --queue long,default &
WORKER_PID=$!

# ── Start Frappe (v16.12 removed --host flag; binds 0.0.0.0 by default) ──────
SERVE_PORT="${PORT:-8000}"
echo "==> Starting Frappe on port $SERVE_PORT..."
bench serve --port "$SERVE_PORT"

kill $WORKER_PID 2>/dev/null || true
