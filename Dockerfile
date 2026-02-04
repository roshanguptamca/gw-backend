# ==============================
# GuideWisey Dockerfile
# ==============================

# Use official Python 3.13 slim image
FROM python:3.13-slim

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project files
COPY . .

# Set environment variables
ENV DJANGO_SETTINGS_MODULE=guidewisey.settings
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Run database migrations
RUN python manage.py migrate --noinput

# Collect static files
RUN python manage.py collectstatic --noinput

# Create hardcoded superuser if not exists
RUN python manage.py shell -c "from django.contrib.auth import get_user_model; \
User = get_user_model(); \
User.objects.filter(username='admin').exists() or User.objects.create_superuser('admin','admin@example.com','admin123')"

# Expose the port
EXPOSE 8000

# Start the app with Gunicorn on dynamic PORT
CMD ["sh", "-c", "gunicorn guidewisey.wsgi:application --bind 0.0.0.0:$PORT --workers 3"]
