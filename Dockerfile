# TenderShield Nexus - single container: FastAPI backend serving the built React dashboard.

# --- Frontend build ---------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Public MST Testnet contract address (see blockchain/README.md). Override with --build-arg.
ARG VITE_TENDERSHIELD_CONTRACT_ADDRESS=0xC5a5Eae08f4c33A720073AF5379667cb662d8D80
ENV VITE_TENDERSHIELD_CONTRACT_ADDRESS=$VITE_TENDERSHIELD_CONTRACT_ADDRESS
RUN npm run build

# --- Runtime ----------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TS_DATA_DIR=/data \
    TS_STATIC_DIR=/app/static \
    TS_ENV=production \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
COPY backend/models ./models
COPY --from=web /web/dist ./static
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/ready' % os.environ.get('PORT', '8000'))"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
