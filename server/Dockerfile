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

# Create startup script for dual-port mode
RUN cat > /app/start.sh << 'EOF'
#!/bin/bash
set -e

# Run migrations first
alembic upgrade head

# Start Control API on port 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
CONTROL_PID=$!

# Start Agent API on port 8001 (same app, different port)
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
AGENT_PID=$!

# Wait for both processes
wait $CONTROL_PID $AGENT_PID
EOF

RUN chmod +x /app/start.sh

# Switch to non-root user
USER appuser

EXPOSE 8000
EXPOSE 8001

# Run startup script
CMD ["/app/start.sh"]
