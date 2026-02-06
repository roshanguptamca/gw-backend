#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
while ! nc -z "$DB_HOST" "$DB_PORT"; do
  sleep 1
done
echo "PostgreSQL is available"

python manage.py migrate --noinput

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

gunicorn guidewisey.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 3
