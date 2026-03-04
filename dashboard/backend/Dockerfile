# PR-Agent Dashboard Backend - GCP/Cloud SQL ready
# Build: docker build -f dashboard/backend/Dockerfile -t pr-agent-dashboard-backend .
# Run:   docker run -p 8000:8000 -e DATABASE_URL="postgresql://..." pr-agent-dashboard-backend

FROM python:3.12-slim

WORKDIR /app

# Install dependencies (psycopg2 may need libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY dashboard/backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY dashboard/backend/ ./

# Cloud Run and GCP expect PORT; default 8000 for local
ENV PORT=8000
EXPOSE 8000

# PORT is set by Cloud Run at runtime; default 8000 for local
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
