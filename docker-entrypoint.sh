#!/bin/bash
set -e

cd /home/frappe/frappe-bench

# ── Env defaults (try every Railway MySQL/Redis variable naming convention) ───
SITE_NAME="${SITE_NAME:-impactos.localhost}"
DB_HOST="${MYSQLHOST:-${MYSQLDATABASE_HOST:-${DB_HOST:-localhost}}}"
DB_PORT="${MYSQLPORT:-${MYSQLDATABASE_PORT:-3306}}"
DB_ROOT_PASSWORD="${MYSQLPASSWORD:-${MYSQL_ROOT_PASSWORD:-frappe}}"
REDIS_HOST="${REDISHOST:-${REDIS_HOST:-localhost}}"
REDIS_PORT="${REDISPORT:-${REDIS_PORT:-6379}}"

echo "==> Config: DB=$DB_HOST:$DB_PORT REDIS=$REDIS_HOST:$REDIS_PORT SITE=$SITE_NAME"

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
cat > sites/common_site_config.json << EOF
{
    "db_host": "$DB_HOST",
    "db_port": $DB_PORT,
    "redis_cache": "redis://$REDIS_HOST:$REDIS_PORT/0",
    "redis_queue": "redis://$REDIS_HOST:$REDIS_PORT/1",
    "redis_socketio": "redis://$REDIS_HOST:$REDIS_PORT/2",
    "socketio_port": 9000,
    "developer_mode": 1
}
EOF

# ── First-time site creation ──────────────────────────────────────────────────
if [ ! -f "sites/$SITE_NAME/site_config.json" ]; then
    echo "==> Creating site '$SITE_NAME' (first run — takes ~3 mins)..."

    bench new-site "$SITE_NAME" \
        --db-host "$DB_HOST" \
        --db-port "$DB_PORT" \
        --db-root-password "$DB_ROOT_PASSWORD" \
        --admin-password "${ADMIN_PASSWORD:-admin123}" \
        --no-mariadb-socket \
        --install-app impact_os_ai

    bench --site "$SITE_NAME" set-config openai_api_key  "${OPENAI_API_KEY:-}"
    bench --site "$SITE_NAME" set-config jwt_secret       "${JWT_SECRET:-impactos-change-this}"
    bench --site "$SITE_NAME" set-config developer_mode  1

    echo "==> Site created!"
else
    echo "==> Site exists — running migrations..."
    bench --site "$SITE_NAME" migrate || true
fi

echo "$SITE_NAME" > sites/currentsite.txt

# ── Start background worker (processes frappe.enqueue jobs) ──────────────────
echo "==> Starting background worker..."
bench worker --queue long,default &
WORKER_PID=$!

# ── Start Frappe ──────────────────────────────────────────────────────────────
echo "==> Starting Frappe on 0.0.0.0:8000..."
bench serve --port 8000 --host 0.0.0.0

# If bench serve exits, also kill the worker
kill $WORKER_PID 2>/dev/null || true
