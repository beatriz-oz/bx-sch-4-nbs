# The API image (FastAPI). Also used by the scheduler service (see deploy/compose.yaml).
FROM python:3.14-slim

# uv, pinned to the version used to write uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first: this layer is reused while only the code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md alembic.ini ./
COPY alembic ./alembic
COPY src ./src
RUN uv sync --frozen --no-dev

# Never run as root.
RUN useradd --create-home --uid 10001 app
USER app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# Migrations first, then the API. The proxy (Caddy) sets X-Forwarded-*: trust it, it is the only way in.
CMD ["sh", "-c", "alembic upgrade head && uvicorn bx_sch_4_nbs.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
