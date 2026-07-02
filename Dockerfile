# ==============================
# GuideWisey Dockerfile (PROD)
# ==============================

FROM python:3.11-slim

# Prevent Python from writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install system dependencies
# NOTE: `git` is required by SecureWise's scan engines (they shell out to
# `git ls-remote` / `git clone` to validate and fetch scan targets). The base
# python:3.11-slim image does NOT include git — omitting it here causes scans
# to fail in production with "[Errno 2] No such file or directory: 'git'".
RUN apt-get update && apt-get install -y \
    build-essential \
    gettext \
    netcat-openbsd \
    git \
    ca-certificates \
    libcairo2 \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz-subset0 \
    libjpeg62-turbo \
    libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip + install Python deps
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure entrypoints are executable
RUN chmod +x /app/entrypoint.sh /app/scheduler_entrypoint.sh

# Django settings module
ENV DJANGO_SETTINGS_MODULE=guidewisey.settings

# Expose port (Render will override PORT)
EXPOSE 8000

# Start app via entrypoint
CMD ["./entrypoint.sh"]
