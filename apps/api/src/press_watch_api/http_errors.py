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


def database_error_responses() -> dict[int, dict[str, object]]:
    """読み取りAPIで共有するDB関連エラーと既定500のOpenAPI定義を生成

    HTTP応答の生成・例外の分類は行わず、routeごとに独立した辞書を返す。

    Returns:
        500の固定JSON・既定text/plainと、503の固定JSONの応答定義
    """

    return {
        500: {
            "model": ErrorResponse,
            "description": (
                "503の条件に該当しないDB設定・初期化・処理・Session終了の失敗は"
                "固定JSONを返す。"
                "想定外例外やレスポンスDTOの検証失敗は既定のtext/plainを返す。"
            ),
            "content": {
                "application/json": {"example": {"detail": "Internal server error"}},
                "text/plain": {
                    "schema": {"type": "string"},
                    "example": "Internal Server Error",
                },
            },
        },
        503: {
            "model": ErrorResponse,
            "description": (
                "SQLAlchemyのTimeoutError、または"
                "DBAPIError.connection_invalidatedがTrueの場合に固定JSONを返す。"
                "復旧や再試行の成功は保証しない。"
            ),
            "content": {
                "application/json": {"example": {"detail": "Service unavailable"}},
            },
        },
    }


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
