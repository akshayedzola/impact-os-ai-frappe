#!/bin/bash
set -e

cd /home/frappe/frappe-bench

SITE_NAME="${SITE_NAME:-impactos.localhost}"
DB_HOST="${MYSQLDATABASE_HOST:-${DB_HOST:-localhost}}"
DB_PORT="${MYSQLDATABASE_PORT:-3306}"
DB_ROOT_PASSWORD="${MYSQLPASSWORD:-${MYSQL_ROOT_PASSWORD:-frappe}}"
REDIS_URL="${REDISHOST:-${REDIS_HOST:-localhost}}"
REDIS_PORT="${REDISPORT:-6379}"

echo "==> Waiting for MariaDB at $DB_HOST:$DB_PORT..."
until mysql -h "$DB_HOST" -P "$DB_PORT" -u root -p"$DB_ROOT_PASSWORD" -e "SELECT 1" 2>/dev/null; do
    echo "    MariaDB not ready, retrying in 3s..."
    sleep 3
done
echo "==> MariaDB is up!"

echo "==> Waiting for Redis at $REDIS_URL:$REDIS_PORT..."
until redis-cli -h "$REDIS_URL" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; do
    echo "    Redis not ready, retrying in 3s..."
    sleep 3
done
echo "==> Redis is up!"

# Write common_site_config.json
cat > sites/common_site_config.json << EOF
{
    "db_host": "$DB_HOST",
    "db_port": $DB_PORT,
    "redis_cache": "redis://$REDIS_URL:$REDIS_PORT/0",
    "redis_queue": "redis://$REDIS_URL:$REDIS_PORT/1",
    "redis_socketio": "redis://$REDIS_URL:$REDIS_PORT/2",
    "socketio_port": 9000,
    "developer_mode": 1
}
EOF

# First-time site setup
if [ ! -f "sites/$SITE_NAME/site_config.json" ]; then
    echo "==> Creating site: $SITE_NAME (first run — takes ~3 minutes)"

    bench new-site "$SITE_NAME" \
        --db-host "$DB_HOST" \
        --db-port "$DB_PORT" \
        --db-root-password "$DB_ROOT_PASSWORD" \
        --admin-password "${ADMIN_PASSWORD:-admin123}" \
        --no-mariadb-socket \
        --install-app impact_os_ai

    bench --site "$SITE_NAME" set-config openai_api_key "${OPENAI_API_KEY:-}"
    bench --site "$SITE_NAME" set-config jwt_secret "${JWT_SECRET:-impactos-change-this-secret}"
    bench --site "$SITE_NAME" set-config developer_mode 1

    echo "==> Site ready!"
else
    echo "==> Site exists, running migrations..."
    bench --site "$SITE_NAME" migrate || true
fi

echo "$SITE_NAME" > sites/currentsite.txt

echo "==> Starting Frappe on port 8000..."
bench serve --port 8000 --host 0.0.0.0
