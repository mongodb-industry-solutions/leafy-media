#
# Dockerfile - Flask App for Leafy Media (Kanopy)
# Sidecar container - nginx proxies to this on port 8000
#
# Copyright (c) 2024, 2025 MongoDB Inc.
#
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn

# Copy application code
COPY . .

# Create directories for content (empty initially, will use S3 later)
RUN mkdir -p /app/content/images /app/content/audio /app/content/video/frames

# Set environment variables
ENV FLASK_CONFIG=production
ENV PYTHONUNBUFFERED=1

# Sidecar runs on port 8000 (nginx main container handles 8080)
EXPOSE 8000

# Run with gunicorn on port 8000
# Note: Health checks are handled by Kubernetes probes, not Docker HEALTHCHECK
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "300", "--graceful-timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "--capture-output", "--log-level", "info", "manage:app"]
