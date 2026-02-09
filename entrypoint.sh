#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 1
done
echo "PostgreSQL is available"

# Apply migrations
echo "Applying migrations..."
python manage.py migrate --noinput

# Optional: create admin superuser if not exists
echo "Checking admin user..."
python manage.py shell << EOF
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username="admin").exists():
    User.objects.create_superuser(
        "admin",
        "admin@example.com",
        "admin123"
    )
EOF

# Suppress pypdf ARC4 deprecation warnings
export PYTHONWARNINGS="ignore::DeprecationWarning:pypdf"

# Gunicorn configuration
WEB_CONCURRENCY=${WEB_CONCURRENCY:-1}   # 1 worker by default for small Render instance
GUNICORN_TIMEOUT=${GUNICORN_TIMEOUT:-120}  # 120s timeout

echo "Starting Gunicorn with $WEB_CONCURRENCY worker(s) and timeout $GUNICORN_TIMEOUT..."
exec gunicorn guidewisey.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers $WEB_CONCURRENCY \
    --timeout $GUNICORN_TIMEOUT \
    --log-level info
