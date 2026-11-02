FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8 AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.2@sha256:c4f5de312ee66d46810635ffc5df34a1973ba753e7241ce3a08ef979ddd7bea5 /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
WORKDIR /workspace/apps/api
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --locked --no-dev
WORKDIR /workspace/packages/scraper
COPY packages/scraper/pyproject.toml packages/scraper/uv.lock ./
RUN uv sync --locked --no-dev

FROM python:3.14-slim@sha256:cd89c30eda26ee911a4611b18680086e0ea42e6f5f8cbe653d07fa7958c9cec8 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/apps/api/src \
    HOME=/tmp XDG_CACHE_HOME=/tmp/cache
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
WORKDIR /workspace/apps/api
COPY --from=build --chown=app:app /workspace/apps/api/.venv .venv
COPY apps/api/src src
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/alembic.ini ./
COPY apps/api/migrations migrations
COPY --from=build /usr/local/bin/uv /usr/local/bin/uv
COPY --from=build --chown=app:app /workspace/packages/scraper/.venv /workspace/packages/scraper/.venv
COPY packages/scraper/pyproject.toml packages/scraper/uv.lock /workspace/packages/scraper/
COPY packages/scraper/src /workspace/packages/scraper/src
# 子プロセスはUV環境変数を引き継がないため、設定ファイルで取得を禁止する。
RUN mkdir -p /etc/uv && printf 'offline = true\npython-downloads = "never"\n' > /etc/uv/uv.toml
USER app
ENTRYPOINT ["/workspace/apps/api/.venv/bin/python", "-m", "press_watch_api.commands.fetch_and_save_env_press"]
