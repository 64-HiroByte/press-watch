from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AfterValidator, Field
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.http_errors import database_error_responses
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
DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100
MAX_TITLE_QUERY_LENGTH = 100
TITLE_QUERY_PATTERN = r"^[^\x00]*$"
MAX_FIXED_CATEGORY_COUNT = 20
MAX_FIXED_CATEGORY_LENGTH = 100
FIXED_CATEGORY_SLUG_PATTERN = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
FIXED_CATEGORY_QUERY_PATTERN = rf"^(?:{FIXED_CATEGORY_SLUG_PATTERN})?$"

# 長さは元の入力、slug形式は前後空白の除去後に検証する。
_FixedCategoryQueryValue = Annotated[
    str,
    Field(max_length=MAX_FIXED_CATEGORY_LENGTH),
    AfterValidator(str.strip),
    Field(pattern=FIXED_CATEGORY_QUERY_PATTERN),
]


router = APIRouter(prefix="/press-releases", tags=["press-releases"])


@router.get(
    "",
    responses=database_error_responses(),
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
    fixed_category: Annotated[
        list[_FixedCategoryQueryValue] | None,
        Query(
            max_length=MAX_FIXED_CATEGORY_COUNT,
            description=(
                "固定カテゴリのslug。同名クエリの繰り返しでOR指定する。"
                "指定数は空要素・重複の除去前に"
                f"{MAX_FIXED_CATEGORY_COUNT}件まで、"
                "各値は前後空白の除去前に"
                f"{MAX_FIXED_CATEGORY_LENGTH}文字まで。"
                "前後空白を除去した非空の値は"
                f"{FIXED_CATEGORY_SLUG_PATTERN}に完全一致させる。"
                "空要素と重複は除外し、未指定・全要素空は絞り込まない。"
                "形式不正・上限超過は422、未定義slugは一致なしとして扱う。"
                "qとの組み合わせはAND条件。"
            ),
        ),
    ] = None,
) -> PressReleaseListResponse:
    """保存済み報道発表をタイトルと固定カテゴリで絞り込み、ページ単位で取得

    カテゴリ内のOR条件とタイトル条件をANDで組み合わせる。
    入力の長さ・形式とカテゴリの前後空白はFastAPIの入力検証で処理済み。
    Sessionの生成・終了とDB例外のHTTP応答への変換は既存の共通処理に委ねる。

    Args:
        session: 一覧取得に使うリクエスト単位のDB Session
        page: 1から始まるページ番号
        page_size: 1ページに含める最大件数
        q: タイトルの部分一致検索語。前後空白を除去し、空なら検索未指定
        fixed_category: 前後空白を除去済みのslug列。空要素と重複を除いて使用

    Returns:
        条件に一致する報道発表一覧と、絞り込み後の総件数・総ページ数
        0件または超過ページでは空のitemsと要求されたページ番号を保持
    """

    title_query = q.strip() if q is not None else None
    if not title_query:
        title_query = None
    fixed_category_slugs = tuple(dict.fromkeys(
        value for value in fixed_category or () if value
    ))

    offset = (page - 1) * page_size
    total_items = count_press_releases(
        session,
        title_query=title_query,
        fixed_category_slugs=fixed_category_slugs,
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
            fixed_category_slugs=fixed_category_slugs,
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
