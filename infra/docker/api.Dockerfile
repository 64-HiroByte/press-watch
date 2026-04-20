FROM python:3.14-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /uvx /usr/local/bin/

COPY apps/api/pyproject.toml apps/api/uv.lock ./

RUN uv sync --frozen

COPY apps/api/src src

EXPOSE 8000

CMD ["uv", "run", "fastapi", "dev", "src/press_watch_api/main.py", "--host", "0.0.0.0"]
