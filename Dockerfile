FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project --extra pipelines

COPY fraud_detector/ ./fraud_detector/
RUN uv sync --frozen --no-dev --no-editable --extra pipelines

ENV PATH="/app/.venv/bin:$PATH"
