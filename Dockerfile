# Use official Python 3.13 image
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

# Install dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose any port (Vercel uses dynamic $PORT)
EXPOSE 8000

# Start Gunicorn on Vercel dynamic port
CMD ["sh", "-c", "gunicorn guidewisey.wsgi:application --bind 0.0.0.0:$PORT --workers 3"]