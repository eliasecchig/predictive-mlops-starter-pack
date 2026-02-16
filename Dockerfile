FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.13 /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY fraud_detector/_version.py ./fraud_detector/_version.py
RUN uv sync --frozen --no-dev --no-editable --no-install-project --extra pipelines
RUN uv pip install pip

ENV PATH="/app/.venv/bin:$PATH"
