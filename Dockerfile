# Satark: one container = API + PWA + registry DB (LLD §19.1). Self-contained: builds the PWA and the
# registry database from the committed snapshots, so `gcloud run deploy --source .` works from a clean
# checkout. Build context is the repo root.
#
#   docker build -t satark .
#   docker build -t satark --build-arg INSTALL_OCR=true .   # + rapidocr for screenshot OCR without an AI model
#   docker run -p 8080:8080 -e SATARK_LLM=... satark

# ---- 1. the PWA -----------------------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
COPY content/ /src/content/
RUN npm run build

# ---- 2. the registry database (SEBI/NSE snapshots + threat feeds when the network allows) ------------
FROM python:3.12-slim AS data
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/
ENV UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra ingest --no-install-project
COPY satark/ ./satark/
COPY config/ ./config/
COPY data/manual/ ./data/manual/
RUN (.venv/bin/python -m satark.ingest --fetch || .venv/bin/python -m satark.ingest) && ls -la data/registry.db

# ---- 3. runtime -----------------------------------------------------------------------------------
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /usr/local/bin/
ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock ./
ARG INSTALL_OCR=false
RUN if [ "$INSTALL_OCR" = "true" ]; then \
      uv sync --frozen --no-dev --extra ocr --no-install-project; \
    else \
      uv sync --frozen --no-dev --no-install-project; \
    fi
# With OCR: the optional Devanagari recognition model for Hindi screenshots (~9 MB, Apache-2.0); skipped offline.
COPY scripts/get_ocr_models.sh ./scripts/get_ocr_models.sh
RUN if [ "$INSTALL_OCR" = "true" ]; then \
      (apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
       && bash scripts/get_ocr_models.sh) || echo "Hindi OCR model not downloaded"; \
    fi

COPY satark/ ./satark/
COPY config/ ./config/
COPY content/ ./content/
COPY skills/ ./skills/
COPY --from=data /app/data/registry.db ./data/registry.db
COPY --from=data /app/data/manual/misc/iana_rdap_dns.json ./data/manual/misc/iana_rdap_dns.json
COPY --from=web /src/web/dist ./web/dist

RUN useradd --create-home --uid 1000 satark && chown -R satark:satark /app
USER satark

EXPOSE 8080
# One worker on purpose: cases, event streams and rate limits live in process memory (LLD §3.7).
CMD ["sh", "-c", "uvicorn satark.app:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
