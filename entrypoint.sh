#!/bin/sh
set -e

# Wait for PostgreSQL only if DB_HOST is set (skip for SQLite local dev)
if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
  echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 1
  done
  echo "PostgreSQL is available"
else
  echo "No DB_HOST set — using SQLite"
fi

# Apply migrations
echo "Applying migrations..."
python manage.py migrate --noinput

# Suppress pypdf ARC4 deprecation warnings
export PYTHONWARNINGS="ignore::DeprecationWarning:pypdf"

# Gunicorn configuration
WEB_CONCURRENCY=${WEB_CONCURRENCY:-2}
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120}

echo "Starting Gunicorn with $WEB_CONCURRENCY worker(s), timeout ${GUNICORN_TIMEOUT}s..."
exec gunicorn guidewisey.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers $WEB_CONCURRENCY \
    --timeout $GUNICORN_TIMEOUT \
    --log-level info
