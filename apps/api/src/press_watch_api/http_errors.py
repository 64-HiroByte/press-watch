import sys
from typing import Literal

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, TimeoutError as SQLAlchemyTimeoutError

from press_watch_api.schemas.error import ErrorResponse


class DatabaseLifecycleError(Exception):
    """内部情報を持たないDB Sessionの生成・終了エラー"""

    def __init__(self, operation: Literal["initialization", "cleanup"]) -> None:
        self.operation = operation
        super().__init__(operation)


def write_database_diagnostic(
    event: Literal[
        "database_error",
        "database_initialization_failed",
        "database_cleanup_failed",
    ],
) -> None:
    """固定イベントだけをstderrへ出力し、出力失敗をHTTP処理へ波及させない"""

    try:
        sys.stderr.write(f"{event}\n")
        sys.stderr.flush()
    except Exception:
        # 出力先の障害について再度診断すると、例外連鎖が露出し得る。
        return


def _database_error_status(exc: Exception) -> int:
    if isinstance(exc, SQLAlchemyTimeoutError) or (
        isinstance(exc, DBAPIError) and exc.connection_invalidated
    ):
        return 503
    return 500


async def database_error_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """DB関連の失敗を内部情報のないHTTP応答へ変換"""

    status_code = _database_error_status(exc)
    message = (
        "Service unavailable" if status_code == 503 else "Internal server error"
    )
    if isinstance(exc, DatabaseLifecycleError):
        if exc.operation == "initialization":
            write_database_diagnostic("database_initialization_failed")
        else:
            write_database_diagnostic("database_cleanup_failed")
    else:
        write_database_diagnostic("database_error")
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(detail=message).model_dump(),
    )
