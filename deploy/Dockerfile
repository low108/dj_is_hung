# The API for the public demo (Cloud Run). Built by scripts/deploy.sh from a staged folder holding only the
# code, the speed-dating CSV the pools need, and the demo replay; the image stays private in the project.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY garden garden
COPY api api
COPY data data
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
