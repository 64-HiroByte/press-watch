FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

FROM base AS dependencies
COPY --from=ghcr.io/astral-sh/uv:0.11.2@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 /uv /uvx /usr/local/bin/
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --locked --no-dev

FROM dependencies AS development
RUN uv sync --frozen
COPY apps/api/src src
EXPOSE 8000
CMD ["uv", "run", "fastapi", "dev", "src/press_watch_api/main.py", "--host", "0.0.0.0"]

FROM dependencies AS scraper-dependencies
WORKDIR /workspace/packages/scraper
COPY packages/scraper/pyproject.toml packages/scraper/uv.lock ./
RUN uv sync --locked --no-dev

FROM base AS runtime
ENV PYTHONPATH=/workspace/apps/api/src HOME=/tmp XDG_CACHE_HOME=/tmp/cache
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
WORKDIR /workspace/apps/api
COPY --from=dependencies --chown=app:app /app/.venv /app/.venv
COPY apps/api/src src
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/alembic.ini ./
COPY apps/api/migrations migrations
USER app

FROM runtime AS job
USER root
COPY --from=dependencies /usr/local/bin/uv /usr/local/bin/uv
COPY --from=scraper-dependencies --chown=app:app /workspace/packages/scraper/.venv /workspace/packages/scraper/.venv
COPY packages/scraper/pyproject.toml packages/scraper/uv.lock /workspace/packages/scraper/
COPY packages/scraper/src /workspace/packages/scraper/src
# 子プロセスはUV環境変数を引き継がないため、設定ファイルで取得を禁止する。
RUN mkdir -p /etc/uv && printf 'offline = true\npython-downloads = "never"\n' > /etc/uv/uv.toml
USER app
STOPSIGNAL SIGINT
ENTRYPOINT ["/app/.venv/bin/python", "-m", "press_watch_api.commands.fetch_and_save_env_press"]

FROM runtime AS production
EXPOSE 8000
CMD ["/bin/sh", "-c", "exec /app/.venv/bin/uvicorn press_watch_api.main:app --host \"${HOST:-0.0.0.0}\" --port \"${PORT:-8000}\" --workers 1"]
