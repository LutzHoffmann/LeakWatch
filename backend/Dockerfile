FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY src ./src
COPY README.md ../README.md

RUN uv sync --no-dev --no-install-project
RUN uv sync --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/pyproject.toml

CMD ["arq", "leakwatch.worker.WorkerSettings"]
