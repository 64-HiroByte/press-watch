from fastapi import FastAPI
from sqlalchemy.exc import SQLAlchemyError

from press_watch_api.http_errors import (
    DatabaseLifecycleError,
    database_error_handler,
)
from press_watch_api.routers.press_releases import router as press_releases_router

app = FastAPI(title="PressWatch API")
app.add_exception_handler(SQLAlchemyError, database_error_handler)
app.add_exception_handler(DatabaseLifecycleError, database_error_handler)
app.include_router(press_releases_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "service": "press-watch-api",
        "status": "ready",
    }


@app.get("/health")
def read_health() -> dict[str, str]:
    """APIプロセスのlivenessステータスを返す"""

    return {"status": "ok"}
