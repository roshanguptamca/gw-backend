# ==============================
# GuideWisey Dockerfile (PROD)
# ==============================

FROM python:3.13-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    gettext \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project files
COPY . .

# Ensure entrypoint is executable
RUN chmod +x /app/entrypoint.sh

# Django settings module
ENV DJANGO_SETTINGS_MODULE=guidewisey.settings

# Expose port (Render will override PORT)
EXPOSE 8000

# Start app via entrypoint
CMD ["./entrypoint.sh"]
