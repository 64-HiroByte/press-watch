from math import ceil
from time import monotonic

from fastapi import HTTPException, Request
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from press_watch_api.schemas.error import ErrorResponse


BURST_CAPACITY = 20
REFILL_PER_SECOND = 2
RATE_LIMIT_ERROR_DETAIL = "Too many requests"

RATE_LIMIT_RESPONSES = {
    HTTP_429_TOO_MANY_REQUESTS: {
        "model": ErrorResponse,
        "description": "内部APIの共有枠に空きがない",
        "content": {
            "application/json": {
                "example": {"detail": RATE_LIMIT_ERROR_DETAIL},
            },
        },
        "headers": {
            "Retry-After": {
                "description": "次の1件分が補充されるまでの秒数（切り上げ）",
                "schema": {"type": "integer", "minimum": 1},
            },
        },
    },
}


class RequestRateLimit:
    """読み取りAPIが同一イベントループ上で共有するトークンバケット"""

    def __init__(self) -> None:
        """満杯のバケットを準備"""
        self._tokens = float(BURST_CAPACITY)
        self._updated_at = monotonic()

    def take(self) -> int | None:
        """経過時間分を補充し、空きがあれば1件分を消費

        Returns:
            許可時はNone、拒否時は次の補充までの秒数を切り上げた値
        """
        now = monotonic()
        self._tokens = min(
            BURST_CAPACITY,
            self._tokens + (now - self._updated_at) * REFILL_PER_SECOND,
        )
        self._updated_at = now
        if self._tokens < 1:
            return ceil((1 - self._tokens) / REFILL_PER_SECOND)

        self._tokens -= 1
        return None


async def enforce_request_rate_limit(request: Request) -> None:
    """DBセッションを使う前に読み取りAPIの共有枠を確認

    Args:
        request: アプリの共有バケットを参照する要求

    Raises:
        HTTPException: 枠不足による429
    """
    limiter: RequestRateLimit = request.app.state.request_rate_limit
    retry_after = limiter.take()
    if retry_after is not None:
        raise HTTPException(
            status_code=HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMIT_ERROR_DETAIL,
            headers={"Retry-After": str(retry_after)},
        )
