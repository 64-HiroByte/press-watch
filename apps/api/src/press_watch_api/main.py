from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.exc import SQLAlchemyError

from press_watch_api.db_tls import certificate_environment
from press_watch_api.http_errors import (
    DatabaseLifecycleError,
    database_error_handler,
)
from press_watch_api.request_rate_limit import (
    RATE_LIMIT_RESPONSES,
    RequestRateLimit,
    enforce_request_rate_limit,
)
from press_watch_api.routers.fixed_categories import router as fixed_categories_router
from press_watch_api.routers.press_releases import router as press_releases_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """API起動中だけ環境変数からlibpq用のCAファイルを提供

    Args:
        _app: このライフサイクルを実行するFastAPIアプリ

    Yields:
        CA指定の準備を終えた状態

    Raises:
        RuntimeError: CA用の環境変数が設定済みで空の場合
    """

    with certificate_environment():
        yield


app = FastAPI(title="PressWatch API", lifespan=lifespan)
app.add_exception_handler(SQLAlchemyError, database_error_handler)
app.add_exception_handler(DatabaseLifecycleError, database_error_handler)
app.state.request_rate_limit = RequestRateLimit()
for router in (fixed_categories_router, press_releases_router):
    app.include_router(
        router,
        dependencies=[Depends(enforce_request_rate_limit)],
        responses=RATE_LIMIT_RESPONSES,
    )


@app.get("/")
def read_root() -> dict[str, str]:
    """APIのサービス情報を返す

    Returns:
        サービス名と固定ステータス `ready`
    """
    return {
        "service": "press-watch-api",
        "status": "ready",
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    """APIプロセスのlivenessステータスを返す"""

    return {"status": "ok"}
