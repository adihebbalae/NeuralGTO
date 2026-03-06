# NeuralGTO FastAPI Backend — Google Cloud Run Dockerfile
# Optimized for always-free tier (~128 MB base image + deps)

FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal for Cloud Run free tier)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY backend /app/backend
COPY poker_gpt /app/poker_gpt
COPY docs /app/docs
COPY .env.example /app/.env.example

# Set PYTHONPATH so imports work (backend/app + poker_gpt root)
ENV PYTHONPATH=/app/backend:/app:$PYTHONPATH
WORKDIR /app/backend

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      fastapi>=0.135.1 \
      uvicorn>=0.41.0 \
      pydantic>=2.12.5 \
      python-dotenv>=1.2.2 \
      slowapi>=0.1.9 \
      google-cloud-secret-manager

# (TexasSolver binary not needed for Cloud Run — solver unavailable forces LLM fallback)
# See docs/DEPLOYMENT.md for migration to compute VM with TexasSolver

# Create work directory for solver (even if unused)
RUN mkdir -p /tmp/_work

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || exit 1

# Cloud Run requires port 8080
ENV PORT=8080

# Run FastAPI app on port specified by Cloud Run
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
