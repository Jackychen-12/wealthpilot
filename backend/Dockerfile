FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

COPY src/ src/

ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000

CMD ["uv", "run", "uvicorn", "wealthpilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
