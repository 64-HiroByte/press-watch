from datetime import date
import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import AfterValidator, BeforeValidator, Field
from sqlalchemy.orm import Session

from press_watch_api.dependencies import get_db_session
from press_watch_api.http_errors import database_error_responses
from press_watch_api.repositories.fixed_category import (
    list_press_release_fixed_categories,
)
from press_watch_api.repositories.press_release import (
    count_press_releases,
    list_press_releases,
)
from press_watch_api.schemas.fixed_category import FixedCategoryMembershipItem
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


def _parse_publication_date(value: str) -> date:
    """ASCIIのYYYY-MM-DDに完全一致する実在日を変換

    Args:
        value: 空白除去や補完を行わない日付クエリの入力値

    Returns:
        形式と実在日の検証を通った公開日

    Raises:
        ValueError: 形式不一致または実在しない日付。入力検証の422へ接続
    """

    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("日付はYYYY-MM-DD形式で指定してください")
    return date.fromisoformat(value)


_PublicationDateQueryValue = Annotated[
    date, BeforeValidator(_parse_publication_date)
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
                "q・公開日との組み合わせはAND条件。"
            ),
        ),
    ] = None,
    published_from: Annotated[
        _PublicationDateQueryValue | None,
        Query(description=(
            "公開日の下限（当日を含む）。ASCIIのYYYY-MM-DDの実在日。"
            "未指定は下限制限なし。形式不正・実在しない日付は422。"
        )),
    ] = None,
    published_to: Annotated[
        _PublicationDateQueryValue | None,
        Query(description=(
            "公開日の上限（当日を含む）。ASCIIのYYYY-MM-DDの実在日。"
            "未指定は上限制限なし。形式不正・実在しない日付・下限より前は422。"
        )),
    ] = None,
) -> PressReleaseListResponse:
    """保存済み報道発表をタイトル・固定カテゴリ・公開日で絞り込み、ページ単位で取得

    カテゴリ内のOR条件とタイトル・公開日の条件をANDで組み合わせる。
    入力の長さ・形式とカテゴリの前後空白はFastAPIの入力検証で処理済み。
    公開日の両端を含め、逆順は拒否し、日付の入れ替えや未指定側の補完は行わない。
    検索カテゴリによらず、ページ内の記事の全所属を一括取得し表示順で返す。
    Sessionの生成・終了とDB例外のHTTP応答への変換は既存の共通処理に委ねる。

    Args:
        session: 一覧取得に使うリクエスト単位のDB Session
        page: 1から始まるページ番号
        page_size: 1ページに含める最大件数
        q: タイトルの部分一致検索語。前後空白を除去し、空なら検索未指定
        fixed_category: 前後空白を除去済みのslug列。空要素と重複を除いて使用
        published_from: 検証・変換済みの下限日。Noneなら下限制限なし
        published_to: 検証・変換済みの上限日。Noneなら上限制限なし

    Returns:
        条件に一致する報道発表一覧と、絞り込み後の総件数・総ページ数
        0件または超過ページでは空のitemsと要求されたページ番号を保持
        件数取得後に一覧が空になった場合も、取得済みの件数を保持

    Raises:
        RequestValidationError: 下限が上限より新しい場合。published_toの422として応答
    """

    if (
        published_from is not None
        and published_to is not None
        and published_from > published_to
    ):
        raise RequestValidationError([{
            "type": "value_error",
            "loc": ("query", "published_to"),
            "msg": "公開日の上限は下限以降で指定してください",
            "input": published_to.isoformat(),
        }])

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
        published_from=published_from,
        published_to=published_to,
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
            published_from=published_from,
            published_to=published_to,
        )

    categories_by_release = (
        list_press_release_fixed_categories(
            session, [press_release.id for press_release in press_releases]
        )
        if press_releases
        else {}
    )

    return PressReleaseListResponse(
        items=[
            PressReleaseListItem(
                title=press_release.title,
                source_url=press_release.source_url,
                published_at=press_release.published_at,
                source_categories=press_release.source_categories,
                fixed_categories=[
                    FixedCategoryMembershipItem.model_validate(category)
                    for category in categories_by_release.get(
                        press_release.id, ()
                    )
                ],
            )
            for press_release in press_releases
        ],
        pagination=PressReleasePagination(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )
