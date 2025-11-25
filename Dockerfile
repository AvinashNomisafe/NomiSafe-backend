# Base image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy project
COPY . /app

# Create directories and set permissions
RUN mkdir -p /app/staticfiles /app/media && \
    useradd -ms /bin/bash appuser && \
    chown -R appuser:appuser /app

USER appuser

# Expose port for gunicorn
EXPOSE 8000

# Entrypoint script runs migrations, collectstatic, then gunicorn
CMD ["/bin/sh", "/app/entrypoint.sh"]
