from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.repositories.press_release import (
    count_press_releases,
    list_press_releases,
)
from press_watch_api.schemas.press_release import (
    PressReleaseListItem,
    PressReleaseListResponse,
    PressReleasePagination,
)


DEFAULT_PAGE = 1
MIN_PAGE = 1
MAX_PAGE = 10_000
DEFAULT_PAGE_SIZE = 20
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 100


router = APIRouter(prefix="/press-releases", tags=["press-releases"])


@router.get("")
def read_press_releases(
    session: Annotated[Session, Depends(get_db_session)],
    page: Annotated[int, Query(ge=MIN_PAGE, le=MAX_PAGE)] = DEFAULT_PAGE,
    page_size: Annotated[
        int,
        Query(ge=MIN_PAGE_SIZE, le=MAX_PAGE_SIZE),
    ] = DEFAULT_PAGE_SIZE,
) -> PressReleaseListResponse:
    """保存済み報道発表を新着順でページ単位に取得

    Args:
        session: 一覧取得に使うリクエスト単位のDB Session
        page: 1から始まるページ番号
        page_size: 1ページに含める最大件数

    Returns:
        報道発表一覧とページ情報
    """

    offset = (page - 1) * page_size
    total_items = count_press_releases(session)
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
