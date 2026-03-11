# ============================================================
# Multi-stage Dockerfile for Cert Control Plane
# Stage 1: Build React frontend
# Stage 2: Python application with frontend assets
# ============================================================

# ── Stage 1: Frontend build ──
FROM node:22.14-alpine3.21 AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --production=false
COPY frontend/ .
RUN npm run build

# ── Stage 2: Python application ──
FROM python:3.12.9-slim

# Create non-root user
RUN adduser --disabled-password --no-create-home --gecos "" appuser

WORKDIR /app

# Install Python dependencies first (cache layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application code
COPY alembic/ alembic/
COPY alembic.ini .
COPY app/ app/

# Copy frontend build artifacts from stage 1
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# Create certs directory (will be mounted as volume)
RUN mkdir -p /certs && chown appuser:appuser /certs

# Switch to non-root user
USER appuser

EXPOSE 8000

# Run migrations then start server
# Migrations run separately so failures are clearly visible
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
