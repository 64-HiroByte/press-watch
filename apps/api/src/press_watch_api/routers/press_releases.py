from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.repositories.press_release import (
    count_press_releases,
    list_press_releases,
)
from press_watch_api.schemas.error import ErrorResponse
from press_watch_api.schemas.press_release import (
    PressReleaseListItem,
    PressReleaseListResponse,
    PressReleasePagination,
)


DEFAULT_PAGE = 1
MIN_PAGE = 1
MAX_PAGE = 10_000
DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
MAX_TITLE_QUERY_LENGTH = 100
TITLE_QUERY_PATTERN = r"^[^\x00]*$"


router = APIRouter(prefix="/press-releases", tags=["press-releases"])


@router.get(
    "",
    responses={
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
    },
)
def read_press_releases(
    session: Annotated[Session, Depends(get_db_session, scope="function")],
    page: Annotated[int, Query(ge=MIN_PAGE, le=MAX_PAGE)] = DEFAULT_PAGE,
    page_size: Annotated[
        int,
        Query(ge=MIN_PAGE_SIZE, le=MAX_PAGE_SIZE),
    ] = DEFAULT_PAGE_SIZE,
    q: Annotated[
        str | None,
        Query(
            max_length=MAX_TITLE_QUERY_LENGTH,
            pattern=TITLE_QUERY_PATTERN,
        ),
    ] = None,
) -> PressReleaseListResponse:
    """保存済み報道発表を任意のタイトル検索条件でページ単位に取得

    Args:
        session: 一覧取得に使うリクエスト単位のDB Session
        page: 1から始まるページ番号
        page_size: 1ページに含める最大件数
        q: タイトルの部分一致検索に使う文字列

    Returns:
        報道発表一覧とページ情報
    """

    title_query = q.strip() if q is not None else None
    if not title_query:
        title_query = None

    offset = (page - 1) * page_size
    total_items = count_press_releases(
        session,
        title_query=title_query,
    )
    total_pages = (
        (total_items + page_size - 1) // page_size
        if total_items > 0
        else 0
    )

    if offset >= total_items:
        press_releases = ()
    else:
        press_releases = list_press_releases(
            session,
            limit=page_size,
            offset=offset,
            title_query=title_query,
        )

    return PressReleaseListResponse(
        items=[
            PressReleaseListItem.model_validate(press_release)
            for press_release in press_releases
        ],
        pagination=PressReleasePagination(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )
