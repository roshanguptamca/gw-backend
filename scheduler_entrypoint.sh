#!/bin/sh
# Entrypoint for the APScheduler worker service.
# Waits for PostgreSQL, runs migrations (idempotent), then starts the scheduler.
set -e

# Wait for PostgreSQL if DB_HOST is set (Docker Compose local dev)
if [ -n "$DB_HOST" ] && [ -n "$DB_PORT" ]; then
  echo "Scheduler: waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
  while ! nc -z "$DB_HOST" "$DB_PORT"; do
    sleep 1
  done
  echo "Scheduler: PostgreSQL is available"
fi

# Apply any pending migrations (safe to run multiple times; web service may beat us to it)
echo "Scheduler: applying migrations..."
python manage.py migrate --noinput

echo "Scheduler: starting runapscheduler..."
exec python manage.py runapscheduler
